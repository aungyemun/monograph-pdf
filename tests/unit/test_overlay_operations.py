"""Duplicate, copy/paste, stacking order, aspect-ratio lock and undoable property changes work for
shapes and pictures as well as text boxes (0.3.0); shapes survive the recovery session."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document import open_document  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from core.editing.image_box import ImageBox  # noqa: E402


@pytest.fixture()
def edit(tmp_path: Path):
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(src)
    doc.close()
    pdf = open_document(src)
    model = EditableDocument(pdf)
    yield model
    pdf.close()


def _png(tmp_path: Path) -> Path:
    from PIL import Image

    p = tmp_path / "pic.png"
    Image.new("RGB", (200, 100), (200, 30, 30)).save(p)
    return p


def _image(edit, tmp_path, rect=Rect(100, 100, 200, 100)):
    img = ImageBox(page_index=0, rect=rect, source_path=str(_png(tmp_path)))
    edit.add_image(img)
    return img


def test_duplicate_shapes_lines_and_pictures_with_undo_redo(edit, tmp_path):
    rect = edit.create_shape(0, Rect(50, 50, 80, 40), "rectangle")
    line = edit.create_shape(0, Rect(10, 10, 100, 0), "line", x0=10, y0=10, x1=110, y1=10)
    free = edit.create_shape(0, Rect(0, 0, 1, 1), "freehand", points=[(5, 5), (20, 25)])
    img = _image(edit, tmp_path)
    edit.select([rect.object_id, line.object_id, free.object_id, img.object_id])
    edit.duplicate_selection()
    assert len(edit.shapes) == 6 and len(edit.images) == 2
    dups = [edit.overlay(i)[1] for i in edit.selection]
    assert len(dups) == 4
    dline = next(d for d in dups if getattr(getattr(d, "kind", None), "value", "") == "line")
    assert (dline.x0, dline.y0, dline.x1, dline.y1) == (22, 22, 122, 22)
    dfree = next(d for d in dups if getattr(getattr(d, "kind", None), "value", "") == "freehand")
    assert dfree.points == [(17, 17), (32, 37)]
    edit.undo()
    assert len(edit.shapes) == 3 and len(edit.images) == 1
    edit.redo()
    assert len(edit.shapes) == 6 and len(edit.images) == 2


def test_copy_and_paste_shapes_and_pictures(edit, tmp_path):
    shape = edit.create_shape(0, Rect(50, 50, 80, 40), "ellipse")
    img = _image(edit, tmp_path)
    box = edit.create_text_box(0, Rect(300, 300, 100, 30), text="T")
    edit.select([shape.object_id, img.object_id, box.object_id])
    payload = edit.clipboard_copy()
    edit.clipboard_paste(payload, page_index=1)
    assert len(edit.shapes) == 2 and len(edit.images) == 2 and len(edit.objects) == 2
    assert {edit.overlay(i)[1].page_index for i in edit.selection} == {1}
    # older clipboards held text boxes only (plain dictionaries) and still paste
    edit.clipboard_paste([box.to_dict()])
    assert len(edit.objects) == 3


def test_stacking_order_is_shared_by_text_pictures_and_shapes(edit, tmp_path):
    box = edit.create_text_box(0, Rect(100, 100, 100, 40), text="T")
    img = _image(edit, tmp_path)
    shape = edit.create_shape(0, Rect(100, 100, 80, 40), "rectangle")
    order = lambda: [o.object_id for o in edit.overlays_on_page(0)]  # noqa: E731
    assert order() == [box.object_id, img.object_id, shape.object_id]
    edit.select([shape.object_id])
    edit.layer_selection("back")
    assert order() == [shape.object_id, box.object_id, img.object_id]
    edit.select([box.object_id])
    edit.layer_selection("forward")
    assert order() == [shape.object_id, img.object_id, box.object_id]
    edit.undo()
    assert order() == [shape.object_id, box.object_id, img.object_id]
    edit.undo()
    assert order() == [box.object_id, img.object_id, shape.object_id]
    # the topmost object is the one hit
    assert edit.hit_test(0, _pt(120, 110)) == shape.object_id  # the topmost object is hit


def _pt(x, y):
    from core.editing.geometry import Point

    return Point(x, y)


def test_saved_drawing_order_follows_the_stacking_order(edit, tmp_path):
    from engines.bake_edits import overlays_in_order

    box = edit.create_text_box(0, Rect(100, 100, 100, 40), text="T")
    shape = edit.create_shape(0, Rect(100, 100, 80, 40), "rectangle")
    edit.select([shape.object_id])
    edit.layer_selection("back")
    assert [o.object_id for _k, o in overlays_in_order(edit)] == [shape.object_id, box.object_id]


def test_picture_aspect_ratio_lock(edit, tmp_path):
    img = _image(edit, tmp_path)  # 200 x 100, locked by default
    edit.live_resize(img.object_id, Rect(100, 100, 300, 100))  # drag the right edge
    assert (img.rect.w, img.rect.h) == (300, 150)
    edit.live_resize(img.object_id, Rect(50, 100, 350, 150))  # drag the left edge: right edge stays
    assert img.rect.x1 == pytest.approx(400) and img.rect.w / img.rect.h == pytest.approx(2.0)
    img.lock_aspect = False
    edit.live_resize(img.object_id, Rect(0, 0, 100, 100))
    assert (img.rect.w, img.rect.h) == (100, 100)


def test_shape_aspect_lock_keeps_the_ratio_not_a_square(edit):
    shape = edit.create_shape(0, Rect(0, 0, 120, 60), "rectangle")
    shape.lock_aspect = True
    edit.live_resize(shape.object_id, Rect(0, 0, 240, 60))
    assert (shape.rect.w, shape.rect.h) == (240, 120)


def test_property_changes_of_shapes_and_pictures_are_undoable_and_merge(edit, tmp_path):
    shape = edit.create_shape(0, Rect(0, 0, 120, 60), "rectangle")
    for w in (2.0, 3.0, 4.0):  # a spin box stepping: one Undo step
        edit.update_shape(shape.object_id, stroke_width=w)
    edit.update_shape(shape.object_id, stroke_color="#ff0000")
    assert shape.stroke_width == 4.0 and shape.stroke_color == "#ff0000"
    edit.undo()
    assert shape.stroke_color != "#ff0000" and shape.stroke_width == 4.0
    edit.undo()
    assert shape.stroke_width == 1.5
    img = _image(edit, tmp_path)
    edit.set_overlay_attrs(img.object_id, opacity=0.4, rotation=30.0)
    edit.undo()
    assert (img.opacity, img.rotation) == (1.0, 0.0)
    edit.redo()
    assert (img.opacity, img.rotation) == (0.4, 30.0)


def test_shapes_survive_the_recovery_session(edit):
    shape = edit.create_shape(0, Rect(10, 20, 30, 40), "ellipse")
    shape.fill_color = "#00ff00"
    data = edit.to_dict()
    edit.shapes.clear()
    edit.load_objects(data)
    restored = edit.shapes[shape.object_id]
    assert restored.fill_color == "#00ff00" and restored.rect.as_tuple() == (10, 20, 30, 40)
