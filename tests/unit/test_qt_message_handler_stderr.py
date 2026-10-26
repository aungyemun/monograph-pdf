"""Windowed PyInstaller sets sys.stderr to None — Qt handler must not raise."""

from __future__ import annotations

import sys

from PySide6.QtCore import QtMsgType, qInstallMessageHandler


def test_qt_message_handler_tolerates_none_stderr(monkeypatch) -> None:
    from core.diagnostics import crash

    monkeypatch.setattr(sys, "stderr", None)
    crash.install_qt_message_handler()
    # Emit a debug message through the installed handler chain.
    from PySide6.QtCore import qDebug

    qDebug("validation: stderr is None")
    # Restore a no-op handler so later tests are not affected.
    qInstallMessageHandler(None)
