"""Merge / Split / page-op dialogs with background workers (UI stays responsive)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.organize.merge import MergeJob, combine_to_pdf
from core.organize.split import SplitMode, plan_split, run_split


class OrganizeWorker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancel = False
        self._fn = None

    def cancel(self) -> None:
        self._cancel = True

    def set_task(self, fn) -> None:
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn(
                progress=lambda c, t, m: self.progress.emit(c, t, m),
                cancel=lambda: self._cancel,
            )
            if self._cancel:
                self.cancelled.emit()
            else:
                self.finished_ok.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ProgressDialog(QDialog):
    def __init__(self, title: str = "Working…", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 140)
        layout = QVBoxLayout(self)
        self._label = QLabel(title)
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)
        row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        row.addStretch(1)
        row.addWidget(self._cancel_btn)
        layout.addLayout(row)
        self._worker: OrganizeWorker | None = None
        self.work_result = None

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._label.setText("Cancelling…")

    def start(self, worker: OrganizeWorker) -> None:
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_fail)
        worker.cancelled.connect(self._on_cancelled)
        worker.start()

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        self._label.setText(msg)
        self._bar.setValue(int(100 * cur / max(total, 1)))

    def _on_ok(self, result) -> None:
        self.work_result = result
        self.accept()

    def _on_fail(self, message: str) -> None:
        QMessageBox.warning(self, "Operation failed", message)
        self.reject()

    def _on_cancelled(self) -> None:
        self.work_result = None
        self.reject()


class MergeDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge PDFs")
        self.resize(640, 480)
        self.job = MergeJob()
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Add local PDFs, reorder, include/exclude pages, then combine into a new file.\n"
                "Source files are never modified."
            )
        )
        self._list = QListWidget()
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        btn_add = QPushButton("Add PDFs…")
        btn_add.clicked.connect(self._add)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._remove)
        btn_pages = QPushButton("Set page range…")
        btn_pages.clicked.connect(self._set_pages)
        row.addWidget(btn_add)
        row.addWidget(btn_remove)
        row.addWidget(btn_pages)
        row.addStretch(1)
        layout.addLayout(row)

        self._warn = QLabel("")
        self._warn.setWordWrap(True)
        self._warn.setObjectName("DialogWarning")
        layout.addWidget(self._warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Combine…")
        buttons.accepted.connect(self._combine)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.output_path: Path | None = None

    def _sync_order_from_list(self) -> None:
        order = []
        for i in range(self._list.count()):
            order.append(int(self._list.item(i).data(Qt.ItemDataRole.UserRole)))
        if order and sorted(order) == list(range(len(self.job.sources))):
            self.job.reorder_sources(order)
            self._rebuild_list()

    def _rebuild_list(self) -> None:
        self._list.clear()
        for i, src in enumerate(self.job.sources):
            pages = src.effective_pages()
            err = f" — ERROR: {src.open_error}" if src.open_error else ""
            enc = " [encrypted]" if src.encrypted else ""
            sig = " [signatures]" if src.has_signatures else ""
            text = f"{src.display_name} — {len(pages)}/{src.page_count} pages{enc}{sig}{err}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)
        warn = self.job.signature_warning()
        self._warn.setText(warn or "")

    def _add(self) -> None:
        last = self.job.sources[-1].path if self.job.sources else None
        start = str(Path(last).parent) if last else getattr(self.parent(), "_doc_dir", lambda: "")()
        paths, _ = QFileDialog.getOpenFileNames(self, "Add PDFs", start, "PDF Files (*.pdf)")
        for p in paths:
            src = self.job.add_path(Path(p))
            if src.open_error and "Password" in (src.open_error or ""):
                from ui.password_dialog import PasswordDialog

                dlg = PasswordDialog(self, filename=Path(p).name)
                if dlg.exec() == dlg.DialogCode.Accepted:
                    self.job.sources.pop()
                    self.job.add_path(Path(p), password=dlg.password())
        self._rebuild_list()

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self.job.remove_at(row)
        self._rebuild_list()

    def _set_pages(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        src = self.job.sources[row]
        from PySide6.QtWidgets import QInputDialog

        current = ",".join(str(p + 1) for p in src.effective_pages())
        text, ok = QInputDialog.getText(
            self,
            "Include pages",
            f"Pages for {src.display_name} (e.g. 1-3, 5):",
            text=current,
        )
        if not ok:
            return
        try:
            self.job.set_included_from_range_spec(row, text)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Invalid range", str(exc))
            return
        self._rebuild_list()

    def _combine(self) -> None:
        self._sync_order_from_list()
        if self.job.total_output_pages() <= 0:
            QMessageBox.warning(self, "Combine", "No pages selected.")
            return
        warn = self.job.signature_warning()
        if warn:
            resp = QMessageBox.warning(
                self,
                "Signature warning",
                warn + "\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        prot = self.job.protection_warning()
        if prot:
            resp = QMessageBox.warning(
                self,
                "Protected files",
                prot + "\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        from ui.convert_dialogs import choose_save

        first = next((src.path for src in self.job.sources if src.path), None)
        default = str(Path(first).with_name("combined.pdf")) if first else "combined.pdf"
        dest = choose_save(self, "Save combined PDF", default, "PDF (*.pdf)")
        dest = str(dest) if dest else ""
        if not dest:
            return
        dest_path = Path(dest)
        worker = OrganizeWorker(self)

        def task(*, progress, cancel):
            return combine_to_pdf(self.job, dest_path, progress=progress, cancel=cancel)

        worker.set_task(task)
        dlg = ProgressDialog("Combining…", self)
        dlg.start(worker)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.work_result:
            self.output_path = Path(dlg.work_result)
            self.accept()


class SplitDialog(QDialog):
    def __init__(self, document, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Split PDF")
        self.resize(480, 320)
        self.output_paths: list[Path] = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Split into new PDF files. The source file is not modified."))

        form = QFormLayout()
        self._mode = QComboBox()
        self._mode.addItem("Page ranges (one file per range)", SplitMode.RANGES)
        self._mode.addItem("Selected pages (one file)", SplitMode.SELECTED)
        self._mode.addItem("Every page", SplitMode.EVERY_PAGE)
        self._mode.addItem("Every N pages", SplitMode.EVERY_N)
        self._mode.addItem("By bookmarks (when available)", SplitMode.BOOKMARKS)
        form.addRow("Split by:", self._mode)

        self._ranges = QLineEdit("1-1")
        self._ranges.setPlaceholderText("e.g. 1-3, 5, 8-10")
        form.addRow("Pages:", self._ranges)
        self._every_n = QSpinBox()
        self._every_n.setRange(1, 9999)
        self._every_n.setValue(2)
        form.addRow("Pages per file:", self._every_n)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Split…")
        buttons.accepted.connect(self._run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _run(self) -> None:
        mode = self._mode.currentData()
        try:
            if mode == SplitMode.RANGES:
                plan = plan_split(self.document, mode, range_spec=self._ranges.text())
            elif mode == SplitMode.SELECTED:
                from core.organize.page_ops import parse_page_ranges

                pages = parse_page_ranges(self._ranges.text(), self.document.page_count)
                plan = plan_split(self.document, mode, selected_pages=pages)
            elif mode == SplitMode.EVERY_N:
                plan = plan_split(self.document, mode, every_n=self._every_n.value())
            else:
                plan = plan_split(self.document, mode)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Split", str(exc))
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Output folder")
        if not out_dir:
            return
        worker = OrganizeWorker(self)

        def task(*, progress, cancel):
            return run_split(
                self.document,
                plan,
                Path(out_dir),
                name_prefix=self.document.path.stem,
                progress=progress,
                cancel=cancel,
            )

        worker.set_task(task)
        dlg = ProgressDialog("Splitting…", self)
        dlg.start(worker)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.work_result:
            self.output_paths = list(dlg.work_result)
            self.accept()


class CropDialog(QDialog):
    """Trim the current page: how much to cut from each edge, in millimetres."""

    _MM = 72 / 25.4  # points per millimetre

    def __init__(self, page_width: float, page_height: float, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QVBoxLayout

        self.setWindowTitle("Crop Page")
        self._w, self._h = float(page_width), float(page_height)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        intro = QLabel("Trim the margins of the current page. Nothing is deleted — the hidden area can be restored by cropping again with 0 mm.")
        intro.setWordWrap(True)
        intro.setObjectName("DialogHint")
        root.addWidget(intro)
        layout = QFormLayout()
        self.left, self.top, self.right, self.bottom = (QDoubleSpinBox() for _ in range(4))
        for sp, limit in ((self.left, self._w), (self.right, self._w), (self.top, self._h), (self.bottom, self._h)):
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.setSuffix(" mm")
            sp.setRange(0.0, max(0.0, limit / self._MM - 5))
            sp.valueChanged.connect(self._update)
        layout.addRow("Left:", self.left)
        layout.addRow("Top:", self.top)
        layout.addRow("Right:", self.right)
        layout.addRow("Bottom:", self.bottom)
        root.addLayout(layout)
        self._result = QLabel("")
        self._result.setObjectName("DialogHint")
        root.addWidget(self._result)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("Crop")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._update()

    def _update(self, *_args) -> None:
        w = self._w / self._MM - self.left.value() - self.right.value()
        h = self._h / self._MM - self.top.value() - self.bottom.value()
        ok = w >= 5 and h >= 5
        self._result.setText(
            f"Page after cropping: {max(w, 0):.0f} × {max(h, 0):.0f} mm" if ok else "Too much trimmed — the page would be empty."
        )
        self._ok.setEnabled(ok)

    def crop_tuple(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) in points from the page's top-left corner."""
        m = self._MM
        return (
            self.left.value() * m,
            self.top.value() * m,
            self._w - self.right.value() * m,
            self._h - self.bottom.value() * m,
        )


