"""Rotated pages on a NON-square sheet: display size, text/search/widget geometry, overlays at Save,
undo/redo and save/reopen.

The older full-circle tests use a square page, which hides any width/height mix-up. Here the page is
300 × 500 pt, so a 90° / 270° page must report 500 × 300 and every coordinate the editor works with
must land on the pixels MuPDF draws.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from PIL import Image

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.shape_box import ShapeBox, ShapeKind
from core.editing.text_box import TextBox
from core.organize.page_ops import _doc, rotate_pages
from core.organize.rotate_command import RotatePagesCommand
from core.page_space import rect_to_display, rect_to_page
from engines.bake_edits import bake_into_document

W, H = 300.0, 500.0
ZOOM = 2.0
ROTATIONS = [0, 90, 180, 270]


def _make(path: Path, rotate: int = 0) -> None:
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    page.insert_text((40, 80), "Anchor", fontsize=24, fontname="helv", color=(0, 0, 0))
    page.insert_text((40, 300), "Second line of text", fontsize=12, fontname="helv")
    page.draw_rect(fitz.Rect(40, 380, 140, 430), color=(0, 0, 1), fill=(0.8, 0.9, 1.0))
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.rect = fitz.Rect(40, 120, 200, 145)
    w.field_value = "Value"
    page.add_widget(w)
    page.add_highlight_annot(page.search_for("Anchor")[0])
    if rotate:
        page.set_rotation(rotate)
    doc.save(path.as_posix())
    doc.close()


def _ink_bbox(pix: fitz.Pixmap, pred) -> tuple[int, int, int, int] | None:
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    px = img.load()
    xs, ys = [], []
    for y in range(img.height):
        for x in range(img.width):
            if pred(px[x, y]):
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _dark(p) -> bool:
    return p[0] < 90 and p[1] < 90 and p[2] < 90


def _red(p) -> bool:
    return p[0] > 200 and p[1] < 60 and p[2] < 60


def _close(a, b, tol) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.mark.parametrize("rot", ROTATIONS)
def test_display_size_matches_rendered_page(tmp_path: Path, rot: int):
    src = tmp_path / "a.pdf"
    _make(src, rot)
    pdf = open_document(src)
    try:
        info = pdf.page(0)
        exp = (H, W) if rot in (90, 270) else (W, H)
        assert (info.display_width_pt, info.display_height_pt) == exp
        pix = _doc(pdf).load_page(0).get_pixmap(matrix=fitz.Matrix(1, 1))
        assert (pix.width, pix.height) == (round(exp[0]), round(exp[1]))
    finally:
        pdf.close()


@pytest.mark.parametrize("rot", ROTATIONS)
def test_search_hits_and_spans_are_in_display_space(tmp_path: Path, rot: int):
    """A search hit / native span rectangle encloses the glyphs actually drawn at that spot."""
    src = tmp_path / "a.pdf"
    _make(src, rot)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        hits = pdf.search("Anchor")
        assert hits
        r = Rect(hits[0][1].x0, hits[0][1].y0, hits[0][1].width, hits[0][1].height)
        pix = _doc(pdf).load_page(0).get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        # the highlight annotation tints the word yellow: find that tint, it must sit inside the hit
        yellow = _ink_bbox(pix, lambda p: p[0] > 200 and p[1] > 200 and p[2] < 120)
        assert yellow is not None
        ycx, ycy = (yellow[0] + yellow[2]) / 2, (yellow[1] + yellow[3]) / 2
        assert _close((ycx, ycy), (r.cx * ZOOM, r.cy * ZOOM), 8)
        spans = [s for s in edit.extract_native_spans(0) if s.text.strip() == "Anchor"]
        assert spans
        s = spans[0].rect
        assert _close((s.cx * ZOOM, s.cy * ZOOM), (ycx, ycy), 8)
    finally:
        pdf.close()


@pytest.mark.parametrize("rot", ROTATIONS)
def test_form_field_rect_is_where_the_widget_is_drawn(tmp_path: Path, rot: int):
    src = tmp_path / "a.pdf"
    _make(src, rot)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        field = next(f for f in edit.fields.values() if f.name == "name")
        page = _doc(pdf).load_page(0)
        w = next(iter(page.widgets()))
        expect = rect_to_display(page, w.rect)
        assert _close((field.rect.x, field.rect.y, field.rect.x1, field.rect.y1), tuple(expect), 0.01)
        # round trip between the two spaces is the identity
        back = rect_to_page(page, expect)
        assert _close(tuple(back), tuple(w.rect), 0.01)
    finally:
        pdf.close()


@pytest.mark.parametrize("rot", ROTATIONS)
def test_overlays_baked_on_rotated_page_land_where_shown(tmp_path: Path, rot: int):
    """Shape + text box drawn in display space appear at that display position, upright."""
    src = tmp_path / "a.pdf"
    _make(src, rot)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        dw, dh = (H, W) if rot in (90, 270) else (W, H)
        shape_rect = Rect(dw - 120, dh - 80, 90, 50)  # bottom-right of the *displayed* page
        edit.add_shape(
            ShapeBox(page_index=0, rect=shape_rect, kind=ShapeKind.RECTANGLE, stroke_color="#ff0000", fill_color="#ffff0000"),
            record_dirty=False,
        ) if hasattr(edit, "add_shape") else edit.shapes.update(
            {"s": ShapeBox(page_index=0, rect=shape_rect, kind=ShapeKind.RECTANGLE, stroke_color="#ff0000", fill_color="#ff0000")}
        )
        box_rect = Rect(30, dh - 60, 160, 28)
        edit.add_object(TextBox(page_index=0, rect=box_rect, text="Overlay note"))
        dest = tmp_path / "out.pdf"
        bake_into_document(edit, dest)
    finally:
        pdf.close()
    out = fitz.open(dest.as_posix())
    try:
        page = out[0]
        assert page.rotation == rot
        assert (page.rect.width, page.rect.height) == (dw, dh)
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        red = _ink_bbox(pix, _red)
        assert red is not None, "shape missing"
        exp = (shape_rect.x * ZOOM, shape_rect.y * ZOOM, shape_rect.x1 * ZOOM, shape_rect.y1 * ZOOM)
        assert _close(red, exp, 4 * ZOOM), (red, exp)
        # text box words are extractable and upright in display space (words read left→right)
        words = page.get_text("words", clip=rect_to_page(page, fitz.Rect(box_rect.x, box_rect.y, box_rect.x1, box_rect.y1)))
        texts = [w[4] for w in sorted(words, key=lambda w: tuple(fitz.Point(w[0], w[1]) * page.rotation_matrix))]
        assert "Overlay" in " ".join(w[4] for w in words)
        assert texts
    finally:
        out.close()


def test_four_quarter_turns_restore_geometry_and_pixels(tmp_path: Path):
    src = tmp_path / "a.pdf"
    _make(src)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        edit.add_object(TextBox(page_index=0, rect=Rect(50, 200, 120, 30), text="Keep me"))
        before = edit.objects[next(iter(edit.objects))].rect
        base = _doc(pdf).load_page(0).get_pixmap(matrix=fitz.Matrix(1, 1))
        for _ in range(4):
            edit.commands.execute(RotatePagesCommand(pdf, edit, [0], 90))
        assert _doc(pdf).load_page(0).rotation == 0
        after = edit.objects[next(iter(edit.objects))].rect
        assert _close(before.as_tuple(), after.as_tuple(), 0.001)
        now = _doc(pdf).load_page(0).get_pixmap(matrix=fitz.Matrix(1, 1))
        assert base.samples == now.samples
    finally:
        pdf.close()


@pytest.mark.parametrize("degrees", [90, -90, 180, 270])
def test_rotate_command_undo_redo_restores_overlays(tmp_path: Path, degrees: int):
    src = tmp_path / "a.pdf"
    _make(src)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        edit.add_object(TextBox(page_index=0, rect=Rect(50, 200, 120, 30), text="Note"))
        edit.shapes["s"] = ShapeBox(page_index=0, rect=Rect(10, 20, 60, 30), kind=ShapeKind.RECTANGLE)
        oid = next(iter(edit.objects))
        start_box = edit.objects[oid].rect.as_tuple()
        start_shape = edit.shapes["s"].rect.as_tuple()
        edit.commands.execute(RotatePagesCommand(pdf, edit, [0], degrees))
        turned_box = edit.objects[oid].rect.as_tuple()
        turned_shape = edit.shapes["s"].rect.as_tuple()
        assert _doc(pdf).load_page(0).rotation == degrees % 360
        assert turned_box != start_box and turned_shape != start_shape or degrees % 360 == 0
        if degrees % 180 == 90:  # shape swaps its sides with the page, text box keeps its size
            assert turned_shape[2:] == (start_shape[3], start_shape[2])
            assert turned_box[2:] == start_box[2:]
        assert edit.undo()
        assert _doc(pdf).load_page(0).rotation == 0
        assert edit.objects[oid].rect.as_tuple() == start_box
        assert edit.shapes["s"].rect.as_tuple() == start_shape
        assert edit.redo()
        assert _doc(pdf).load_page(0).rotation == degrees % 360
        assert edit.objects[oid].rect.as_tuple() == turned_box
        assert edit.shapes["s"].rect.as_tuple() == turned_shape
    finally:
        pdf.close()


def test_page_with_existing_rotate_value_then_turned_again(tmp_path: Path):
    src = tmp_path / "a.pdf"
    _make(src, 90)
    pdf = open_document(src)
    try:
        assert pdf.page(0).display_width_pt == H
        rotate_pages(pdf, [0], 90)
        assert _doc(pdf).load_page(0).rotation == 180
        assert (pdf.page(0).display_width_pt, pdf.page(0).display_height_pt) == (W, H)
        rotate_pages(pdf, [0], -270)
        assert _doc(pdf).load_page(0).rotation == 270
        assert (pdf.page(0).display_width_pt, pdf.page(0).display_height_pt) == (H, W)
    finally:
        pdf.close()


@pytest.mark.parametrize("rot", [90, 180, 270])
def test_save_and_reopen_matches_display_before_save(tmp_path: Path, rot: int):
    src = tmp_path / "a.pdf"
    _make(src)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        dw, dh = (H, W) if rot in (90, 270) else (W, H)
        edit.commands.execute(RotatePagesCommand(pdf, edit, [0], rot))
        edit.shapes["s"] = ShapeBox(
            page_index=0, rect=Rect(20, 20, 80, 40), kind=ShapeKind.RECTANGLE, stroke_color="#ff0000", fill_color="#ff0000"
        )
        dest = tmp_path / "out.pdf"
        bake_into_document(edit, dest)
        live = _doc(pdf).load_page(0).get_pixmap(matrix=fitz.Matrix(1, 1))
        live_text = _doc(pdf).load_page(0).get_text("words")
    finally:
        pdf.close()
    re = fitz.open(dest.as_posix())
    try:
        page = re[0]
        assert (page.rotation, page.rect.width, page.rect.height) == (rot, dw, dh)
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
        assert (pix.width, pix.height) == (live.width, live.height)
        # shape sits at its display position after reopening
        red = _ink_bbox(pix, _red)
        assert red is not None and _close(red, (20, 20, 100, 60), 3)
        # same words, same display positions as before saving
        a = sorted((w[4], round(fitz.Point(w[0], w[1]).x), round(w[1])) for w in live_text)
        b = sorted((w[4], round(fitz.Point(w[0], w[1]).x), round(w[1])) for w in page.get_text("words") if w[4] in {x[0] for x in a})
        assert [t for t, _, _ in a] == [t for t, _, _ in b]
    finally:
        re.close()


def test_rotation_reanalyses_only_the_turned_pages(tmp_path: Path):
    d = fitz.open()
    for i in range(6):
        d.new_page(width=300, height=500).insert_text((40, 80), f"page {i}")
    src = tmp_path / "six.pdf"
    d.save(src.as_posix())
    d.close()
    pdf = open_document(src)
    try:
        before = list(pdf.pages())
        rotate_pages(pdf, [2, 4], 90)
        after = pdf.pages()
        for i in (0, 1, 3, 5):
            assert after[i] is before[i], "an untouched page was re-analysed"
        for i in (2, 4):
            assert after[i] is not before[i] and after[i].rotation == 90
            assert (after[i].display_width_pt, after[i].display_height_pt) == (500, 300)
        rotate_pages(pdf, [2, 4], -90)
        assert [p.rotation for p in pdf.pages()] == [0] * 6
    finally:
        pdf.close()
