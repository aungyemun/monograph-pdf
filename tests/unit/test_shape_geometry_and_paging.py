"""Line ends (arrow heads), dash patterns, lines keeping their direction, smooth freehand strokes,
pages analysed only when needed, and search finding full-/half-width forms and form-field values."""

from __future__ import annotations

import math

import fitz
import pytest

from core.editing.geometry import Rect
from core.editing.shape_box import (
    HEAD_STYLES,
    ShapeBox,
    ShapeKind,
    dash_pattern,
    head_length,
    line_geometry,
)


@pytest.mark.parametrize("style", [v for v, _ in HEAD_STYLES if v != "none"])
def test_every_head_sits_on_the_line_end_and_points_along_it(style):
    a, b, marks = line_geometry(0, 0, 100, 0, width=2.0, end=style)
    assert len(marks) == 1 and marks[0][0] == style
    pts = marks[0][1]
    if style == "circle":
        assert pts[0] == pytest.approx((100, 0))
    else:
        xs = [x for x, _y in pts]
        slack = 2.0 if style == "bar" else 1e-6  # a bar is centred on the end, half its thickness past it
        assert max(xs) <= 100 + slack and min(xs) >= 100 - head_length(2.0) - 2.5  # behind the tip
        assert any(abs(y) > 1 for _x, y in pts) or style == "bar"  # it has width across the line
    assert a == pytest.approx((0, 0))
    assert b[0] <= 100 + 1e-6  # a filled head shortens the line so it does not poke through the tip


def test_heads_follow_the_direction_and_scale_with_the_line():
    _a, _b, marks = line_geometry(100, 100, 100, 0, width=1.0, end="filled")  # pointing up
    tip = marks[0][1][0]
    assert tip == pytest.approx((100, 0))
    assert all(y >= -1e-6 for _x, y in marks[0][1])  # the head lies below the tip (towards the line)
    assert head_length(4.0) > head_length(1.0)
    assert head_length(1.0, 20.0) == 20.0  # a chosen size wins
    _a, _b, both = line_geometry(0, 0, 50, 0, width=1.0, start="open", end="stealth")
    assert {m[0] for m in both} == {"open", "stealth"}


def test_dash_patterns_scale_with_width_and_solid_has_none():
    assert dash_pattern("solid", 2) is None
    assert dash_pattern("dashed", 2) == pytest.approx([2 * v for v in dash_pattern("dashed", 1)])
    assert len(dash_pattern("dash_dot", 1)) == 4
    assert dash_pattern("long_dash", 1)[0] > dash_pattern("dashed", 1)[0]


@pytest.mark.parametrize("ends", [(100, 300, 200, 150), (300, 100, 100, 100), (50, 50, 50, 250)])
def test_moving_or_resizing_a_line_keeps_its_direction(ends):
    x0, y0, x1, y1 = ends
    s = ShapeBox(page_index=0, rect=Rect(0, 0, 1, 1), kind=ShapeKind.ARROW, x0=x0, y0=y0, x1=x1, y1=y1)
    s.sync_rect_from_line()
    r = s.rect
    s.fit_to_rect(Rect(r.x + 10, r.y - 5, r.w, r.h))  # a move (or its undo)
    assert (s.x0, s.y0, s.x1, s.y1) == pytest.approx((x0 + 10, y0 - 5, x1 + 10, y1 - 5))
    before = math.atan2(y1 - y0, x1 - x0)
    s.fit_to_rect(Rect(s.rect.x, s.rect.y, s.rect.w * 2, s.rect.h * 2))  # a resize
    after = math.atan2(s.y1 - s.y0, s.x1 - s.x0)
    assert math.copysign(1, math.cos(after)) == math.copysign(1, math.cos(before)) or abs(math.cos(before)) < 1e-9
    assert math.copysign(1, math.sin(after)) == math.copysign(1, math.sin(before)) or abs(math.sin(before)) < 1e-9


def test_old_arrows_keep_their_open_head_new_ones_are_filled():
    old = ShapeBox.from_dict({"kind": "arrow", "rect": [0, 0, 10, 10]})
    assert old.heads() == ("none", "open")
    new = ShapeBox(page_index=0, rect=Rect(0, 0, 1, 1), kind=ShapeKind.ARROW)
    assert new.heads() == ("none", "filled")
    again = ShapeBox.from_dict(new.to_dict())
    assert (again.start_head, again.end_head, again.head_size) == (new.start_head, new.end_head, new.head_size)


