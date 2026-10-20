"""Highlight tool: continuous mode, free-area (ink) highlights, mixed strokes, undo/redo, rotation, save/reopen."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

TEMPLATES = Path(__file__).resolve().parents[1] / "fixtures" / "templates"
PLAYGROUND = TEMPLATES / "pdf" / "highlight_playground.pdf"
MIXED = TEMPLATES / "pdf" / "mixed_sizes_and_rotations.pdf"
CROP = TEMPLATES / "pdf" / "cropbox_offset.pdf"
if not PLAYGROUND.is_file():  # pragma: no cover
    pytest.skip("template PDFs not generated (run tests/fixtures/templates/make_templates.py)", allow_module_level=True)

# Display-space points on the (unrotated) playground page.
TEXT_Y = 118.0          # a line of body text, x 70..525
BLANK_A = [(380, 740), (500, 740)]    # empty area bottom right
BLANK_B = [(380, 770), (500, 770)]
MARKER_W = 11.0


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-highlight"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 900)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(window, tmp_path, src=PLAYGROUND, name="work.pdf", rotation=0):
    dst = tmp_path / name
    d = fitz.open(src.as_posix())
    if rotation:
        d[0].set_rotation(rotation)
    d.save(dst.as_posix())
    d.close()
    assert window.open_path(dst)
    return dst


def _drag(window, qtbot, page, pts):
    """Real mouse drag on the canvas along display-space points (PDF points, display orientation)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    inner = window._canvas._canvas  # noqa: SLF001
    wp = [inner.pdf_to_widget(page, Point(x, y)) for x, y in pts]
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[0])
    for p in wp[1:]:
        QTest.mouseMove(inner, p)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[-1])
    qtbot.wait(60)


def _line(x0, x1, y, n=12):
    return [(x0 + (x1 - x0) * i / n, y) for i in range(n + 1)]


def _annots(window, subtype=None):
    from types import SimpleNamespace

    out = []
    for p in window._document._backend._doc:  # noqa: SLF001
        for a in p.annots() or []:
            if subtype is None or a.type[1] == subtype:
                out.append(SimpleNamespace(type=a.type, rect=fitz.Rect(a.rect), opacity=a.opacity, border=a.border,
                                           info=a.info, colors=a.colors, vertices=a.vertices))
    return out


