"""Load offline branding assets into Qt icons/pixmaps."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from core.product_meta import branding_assets_ok, icon_path, resolve_app_icon_path


def load_app_icon() -> QIcon:
    """Multi-resolution application icon from bundled resources (no network)."""
    icon = QIcon()
    ico = resolve_app_icon_path()
    if ico is not None and ico.suffix.lower() == ".ico":
        icon.addFile(str(ico))
        return icon
    for size in (16, 24, 32, 48, 64, 128, 256):
        png = icon_path(f"windows/monograph_pdf_{size}.png")
        if png.is_file():
            icon.addFile(str(png))
    if icon.isNull() and ico is not None:
        icon.addFile(str(ico))
    return icon


def apply_application_icon(app: QApplication | None = None) -> tuple[bool, str]:
    ok, detail = branding_assets_ok()
    target = app or QApplication.instance()
    icon = load_app_icon()
    if target is not None and not icon.isNull():
        target.setWindowIcon(icon)
    if icon.isNull():
        return False, "Application icon could not be loaded"
    return ok, detail


def load_logo_pixmap(logical_px: int = 64) -> QPixmap | None:
    from core.product_meta import resolve_about_logo_path

    path = resolve_about_logo_path()
    if path is None:
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    app = QApplication.instance()
    dpr = float(app.devicePixelRatio()) if app is not None else 1.0
    target = max(1, int(logical_px * dpr))
    scaled = pix.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled
