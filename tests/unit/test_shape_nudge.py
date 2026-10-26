"""Keyboard nudge must move shapes, images, and form fields — not only text boxes."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.forms.fields import FieldType, FormField


def _blank_edit(tmp_path: Path) -> EditableDocument:
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(src)
    doc.close()
    return EditableDocument(open_document(src))


def test_nudge_moves_rectangle_shape(tmp_path: Path):
    edit = _blank_edit(tmp_path)
    shape = edit.create_shape(0, Rect(100, 200, 80, 40), "rectangle")
    before = Rect(*shape.rect.as_tuple())
    edit.select([shape.object_id])
    edit.nudge_selection(5, -3)
    assert shape.rect.x == pytest.approx(before.x + 5)
    assert shape.rect.y == pytest.approx(before.y - 3)
    assert shape.rect.w == pytest.approx(before.w)
    assert shape.rect.h == pytest.approx(before.h)
    edit.undo()
    assert shape.rect.as_tuple() == before.as_tuple()
    edit.redo()
    assert shape.rect.x == pytest.approx(before.x + 5)


def test_nudge_moves_ellipse_and_line(tmp_path: Path):
    edit = _blank_edit(tmp_path)
    ellipse = edit.create_shape(0, Rect(50, 50, 60, 40), "ellipse")
    line = edit.create_shape(0, Rect(200, 200, 100, 0), "line")
    edit.select([ellipse.object_id, line.object_id])
    ex, ey = ellipse.rect.x, ellipse.rect.y
    lx0, ly0 = line.x0, line.y0
    edit.nudge_selection(10, 4)
    assert ellipse.rect.x == pytest.approx(ex + 10)
    assert ellipse.rect.y == pytest.approx(ey + 4)
    assert line.x0 == pytest.approx(lx0 + 10)
    assert line.y0 == pytest.approx(ly0 + 4)


def test_nudge_moves_form_field(tmp_path: Path):
    edit = _blank_edit(tmp_path)
    field = FormField(
        page_index=0,
        rect=Rect(72, 72, 120, 24),
        field_type=FieldType.TEXT,
        name="name",
        is_acroform=False,
    )
    edit.add_form_field(field)
    edit.field_selection = [field.object_id]
    edit.selection = []
    edit.nudge_selection(0, 12)
    assert field.rect.y == pytest.approx(84.0)
    assert field.appearance_dirty


def test_nudge_clamped_to_page(tmp_path: Path):
    edit = _blank_edit(tmp_path)
    page = edit.pdf.page(0)
    shape = edit.create_shape(0, Rect(page.display_width_pt - 50, 10, 40, 30), "rectangle")
    edit.select([shape.object_id])
    edit.nudge_selection(100, 0)
    assert shape.rect.x1 == pytest.approx(page.display_width_pt)
