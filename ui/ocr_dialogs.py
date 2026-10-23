"""OCR progress and Make PDF Editable analysis dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.ocr.analysis import EditableAnalysis


class AnalysisDialog(QDialog):
    def __init__(self, analysis: EditableAnalysis, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Make PDF Editable — Analysis")
        self.resize(560, 480)
        self.analysis = analysis
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Inspection complete. Nothing has been modified yet.\n"
            "Review the summary before running OCR or other conversion."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText("\n".join(analysis.summary_lines))
        layout.addWidget(self._text)
        buttons = QDialogButtonBox()
        self.btn_ocr = buttons.addButton(
            "OCR pages that need it…", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.btn_close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.btn_ocr.clicked.connect(self.accept)
        self.btn_close.clicked.connect(self.reject)
        if not analysis.pages_needing_ocr:
            self.btn_ocr.setEnabled(False)
            self.btn_ocr.setText("No OCR needed")
        layout.addWidget(buttons)


class OcrWorker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, document, options, destination, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.options = options
        self.destination = destination
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        from core.diagnostics import EventId, diagnostics
        from core.ocr.pipeline import OcrCancelled, run_ocr

        diagnostics.record(EventId.OCR_STARTED)
        try:
            result = run_ocr(
                self.document,
                self.options,
                progress=lambda c, t, m: self.progress.emit(c, t, m),
                cancel=lambda: self._cancel,
                destination=self.destination,
            )
            if self._cancel:
                self.cancelled.emit()
            else:
                self.finished_ok.emit(result)
        except OcrCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            import subprocess

            diagnostics.record(EventId.OCR_FAILED)
            if isinstance(exc, (subprocess.SubprocessError, OSError)):
                diagnostics.record(EventId.SUBPROCESS_FAILED)
            self.failed.emit(str(exc))


class OcrProgressDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR")
        self.setModal(True)
        self.resize(420, 140)
        layout = QVBoxLayout(self)
        self._label = QLabel("Starting OCR…")
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
        self._worker: OcrWorker | None = None
        self.ocr_result = None

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._label.setText("Cancelling…")

    def start(self, worker: OcrWorker) -> None:
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
        self.ocr_result = result
        self.accept()

    def _on_fail(self, message: str) -> None:
        QMessageBox.warning(self, "OCR failed", message)
        self.reject()

    def _on_cancelled(self) -> None:
        self.ocr_result = None
        self.reject()


# --- 0.3.0: recognised text, OCR scope and OCR languages -------------------------------------------

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QRadioButton,
)


def ocr_language_label(codes: str) -> str:
    from core.ocr.language_packs import available_languages

    names = available_languages()
    return " + ".join(names.get(c, c) for c in codes.split("+") if c)


class OcrTextDialog(QDialog):
    """Recognised text: correct it, copy it, or save it as a text file or Word document."""

    def __init__(self, result, *, title: str = "Recognized Text", languages: str = "", start_dir: str = "",
                 doc_title: str = "", metadata: dict | None = None, parent=None) -> None:
        from core.ocr.text_export import document_text, page_text

        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 520)
        self.ocr_result = result
        self._start_dir = start_dir
        self._doc_title = doc_title
        self._metadata = metadata
        pages = [p for p in result.pages if p.words]
        layout = QVBoxLayout(self)
        words = [w for p in pages for w in p.words]
        low = sum(1 for w in words if w.low_confidence)
        info = QLabel(
            (f"{len(words)} word(s) recognized" + (f" in {len(pages)} page(s)" if len(pages) > 1 else "")
             + (f" — {low} with low confidence: check them" if low else "")
             + (f".  Languages: {ocr_language_label(languages)}" if languages else ""))
            if words else "No text was recognized. Try a larger area, another language, or a sharper scan.")
        info.setWordWrap(True)
        layout.addWidget(info)
        hint = QLabel("You can correct the text here before copying or saving it. The PDF is not changed.")
        hint.setObjectName("ContextHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Recognized text")
        if len(pages) == 1:
            self.text.setPlainText(pages[0].full_text or page_text(pages[0].words))
        elif pages:
            self.text.setPlainText(document_text(pages))
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy)
        self.txt_btn = QPushButton("Save as Text…")
        self.txt_btn.clicked.connect(self.save_text)
        self.docx_btn = QPushButton("Save as Word…")
        self.docx_btn.clicked.connect(self.save_docx)
        for b in (self.copy_btn, self.txt_btn, self.docx_btn):
            b.setEnabled(bool(words))
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def copy(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_btn.setText("Copied")

    def _target(self, caption: str, suffix: str, filt: str) -> str:
        from pathlib import Path

        start = str(Path(self._start_dir or ".") / f"{self._doc_title or 'recognized-text'}{suffix}")
        path, _ = QFileDialog.getSaveFileName(self, caption, start, filt)
        if path and not path.lower().endswith(suffix):
            path += suffix
        return path

    def save_text(self, path: str | None = None) -> str:
        from pathlib import Path

        from core.ocr.text_export import write_text

        path = path or self._target("Save Recognized Text", ".txt", "Text (*.txt)")
        if not path:
            return ""
        try:
            write_text(self.text.toPlainText(), Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Save as Text", f"The file could not be written: {exc.strerror or exc}")
            return ""
        return path

    def save_docx(self, path: str | None = None) -> str:
        from pathlib import Path

        from core.ocr.text_export import write_docx

        path = path or self._target("Save as Word Document", ".docx", "Word document (*.docx)")
        if not path:
            return ""
        pages = [p for p in self.ocr_result.pages if p.words]
        try:
            write_docx(pages, Path(path), title=self._doc_title, edited_text=self.text.toPlainText(),
                       metadata=self._metadata)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save as Word", f"The document could not be written: {exc}")
            return ""
        return path


class OcrScopeDialog(QDialog):
    """Which pages to recognize, and in which languages."""

    def __init__(self, *, page_count: int, current_page: int, selected: list[int], languages: str,
                 title: str = "Recognize Text", parent=None) -> None:
        from PySide6.QtWidgets import QLineEdit

        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._page_count = page_count
        self._current = current_page
        self._selected = sorted(set(selected))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 12)
        intro = QLabel("Turns the pictures of scanned pages into text you can read, copy and search. "
                       "Nothing leaves this computer.")
        intro.setObjectName("DialogHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        box = QGroupBox("Pages")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)
        self.group = QButtonGroup(self)
        self.r_current = QRadioButton(f"Current page ({current_page + 1})")
        self.r_selected = QRadioButton(f"Selected pages ({len(self._selected)})")
        self.r_all = QRadioButton(f"All pages ({page_count})")
        self.r_range = QRadioButton("Pages:")
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText(f"e.g. 1-3, 7  (1–{page_count})")
        self.range_edit.setAccessibleName("Page range")
        self.range_edit.textEdited.connect(lambda _t: self.r_range.setChecked(True))
        self.r_selected.setEnabled(len(self._selected) > 1)
        for i, r in enumerate((self.r_current, self.r_selected, self.r_all, self.r_range)):
            self.group.addButton(r, i)
        for r in (self.r_current, self.r_selected, self.r_all):
            bl.addWidget(r)
        rng = QHBoxLayout()
        rng.addWidget(self.r_range)
        rng.addWidget(self.range_edit, 1)
        bl.addLayout(rng)
        self.range_error = QLabel("")
        self.range_error.setObjectName("InspectorError")
        self.range_error.hide()
        bl.addWidget(self.range_error)
        self.r_current.setChecked(True)
        self.skip_text = QCheckBox("Skip pages that already contain text")
        self.skip_text.setChecked(True)
        bl.addWidget(self.skip_text)
        layout.addWidget(box)
        self.languages = LanguagePicker(languages)
        layout.addWidget(self.languages, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Recognize")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _range_pages(self) -> list[int] | None:
        from core.organize.page_ops import parse_page_ranges

        try:
            pages = parse_page_ranges(self.range_edit.text(), self._page_count)
        except ValueError as exc:
            self.range_error.setText(str(exc))
            self.range_error.show()
            return None
        if not pages:
            self.range_error.setText("Type the pages to recognize, e.g. 1-3, 7")
            self.range_error.show()
            return None
        self.range_error.hide()
        return pages

    def _accept(self) -> None:
        if self.r_range.isChecked() and self._range_pages() is None:
            self.range_edit.setFocus()
            return
        self.accept()

    def pages(self) -> list[int]:
        if self.r_all.isChecked():
            return list(range(self._page_count))
        if self.r_selected.isChecked():
            return list(self._selected)
        if self.r_range.isChecked():
            return self._range_pages() or [self._current]
        return [self._current]


class LanguagePicker(QGroupBox):
    """Check the OCR languages to use (bundled and installed optional ones).

    Built for many languages: a search box filters the list (from 7 languages on), the chosen ones
    are listed under it, every row shows the language's name and its Tesseract code, and at least
    one language always stays chosen."""

    SEARCH_FROM = 7

    def __init__(self, selected: str, parent=None) -> None:
        from PySide6.QtWidgets import QLineEdit

        from core.ocr.language_packs import available_languages

        super().__init__("Languages", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        langs = available_languages()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a language…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Find a language")
        self.search.textChanged.connect(self._filter)
        self.search.setVisible(len(langs) >= self.SEARCH_FROM)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("OcrLanguageList")
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(1)
        self.list.setAccessibleName("OCR languages")
        chosen = set(selected.split("+"))
        for code, name in sorted(langs.items(), key=lambda kv: (kv[0] not in chosen, kv[1].casefold())):
            item = QListWidgetItem(f"{name}   ·   {code}")
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setToolTip(f"{name} (Tesseract language code {code})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code in chosen else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        if not any(self.list.item(i).checkState() == Qt.CheckState.Checked for i in range(self.list.count())) \
                and self.list.count():
            self.list.item(0).setCheckState(Qt.CheckState.Checked)
        rows = max(2, min(7, self.list.count()))
        row_h = max(24, self.list.sizeHintForRow(0) if self.list.count() else 24) + 2
        self.list.setMinimumHeight(rows * row_h + 8)
        if self.list.count() <= 7:  # a short list: no empty space under it
            self.list.setMaximumHeight(rows * row_h + 8)
        self.list.itemChanged.connect(self._changed)
        layout.addWidget(self.list, 1)
        self.summary = QLabel("")
        self.summary.setObjectName("DialogHint")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        note = QLabel("More languages: OCR ▸ OCR Languages. Choose only the languages on the pages: "
                      "fewer languages recognize faster and more accurately.")
        note.setObjectName("ContextHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._changed()

    def _filter(self, text: str) -> None:
        t = text.strip().casefold()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(t) and t not in item.text().casefold())

    def _changed(self, item=None) -> None:
        checked = [self.list.item(i) for i in range(self.list.count())
                   if self.list.item(i).checkState() == Qt.CheckState.Checked]
        if not checked and item is not None:  # the last language cannot be unticked
            self.list.blockSignals(True)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.blockSignals(False)
            checked = [item]
        names = [c.text().split("   ·")[0] for c in checked]
        text = "Recognize: " + ", ".join(names)
        if len(names) > 3:
            text += " — many languages: slower, and similar letters may be mixed up"
        self.summary.setText(text)

    def value(self) -> str:
        codes = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                 if self.list.item(i).checkState() == Qt.CheckState.Checked]
        return "+".join(codes) or "eng"


class OcrLanguagesDialog(QDialog):
    """Default OCR languages, and optional languages installed from verified files."""

    def __init__(self, languages: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR Languages")
        self.resize(560, 520)
        self._languages = languages
        self._layout = QVBoxLayout(self)
        self.picker = LanguagePicker(languages)
        self._layout.addWidget(QLabel("Languages used for OCR:"))
        self._layout.addWidget(self.picker)
        box = QGroupBox("Optional languages")
        bl = QVBoxLayout(box)
        text = QLabel(
            "English and Japanese are included. Other languages are not downloaded by Monograph PDF: download "
            "the language file from the address shown (the official Tesseract release used for the included "
            "languages), then choose Install from File. Only a file whose size and SHA-256 match is accepted.")
        text.setWordWrap(True)
        bl.addWidget(text)
        self.packs = QListWidget()
        self.packs.setWordWrap(True)
        bl.addWidget(self.packs, 1)
        row = QHBoxLayout()
        self.install_btn = QPushButton("Install from File…")
        self.install_btn.clicked.connect(self._install)
        self.copy_btn = QPushButton("Copy Download Address")
        self.copy_btn.clicked.connect(self._copy_url)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove)
        for b in (self.install_btn, self.copy_btn, self.remove_btn):
            row.addWidget(b)
        bl.addLayout(row)
        self._layout.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._layout.addWidget(buttons)
        self._fill()

    def _fill(self) -> None:
        from core.ocr.language_packs import catalog, installed

        have = {p.code for p in installed()}
        self.packs.clear()
        for p in catalog():
            state = "installed" if p.code in have else "not installed"
            item = QListWidgetItem(f"{p.name} — {state}\n{p.url}  ({p.size / 1e6:.1f} MB)")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.packs.addItem(item)

    def _refresh_picker(self) -> None:
        current = self.picker.value()
        index = self._layout.indexOf(self.picker)
        self._layout.removeWidget(self.picker)
        self.picker.deleteLater()
        self.picker = LanguagePicker(current)
        self._layout.insertWidget(index, self.picker)

    def install_file(self, path: str) -> bool:
        from pathlib import Path

        from core.ocr.language_packs import LanguagePackError, install_from_file

        try:
            pack = install_from_file(Path(path))
        except LanguagePackError as exc:
            QMessageBox.warning(self, "Install OCR Language", str(exc))
            return False
        QMessageBox.information(self, "Install OCR Language", f"{pack.name} is installed and verified.")
        self._fill()
        self._refresh_picker()
        return True

    def _install(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Install OCR Language", "", "Tesseract language data (*.traineddata)")
        if path:
            self.install_file(path)

    def _copy_url(self) -> None:
        item = self.packs.currentItem()
        if item is not None:
            QApplication.clipboard().setText(item.data(Qt.ItemDataRole.UserRole).url)

    def _remove(self) -> None:
        from core.ocr.language_packs import remove

        item = self.packs.currentItem()
        if item is not None and remove(item.data(Qt.ItemDataRole.UserRole).code):
            self._fill()
            self._refresh_picker()

    def value(self) -> str:
        return self.picker.value()
