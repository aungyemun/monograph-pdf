"""Eraser and highlighter: the same marks as before, found quickly (the eraser used to read every
annotation of the page again for every 1.5 pt of the stroke: over a second for a long stroke)."""

from __future__ import annotations

import time

import fitz
import pytest

from core.editing.geometry import Point


@pytest.fixture
def doc(tmp_path):
    from core.document import open_document

    d = fitz.open()
    p = d.new_page()
    for i in range(55):
        p.insert_text((40, 40 + i * 14), ("Lorem ipsum dolor sit amet consectetur adipiscing elit " * 2)[:95], fontsize=10)
    path = tmp_path / "t.pdf"
    d.save(path)
    d.close()
    document = open_document(path)
    page = document._backend._doc[0]  # noqa: SLF001
    for i in range(0, 55, 2):
        page.add_highlight_annot(fitz.Rect(40, 31 + i * 14, 400, 42 + i * 14))
    for i in range(10):
        a = page.add_ink_annot([[(50 + i * 30, 100), (60 + i * 30, 600)]])
        a.update()
    yield document
    document.close()


def test_eraser_finds_every_touched_mark_fast(doc):
    from core.annotations.ops import annotations_along, annotations_at

    pts = [Point(45 + k * 1.2, 100 + k * 1.0) for k in range(400)]
    t = time.perf_counter()
    hits = annotations_along(doc, 0, pts, radius_pt=5.0)
    elapsed = time.perf_counter() - t
    assert elapsed < 0.4, f"eraser stroke took {elapsed:.2f} s"
    # the same marks as testing every sample point one by one
    slow = set()
    for p in pts:
        slow.update(h["xref"] for h in annotations_at(doc, 0, p, tolerance_pt=10.0))
    assert slow <= {h["xref"] for h in hits}
    # a single click: only what is under it
    one = annotations_along(doc, 0, [Point(200, 37)], radius_pt=1.0)
    assert len(one) == 1 and one[0]["kind"] == "Highlight"
    assert annotations_along(doc, 0, [Point(560, 790)], radius_pt=5.0) == []


def test_highlight_stroke_marks_only_the_line_drawn_over_and_reuses_the_text(doc):
    from core.annotations.ops import classify_stroke

    stroke = [Point(40 + k * 0.8, 120) for k in range(200)]
    rects, runs = classify_stroke(doc, 0, stroke)
    assert len(rects) == 1 and not runs
    r = rects[0]
    assert r.y <= 120 <= r.y + r.h and 150 < r.x + r.w < 205, r  # from the start to where the pen stopped
    t = time.perf_counter()
    for _ in range(5):
        classify_stroke(doc, 0, stroke)
    assert (time.perf_counter() - t) / 5 < 0.05, "the page's text is extracted once, not for every stroke"
