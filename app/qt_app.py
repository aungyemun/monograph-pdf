"""Minimal Qt application factory — imported before the heavy main window stack."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def create_application(argv: list[str]) -> QApplication:
    """Create (or reuse) QApplication. High-DPI policy must be set before the first instance."""
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(argv)
    return app  # type: ignore[return-value]
