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
        # Drop-down lists, menus and tooltips appear at once: Windows' slide / fade animations made
        # them flicker and lag (a list could be redrawn several times while it slid open)
        for effect in (Qt.UIEffect.UI_AnimateCombo, Qt.UIEffect.UI_AnimateMenu, Qt.UIEffect.UI_FadeMenu,
                       Qt.UIEffect.UI_AnimateTooltip, Qt.UIEffect.UI_FadeTooltip):
            QApplication.setEffectEnabled(effect, False)
    return app  # type: ignore[return-value]
