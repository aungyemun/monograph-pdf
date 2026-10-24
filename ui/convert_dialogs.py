"""Convert / Export / Optimize dialogs (offline)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.convert.capabilities import Fidelity, list_capabilities


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogHint")
    lab.setWordWrap(True)
    return lab


def _ok_cancel(dialog: QDialog, ok_text: str = "OK") -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


class CapabilitiesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

        self.setWindowTitle("Conversion Quality Guide")
        self.setMinimumSize(760, 420)
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_title("What each conversion can and cannot do"))
        layout.addWidget(_hint("Everything runs on this computer. “Best effort” results are close to the PDF, "
                               "but not exact copies."))
        caps = list_capabilities()
        table = QTableWidget(len(caps), 3)
        table.setHorizontalHeaderLabels(["Conversion", "Quality", "What to expect"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setWordWrap(True)
        table.setAlternatingRowColors(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        colors = {
            Fidelity.HIGH: QColor("#15803d"),
            Fidelity.BEST_EFFORT: QColor("#b45309"),
            Fidelity.UNSUPPORTED: QColor("#b91c1c"),
        }
        labels = {Fidelity.HIGH: "High", Fidelity.BEST_EFFORT: "Best effort", Fidelity.UNSUPPORTED: "Not available"}
        for row, c in enumerate(caps):
            status = labels[c.fidelity] if c.implemented or c.fidelity == Fidelity.UNSUPPORTED else labels[c.fidelity] + " · not available"
            cells = (QTableWidgetItem(c.title), QTableWidgetItem(status), QTableWidgetItem(c.notes))
            cells[1].setForeground(colors[c.fidelity])
            for col, cell in enumerate(cells):
                table.setItem(row, col, cell)
        header.sectionResized.connect(lambda *_: table.resizeRowsToContents())
        layout.addWidget(table, 1)
        self._table = table
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._table.resizeRowsToContents()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._table.resizeRowsToContents()


class _PageScope(QWidget):
    """All pages / current page / custom range (1-based, e.g. 1-3,5)."""

    def __init__(self, page_count: int = 0, current: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._count = page_count
        self._current = current
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem("All pages", "all")
        self.combo.addItem("Current page", "current")
        self.combo.addItem("Page range…", "range")
        self.range = QLineEdit()
        self.range.setPlaceholderText("e.g. 1-3, 5")
        self.range.setEnabled(False)
        self.combo.currentIndexChanged.connect(lambda: self.range.setEnabled(self.combo.currentData() == "range"))
        row.addWidget(self.combo)
        row.addWidget(self.range, 1)

    def pages(self) -> list[int] | None:
        mode = self.combo.currentData()
        if mode == "current":
            return [self._current]
        if mode == "range" and self.range.text().strip() and self._count:
            from core.organize.page_ops import parse_page_ranges

            return parse_page_ranges(self.range.text().strip(), self._count)
        return None


# Watermark and header/footer dialogs live in ui/page_marks_dialogs.py (live preview, presets,
# picture watermarks, backgrounds); the names stay importable from here.
from ui.page_marks_dialogs import HeaderFooterDialog, WatermarkDialog  # noqa: E402,F401


def _open_document_path(widget) -> Path | None:
    """Path of the PDF open in the main window that owns ``widget`` (None when nothing is open)."""
    w = widget
    while w is not None:
        doc = getattr(w, "_document", None)
        if doc is not None and getattr(doc, "path", None):
            return Path(doc.path)
        w = w.parent() if hasattr(w, "parent") else None
    return None


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))
    except OSError:
        return False


def choose_save(parent, title: str, default_name: str, filter_: str) -> Path | None:
    """Save dialog; appends the filter's extension when the user omits it.

    The PDF that is open in Monograph PDF cannot be the target (Windows keeps it locked, and an
    export must not silently replace the document being edited): the user is asked for
    another name instead.
    """
    import re

    for _attempt in range(3):
        path, chosen = QFileDialog.getSaveFileName(parent, title, default_name, filter_)
        if not path:
            return None
        out = Path(path)
        if not out.suffix:
            m = re.search(r"\*\.(\w+)", chosen or filter_)
            if m:
                out = out.with_suffix("." + m.group(1))
        current = _open_document_path(parent)
        if current is None or not _same_file(out, current):
            return out
        QMessageBox.warning(
            parent,
            title,
            f"“{out.name}” is open in Monograph PDF, so it cannot be replaced here.\n\n"
            "Choose another file name (or save the open document with File ▸ Save).",
        )
        default_name = str(out.with_name(f"{out.stem}-1{out.suffix}"))
    return None


def choose_dir(parent, title: str) -> Path | None:
    path = QFileDialog.getExistingDirectory(parent, title)
    return Path(path) if path else None


def fidelity_confirm(parent, title: str, notice: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText("The result may not match the PDF exactly.")
    detail = notice.removeprefix("Best-effort:").strip()
    box.setInformativeText(detail[:1].upper() + detail[1:])
    box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Ok).setText("Continue…")
    box.setDefaultButton(QMessageBox.StandardButton.Ok)
    return box.exec() == QMessageBox.StandardButton.Ok


class ExportProtectionNotes(QWidget):
    """What happens to digital signatures and watermarks in an export (core/security/protection.py),
    with the choice to leave out marks added with Monograph PDF that are still removable."""

    def __init__(self, info, *, target: str) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.include_marks: QCheckBox | None = None
        lines = []
        if getattr(info, "signatures", 0):
            lines.append(f"The PDF is digitally signed. The {target} shows how the signature looks but is "
                         "not digitally signed.")
        if getattr(info, "other_watermarks", False):
            lines.append("A watermark made by another program is part of the pages and is kept.")
        for text in lines:
            lab = _hint(text)
            lay.addWidget(lab)
        if getattr(info, "marks", None):
            self.include_marks = QCheckBox("Include the watermark, header/footer and background added with "
                                           "Monograph PDF")
            self.include_marks.setChecked(True)
            self.include_marks.setToolTip("Clear to convert the pages without them. A watermark locked with "
                                          "Protect with Password is part of the pages and always stays.")
            lay.addWidget(self.include_marks)
        self.setVisible(bool(lines) or self.include_marks is not None)

    def leave_out_marks(self) -> set[str]:
        if self.include_marks is None or self.include_marks.isChecked():
            return set()
        from core.convert.page_marks import ALL_KINDS

        return set(ALL_KINDS)


class PdfToPowerPointDialog(QDialog):
    """Choose how a PDF becomes slides: whole pages as pictures, or pictures plus editable text; the slide
    size policy for documents whose pages differ in size; and the picture quality."""

    SIZE_POLICY_LABELS = (
        ("true_size", "Largest page size — every page at its true size, centered"),
        ("fit", "Largest page size — every page enlarged or reduced to fill the slide"),
        ("first_page", "First page's size — other pages fitted into it"),
        ("custom", "Chosen slide size — every page fitted into it"),
        ("split", "Separate presentation for each page size"),
    )

    def __init__(self, parent=None, *, page_groups: list[tuple[str, list[int]]] | None = None,
                 protection=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QRadioButton

        from core.convert.pdf_to_pptx import (
            EDITABLE_NOTICE,
            LAYOUT_NOTICE,
            SLIDE_PRESETS_PT,
        )

        self.setWindowTitle("PDF to PowerPoint")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Convert PDF to PowerPoint (.pptx)"))
        groups = page_groups or []
        mixed = len(groups) > 1
        if mixed:
            text = "This PDF has pages of different sizes: " + "; ".join(
                f"{label} ({len(members)} page{'s' if len(members) != 1 else ''})" for label, members in groups[:6]
            ) + ". A PowerPoint file has one slide size, so choose how to handle them."
        else:
            text = "Slides use the PDF's page size (an A4 PDF gives A4 slides)."
        size_note = QLabel(text)
        size_note.setWordWrap(True)
        root.addWidget(size_note)
        form = QFormLayout()
        self.size_policy = QComboBox()
        for key, label in self.SIZE_POLICY_LABELS:
            if key == "split" and not mixed:
                continue
            if key in ("fit", "first_page") and not mixed:
                continue
            self.size_policy.addItem(label if mixed or key != "true_size" else "PDF page size", key)
        form.addRow("Slide size:", self.size_policy)
        self.custom_size = QComboBox()
        for name, size in SLIDE_PRESETS_PT.items():
            self.custom_size.addItem(name, size)
        form.addRow("Chosen size:", self.custom_size)
        self.quality = QComboBox()
        for dpi, label in ((150, "Standard (150 dpi) — smaller file"), (200, "High (200 dpi, recommended)"),
                           (300, "Print (300 dpi) — larger file")):
            self.quality.addItem(label, dpi)
        self.quality.setCurrentIndex(1)
        form.addRow("Picture quality:", self.quality)
        root.addLayout(form)
        self._layout = QRadioButton("Layout-preserving (recommended)")
        self._layout.setChecked(True)
        self._editable = QRadioButton("Editable text")
        for radio, note in ((self._layout, LAYOUT_NOTICE), (self._editable, EDITABLE_NOTICE)):
            root.addWidget(radio)
            detail = note.split(": ", 1)[1]
            lab = QLabel(detail[:1].upper() + detail[1:])
            lab.setWordWrap(True)
            lab.setContentsMargins(24, 0, 0, 0)
            root.addWidget(lab)
        self.protection_notes = ExportProtectionNotes(protection, target="presentation")
        root.addWidget(self.protection_notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.size_policy.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self.custom_size.setEnabled(self.policy() == "custom")

    def mode(self) -> str:
        return "editable" if self._editable.isChecked() else "layout"

    def policy(self) -> str:
        return str(self.size_policy.currentData())

    def options(self) -> dict:
        """Keyword arguments for pdf_to_pptx / pdf_to_pptx_split."""
        opts = {"mode": self.mode(), "dpi": int(self.quality.currentData())}
        policy = self.policy()
        if policy != "split":
            opts["size_policy"] = policy
        if policy == "custom":
            opts["custom_size_pt"] = tuple(self.custom_size.currentData())
        return opts


class PdfToWordDialog(QDialog):
    """Choose the PDF → Word engine and page scope."""

    def __init__(self, parent=None, *, page_count: int = 0, current_page: int = 0, protection=None) -> None:
        super().__init__(parent)
        from core.convert.pdf_to_docx import layout_engine_available, word_engine_available

        self.setWindowTitle("PDF to Word")
        self.setMinimumWidth(500)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Convert PDF to Word (.docx)"))
        layout = QFormLayout()
        layout.setVerticalSpacing(8)
        self.engine = QComboBox()
        if layout_engine_available():
            self.engine.addItem("Keep layout — fonts, tables, images, columns (recommended)", "layout")
        if word_engine_available():
            self.engine.addItem("Microsoft Word reflow — best for long flowing text", "word")
        self.engine.addItem("Text only — plain paragraphs", "text")
        layout.addRow("Conversion:", self.engine)
        self.scope = _PageScope(page_count, current_page)
        layout.addRow("Pages:", self.scope)
        root.addLayout(layout)
        self.notes = _hint("")
        root.addWidget(self.notes)
        self.protection_notes = ExportProtectionNotes(protection, target="Word document")
        root.addWidget(self.protection_notes)
        self.open_after = QCheckBox("Open the Word document when finished")
        self.open_after.setChecked(True)
        root.addWidget(self.open_after)
        root.addWidget(_ok_cancel(self, "Convert…"))
        self.engine.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        notes = {
            "layout": "Rebuilds every page as editable Word content and keeps the original look: "
            "fonts, sizes, colors, paragraphs, tables, images, and each page's size and orientation (mixed sizes "
            "stay mixed). Exact positions can make heavy re-editing harder. Runs offline.",
            "word": "Uses the Microsoft Word installed on this computer (PDF Reflow). Text flows "
            "naturally for heavy re-editing; complex layouts may shift.",
            "text": "Editable text: plain paragraphs that reflow freely, one Word section per page with "
            "that page's size and orientation. Pictures and exact positions are not kept.",
        }
        self.notes.setText(notes.get(str(self.engine.currentData()), ""))

    def values(self) -> dict:
        return {
            "engine": str(self.engine.currentData()),
            "pages": self.scope.pages(),
            "open_after": self.open_after.isChecked(),
            "leave_out_marks": self.protection_notes.leave_out_marks(),
        }
