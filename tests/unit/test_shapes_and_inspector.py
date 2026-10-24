"""Shapes overlays, constraints, autofit, inspector context switching."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.editing.edit_model import EditableDocument, EditTool
from core.editing.geometry import Point, Rect
from core.editing.shape_box import ShapeKind, constrain_line_angle, constrain_rect_aspect
from core.forms.autofit import effective_form_font_size
from core.forms.fields import FieldType, FormField
from core.document import open_document

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "outputs" / "generated" / "shapes"
SAMPLES = ROOT / "tests" / "samples"


def _letter_sample(tmp_path: Path | None = None) -> Path:
    """Prefer a normal page PDF; never the tiny OCR fixtures that sort first as ``*.pdf``."""
    for name in ("sample_plain.pdf", "sample_invitation_form.pdf", "sample_image_page.pdf"):
        cand = SAMPLES / name
        if cand.is_file():
            return cand
    if tmp_path is None:
        tmp_path = OUT
    tmp_path.mkdir(parents=True, exist_ok=True)
    blank = tmp_path / "letter_blank.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(blank)
    doc.close()
    return blank


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_samples import main as base

    base()
    OUT.mkdir(parents=True, exist_ok=True)


def test_square_and_circle_constraints():
    r = constrain_rect_aspect(Point(10, 10), Point(60, 30), square=True)
    assert abs(r.w - r.h) < 1e-6
    end = constrain_line_angle(Point(0, 0), Point(10, 1), snap=True)
    assert abs(end.y) < 1e-6 or abs(abs(end.x) - abs(end.y)) < 1e-6 or abs(end.x) < 1e-6


def test_create_shapes_and_bake(tmp_path: Path):
    src = _letter_sample(tmp_path)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    rect = edit.create_shape(0, Rect(72, 72, 120, 60), "rectangle")
    assert rect.kind == ShapeKind.RECTANGLE
    ell = edit.create_shape(0, Rect(72, 160, 80, 80), "ellipse", lock_aspect=True)
    assert ell.lock_aspect
    line = edit.create_shape(
        0, Rect(72, 260, 100, 10), "line", x0=72, y0=260, x1=172, y1=260
    )
    assert line.kind == ShapeKind.LINE
    arrow = edit.create_shape(
        0, Rect(72, 280, 100, 20), "arrow", x0=72, y0=290, x1=172, y1=300
    )
    assert arrow.kind == ShapeKind.ARROW
    out = tmp_path / "shapes_baked.pdf"
    from engines.bake_edits import bake_via_backend

    bake_via_backend(edit, out)
    assert out.is_file() and out.stat().st_size > 100
    doc = fitz.open(out)
    try:
        assert doc.page_count >= 1
    finally:
        doc.close()
    pdf.close()


def test_shape_move_one_undo(tmp_path: Path):
    # Use a letter-size page. ``tests/samples/*.pdf`` starts with tiny OCR fixtures whose
    # width (~92 pt) clamps a (10, 5) move via keep-on-page.
    blank = tmp_path / "letter.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(blank)
    doc.close()
    pdf = open_document(blank)
    edit = EditableDocument(pdf)
    s = edit.create_shape(0, Rect(50, 50, 40, 40), "rectangle")
    before = edit.begin_transform_snapshot()
    edit.live_translate([s.object_id], 10, 5, snap=False, notify=False)
    edit.commit_transform(before, name="Move")
    assert abs(s.rect.x - 60) < 0.1
    edit.undo()
    assert abs(s.rect.x - 50) < 0.1
    edit.redo()
    assert abs(s.rect.x - 60) < 0.1
    pdf.close()


def test_form_auto_font_size_preserved():
    field = FormField(
        page_index=0,
        rect=Rect(0, 0, 120, 18),
        field_type=FieldType.TEXT,
        name="a",
        value="Hi",
        font_size=0.0,
        is_acroform=True,
    )
    assert field.font_size == 0.0
    short = effective_form_font_size(field, "Hi")
    long = effective_form_font_size(field, "A" * 80)
    assert short >= long
    assert long >= 6.0


def test_inspector_context_switch(qtbot):
    from ui.inspector_panel import InspectorPanel
    from ui.main_window import MainWindow, create_application
    from core.editing.text_box import TextBox

    create_application(["pdf-inspector"])
    window = MainWindow()
    qtbot.addWidget(window)
    src = _letter_sample(OUT)
    assert window.open_path(src)
    edit = window._edit  # noqa: SLF001
    insp: InspectorPanel = window._inspector  # noqa: SLF001

    box = edit.create_text_box(0, Rect(40, 40, 120, 36), text="Hello")
    window._refresh_inspector()
    assert insp._box is not None and insp._box.object_id == box.object_id

    shape = edit.create_shape(0, Rect(40, 100, 80, 40), "rectangle")
    window._refresh_inspector()
    assert insp._shape is not None and insp._shape.object_id == shape.object_id

    # Field context if any
    if edit.fields:
        fid = next(iter(edit.fields))
        edit.begin_field_edit(fid)
        window._refresh_inspector()
        assert insp._field is not None

    # Blank → document
    edit.clear_selection()
    edit.field_selection = []
    edit.editing_field_id = None
    window._refresh_inspector()
    assert insp._box is None and insp._shape is None

    # Shape tool parity
    window._set_tool(EditTool.SHAPE_RECT)
    assert edit.tool == EditTool.SHAPE_RECT
    window.close_document(save_session=False)
    window.close()


def test_font_cache_fast():
    from core.editing.font_cache import cached_font_families

    a = cached_font_families()
    b = cached_font_families()
    assert a is b  # lru identity
    import sys

    if sys.platform == "win32":  # other systems' test containers may have only the bundled fonts
        assert len(a) > 10
