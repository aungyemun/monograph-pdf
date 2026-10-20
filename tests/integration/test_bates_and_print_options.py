"""Bates numbers in Header & Footer, and the print options added with them (odd/even, reverse,
document without comments)."""

from __future__ import annotations

import fitz

from core.convert.page_marks import HeaderFooterSpec, apply_page_marks, render_preview
from core.document import open_document
from core.printing import order_print_pages, render_page_png_for_print


def _doc(path, n=4):
    d = fitz.open()
    for i in range(n):
        d.new_page().insert_text((72, 300), f"Body {i + 1}")
    d.save(path)
    d.close()
    return path


def test_bates_identifier_format():
    spec = HeaderFooterSpec(bates_prefix="CASE-", bates_suffix="-X", bates_start=41, bates_digits=6)
    assert spec.bates(0) == "CASE-000041-X"
    assert spec.bates(9) == "CASE-000050-X"
    assert HeaderFooterSpec(bates_digits=99).bates(0) == "000000000001"  # capped at 12 digits


def test_bates_numbers_are_written_on_every_page(tmp_path):
    doc = open_document(_doc(tmp_path / "in.pdf"))
    spec = HeaderFooterSpec(footer_left="{bates}", footer_right="{page}/{total}", bates_prefix="ACME", bates_start=100)
    apply_page_marks(doc, tmp_path / "out.pdf", header_footer=spec)
    doc.close()
    out = fitz.open(tmp_path / "out.pdf")
    for i, page in enumerate(out):
        text = page.get_text()
        assert f"ACME{100 + i:06d}" in text
        assert f"{i + 1}/4" in text
    out.close()


def test_bates_in_preview_uses_the_page_position(tmp_path):
    d = fitz.open()
    for _ in range(3):
        d.new_page()
    d.save(tmp_path / "blank.pdf")
    d.close()
    doc = open_document(tmp_path / "blank.pdf")
    bates = HeaderFooterSpec(footer_left="{bates}", bates_prefix="P", bates_digits=3)
    fixed = HeaderFooterSpec(footer_left="P001")
    p0 = render_preview(doc, 0, dpi=72, header_footer=bates).samples
    p2 = render_preview(doc, 2, dpi=72, header_footer=bates).samples
    f0 = render_preview(doc, 0, dpi=72, header_footer=fixed).samples
    doc.close()
    assert p0 == f0  # page 1 shows P001
    assert p0 != p2  # page 3 shows P003


def test_print_page_order():
    pages = [0, 1, 2, 3, 4]
    assert order_print_pages(pages, subset="odd") == [0, 2, 4]
    assert order_print_pages(pages, subset="even") == [1, 3]
    assert order_print_pages(pages, subset="even", reverse=True) == [3, 1]
    assert order_print_pages([4, 1], reverse=True) == [1, 4]
    assert order_print_pages([1], subset="odd") == []


def test_printing_without_comments_keeps_fields(tmp_path):
    d = fitz.open()
    p = d.new_page(width=200, height=200)
    annot = p.add_rect_annot(fitz.Rect(10, 10, 90, 90))
    annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
    annot.update()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "f"
    w.rect = fitz.Rect(110, 110, 190, 190)
    w.fill_color = (0, 0, 1)
    w.field_value = ""
    p.add_widget(w)
    d.save(tmp_path / "c.pdf")
    d.close()
    doc = open_document(tmp_path / "c.pdf")

    def pixel(png, x, y):
        pm = fitz.Pixmap(png)
        return pm.pixel(x, y)

    with_comments = render_page_png_for_print(doc, 0, dpi=72)
    without = render_page_png_for_print(doc, 0, dpi=72, comments=False)
    assert pixel(with_comments, 50, 50)[:3] == (255, 0, 0)
    assert pixel(without, 50, 50)[:3] == (255, 255, 255)
    assert pixel(without, 150, 150)[2] > 200 and pixel(without, 150, 150)[0] < 60  # field still printed
    # the document itself is untouched
    assert len(list(doc._backend._doc[0].annots())) == 1  # noqa: SLF001
    doc.close()


def test_print_source_with_unsaved_changes_keeps_comments_separate(tmp_path):
    """Printing works from a flattened copy when there are unsaved changes: form fields are
    flattened there, but comments must stay annotations so “Document only” can leave them out."""
    from core.editing.edit_model import EditableDocument
    from core.printing import prepare_print_source

    d = fitz.open()
    p = d.new_page(width=200, height=200)
    p.add_highlight_annot(fitz.Rect(10, 10, 90, 30))
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "f"
    w.rect = fitz.Rect(110, 110, 190, 130)
    w.field_value = "x"
    p.add_widget(w)
    d.save(tmp_path / "u.pdf")
    d.close()
    doc = open_document(tmp_path / "u.pdf")
    edit = EditableDocument(doc)
    edit.dirty = True
    source = prepare_print_source(doc, edit)
    try:
        page = source.document._backend._doc[0]  # noqa: SLF001
        kinds = [a.type[0] for a in page.annots()]
        assert fitz.PDF_ANNOT_HIGHLIGHT in kinds
        assert not list(page.widgets() or [])  # fields flattened for reliable printing
        assert source.temp_path is not None
    finally:
        source.close()
    assert edit.flatten_on_save is False and getattr(edit, "flatten_comments", True) is True
    doc.close()
