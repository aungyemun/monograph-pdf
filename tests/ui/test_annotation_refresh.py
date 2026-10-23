"""Adding a highlight (or another comment) redraws only that page, in place: the view is not reset,
the page never goes blank, and the new picture shows the highlight at once."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-annot-refresh"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    src = tmp_path / "text.pdf"
    doc = fitz.open()
    for n in range(3):
        doc.new_page(width=595, height=842).insert_text((72, 120), f"Highlight this sentence on page {n + 1}",
                                                        fontsize=18)
    doc.save(str(src))
    doc.close()
    assert w.open_path(src)
    qtbot.wait(100)
    yield w
    w.close_document(save_session=False)
    w.close()


def _page_pixmap(w, page):
    from core.render_cache import RenderKey

    inner = w._canvas._canvas  # noqa: SLF001
    key = RenderKey.make(page, inner._zoom, inner._pages[page].rotation, inner._device_pixel_ratio())  # noqa: SLF001
    return inner._cache.get(key)  # noqa: SLF001


def _yellow_pixels(pix) -> int:
    img = pix.toImage()
    n = 0
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            if c.red() > 200 and c.green() > 200 and c.blue() < 120:
                n += 1
    return n


def test_highlight_redraws_the_page_in_place(win, qtbot, monkeypatch):
    from core.editing.annot_commands import HighlightStrokeCommand
    from core.editing.geometry import Rect

    inner = win._canvas._canvas  # noqa: SLF001
    win._canvas.go_to_page(0)  # noqa: SLF001
    inner._render_visible()  # noqa: SLF001
    before = _page_pixmap(win, 0)
    assert before is not None and _yellow_pixels(before) == 0
    resets = []
    monkeypatch.setattr(inner, "set_document", lambda *a, **k: resets.append("canvas"))
    monkeypatch.setattr(win._left, "set_document", lambda *a, **k: resets.append("panels"))  # noqa: SLF001
    blank = []
    real_discard = inner._cache.discard  # noqa: SLF001

    def discard(key):
        if key.page_index == 0:
            blank.append(key)
        return real_discard(key)

    monkeypatch.setattr(inner._cache, "discard", discard)  # noqa: SLF001
    thumbs = []
    monkeypatch.setattr(win._left.thumbs, "refresh_pages", lambda pages: thumbs.append(list(pages)))  # noqa: SLF001
    v = win._canvas.verticalScrollBar().value()  # noqa: SLF001

    win._edit.commands.execute(HighlightStrokeCommand(  # noqa: SLF001
        win._document, win._edit, 0, [Rect(70, 100, 330, 26)], [], color=(1.0, 1.0, 0.0)))  # noqa: SLF001
    win._after_annotation(0, "Highlight added")  # noqa: SLF001

    after = _page_pixmap(win, 0)
    assert resets == [] and blank == []  # no reload of the view, the page was never without a picture
    assert after is not None and after is not before and _yellow_pixels(after) > 20  # shown at once
    assert thumbs == [[0]]  # only that thumbnail
    assert win._canvas.verticalScrollBar().value() == v  # noqa: SLF001
    assert win._edit.dirty  # noqa: SLF001


def test_other_pages_keep_their_pictures(win, qtbot):
    from core.editing.annot_commands import MarkupAnnotCommand
    from core.editing.geometry import Rect

    inner = win._canvas._canvas  # noqa: SLF001
    win._canvas.go_to_page(0)  # noqa: SLF001
    inner._render_visible()  # noqa: SLF001
    others = {p: _page_pixmap(win, p) for p in (1,) if _page_pixmap(win, p) is not None}
    win._edit.commands.execute(MarkupAnnotCommand(  # noqa: SLF001
        win._document, win._edit, 0, "underline", [Rect(70, 100, 330, 26)], color=(0, 0, 1)))  # noqa: SLF001
    win._after_annotation(0, "Underline added")  # noqa: SLF001
    for p, pix in others.items():
        assert _page_pixmap(win, p) is pix


def test_undo_and_redo_of_a_highlight_show_at_once(win, qtbot):
    from core.editing.annot_commands import HighlightStrokeCommand
    from core.editing.geometry import Rect

    inner = win._canvas._canvas  # noqa: SLF001
    win._canvas.go_to_page(0)  # noqa: SLF001
    inner._render_visible()  # noqa: SLF001
    win._edit.commands.execute(HighlightStrokeCommand(  # noqa: SLF001
        win._document, win._edit, 0, [Rect(70, 100, 330, 26)], [], color=(1.0, 1.0, 0.0)))  # noqa: SLF001
    win._after_annotation(0, "Highlight added")  # noqa: SLF001
    assert _yellow_pixels(_page_pixmap(win, 0)) > 20
    win._undo()  # noqa: SLF001
    qtbot.wait(50)
    inner._render_visible()  # noqa: SLF001
    assert _yellow_pixels(_page_pixmap(win, 0)) == 0
    win._redo()  # noqa: SLF001
    qtbot.wait(50)
    inner._render_visible()  # noqa: SLF001
    assert _yellow_pixels(_page_pixmap(win, 0)) > 20
