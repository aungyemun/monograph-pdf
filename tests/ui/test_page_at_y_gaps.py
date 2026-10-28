"""A height between two pages belongs to the page above, never to the last page.

Regression (0.5.0 validation): ``page_at_y`` returned the last page for a y in the gap between two
pages. Whenever the top or bottom edge of the window fell in a gap, every page from the current one to
the end of the document was rendered at once (freezes of several seconds in a 300-page document), the
current page jumped to the last page, and zooming around a pointer in a gap jumped to the end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def canvas(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-page-gaps"])
    src = tmp_path / "pages.pdf"
    doc = fitz.open()
    for i in range(40):
        doc.new_page(width=595, height=842).insert_text((72, 72), f"Page {i + 1}")
    doc.save(src)
    doc.close()
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 900)
    win.show()
    assert win.open_path(src)
    yield win._canvas  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def test_gap_between_pages_maps_to_page_above(canvas):
    inner = canvas._canvas  # noqa: SLF001
    layouts = inner._layouts  # noqa: SLF001
    assert len(layouts) == 40
    for i in range(len(layouts) - 1):
        assert inner.page_at_y(layouts[i].top()) == i
        assert inner.page_at_y(layouts[i].bottom()) == i
        gap = range(layouts[i].bottom() + 1, layouts[i + 1].top())
        assert gap, "pages are laid out with a gap between them"
        for y in (gap.start, gap.stop - 1):
            assert inner.page_at_y(y) == i, (i, y)
    assert inner.page_at_y(-50) == 0
    assert inner.page_at_y(layouts[-1].bottom() + 500) == len(layouts) - 1


def test_window_edge_in_a_gap_renders_only_nearby_pages(qtbot, canvas):
    """With the bottom edge of the window in a gap only the visible pages (±1) are rendered."""
    inner = canvas._canvas  # noqa: SLF001
    layouts = inner._layouts  # noqa: SLF001
    bar = canvas.verticalScrollBar()
    doc = inner._document  # noqa: SLF001
    real = doc.render_rgb
    for gap_y in range(layouts[5].bottom() + 1, layouts[6].top()):
        # bottom edge of the visible area (QRect.bottom() = top + height - 1) exactly in the gap
        bar.setValue(max(0, gap_y - inner.visibleRegion().boundingRect().height() + 1))
        qtbot.wait(20)
        visible = inner.visibleRegion().boundingRect()
        if visible.bottom() != gap_y:
            continue
        rendered: list[int] = []

        def spy(i, *a, _r=rendered, **k):
            _r.append(i)
            return real(i, *a, **k)

        inner._cache.clear()  # noqa: SLF001
        doc.render_rgb = spy
        try:
            inner._render_visible()  # noqa: SLF001
        finally:
            doc.render_rgb = real
        assert rendered, "something visible is rendered"
        assert max(rendered) <= 7, (gap_y, sorted(set(rendered)))
        assert canvas.focus_page <= 6
        return
    pytest.fail("could not place the bottom edge of the window in a gap")
