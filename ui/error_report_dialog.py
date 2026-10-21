"""Error-report dialog: exactly two decisions — Don't Send / Send to Developer.

The sanitized report is shown in full (read-only, scrollable) before the user decides. Nothing is
transmitted unless the user clicks Send to Developer; sending runs off the UI thread with a
timeout, the result shown is the real outcome, and there is no automatic retry.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from core.diagnostics import client
from core.diagnostics import report as reports

DONT_SEND = "Don’t Send"
SEND = "Send to Developer"


class _Sender(QThread):
    finished_with = Signal(object)

    def __init__(self, report: dict, config) -> None:
        super().__init__()
        self._report, self._config = report, config

    def run(self) -> None:
        try:
            self.finished_with.emit(client.send(self._report, self._config))
        except Exception:  # noqa: BLE001
            self.finished_with.emit(client.SendResult(False, "The report could not be sent. Nothing more will be sent."))


class ErrorReportDialog(QDialog):
    def __init__(self, report: dict, *, summary: str, parent=None, config=None) -> None:
        super().__init__(parent)
        self.report = reports.validate(report)
        self.sent: client.SendResult | None = None
        self._config = config
        self._sender: _Sender | None = None
        self.setWindowTitle("Monograph PDF — Problem Report")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel(summary)
        head.setWordWrap(True)
        lay.addWidget(head)
        explain = QLabel(
            "You can send the technical report below to the developer to help fix this problem. It contains "
            "only limited technical information — no document content, file names, folder paths, user "
            "names or typed text — and is sent only if you click “Send to Developer”."
        )
        explain.setWordWrap(True)
        explain.setObjectName("DialogHint")
        lay.addWidget(explain)
        details = QPlainTextEdit(reports.render(self.report))
        details.setReadOnly(True)
        details.setObjectName("ReportDetails")
        details.setMinimumHeight(170)
        lay.addWidget(details)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)
        self.buttons = QDialogButtonBox()
        self.dont_send = self.buttons.addButton(DONT_SEND, QDialogButtonBox.ButtonRole.RejectRole)
        self.send_button = self.buttons.addButton(SEND, QDialogButtonBox.ButtonRole.AcceptRole)
        self.dont_send.clicked.connect(self.reject)
        self.send_button.clicked.connect(self._send)
        lay.addWidget(self.buttons)
        self.dont_send.setDefault(True)

    def _send(self) -> None:
        if self._sender is not None:
            return
        self.send_button.setEnabled(False)
        self.dont_send.setEnabled(False)
        self._status.setText("Sending…")
        self._sender = _Sender(self.report, self._config)
        self._sender.finished_with.connect(self._sent)
        self._sender.start()

    def _sent(self, result) -> None:
        self.sent = result
        if self._sender is not None:
            self._sender.wait(2000)
        if result.ok:
            QMessageBox.information(self, "Report sent", result.message)
        else:
            QMessageBox.warning(self, "Report not sent", result.message)
        self.accept()

    def reject(self) -> None:
        if self._sender is not None and self._sender.isRunning():
            return  # wait for the real outcome (the request has a 15-second limit)
        super().reject()