def test_freehand_points_scale_with_the_box():
    s = ShapeBox(page_index=0, rect=Rect(0, 0, 100, 100), kind=ShapeKind.FREEHAND, points=[(0, 0), (100, 50), (50, 100)])
    s.fit_to_rect(Rect(10, 10, 50, 200))
    assert s.points == pytest.approx([(10, 10), (60, 110), (35, 210)])


def test_freehand_jitter_is_removed_and_curves_pass_the_ends():
    from core.editing.freehand import simplify, smooth_segments

    straight = [(x, 100 + (0.2 if x % 2 else -0.2)) for x in range(0, 200, 2)]
    assert len(simplify(straight, 0.5)) == 2  # a wobbly straight stroke becomes a straight line
    wave = [(x, 100 + 30 * math.sin(x / 20)) for x in range(0, 200, 2)]
    kept = simplify(wave, 0.5)
    assert 6 < len(kept) < len(wave)  # the shape is kept with far fewer points
    segs = smooth_segments(kept)
    assert segs[0][0] == pytest.approx(kept[0]) and segs[-1][3] == pytest.approx(kept[-1])
    assert all(segs[i][3] == pytest.approx(segs[i + 1][0]) for i in range(len(segs) - 1))  # continuous


def _doc(tmp_path, pages=3):
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"Page {i + 1} 2026-0417 (50%) $12.50 #tag", fontsize=12)
    path = tmp_path / "doc.pdf"
    d.save(path)
    d.close()
    return path


def test_opening_reads_page_sizes_only_content_on_demand(tmp_path):
    from core.document import open_document

    doc = open_document(_doc(tmp_path))
    try:
        pages = doc.pages()
        assert not any(p.content_analyzed for p in pages), "opening must not extract every page's text"
        assert pages[1].width_pt == pytest.approx(595, abs=1)
        assert pages[1].has_text and pages[1].char_count > 10 and pages[1].content_analyzed
        assert not pages[2].content_analyzed
    finally:
        doc.close()


def test_search_finds_words_numbers_symbols_and_width_variants(tmp_path):
    from core.document import open_document
    from engines.mupdf_backend import search_variants

    doc = open_document(_doc(tmp_path))
    try:
        for q in ("page 2", "2026-0417", "(50%)", "$12.50", "#tag", "２０２６"):
            assert doc.search(q), q
        assert len(doc.search("Page")) == 3
        assert search_variants("2月") == ["2月", "２月"]
        assert search_variants("ＡＢＣ")[:2] == ["ＡＢＣ", "ABC"]
    finally:
        doc.close()


def test_search_finds_text_typed_into_form_fields(tmp_path):
    from core.document import open_document

    d = fitz.open()
    page = d.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "plan"
    w.rect = fitz.Rect(72, 100, 300, 130)
    w.field_value = "Visit Miyazaki"
    page.add_widget(w)
    path = tmp_path / "form.pdf"
    d.save(path)
    d.close()
    doc = open_document(path)
    try:
        hits = doc.search("miyazaki")
        assert hits and hits[0][0] == 0
        assert doc.search_page(0, "Miyazaki")
    finally:
        doc.close()


def test_an_arrow_can_have_no_heads_and_old_unpadded_lines_move_exactly():
    s = ShapeBox(page_index=0, rect=Rect(0, 0, 1, 1), kind=ShapeKind.ARROW, start_head="none", end_head="none")
    assert s.heads() == ("none", "none")
    assert ShapeBox.from_dict(s.to_dict()).heads() == ("none", "none")
    old = ShapeBox(page_index=0, rect=Rect(100, 100, 100, 50), kind=ShapeKind.LINE, x0=100, y0=100, x1=200, y1=150)
    old.fit_to_rect(Rect(110, 100, 100, 50))  # a box exactly around the ends (saved by earlier versions)
    assert (old.x0, old.y0, old.x1, old.y1) == pytest.approx((110, 100, 210, 150))


def test_page_info_can_be_copied_and_pickled(tmp_path):
    import copy
    import pickle

    from core.document import open_document

    doc = open_document(_doc(tmp_path, pages=1))
    try:
        p = doc.pages()[0]
        assert copy.deepcopy(p) is p
        q = pickle.loads(pickle.dumps(p))
        assert q == p and q.char_count == p.char_count
    finally:
        doc.close()