def _esc(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.keyClick(window._canvas._canvas, Qt.Key.Key_Escape)  # noqa: SLF001
    qtbot.wait(30)


def test_mode_stays_active_for_many_strokes_until_escape(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    assert window._canvas.region_pick_active  # noqa: SLF001
    for y in (TEXT_Y, TEXT_Y + 12, 740.0):
        _drag(window, qtbot, 0, _line(100, 400, y))
        assert window._canvas.region_pick_active, "mode ended after a stroke"  # noqa: SLF001
        assert window.act_annot_highlight.isChecked()
    assert len(_annots(window)) >= 3
    _esc(window, qtbot)
    assert not window._canvas.region_pick_active  # noqa: SLF001
    assert window.act_select_tool.isChecked() and not window.act_annot_highlight.isChecked()
    n = len(_annots(window))
    _drag(window, qtbot, 0, _line(100, 400, 600))  # Select mode: no highlight any more
    assert len(_annots(window)) == n


def test_free_area_stroke_creates_ink_highlight_with_marker_appearance(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 520, 745))
    inks = _annots(window, "Ink")
    assert len(inks) == 1 and not _annots(window, "Highlight")
    a = inks[0]
    assert a.opacity == pytest.approx(0.4, abs=0.01)
    assert a.border["width"] == pytest.approx(MARKER_W)
    assert a.info.get("subject") == "Free-area highlight"
    assert tuple(round(c, 2) for c in a.colors["stroke"]) == (1.0, 1.0, 0.0)
    pix = window._document._backend._doc[0].get_pixmap(dpi=72, alpha=False)  # noqa: SLF001
    r, g, b = pix.pixel(450, 745)
    assert r > 240 and g > 240 and b < 200, "translucent yellow expected over white"


def test_free_highlight_over_dark_background_keeps_content_visible(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(330, 520, 590))  # over "White text on dark"
    pix = window._document._backend._doc[0].get_pixmap(dpi=72, alpha=False)  # noqa: SLF001
    assert sum(pix.pixel(420, 588)) < 300, "multiply blend must not wash out the dark field"


def test_text_stroke_uses_quadpoints_not_ink(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(75, 300, TEXT_Y - 4))
    hl = _annots(window, "Highlight")
    assert len(hl) == 1 and not _annots(window, "Ink")
    assert hl[0].vertices and len(hl[0].vertices) % 4 == 0


def test_mixed_stroke_makes_text_and_free_parts_and_one_undo_step(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    # across a text line, then straight down through blank margin to the empty bottom-right area
    pts = _line(75, 300, TEXT_Y - 4) + [(300, y) for y in range(130, 330, 12)] + [(300 + i * 10, 740) for i in range(0, 20)]
    _drag(window, qtbot, 0, [(x, y) for x, y in pts])
    assert _annots(window, "Highlight") and _annots(window, "Ink")
    before = len(_annots(window))
    assert window._edit.undo()  # noqa: SLF001
    assert len(_annots(window)) == before - 2, "one stroke must undo as one step (text part + free part)"
    assert window._edit.redo()  # noqa: SLF001
    assert len(_annots(window)) == before


def test_each_stroke_is_its_own_undo_step(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    _drag(window, qtbot, 0, _line(380, 500, 770))
    assert len(_annots(window)) == 2
    assert window._edit.undo()  # noqa: SLF001
    assert len(_annots(window)) == 1
    assert window._edit.undo()  # noqa: SLF001
    assert not _annots(window)
    assert window._edit.redo() and window._edit.redo()  # noqa: SLF001
    assert len(_annots(window)) == 2
    assert window._canvas.region_pick_active  # mode survives undo/redo  # noqa: SLF001


def test_click_without_drag_creates_nothing_and_mode_continues(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, [(450, 745)])
    assert not _annots(window)
    assert window._canvas.region_pick_active  # noqa: SLF001


def test_switching_tool_or_closing_document_ends_mode(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    window.act_text_tool.trigger()
    assert not window._canvas.region_pick_active  # noqa: SLF001
    window.act_annot_highlight.trigger()
    assert window._canvas.region_pick_active  # noqa: SLF001
    window.close_document(save_session=False)
    assert not window._canvas.region_pick_active  # noqa: SLF001
    assert window._markup_sticky is None  # noqa: SLF001


def test_color_change_applies_to_next_stroke_while_mode_active(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    window._set_highlight_color("#90ee90")  # noqa: SLF001
    qtbot.wait(40)
    assert window._canvas.region_pick_active  # noqa: SLF001
    _drag(window, qtbot, 0, _line(380, 500, 770))
    cols = [tuple(round(c * 255) for c in a.colors["stroke"]) for a in _annots(window, "Ink")]
    assert cols[0] == (255, 255, 0) and cols[1] == (144, 238, 144)


def test_cursor_is_custom_marker_while_active(window, qtbot, tmp_path):
    from PySide6.QtCore import Qt

    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    inner = window._canvas._canvas  # noqa: SLF001
    assert inner.cursor().shape() == Qt.CursorShape.BitmapCursor
    assert "Highlight mode" in window.statusBar().currentMessage()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_free_highlight_lands_under_the_pen_on_rotated_pages(window, qtbot, tmp_path, rotation):
    _open(window, tmp_path, rotation=rotation)
    page = window._document.page(0)  # noqa: SLF001
    # a display-space stroke over empty space: use the page centre-right area (blank on every rotation test below)
    dw, dh = page.display_width_pt, page.display_height_pt
    # pick display points that map to the blank bottom-right of the unrotated page
    import fitz as _f

    pg = window._document._backend._doc[0]  # noqa: SLF001
    p_a = _f.Point(380, 745) * pg.rotation_matrix
    p_b = _f.Point(500, 745) * pg.rotation_matrix
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, [(p_a.x + (p_b.x - p_a.x) * i / 10, p_a.y + (p_b.y - p_a.y) * i / 10) for i in range(11)])
    inks = _annots(window, "Ink")
    assert len(inks) == 1, (rotation, dw, dh)
    r = inks[0].rect
    assert abs((r.x0 + r.x1) / 2 - 440) < 8 and abs((r.y0 + r.y1) / 2 - 745) < 8
    pix = pg.get_pixmap(dpi=72, alpha=False)
    mid = _f.Point(440, 745) * pg.rotation_matrix
    r_, g_, b_ = pix.pixel(int(mid.x), int(mid.y))
    assert b_ < 200 and r_ > 240


def test_save_and_reopen_preserves_highlights_and_rotation(window, qtbot, tmp_path):
    dst = _open(window, tmp_path, rotation=90)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(300, 400, 60))
    n = len(_annots(window))
    assert n >= 1
    _esc(window, qtbot)
    window.save_document()
    assert not window._edit.dirty  # noqa: SLF001
    d = fitz.open(dst.as_posix())
    try:
        assert d[0].rotation == 90
        assert len(list(d[0].annots())) == n
    finally:
        d.close()


def test_core_classify_stroke_blank_page_is_all_free(tmp_path):
    from core.annotations import classify_stroke
    from core.document import open_document
    from core.editing.geometry import Point

    src = tmp_path / "blank.pdf"
    d = fitz.open()
    d.new_page(width=300, height=300)
    d.save(src.as_posix())
    d.close()
    doc = open_document(src)
    rects, runs = classify_stroke(doc, 0, [Point(20, 20), Point(200, 20)])
    assert rects == [] and len(runs) == 1
    assert classify_stroke(doc, 0, [Point(20, 20), Point(21, 20)]) == ([], [])  # too short
    doc.close()


def test_cropbox_page_highlight_stays_inside_visible_area(window, qtbot, tmp_path):
    _open(window, tmp_path, src=CROP)
    window.act_annot_highlight.trigger()
    page = window._document.page(0)  # noqa: SLF001
    _drag(window, qtbot, 0, _line(30, page.display_width_pt - 30, page.display_height_pt / 2 + 100))
    inks = _annots(window, "Ink")
    assert len(inks) == 1
    pg = window._document._backend._doc[0]  # noqa: SLF001
    r = inks[0].rect
    assert pg.rect.width == pytest.approx(512, abs=1)  # PyMuPDF page space starts at the CropBox corner
    assert r.x0 >= -20 and r.x1 <= pg.rect.x1 + 20
    pix = pg.get_pixmap(dpi=72, alpha=False)
    cy = int((r.y0 + r.y1) / 2)
    assert pix.pixel(int((r.x0 + r.x1) / 2), cy)[2] < 230, "ink must render inside the visible CropBox area"


def test_scanned_page_and_image_and_table_get_free_highlights(window, qtbot, tmp_path):
    _open(window, tmp_path, src=TEMPLATES / "pdf" / "scanned_memo_300dpi.pdf")
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(80, 400, 280))  # over the scanned text (no text layer)
    assert len(_annots(window, "Ink")) == 1 and not _annots(window, "Highlight")
    _esc(window, qtbot)
    _open(window, tmp_path, name="second.pdf")
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(80, 280, 360))   # over the picture
    _drag(window, qtbot, 0, _line(330, 520, 340))  # over the table
    assert len(_annots(window, "Ink")) == 2
