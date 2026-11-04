"""The page view and the thumbnails draw a little at a time and never hold up scrolling.

PyMuPDF keeps Python's GIL while it renders, so a render on a worker thread froze the window as long
as one on the GUI thread (measured: a 246 ms render stalled the GUI thread 243 ms). Audit 2026-11:
dragging the scroll bar through a 120-page colour-scan PDF froze the window up to 273 ms per jump,
because every visible page and its neighbours were drawn in one go, and thumbnails were drawn on
thread-pool threads using the same document as the page view.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-incremental"])
    src = tmp_path / "pages.pdf"
    doc = fitz.open()
    for i in range(60):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=24)
        page.draw_rect(fitz.Rect(72, 120, 523, 700), color=(0, 0, 0), fill=(0.2, 0.3, 0.8))
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    assert w.open_path(src)
    qtbot.waitUntil(lambda: not w._canvas._canvas._render_timer.isActive(), timeout=5000)  # noqa: SLF001
    yield w
    w.close_document(save_session=False)
    w.close()


def _slow_renders(monkeypatch, doc, seconds: float) -> list[int]:
    calls: list[int] = []
    real = doc.render_rgb

    def slow(i, *a, **k):
        calls.append(i)
        time.sleep(seconds)
        return real(i, *a, **k)

    monkeypatch.setattr(doc, "render_rgb", slow)
    return calls


def _visible_pages(inner) -> list[int]:
    vis = inner.visibleRegion().boundingRect()
    return list(range(inner.page_at_y(vis.top()), inner.page_at_y(vis.bottom()) + 1))


def _drawn(inner, i: int) -> bool:
    from core.render_cache import RenderKey

    key = RenderKey.make(i, inner._zoom, inner._pages[i].rotation, inner._device_pixel_ratio())  # noqa: SLF001
    return inner._cache.get(key) is not None  # noqa: SLF001


def test_one_turn_draws_about_one_frame_then_continues(win, qtbot, monkeypatch):
    from ui import pdf_canvas

    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    inner._last_scroll_t = 0.0  # noqa: SLF001 — not scrolling
    canvas.set_manual_zoom(0.25)  # several pages on screen at once
    qtbot.waitUntil(lambda: not inner._render_timer.isActive(), timeout=5000)  # noqa: SLF001
    inner._cache.clear()  # noqa: SLF001
    calls = _slow_renders(monkeypatch, inner._document, pdf_canvas.RENDER_STEP_BUDGET_S * 2)  # noqa: SLF001
    visible = _visible_pages(inner)
    assert len(visible) >= 3
    inner._last_scroll_t = 0.0  # noqa: SLF001
    inner._render_step()  # noqa: SLF001
    assert len(calls) == 1, f"one slow page per turn, then input is handled: {calls}"
    middle = inner.visibleRegion().boundingRect().center().y()
    nearest = min(visible, key=lambda i: abs(inner._layouts[i].center().y() - middle))  # noqa: SLF001
    assert calls[0] == nearest, "the page in the middle of the view is drawn first"
    assert inner._render_timer.isActive(), "the rest follows on the next turn"  # noqa: SLF001
    qtbot.waitUntil(lambda: all(_drawn(inner, i) for i in visible), timeout=5000)


def test_heavy_pages_show_a_quick_preview_while_scrolling_then_sharp(win, qtbot, monkeypatch):
    from ui import pdf_canvas

    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    inner._render_costs = [pdf_canvas.HEAVY_RENDER_S * 3] * 8  # noqa: SLF001 — a document of large pictures
    bar = canvas.verticalScrollBar()
    bar.setValue(inner.page_top(30))  # noqa: SLF001 — a jump: the user is scrolling
    target = _visible_pages(inner)
    assert not any(_drawn(inner, i) for i in target)
    inner._render_step()  # noqa: SLF001
    previews = inner._previews  # noqa: SLF001
    assert any(i in previews for i in target), "a quick picture is shown at once"
    assert not any(_drawn(inner, i) for i in target), "sharp pages wait until scrolling stops"
    p = next(i for i in target if i in previews)
    small = previews[p][1]
    page_px = inner._layouts[p].width() * inner._device_pixel_ratio()  # noqa: SLF001
    assert small.width() < page_px * 0.5, "the preview is small, so it is quick to draw"
    img = inner.grab(inner._layouts[p]).toImage()  # noqa: SLF001
    blue = sum(1 for x in range(0, img.width(), 9) for y in range(0, img.height(), 9)
               if img.pixelColor(x, y).blue() > 150 and img.pixelColor(x, y).red() < 120)
    assert blue > 0, "the page shows its (scaled) picture, not a blank page, while scrolling"
    qtbot.waitUntil(lambda: all(_drawn(inner, i) for i in target), timeout=5000)
    assert not any(i in inner._previews for i in target), "previews give way to the sharp pages"  # noqa: SLF001


def test_a_preview_is_never_shown_for_changed_content(win, qtbot):
    from ui import pdf_canvas

    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    inner._render_costs = [pdf_canvas.HEAVY_RENDER_S * 3] * 8  # noqa: SLF001
    canvas.verticalScrollBar().setValue(inner.page_top(20))  # noqa: SLF001
    inner._render_step()  # noqa: SLF001
    shown = [i for i in _visible_pages(inner) if i in inner._previews]  # noqa: SLF001
    assert shown
    inner.drop_stale(shown)  # what a content change (annotation, form value, undo) does
    assert not any(i in inner._previews for i in shown)  # noqa: SLF001
    inner._render_step()  # noqa: SLF001
    inner.rerender_all()  # a change of how pixels are shown (monitor colours)
    assert not inner._previews  # noqa: SLF001


def test_thumbnails_wait_while_the_page_view_is_busy(win, qtbot):
    from PySide6.QtCore import QThreadPool

    thumbs = win._left.thumbs  # noqa: SLF001
    qtbot.waitUntil(lambda: not thumbs.item(0).icon().isNull(), timeout=5000)
    busy = [True]
    thumbs.set_busy_probe(lambda: busy[0])
    thumbs.release_images()
    thumbs.restore_images()
    qtbot.wait(250)
    assert thumbs.item(0).icon().isNull(), "no thumbnail is drawn while the page view scrolls or draws"
    busy[0] = False
    qtbot.waitUntil(lambda: not thumbs.item(0).icon().isNull(), timeout=5000)
    assert QThreadPool.globalInstance().activeThreadCount() == 0, "thumbnails are not drawn on worker threads"


def test_refreshing_every_thumbnail_only_redraws_those_near_the_view(win, qtbot, monkeypatch):
    from ui import thumbnail_panel

    thumbs = win._left.thumbs  # noqa: SLF001
    thumbs.set_busy_probe(None)
    qtbot.waitUntil(lambda: not thumbs.item(0).icon().isNull(), timeout=5000)
    drawn: list[int] = []
    real = thumbnail_panel.render_thumbnail_image
    monkeypatch.setattr(thumbnail_panel, "render_thumbnail_image",
                        lambda doc, i, *a, **k: (drawn.append(i), real(doc, i, *a, **k))[1])
    before = thumbs.item(0).icon().cacheKey()
    thumbs.refresh_pages(range(thumbs.count()))
    qtbot.waitUntil(lambda: not thumbs._queue, timeout=5000)  # noqa: SLF001
    assert 0 in drawn and thumbs.item(0).icon().cacheKey() != before, "the visible thumbnail is redrawn"
    assert len(drawn) < 40, f"far-away thumbnails are only drawn again when shown: {len(drawn)}"


def test_a_page_that_cannot_be_drawn_is_tried_once_and_drawing_stops(win, qtbot, monkeypatch):
    """Review 2026-11: a visible page whose render raised was retried on every turn for ever (window
    busy, thumbnails waiting); it is tried once until its content, the zoom or the document changes."""
    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    inner._cache.clear()  # noqa: SLF001
    broken = _visible_pages(inner)[0]
    doc = inner._document  # noqa: SLF001
    real = doc.render_rgb
    tries: list[int] = []

    def flaky(i, *a, **k):
        if i == broken:
            tries.append(i)
            time.sleep(0.02)  # the failure takes longer than one turn's budget
            raise RuntimeError("damaged content stream")
        return real(i, *a, **k)

    monkeypatch.setattr(doc, "render_rgb", flaky)
    win._left.thumbs.set_busy_probe(lambda: True)  # noqa: SLF001 — count the page view's attempts only
    inner._last_scroll_t = 0.0  # noqa: SLF001
    inner._schedule_render()  # noqa: SLF001
    qtbot.waitUntil(lambda: not inner._render_timer.isActive(), timeout=3000)  # noqa: SLF001
    qtbot.wait(200)
    assert not inner._render_timer.isActive(), "drawing stops"  # noqa: SLF001
    assert len(tries) == 1, f"the damaged page is tried once, not on every turn: {len(tries)}"
    assert not inner.render_busy(), "other drawing (thumbnails) is not held up"
    inner.drop_stale([broken])  # its content changed (e.g. repaired by an edit): tried again
    inner._schedule_render()  # noqa: SLF001
    qtbot.waitUntil(lambda: len(tries) == 2, timeout=3000)


def test_fast_scroll_events_do_not_starve_drawing(win, qtbot):
    """Review 2026-11: every scroll event restarted the 16 ms render timer, so scroll events closer than
    16 ms apart (precision touchpads, kinetic scrolling) held all drawing back until scrolling stopped."""
    from ui import pdf_canvas

    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    inner._render_costs = [pdf_canvas.HEAVY_RENDER_S * 3] * 8  # noqa: SLF001 — previews while scrolling
    bar = canvas.verticalScrollBar()
    steps = [0]
    real = inner._render_step  # noqa: SLF001
    inner._render_timer.timeout.disconnect()  # noqa: SLF001
    inner._render_timer.timeout.connect(lambda: (steps.__setitem__(0, steps[0] + 1), real()))  # noqa: SLF001
    from PySide6.QtWidgets import QApplication

    end = time.perf_counter() + 0.5
    while time.perf_counter() < end:  # a scroll event every ~6 ms for half a second
        bar.setValue(bar.value() + 25)
        QApplication.processEvents()
        time.sleep(0.006)
    assert steps[0] >= 5, f"pages are drawn while scrolling, not only after it stops: {steps[0]} turns"
    assert any(i in inner._previews or _drawn(inner, i) for i in _visible_pages(inner))  # noqa: SLF001


def test_zoomed_in_heavy_pages_draw_no_sharp_tiles_while_scrolling(win, qtbot, monkeypatch):
    from ui import pdf_canvas

    canvas = win._canvas  # noqa: SLF001
    inner = canvas._canvas  # noqa: SLF001
    canvas.set_manual_zoom(4.0)  # pages larger than MAX_PAGE_PIXELS: low-resolution base + sharp tiles
    qtbot.waitUntil(lambda: not inner._render_timer.isActive(), timeout=8000)  # noqa: SLF001
    inner._render_costs = [pdf_canvas.HEAVY_RENDER_S * 3] * 8  # noqa: SLF001
    canvas.verticalScrollBar().setValue(inner.page_top(10) + 300)  # noqa: SLF001 — the user scrolls
    drawn_tiles: list = []
    real = inner._render_tiles  # noqa: SLF001
    monkeypatch.setattr(inner, "_render_tiles", lambda *a, **k: (drawn_tiles.append(a[0]), real(*a, **k))[1])
    inner._render_step()  # noqa: SLF001
    assert not drawn_tiles, "sharp tiles wait for scrolling to stop (the base page shows meanwhile)"
    qtbot.waitUntil(lambda: bool(drawn_tiles), timeout=3000)  # ... and then follow


def test_hidden_thumbnail_panel_forgets_changed_pictures_and_redraws_when_shown(win, qtbot):
    thumbs = win._left.thumbs  # noqa: SLF001
    thumbs.set_busy_probe(None)
    qtbot.waitUntil(lambda: not thumbs.item(0).icon().isNull(), timeout=5000)
    thumbs.hide()
    thumbs.refresh_pages(range(thumbs.count()))  # e.g. Match Monitor Colors while another tab is shown
    assert thumbs.item(0).icon().isNull(), "no out-of-date picture is kept"
    thumbs.show()
    qtbot.waitUntil(lambda: not thumbs.item(0).icon().isNull(), timeout=5000)
