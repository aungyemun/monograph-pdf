"""Colour accuracy on screen: PDF colours rendered with ICC management (CMYK is converted with its
profile, not naively), and rendered pages, edited objects and placed pictures converted to the
monitor's colour profile when it is not sRGB (wide-gamut monitors). An sRGB monitor shows the
rendered pixels unchanged."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

from PySide6.QtGui import QColor, QColorSpace, QImage  # noqa: E402


@pytest.fixture
def app():
    from ui.main_window import create_application

    return create_application(["monograph-pdf-colors"])


@pytest.fixture
def dc(app):
    from ui import display_color

    yield display_color
    display_color._reset_for_tests(None)  # noqa: SLF001


def _red(fmt=QImage.Format.Format_RGB888) -> QImage:
    img = QImage(8, 8, fmt)
    img.fill(QColor(255, 0, 0))
    return img


def test_srgb_monitor_shows_rendered_pixels_unchanged(dc):
    dc._reset_for_tests(None)  # noqa: SLF001
    assert QColor(dc.to_display(_red()).pixel(2, 2)).getRgb()[:3] == (255, 0, 0)
    assert dc.qcolor("#ff0000").getRgb()[:3] == (255, 0, 0)
    assert dc.monitor_profile_name() == ""


def test_wide_gamut_monitor_gets_converted_pixels_and_colors(dc):
    dc._reset_for_tests(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))  # noqa: SLF001
    for fmt in (QImage.Format.Format_RGB888, QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32):
        r, g, b, _ = QColor(dc.to_display(_red(fmt)).pixel(2, 2)).getRgb()
        assert abs(r - 234) <= 2 and abs(g - 51) <= 3 and abs(b - 35) <= 3, (fmt, r, g, b)  # sRGB red in P3
    c = QColor(255, 0, 0, 128)
    m = dc.qcolor(c)
    assert m.alpha() == 128 and abs(m.red() - 234) <= 2
    dc.set_enabled(False)  # View > Match Colors to Monitor Profile off
    assert QColor(dc.to_display(_red()).pixel(2, 2)).getRgb()[:3] == (255, 0, 0)
    dc.set_enabled(True)


def test_picture_with_its_own_profile_is_shown_in_srgb(dc):
    dc._reset_for_tests(None)  # noqa: SLF001
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(QColor(0, 255, 0))
    img.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.AdobeRgb))
    r, g, b, _ = QColor(dc.image_for_screen(img).pixel(2, 2)).getRgb()
    assert g == 255 and r == 0 and b < 80, "Adobe RGB green is outside sRGB: clipped, not shown as sRGB green"


def test_cmyk_page_colors_are_color_managed(app, tmp_path):
    from core.document import open_document

    d = fitz.open()
    p = d.new_page(width=100, height=100)
    p.draw_rect(p.rect, color=None, fill=(1, 0, 0))
    d.update_stream(p.get_contents()[0], b"q 0 1 1 0 k 0 0 100 100 re f Q")  # CMYK red
    path = tmp_path / "cmyk.pdf"
    d.save(path)
    d.close()
    doc = open_document(path)
    try:
        img = QImage.fromData(doc.render_pixmap_png(0, zoom=1.0), "PNG")
    finally:
        doc.close()
    r, g, b, _ = QColor(img.pixel(50, 50)).getRgb()
    assert (r, g, b) != (255, 0, 0), "CMYK converted naively (no ICC colour management)"
    assert abs(r - 237) <= 4 and abs(g - 28) <= 6 and abs(b - 36) <= 6, (r, g, b)
