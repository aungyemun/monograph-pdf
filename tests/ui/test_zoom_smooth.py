"""Zooming: the point under the mouse stays put, a burst of wheel steps renders once, and the page
is never blank while the sharp picture at the new zoom is being made (the old one is shown scaled)."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint  # noqa: E402


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-zoom"])
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    for i in range(6):
        d.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=24)
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1300, 900)
    w.show()
    assert w.open_path(src)
    qtbot.waitUntil(lambda: len(w._canvas._canvas._cache) > 0, timeout=3000)  # noqa: SLF001
    yield w
    w.close_document(save_session=False)
    w.close()


def test_zoom_keeps_the_point_under_the_mouse(win, qtbot):
    outer = win._canvas  # noqa: SLF001
    inner = outer._canvas  # noqa: SLF001
    outer.verticalScrollBar().setValue(300)
    qtbot.wait(50)
    anchor = QPoint(400, 300)
    hb, vb = outer.horizontalScrollBar(), outer.verticalScrollBar()
    content = QPoint(hb.value() + anchor.x(), vb.value() + anchor.y())
    page = inner.page_at_y(content.y())
    r = inner._layouts[page]  # noqa: SLF001
    fy = (content.y() - r.top()) / r.height()
    outer.set_manual_zoom(outer.zoom * 1.6, anchor)
    r2 = inner._layouts[page]  # noqa: SLF001
    fy2 = (vb.value() + anchor.y() - r2.top()) / r2.height()
    assert abs(fy2 - fy) < 0.01, (fy, fy2)


def test_zoom_burst_shows_scaled_pages_then_renders_once(win, qtbot):
    outer = win._canvas  # noqa: SLF001
    inner = outer._canvas  # noqa: SLF001
    calls = []
    original = inner._render_visible  # noqa: SLF001
    inner._render_timer.timeout.disconnect()  # noqa: SLF001
    inner._render_timer.timeout.connect(lambda: (calls.append(1), original()))  # noqa: SLF001
    for _ in range(5):
        outer.zoom_in()
        qtbot.wait(10)
    assert len(inner._cache) == 0 and inner._stale_pix, "the previous pictures are kept to be shown scaled"  # noqa: SLF001
    img = inner.grab(inner._layouts[inner._focus_page]).toImage()  # noqa: SLF001
    dark = sum(1 for x in range(0, img.width(), 7) for y in range(0, img.height(), 7)
               if img.pixelColor(x, y).lightness() < 120)
    assert dark > 0, "the page is drawn (scaled), not blank, while zooming"
    qtbot.waitUntil(lambda: len(inner._cache) > 0 and not inner._render_timer.isActive(), timeout=3000)  # noqa: SLF001
    assert len(calls) <= 2, f"rendered {len(calls)} times for one burst"
