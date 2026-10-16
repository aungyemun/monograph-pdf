"""Rotation through a full circle: pages (multiples of 90°) and placed objects (any angle).

A page is rotated one quarter-turn at a time until it is back where it started; at every
step its text, fonts, sizes, colours and drawn content must be intact and displayed the
right way round.  A placed picture is turned through 0°..360° in 15° steps (and a few odd
angles); at each angle it must keep its size, its centre and its colours.
"""

from __future__ import annotations

import math
from pathlib import Path

import fitz
import pytest
from PIL import Image

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.image_box import ImageBox
from core.editing.text_box import TextBox
from core.organize.page_ops import _doc, rotate_pages
from engines.bake_edits import bake_into_document

PAGE_W, PAGE_H = 400.0, 400.0
ZOOM = 2.0


def _make_source(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((40, 60), "Quarterly report 2026", fontsize=18, fontname="helv", color=(0.8, 0.1, 0.1))
    page.insert_text((40, 90), "Body text in Times 11 pt, Lorem ipsum.", fontsize=11, fontname="tiro")
    page.insert_text((40, 110), "Courier line 9 pt 0123456789", fontsize=9, fontname="cour")
    page.draw_rect(fitz.Rect(40, 140, 160, 200), color=(0, 0, 1), fill=(0.8, 0.9, 1.0), width=2)
    page.add_highlight_annot(page.search_for("Quarterly")[0])
    doc.save(path.as_posix())
    doc.close()


def _spans(page: fitz.Page) -> list[tuple[str, str, float, int]]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                out.append((span["text"], span["font"], round(span["size"], 2), span["color"]))
    return out


def _bbox_of_ink(pix: fitz.Pixmap) -> tuple[int, int, int, int]:
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    ink = img.convert("L").point(lambda v: 255 if v < 235 else 0)
    box = ink.getbbox()
    assert box is not None, "nothing was drawn"
    return box


# ------------------------------------------------------------------ pages


def test_page_rotation_full_circle_keeps_content(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source(src)
    pdf = open_document(src)
    try:
        base = fitz.open(src.as_posix())
        base_spans = _spans(base[0])
        base_words = base[0].get_text("words")
        base_pix = base[0].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
        base_img = Image.frombytes("RGB", (base_pix.width, base_pix.height), base_pix.samples)
        base.close()
        assert base_spans, "sample has no text"

        for step in range(1, 5):  # 90, 180, 270, 360
            rotate_pages(pdf, [0], 90)
            page = _doc(pdf).load_page(0)
            assert page.rotation == (90 * step) % 360
            # text, fonts, sizes and colours are unchanged by rotating the view
            assert _spans(page) == base_spans
            assert len(page.get_text("words")) == len(base_words)
            assert page.search_for("Quarterly"), "text lost its searchable position"
            assert page.annots(), "annotation lost"
            # the page is displayed the right way round: pixels equal the unrotated render turned by the same angle
            pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            expected = base_img.rotate(-90 * step, expand=True)
            assert img.size == expected.size
            diff = sum(
                abs(a - b)
                for pa, pb in zip(img.convert("L").resize((100, 100)).getdata(), expected.convert("L").resize((100, 100)).getdata())
                for a, b in [(pa, pb)]
            ) / 10000.0
            assert diff < 6.0, f"page content differs after {90 * step}° (mean diff {diff:.2f})"
        assert page.rotation == 0  # one full round is the identity
    finally:
        pdf.close()


def test_page_rotation_counter_clockwise_full_circle(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source(src)
    pdf = open_document(src)
    try:
        for _ in range(4):
            rotate_pages(pdf, [0], -90)
        page = _doc(pdf).load_page(0)
        assert page.rotation == 0
        assert page.search_for("Quarterly")
    finally:
        pdf.close()


@pytest.mark.parametrize("bad", [1, 45, 89, 180 + 1, -30])
def test_page_rotation_only_in_quarter_turns(tmp_path: Path, bad: int):
    """PDF page rotation (/Rotate) is defined only in multiples of 90°; anything else is refused."""
    src = tmp_path / "src.pdf"
    _make_source(src)
    pdf = open_document(src)
    try:
        with pytest.raises(ValueError):
            rotate_pages(pdf, [0], bad)
        assert _doc(pdf).load_page(0).rotation == 0
    finally:
        pdf.close()


def test_rotated_pages_survive_save_and_reopen(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_source(src)
    for turns in range(0, 5):
        pdf = open_document(src)
        try:
            for _ in range(turns):
                rotate_pages(pdf, [0], 90)
            edit = EditableDocument(pdf)
            edit.add_object(TextBox(page_index=0, rect=Rect(200, 220, 150, 24), text="Added note"))
            dest = tmp_path / f"out_{turns}.pdf"
            bake_into_document(edit, dest)
        finally:
            pdf.close()
        out = fitz.open(dest.as_posix())
        try:
            page = out[0]
            assert page.rotation == (90 * turns) % 360
            text = page.get_text()
            assert "Quarterly report 2026" in text and "Added note" in text
            assert page.get_pixmap(alpha=False).width > 0
        finally:
            out.close()


# ------------------------------------------------------------------ placed pictures


def _picture(path: Path, size=(120, 60)) -> None:
    img = Image.new("RGB", size, (220, 30, 120))
    img.save(path)


def _render_with_picture(tmp_path: Path, angle: float, opacity: float, name: str) -> tuple[fitz.Pixmap, Rect]:
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=PAGE_W, height=PAGE_H)
    doc.save(src.as_posix())
    doc.close()
    pic = tmp_path / "pic.png"
    _picture(pic)
    rect = Rect(125, 160, 150, 75)  # centre (200, 197.5)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        edit.add_image(ImageBox(page_index=0, rect=rect, source_path=str(pic), rotation=angle, opacity=opacity), record_dirty=False)
        dest = tmp_path / f"{name}.pdf"
        bake_into_document(edit, dest)
    finally:
        pdf.close()
    out = fitz.open(dest.as_posix())
    try:
        return out[0].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False), rect
    finally:
        out.close()


ANGLES = [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225, 240, 255, 270, 285, 300, 315, 330, 345, 360, 7.5, 22, 359]


@pytest.mark.parametrize("opacity", [1.0, 0.6])
@pytest.mark.parametrize("angle", ANGLES)
def test_picture_turned_through_any_angle_keeps_size_and_centre(tmp_path: Path, angle: float, opacity: float):
    pix, rect = _render_with_picture(tmp_path, angle, opacity, "a")
    x0, y0, x1, y1 = _bbox_of_ink(pix)
    rad = math.radians(angle)
    c, s = abs(math.cos(rad)), abs(math.sin(rad))
    exp_w = (rect.w * c + rect.h * s) * ZOOM
    exp_h = (rect.w * s + rect.h * c) * ZOOM
    cx, cy = (rect.x + rect.w / 2) * ZOOM, (rect.y + rect.h / 2) * ZOOM
    tol = 5.0
    assert abs((x1 - x0) - exp_w) <= tol, f"{angle}°: width {x1 - x0} expected {exp_w:.1f}"
    assert abs((y1 - y0) - exp_h) <= tol, f"{angle}°: height {y1 - y0} expected {exp_h:.1f}"
    assert abs((x0 + x1) / 2 - cx) <= tol and abs((y0 + y1) / 2 - cy) <= tol, f"{angle}°: centre moved"
    # the picture keeps its colour at its centre (nothing swapped, inverted or blank)
    px = pix.pixel(int(cx), int(cy))
    if opacity >= 0.999:
        assert px == (220, 30, 120)
    else:
        assert px[0] > px[1] and px[2] > px[1]  # tinted magenta over white


def test_picture_full_turn_equals_no_turn(tmp_path: Path):
    a, _ = _render_with_picture(tmp_path, 0, 1.0, "zero")
    b, _ = _render_with_picture(tmp_path, 360, 1.0, "full")
    assert a.samples == b.samples
