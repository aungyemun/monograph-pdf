"""Change Page Size: content is fitted, text stays text, fields and links move with it."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.organize.resize import PAPER_SIZES, FitMode, Orientation, resize_pdf

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _form_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter
    page.insert_text((72, 72), "Header line", fontsize=14)
    page.draw_rect(fitz.Rect(72, 100, 300, 130))
    w = fitz.Widget()
    w.field_name = "name"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 100, 300, 130)
    page.add_widget(w)
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 400, 200, 420), "uri": "https://example.org"})
    page.add_highlight_annot(fitz.Rect(72, 60, 200, 76))
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize("paper", ["A4", "B5 (JIS)", "Legal", "A5"])
def test_fit_keeps_text_fields_links_inside_new_page(tmp_path, paper):
    src = _form_pdf(tmp_path / "in.pdf")
    out = tmp_path / f"out-{paper}.pdf"
    resize_pdf(src, out, PAPER_SIZES[paper])
    with fitz.open(out) as d:
        page = d[0]
        w, h = PAPER_SIZES[paper]
        assert abs(page.rect.width - w) < 0.5 and abs(page.rect.height - h) < 0.5
        assert "Header line" in page.get_text()
        widgets = list(page.widgets())
        assert len(widgets) == 1 and widgets[0].field_name == "name"
        assert page.rect.contains(widgets[0].rect)
        links = page.get_links()
        assert len(links) == 1 and page.rect.contains(links[0]["from"])
        assert len(list(page.annots())) >= 1
        # The field still sits on the box drawn under it (same relative position)
        words = page.get_text("words")
        header = next(wd for wd in words if wd[4] == "Header")
        assert header[1] < widgets[0].rect.y0  # header above the field, as before


def test_fit_preserves_proportions_and_centres(tmp_path):
    src = _form_pdf(tmp_path / "in.pdf")
    out = tmp_path / "a5.pdf"
    resize_pdf(src, out, PAPER_SIZES["A5"])
    with fitz.open(src) as a, fitz.open(out) as b:
        ra, rb = a[0].widgets().__next__().rect, b[0].widgets().__next__().rect
        assert abs(ra.width / ra.height - rb.width / rb.height) < 0.01
        s = rb.width / ra.width
        assert s == pytest.approx(min(PAPER_SIZES["A5"][0] / 612, PAPER_SIZES["A5"][1] / 792), rel=0.01)


def test_stretch_fills_and_landscape_and_page_selection(tmp_path):
    src = tmp_path / "three.pdf"
    doc = fitz.open()
    for i in range(3):
        doc.new_page(width=595, height=842).insert_text((50, 50), f"Page {i + 1}")
    doc.save(src)
    doc.close()
    out = tmp_path / "out.pdf"
    res = resize_pdf(src, out, PAPER_SIZES["Letter"], mode=FitMode.STRETCH, orientation=Orientation.LANDSCAPE, pages=[1])
    assert res.pages_changed == 1
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (595, 842)  # untouched
        assert (round(d[1].rect.width), round(d[1].rect.height)) == (792, 612)
        assert "Page 2" in d[1].get_text()


def test_rotated_pages_keep_rotation(tmp_path):
    src = SAMPLES / "sample_rotated_pages.pdf"
    out = tmp_path / "rot.pdf"
    resize_pdf(src, out, PAPER_SIZES["A4"])
    with fitz.open(src) as a, fitz.open(out) as b:
        assert [p.rotation for p in a] == [p.rotation for p in b]
        for pa, pb in zip(a, b):
            assert (pa.rect.width > pa.rect.height) == (pb.rect.width > pb.rect.height)
            assert pa.get_text().strip() == pb.get_text().strip()


def test_cropbox_content_is_what_gets_fitted(tmp_path):
    src = SAMPLES / "sample_cropbox.pdf"
    out = tmp_path / "crop.pdf"
    resize_pdf(src, out, PAPER_SIZES["A4"])
    with fitz.open(src) as a, fitz.open(out) as b:
        assert a[0].get_text().strip() == b[0].get_text().strip()
        assert b[0].cropbox == b[0].mediabox
