"""Batch Convert dialog: add files (or drop them), pick a format and a folder, convert, follow each
file's status. Runs on a worker thread; Cancel stops after the current step and keeps no partial
output (core/convert/batch.py)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.convert.batch import FORMAT_BY_KEY, FORMATS, IMAGE_EXTS, OFFICE_EXTS, PDF_EXTS, BatchItem, BatchOptions, BatchRunner

ALL_EXTS = PDF_EXTS | IMAGE_EXTS | OFFICE_EXTS
STATUS_TEXT = {"waiting": "Waiting", "running": "Converting…", "done": "Done", "failed": "Failed",
               "skipped": "Skipped", "cancelled": "Cancelled"}
MAX_FILES = 2000


class _Worker(QThread):
    updated = Signal(int, object)

    def __init__(self, runner: BatchRunner, parent=None) -> None:
        super().__init__(parent)
        self.runner = runner
        runner.on_update = lambda i, item: self.updated.emit(i, item)

    def run(self) -> None:
        self.runner.run()


class _Table(QTableWidget):
    filesDropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(0, 3, parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()


class BatchConvertDialog(QDialog):
    def __init__(self, parent=None, *, start_dir: str = "", ocr_languages: str = "eng+jpn") -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Convert")
        self.resize(820, 560)
        self.setMinimumSize(560, 420)
        self._start_dir = start_dir
        self._ocr_languages = ocr_languages
        self._items: list[BatchItem] = []
        self._worker: _Worker | None = None
        layout = QVBoxLayout(self)
        intro = QLabel("Add files or drop them here. Every file is converted on this computer; existing files are "
                       "never overwritten.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = _Table()
        self.table.setHorizontalHeaderLabels(["File", "Status", "Result"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Files to convert")
        self.table.filesDropped.connect(self.add_paths)
        layout.addWidget(self.table, 1)
        files = QHBoxLayout()
        self.add_btn = QPushButton("Add Files…")
        self.add_btn.clicked.connect(self._add_files)
        self.folder_btn = QPushButton("Add Folder…")
        self.folder_btn.clicked.connect(self._add_folder)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear)
        for b in (self.add_btn, self.folder_btn, self.remove_btn, self.clear_btn):
            files.addWidget(b)
        files.addStretch(1)
        layout.addLayout(files)

        form = QFormLayout()
        self.format = QComboBox()
        for f in FORMATS:
            self.format.addItem(f.label, f.key)
        self.format.currentIndexChanged.connect(self._sync)
        form.addRow("Convert to:", self.format)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("All pages — or e.g. 1-3, 5")
        form.addRow("Pages:", self.pages)
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 600)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        form.addRow("Picture resolution:", self.dpi)
        out_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText("Choose the folder for the converted files")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_output)
        out_row.addWidget(self.output, 1)
        out_row.addWidget(browse)
        form.addRow("Save in:", out_row)
        layout.addLayout(form)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("ContextHint")
        layout.addWidget(self.note)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.counts = QLabel("")
        layout.addWidget(self.counts)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.start_btn = QPushButton("Convert")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        for b in (self.start_btn, self.cancel_btn, self.close_btn):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self._sync()

    # --- files -----------------------------------------------------------------------------------

    def add_paths(self, paths: list[Path]) -> None:
        known = {it.source.resolve() for it in self._items}
        for p in paths:
            p = Path(p)
            found = sorted(q for q in p.iterdir() if q.is_file()) if p.is_dir() else [p]
            for f in found:
                if f.suffix.lower() not in ALL_EXTS or not f.is_file():
                    continue
                if f.resolve() in known or len(self._items) >= MAX_FILES:
                    continue
                known.add(f.resolve())
                self._items.append(BatchItem(source=f))
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(f.name))
                self.table.item(row, 0).setToolTip(str(f))
                self.table.setItem(row, 1, QTableWidgetItem(STATUS_TEXT["waiting"]))
                self.table.setItem(row, 2, QTableWidgetItem(""))
        if not self.output.text() and self._items:
            self.output.setText(str(self._items[0].source.parent / "Converted"))
        self._sync()

    def _add_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(ALL_EXTS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files", self._start_dir, f"Supported files ({exts})")
        self.add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder", self._start_dir)
        if folder:
            self.add_paths([Path(folder)])

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
            del self._items[r]
        self._sync()

    def _clear(self) -> None:
        self.table.setRowCount(0)
        self._items.clear()
        self._sync()

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save Converted Files In", self.output.text() or self._start_dir)
        if folder:
            self.output.setText(folder)

    # --- state -----------------------------------------------------------------------------------

    def _running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _sync(self) -> None:
        fmt = FORMAT_BY_KEY[self.format.currentData()]
        running = self._running()
        usable = [it for it in self._items if it.source.suffix.lower() in fmt.inputs]
        self.pages.setEnabled(fmt.uses_pages and not running)
        self.dpi.setEnabled(fmt.key in ("png", "jpeg") and not running)
        notes = []
        if self._items and len(usable) < len(self._items):
            notes.append(f"{len(self._items) - len(usable)} file(s) cannot be converted to this format and will be skipped.")
        if fmt.needs == "office":
            from core.convert.office_to_pdf import office_to_pdf_supported

            if not office_to_pdf_supported():
                notes.append("Office files need Microsoft Office or LibreOffice installed on this computer; neither was found.")
        if fmt.needs == "ocr":
            notes.append("Text recognition (OCR) on this computer — slow for long documents. Languages: "
                         + self._ocr_languages.replace("+", ", ") + ".")
        if fmt.key == "xlsx":
            notes.append("Only tables with ruled lines are found; other content is not exported.")
        self.note.setText(" ".join(notes))
        for w in (self.add_btn, self.folder_btn, self.remove_btn, self.clear_btn, self.format):
            w.setEnabled(not running)
        self.start_btn.setEnabled(bool(usable) and not running)
        self.cancel_btn.setEnabled(running)
        self.close_btn.setEnabled(not running)
        self._update_counts()

    def _update_counts(self) -> None:
        c = {k: 0 for k in STATUS_TEXT}
        for it in self._items:
            c[it.status] = c.get(it.status, 0) + 1
        finished = c["done"] + c["failed"] + c["skipped"] + c["cancelled"]
        self.progress.setRange(0, max(1, len(self._items)))
        self.progress.setValue(finished)
        if self._items:
            self.counts.setText(f"{len(self._items)} file(s): {c['done']} done, {c['failed']} failed, "
                                f"{c['skipped']} skipped" + (f", {c['cancelled']} cancelled" if c["cancelled"] else "")
                                + (f", {c['waiting'] + c['running']} to go" if c["waiting"] + c["running"] else ""))
        else:
            self.counts.setText("")

    # --- run -------------------------------------------------------------------------------------

    def start(self) -> None:
        from core.convert.batch import parse_page_range

        out = self.output.text().strip()
        if not out:
            QMessageBox.warning(self, "Batch Convert", "Choose the folder for the converted files.")
            return
        if self.pages.isEnabled() and self.pages.text().strip():
            try:
                parse_page_range(self.pages.text(), 10**6)
            except ValueError as exc:
                QMessageBox.warning(self, "Batch Convert", f"Pages: {exc}")
                return
        try:
            Path(out).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Batch Convert", f"The folder cannot be created: {exc.strerror or exc}")
            return
        for row, it in enumerate(self._items):
            it.status, it.message, it.outputs = "waiting", "", []
            self._show(row, it)
        options = BatchOptions(format_key=self.format.currentData(), output_dir=Path(out),
                               page_range=self.pages.text() if self.pages.isEnabled() else "",
                               dpi=self.dpi.value(), ocr_languages=self._ocr_languages)
        self._worker = _Worker(BatchRunner(self._items, options), self)
        self._worker.updated.connect(self._show)
        self._worker.finished.connect(self._finished)
        self._worker.start()
        self._sync()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.runner.cancel()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("Cancelling…")

    def _show(self, row: int, item: BatchItem) -> None:
        if row >= self.table.rowCount():
            return
        self.table.item(row, 1).setText(STATUS_TEXT.get(item.status, item.status))
        self.table.item(row, 2).setText(item.message)
        self.table.item(row, 2).setToolTip("\n".join(str(p) for p in item.outputs) or item.message)
        self._update_counts()

    def _finished(self) -> None:
        self.cancel_btn.setText("Cancel")
        self._sync()

    def wait_finished(self, ms: int = 120000) -> bool:
        return self._worker is None or self._worker.wait(ms)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._running():
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._running():
            return
        super().reject()
