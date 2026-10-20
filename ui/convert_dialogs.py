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
from core.convert.optimize import OptimizePreset


def _kb(n: int) -> str:
    from ui.app_dialogs import _fmt_bytes

    return _fmt_bytes(n)


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


class OptimizeDialog(QDialog):
    def __init__(self, parent=None, estimate=None) -> None:
        """``estimate(preset) -> (current_bytes, estimated_bytes)`` updates the size line for
        the chosen preset (results are kept, so switching back is instant)."""
        super().__init__(parent)
        self._estimate = estimate
        self._estimates: dict = {}
        self.setWindowTitle("Reduce File Size")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Reduce file size"))
        layout = QFormLayout()
        layout.setVerticalSpacing(8)
        self.preset = QComboBox()
        self.preset.addItem("Lossless — structural cleanup only", OptimizePreset.LOSSLESS)
        self.preset.addItem("High Quality — preserve images", OptimizePreset.HIGH_QUALITY)
        self.preset.addItem("Standard — recommended", OptimizePreset.STANDARD)
        self.preset.addItem("Balanced — may reduce image quality", OptimizePreset.BALANCED)
        self.preset.addItem("Minimum file size — lossy", OptimizePreset.MINIMUM)
        layout.addRow("Preset:", self.preset)
        root.addLayout(layout)
        tip = _hint(
            "Lossless never downsamples images. Balanced and Minimum recompress images and are lossy."
        )
        tip.setObjectName("ContextHint")
        root.addWidget(tip)
        self.remove_meta = QCheckBox("Remove document metadata (title, author, …)")
        root.addWidget(self.remove_meta)
        self.downsample = QCheckBox("Allow image downsampling / recompression")
        root.addWidget(self.downsample)
        self.size_label = QLabel("Size estimate: run Optimize to measure.")
        self.size_label.setObjectName("DialogHint")
        self.size_label.setWordWrap(True)
        root.addWidget(self.size_label)
        root.addWidget(_ok_cancel(self, "Optimize…"))
        self.preset.currentIndexChanged.connect(self._sync_downsample)
        self.preset.currentIndexChanged.connect(self._update_estimate)
        self.preset.setCurrentIndex(2)  # Standard → triggers sync

    def _update_estimate(self) -> None:
        if self._estimate is None:
            return
        preset = self.preset.currentData()
        key = getattr(preset, "value", preset)
        if key not in self._estimates:
            try:
                self._estimates[key] = self._estimate(preset)
            except Exception:  # noqa: BLE001 - the estimate is only a hint
                self._estimates[key] = None
        sizes = self._estimates[key]
        if sizes is None:
            self.size_label.setText("Size estimate: not available for this file.")
            return
        src_b, est_b = sizes
        self.size_label.setText(
            f"Current size: {_kb(src_b)} · with this preset: about {_kb(est_b)} "
            "(estimate with the default options)"
        )

    def _sync_downsample(self) -> None:
        preset = self.preset.currentData()
        if preset == OptimizePreset.LOSSLESS:
            self.downsample.setChecked(False)
            self.downsample.setEnabled(False)
        elif preset == OptimizePreset.HIGH_QUALITY:
            self.downsample.setEnabled(True)
            self.downsample.setChecked(False)
        else:
            self.downsample.setEnabled(True)
            self.downsample.setChecked(True)

    def values(self):
        return {
            "preset": self.preset.currentData(),
            "remove_metadata": self.remove_meta.isChecked(),
            "downsample_images": self.downsample.isChecked(),
        }


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


class PdfToPowerPointDialog(QDialog):
    """Choose how a PDF becomes slides: whole pages as pictures, or pictures plus editable text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QRadioButton

        from core.convert.pdf_to_pptx import EDITABLE_NOTICE, LAYOUT_NOTICE

        self.setWindowTitle("PDF to PowerPoint")
        self.setMinimumWidth(500)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Convert PDF to PowerPoint (.pptx)"))
        size_note = QLabel(
            "Slides use the PDF's page size (an A4 PDF gives A4 slides). If the pages differ in size, the "
            "slide is the widest × tallest page and each page is centered at its true size."
        )
        size_note.setWordWrap(True)
        root.addWidget(size_note)
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def mode(self) -> str:
        return "editable" if self._editable.isChecked() else "layout"


class PdfToWordDialog(QDialog):
    """Choose the PDF → Word engine and page scope."""

    def __init__(self, parent=None, *, page_count: int = 0, current_page: int = 0) -> None:
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
        self.open_after = QCheckBox("Open the Word document when finished")
        self.open_after.setChecked(True)
        root.addWidget(self.open_after)
        root.addWidget(_ok_cancel(self, "Convert…"))
        self.engine.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        notes = {
            "layout": "Rebuilds every page as editable Word content and keeps the original look: "
            "fonts, sizes, colors, paragraphs, tables, images and page size. Runs offline.",
            "word": "Uses the Microsoft Word installed on this computer (PDF Reflow). Text flows "
            "naturally for heavy re-editing; complex layouts may shift.",
            "text": "Extracts the text as simple paragraphs. Use for copy-and-paste only.",
        }
        self.notes.setText(notes.get(str(self.engine.currentData()), ""))

    def values(self) -> dict:
        return {
            "engine": str(self.engine.currentData()),
            "pages": self.scope.pages(),
            "open_after": self.open_after.isChecked(),
        }
