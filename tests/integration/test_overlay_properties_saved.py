"""Properties set in the Properties panel reach the saved PDF (they were shown on screen but dropped
at Save before 0.3.0): text-box opacity, letter spacing and rotation; shape opacity, rotation and
dash style."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document import open_document  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from engines.bake_edits import bake_via_backend  # noqa: E402


@pytest.fixture()
def blank(tmp_path: Path) -> Path:
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(src)
    doc.close()
    return src


def _bake(src: Path, tmp_path: Path, setup) -> fitz.Page:
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    setup(edit)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    return fitz.open(out)[0]


def _chars(page: fitz.Page) -> list[tuple[str, fitz.Rect, tuple]]:
    out = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for ch in span["chars"]:
                    out.append((ch["c"], fitz.Rect(ch["bbox"]), tuple(line["dir"])))
    return out


def test_text_box_letter_spacing_is_saved(blank, tmp_path):
    def make(spacing):
        def setup(edit):
            box = edit.create_text_box(0, Rect(72, 72, 300, 40), text="ABCD")
            box.style.character_spacing = spacing
        chars = [c for c in _chars(_bake(blank, tmp_path, setup)) if c[0] in "ABCD"]
        return chars[3][1].x0 - chars[0][1].x0

    assert make(6.0) == pytest.approx(make(0.0) + 18.0, abs=0.6)  # 3 gaps x 6 pt


def test_text_box_opacity_is_saved(blank, tmp_path):
    def setup(edit):
        box = edit.create_text_box(0, Rect(72, 72, 200, 40), text="Half")
        box.style.opacity = 0.5
    page = _bake(blank, tmp_path, setup)
    doc = page.parent
    states = [doc.xref_object(x) for x in range(1, doc.xref_length()) if "/ca" in (doc.xref_object(x) or "")]
    assert any("/ca .5" in s or "/ca 0.5" in s for s in states), states
    assert "Half" in page.get_text()


@pytest.mark.parametrize("angle,direction", [(90, (0.0, 1.0)), (270, (0.0, -1.0)), (180, (-1.0, 0.0))])
def test_text_box_rotation_is_saved_clockwise_about_the_centre(blank, tmp_path, angle, direction):
    def setup(edit):
        box = edit.create_text_box(0, Rect(150, 300, 200, 40), text="Turned")
        box.style.rotation = float(angle)
    page = _bake(blank, tmp_path, setup)
    chars = [c for c in _chars(page) if c[0].strip()]
    assert chars and all(tuple(round(v, 3) for v in c[2]) == direction for c in chars)
    # the turned text stays inside the turned outline of the box (centre 250, 320)
    union = fitz.Rect(chars[0][1])
    for c in chars[1:]:
        union |= c[1]
    assert abs((union.x0 + union.x1) / 2 - 250) < 110 and abs((union.y0 + union.y1) / 2 - 320) < 110
    assert union.intersects(fitz.Rect(150, 220, 350, 420))


def test_shape_opacity_and_dashes_are_saved(blank, tmp_path):
    def setup(edit):
        shape = edit.create_shape(0, Rect(100, 100, 120, 80), "rectangle")
        shape.stroke_color, shape.fill_color = "#ff0000", "#0000ff"
        shape.opacity, shape.fill_opacity = 0.5, 0.5
        from core.editing.shape_box import StrokeStyle
        shape.stroke_style = StrokeStyle.DASHED
    page = _bake(blank, tmp_path, setup)
    (d,) = [d for d in page.get_drawings() if d.get("fill")]
    assert d["stroke_opacity"] == pytest.approx(0.5, abs=0.01)
    assert d["fill_opacity"] == pytest.approx(0.25, abs=0.01)
    # the dash pattern is in proportion to the line width, the same as on screen (shape_box.dash_pattern)
    from core.editing.shape_box import dash_pattern

    on, off = dash_pattern("dashed", 1.5)
    nums = [float(v) for v in str(d.get("dashes")).strip("[] 0").replace("]", " ").split()]
    assert nums[:2] == pytest.approx([on, off], abs=0.02)


def test_shape_rotation_is_saved_clockwise(blank, tmp_path):
    def setup(edit):
        shape = edit.create_shape(0, Rect(100, 200, 200, 0), "arrow")
        shape.x0, shape.y0, shape.x1, shape.y1 = 100, 200, 300, 200  # pointing right
        shape.sync_rect_from_line()
        shape.rotation = 90.0
    page = _bake(blank, tmp_path, setup)
    pts = [p for d in page.get_drawings() for item in d["items"] for p in item[1:] if isinstance(p, fitz.Point)]
    assert pts
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    assert max(xs) - min(xs) < 20  # now vertical
    assert max(ys) - min(ys) > 190
    # the arrow head (where several lines meet) is at the bottom: turned clockwise
    tip = max(set((round(p.x), round(p.y)) for p in pts), key=lambda q: sum(1 for p in pts if (round(p.x), round(p.y)) == q))
    assert tip[1] > 290