class ChangePageSizeDialog(QDialog):
    """Convert pages to another paper size (A4, Letter, Legal, B5 …) and fit the content."""

    def __init__(
        self,
        page_count: int,
        current_page: int,
        selected: list[int],
        current_sizes: list[tuple[float, float]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QWidget

        from core.organize.resize import PAPER_SIZES, size_label
        from core.page_geometry import label_page_size

        self._count = page_count
        self._current = current_page
        self._selected = list(selected)
        self.setWindowTitle("Change Page Size")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        heading = QLabel("Change page size")
        heading.setObjectName("DialogTitle")
        root.addWidget(heading)

        # What the document uses now
        labels: dict[str, int] = {}
        for w, h in current_sizes:
            lab = label_page_size(w, h)
            key = lab.display if lab.matched else f"Custom — {size_label(w, h)}"
            labels[key] = labels.get(key, 0) + 1
        now = "; ".join(f"{k} ({n} page{'s' if n != 1 else ''})" for k, n in labels.items()) or "—"
        current = QLabel(f"Current: {now}")
        current.setObjectName("DialogHint")
        current.setWordWrap(True)
        root.addWidget(current)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.paper = QComboBox()
        for name, (w, h) in PAPER_SIZES.items():
            self.paper.addItem(f"{name}  —  {size_label(w, h)}", name)
        self.paper.addItem("Custom size…", "custom")
        self.paper.setCurrentIndex(max(0, self.paper.findData("A4")))
        form.addRow("Paper size:", self.paper)

        self.custom_w = QDoubleSpinBox()
        self.custom_h = QDoubleSpinBox()
        for sp, val in ((self.custom_w, 210.0), (self.custom_h, 297.0)):
            sp.setRange(20, 2000)
            sp.setDecimals(1)
            sp.setSuffix(" mm")
            sp.setValue(val)
        custom_row = QHBoxLayout()
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.addWidget(self.custom_w)
        custom_row.addWidget(QLabel("×"))
        custom_row.addWidget(self.custom_h)
        self._custom_box = QWidget()
        self._custom_box.setLayout(custom_row)
        form.addRow("Custom:", self._custom_box)
        self._size_form = form

        self.orientation = QComboBox()
        self.orientation.addItem("Same as each page", "auto")
        self.orientation.addItem("Portrait", "portrait")
        self.orientation.addItem("Landscape", "landscape")
        form.addRow("Orientation:", self.orientation)

        self.fit = QComboBox()
        self.fit.addItem("Fit to page — keep proportions (recommended)", "fit")
        self.fit.addItem("Fill page — keep proportions, edges may be cut", "fill")
        self.fit.addItem("Stretch to page — may distort", "stretch")
        self.fit.addItem("Keep original size — centered", "actual")
        form.addRow("Content:", self.fit)

        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, 50)
        self.margin.setDecimals(1)
        self.margin.setSuffix(" mm")
        self.margin.setToolTip("White space kept around the content (Fit and Stretch)")
        form.addRow("Margin:", self.margin)

        self.scope = QComboBox()
        self.scope.addItem(f"All pages ({page_count})", "all")
        self.scope.addItem(f"Current page ({current_page + 1})", "current")
        if len(self._selected) > 1:
            self.scope.addItem(f"Selected pages ({len(self._selected)})", "selected")
        self.scope.addItem("Page range…", "range")
        self.range = QLineEdit()
        self.range.setPlaceholderText("e.g. 1-3, 5")
        self.range.setEnabled(False)
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.addWidget(self.scope)
        scope_row.addWidget(self.range, 1)
        scope_box = QWidget()
        scope_box.setLayout(scope_row)
        form.addRow("Pages:", scope_box)
        root.addLayout(form)

        hint = QLabel(
            "Text stays selectable and form fields, links and comments move with the content. "
            "The result is saved as a new PDF; the open document is not changed."
        )
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._error.hide()
        root.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Change Size && Save As…")
        buttons.accepted.connect(self._validate_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.paper.currentIndexChanged.connect(self._sync)
        self.fit.currentIndexChanged.connect(self._sync)
        self.scope.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self._size_form.setRowVisible(self._custom_box, self.paper.currentData() == "custom")
        self.adjustSize()
        self.margin.setEnabled(self.fit.currentData() in ("fit", "stretch"))
        self.range.setEnabled(self.scope.currentData() == "range")

    def paper_size(self) -> tuple[float, float]:
        from core.organize.resize import PAPER_SIZES

        key = self.paper.currentData()
        if key == "custom":
            mm = 72.0 / 25.4
            return self.custom_w.value() * mm, self.custom_h.value() * mm
        return PAPER_SIZES[key]

    def paper_name(self) -> str:
        key = self.paper.currentData()
        return "custom" if key == "custom" else str(key).split()[0]

    def pages(self) -> list[int] | None:
        mode = self.scope.currentData()
        if mode == "current":
            return [self._current]
        if mode == "selected":
            return sorted(self._selected)
        if mode == "range":
            from core.organize.page_ops import parse_page_ranges

            return parse_page_ranges(self.range.text().strip(), self._count)
        return None

    def _validate_accept(self) -> None:
        try:
            pages = self.pages()
            if pages is not None and not pages:
                raise ValueError("Enter at least one page.")
        except Exception as exc:  # noqa: BLE001
            self._error.setText(f"Page range: {exc}")
            self._error.show()
            return
        self.accept()


class RotatePagesDialog(QDialog):
    """Rotate all, current, selected, odd, even, or a page range."""

    def __init__(self, page_count: int, current_page: int, selected: list[int], parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QComboBox, QFormLayout, QLabel, QLineEdit, QRadioButton

        self._count = page_count
        self._current = current_page
        self._selected = list(selected)
        self.setWindowTitle("Rotate Pages")
        self.setMinimumWidth(400)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        title = QLabel("Rotate pages")
        title.setObjectName("DialogTitle")
        root.addWidget(title)
        form = QFormLayout()
        self.direction = QComboBox()
        self.direction.addItem("90° clockwise", 90)
        self.direction.addItem("90° counterclockwise", -90)
        self.direction.addItem("180°", 180)
        form.addRow("Direction:", self.direction)
        root.addLayout(form)
        self._group = QButtonGroup(self)
        self.opt_all = QRadioButton(f"All pages ({page_count})")
        self.opt_current = QRadioButton(f"Current page ({current_page + 1})")
        self.opt_selected = QRadioButton(f"Selected thumbnails ({len(selected)})")
        self.opt_selected.setEnabled(len(selected) > 1)
        self.opt_odd = QRadioButton("Odd pages (1, 3, 5 …)")
        self.opt_even = QRadioButton("Even pages (2, 4, 6 …)")
        self.opt_even.setEnabled(page_count > 1)
        self.opt_range = QRadioButton("Pages:")
        self.range = QLineEdit()
        self.range.setPlaceholderText("e.g. 1-3, 5")
        self.range.setEnabled(False)
        self.opt_range.toggled.connect(self.range.setEnabled)
        for i, rb in enumerate((self.opt_all, self.opt_current, self.opt_selected, self.opt_odd, self.opt_even, self.opt_range)):
            self._group.addButton(rb, i)
        for rb in (self.opt_all, self.opt_current, self.opt_selected, self.opt_odd, self.opt_even):
            root.addWidget(rb)
        row = QHBoxLayout()
        row.addWidget(self.opt_range)
        row.addWidget(self.range, 1)
        root.addLayout(row)
        (self.opt_selected if len(selected) > 1 else self.opt_all).setChecked(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Rotate")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def degrees(self) -> int:
        return int(self.direction.currentData())

    def pages(self) -> list[int]:
        n = self._count
        mode = self._group.checkedId()
        if mode == 1:
            return [self._current]
        if mode == 2:
            return list(self._selected)
        if mode == 3:
            return list(range(0, n, 2))
        if mode == 4:
            return list(range(1, n, 2))
        if mode == 5:
            from core.organize.page_ops import parse_page_ranges

            return parse_page_ranges(self.range.text().strip(), n)
        return list(range(n))
