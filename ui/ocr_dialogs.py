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
        from core.ocr.pipeline import OcrCancelled, run_ocr

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
        self.result = None

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
        self.result = result
        self.accept()

    def _on_fail(self, message: str) -> None:
        QMessageBox.warning(self, "OCR failed", message)
        self.reject()

    def _on_cancelled(self) -> None:
        self.result = None
        self.reject()
