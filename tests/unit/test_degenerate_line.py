"""Zero-length lines are never created or saved (0.5.1); short real lines are."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.shape_box import ShapeBox, ShapeKind, is_degenerate_line
from engines.bake_edits import bake_via_backend


def _blank(path: Path) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


def _lines(path: Path):
    with fitz.open(path) as doc:
        return [d for d in doc[0].get_drawings() if any(i[0] == "l" for i in d["items"])]


def test_is_degenerate_line():
    s = ShapeBox(page_index=0, rect=Rect(0, 0, 0, 0), kind=ShapeKind.LINE)
    s.x0 = s.x1 = 50.0
    s.y0 = s.y1 = 60.0
    assert is_degenerate_line(s)
    s.x1 = 50.5
    assert not is_degenerate_line(s)


def test_create_shape_refuses_a_zero_length_line_and_arrow(tmp_path):
    pdf = open_document(_blank(tmp_path / "a.pdf"))
    try:
        edit = EditableDocument(pdf)
        for kind in ("line", "arrow"):
            assert edit.create_shape(0, Rect(50, 60, 0, 0), kind, x0=50, y0=60, x1=50, y1=60) is None
        assert not edit.shapes
        assert not edit.commands.can_undo_now
        short = edit.create_shape(0, Rect(50, 60, 1, 0), "line", x0=50, y0=60, x1=51, y1=60)
        assert short is not None and len(edit.shapes) == 1
    finally:
        pdf.close()


def test_save_skips_a_zero_length_line_already_in_a_session(tmp_path):
    """A recovered editing session from 0.5.0 may still hold one: it is not written."""
    src = _blank(tmp_path / "b.pdf")
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        real = edit.create_shape(0, Rect(100, 100, 2, 0), "line", x0=100, y0=100, x1=102, y1=100)
        dot = ShapeBox(page_index=0, rect=Rect(300, 300, 0, 0), kind=ShapeKind.LINE)
        dot.x0 = dot.x1 = 300.0
        dot.y0 = dot.y1 = 300.0
        edit.shapes[dot.object_id] = dot  # as restored from an old session
        out = tmp_path / "out.pdf"
        bake_via_backend(edit, out, flatten=False)
    finally:
        pdf.close()
    lines = _lines(out)
    assert len(lines) == 1  # the 2-point line only
    assert lines[0]["rect"].x0 < 110 and real is not None
