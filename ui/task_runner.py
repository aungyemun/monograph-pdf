"""Run a slow job off the UI thread behind a small modal progress dialog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout


class _Worker(QThread):
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:  # noqa: D401
        try:
            self.done.emit(self._fn())
        except BaseException as exc:  # noqa: BLE001 — surfaced to the caller
            self.failed.emit(exc)


class BusyDialog(QDialog):
    def __init__(self, title: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        text = QLabel(label)
        text.setWordWrap(True)
        lay.addWidget(text)
        bar = QProgressBar()
        bar.setRange(0, 0)  # indeterminate
        bar.setTextVisible(False)
        lay.addWidget(bar)
        hint = QLabel("Working offline on this computer — please wait.")
        hint.setObjectName("DialogHint")
        lay.addWidget(hint)

    def reject(self) -> None:  # Esc does not abandon a running job
        pass


def run_with_progress(parent, title: str, label: str, fn: Callable[[], Any]) -> Any:
    """Run ``fn`` in a worker thread; block with a busy dialog; return or re-raise."""
    from core import app_env

    app = QApplication.instance()
    headless = (app is not None and app.platformName().lower() in ("offscreen", "minimal")) or app_env.is_true("HEADLESS")
    if headless:
        return fn()
    box: dict[str, Any] = {}
    worker = _Worker(fn)
    dlg = BusyDialog(title, label, parent)
    worker.done.connect(lambda r: (box.__setitem__("result", r), dlg.done(1)))
    worker.failed.connect(lambda e: (box.__setitem__("error", e), dlg.done(0)))
    worker.start()
    if worker.isRunning():
        dlg.exec()
    worker.wait()
    if "error" in box:
        raise box["error"]
    return box.get("result")
