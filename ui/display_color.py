"""Colours on screen as in the PDF: rendered pages converted from sRGB to the monitor's colour profile.

MuPDF renders every page to sRGB with ICC colour management (CMYK, ICC-based, calibrated and
spot colours are converted with their profiles; see docs/COLOR_AND_IMAGE_FIDELITY.md). Windows does
not colour-manage what an application draws: on a wide-gamut monitor (Display P3, Adobe RGB …)
sRGB pixels are shown over-saturated. When the monitor has a colour profile that is not sRGB, the
rendered pages, thumbnails and print previews are converted to it here, so colours look as intended.
On an sRGB monitor (the usual case) nothing is converted.

Read-only: the profile is read from the file Windows assigns to the display (``GetICMProfileW``);
nothing is installed or changed, and documents are never altered — only the pixels on screen.
"""

from __future__ import annotations

import os
import sys
import threading

from PySide6.QtGui import QColor, QColorSpace, QImage

_LOCK = threading.Lock()
_STATE: dict = {"loaded": False, "space": None, "transform": None, "enabled": True, "name": ""}


def _windows_profile_path() -> str:
    """Path of the colour profile Windows uses for the primary display ("" when unknown)."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        if not hdc:
            return ""
        try:
            size = wt.DWORD(0)
            gdi32.GetICMProfileW(hdc, ctypes.byref(size), None)
            buf = ctypes.create_unicode_buffer(max(int(size.value), 260) + 1)
            size = wt.DWORD(len(buf))
            if not gdi32.GetICMProfileW(hdc, ctypes.byref(size), buf):
                return ""
            return buf.value
        finally:
            user32.ReleaseDC(0, hdc)
    except Exception:  # noqa: BLE001 — no profile: treat the monitor as sRGB
        return ""


def _is_srgb(space: QColorSpace) -> bool:
    try:
        return (space.primaries() == QColorSpace.Primaries.SRgb
                and space.transferFunction() in (QColorSpace.TransferFunction.SRgb,))
    except Exception:  # noqa: BLE001
        return False


def _load() -> None:
    if _STATE["loaded"]:
        return
    _STATE["loaded"] = True
    if os.environ.get("MONOGRAPH_PDF_NO_DISPLAY_ICC") == "1" or not sys.platform.startswith("win"):
        return
    path = _windows_profile_path()
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "rb") as fh:
            data = fh.read(4 * 1024 * 1024)  # profiles are small; a bigger file is not a profile
        space = QColorSpace.fromIccProfile(data)
    except Exception:  # noqa: BLE001
        return
    if not space.isValid() or _is_srgb(space):
        return  # sRGB monitor (or an unusable profile): pixels are shown as rendered
    try:
        transform = QColorSpace(QColorSpace.NamedColorSpace.SRgb).transformationToColorSpace(space)
    except Exception:  # noqa: BLE001
        return
    if transform.isIdentity():
        return
    _STATE["space"] = space
    _STATE["transform"] = transform
    _STATE["name"] = space.description() or os.path.basename(path)


def set_enabled(on: bool) -> None:
    with _LOCK:
        _STATE["enabled"] = bool(on)


def is_enabled() -> bool:
    return bool(_STATE["enabled"])


def monitor_profile_name() -> str:
    """Description of the monitor profile used for conversion ("" = sRGB monitor, nothing converted)."""
    with _LOCK:
        _load()
        return _STATE["name"]


def to_display(image: QImage) -> QImage:
    """``image`` (sRGB pixels, as MuPDF renders) converted in place to the monitor profile when one is
    in use; returned unchanged otherwise. Never raises."""
    if image.isNull():
        return image
    with _LOCK:
        _load()
        transform = _STATE["transform"] if _STATE["enabled"] else None
    if transform is None:
        return image
    try:
        if image.format() not in (QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32,
                                  QImage.Format.Format_RGB888, QImage.Format.Format_RGBA8888):
            image = image.convertToFormat(QImage.Format.Format_RGB32)
        image.applyColorTransform(transform)
    except Exception:  # noqa: BLE001 — shown unconverted rather than not at all
        pass
    return image


def _reset_for_tests(space: QColorSpace | None = None) -> None:
    """Tests: use ``space`` as the monitor profile (None = sRGB monitor)."""
    with _LOCK:
        _STATE.update(loaded=True, space=None, transform=None, name="", enabled=True)
        if space is not None and space.isValid() and not _is_srgb(space):
            _STATE["space"] = space
            _STATE["transform"] = QColorSpace(QColorSpace.NamedColorSpace.SRgb).transformationToColorSpace(space)
            _STATE["name"] = space.description() or "test profile"


def qcolor(value) -> QColor:
    """A colour of an object being edited (text box, shape …), given in sRGB like PDF DeviceRGB,
    as it must be drawn on this monitor: the same conversion as the rendered page beneath it, so an
    edited object and the saved result look alike. Alpha is kept."""
    c = QColor(value)
    with _LOCK:
        _load()
        transform = _STATE["transform"] if _STATE["enabled"] else None
    if transform is None or not c.isValid():
        return c
    try:
        alpha = c.alphaF()
        out = transform.map(c)
        out.setAlphaF(alpha)
        return out
    except Exception:  # noqa: BLE001
        return c


def from_display(value) -> QColor:
    """A colour read off the screen (monitor profile) converted back to sRGB — the inverse of
    :func:`qcolor` — so a colour picked from a page is the colour stored in the PDF."""
    c = QColor(value)
    with _LOCK:
        _load()
        space = _STATE["space"] if _STATE["enabled"] else None
    if space is None or not c.isValid():
        return c
    try:
        back = space.transformationToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        alpha = c.alphaF()
        out = back.map(c)
        out.setAlphaF(alpha)
        return out
    except Exception:  # noqa: BLE001
        return c


def image_for_screen(image: QImage) -> QImage:
    """A placed picture prepared for the screen: a picture with its own colour profile (Adobe RGB,
    Display P3 …) is converted to sRGB first — Qt draws pixels as they are — then to the monitor
    profile as above."""
    if image.isNull():
        return image
    try:
        space = image.colorSpace()
        if space.isValid() and not _is_srgb(space):
            image = image.convertedToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    except Exception:  # noqa: BLE001
        pass
    return to_display(image)
