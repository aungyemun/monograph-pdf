"""Round trips through a locally installed office suite (LibreOffice or Microsoft Office; skipped when
neither is installed): PDF → PPTX → PDF, PDF → DOCX → PDF, PPTX → PDF → PPTX, DOCX → PDF → DOCX.

Compared: page/slide size and orientation, text, picture presence and position, colour appearance of
a known patch, and metadata. Conversions are allowed to be lossy (no binary equality). The office
suite opening and converting each generated file is the "opens in compatible software" check; the
OOXML package structure (content types and relationships) is checked separately."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import fitz
import pytest

from core.convert.office_bridge import office_availability
from core.document import open_document

A4 = (595.28, 841.89)
A3L = (1190.55, 841.89)
LEGAL = (612.0, 1008.0)


@pytest.fixture(scope="module", autouse=True)
def _suite():
    if not office_availability(refresh=True).any:
        pytest.skip("no office suite installed (LibreOffice or Microsoft Office)")


def _source_pdf(path: Path, sizes) -> Path:
    doc = fitz.open()
    for i, (w, h) in enumerate(sizes):
        page = doc.new_page(width=w, height=h)
        page.insert_text((60, 80), f"Round trip page {i + 1}", fontsize=20)
        page.draw_rect(fitz.Rect(60, 120, 260, 220), color=None, fill=(0.0, 0.4, 0.8))  # known colour patch
    doc.set_metadata({"title": "Round trip", "author": "QA"})
    doc.save(path)
    doc.close()
    return path


def _sizes(pdf: Path) -> list[tuple[int, int]]:
    with fitz.open(pdf) as d:
        return [(round(p.rect.width), round(p.rect.height)) for p in d]


def _patch_colour(pdf: Path, index: int, rect: fitz.Rect) -> tuple[int, int, int]:
    with fitz.open(pdf) as d:
        page = d[index]
        pix = page.get_pixmap(dpi=36, clip=rect)
        mid = pix.pixel(pix.width // 2, pix.height // 2)
        return mid[:3]


def check_ooxml_package(path: Path) -> None:
    """Every part referenced by a relationship exists and every part has a content type."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        assert "[Content_Types].xml" in names and "_rels/.rels" in names
        ct = z.read("[Content_Types].xml").decode("utf-8")
        defaults = set(re.findall(r'Default Extension="([^"]+)"', ct))
        overrides = set(re.findall(r'Override PartName="/([^"]+)"', ct))
        for n in names:
            if n.endswith("/") or n == "[Content_Types].xml":
                continue
            assert n in overrides or n.rsplit(".", 1)[-1] in defaults, f"no content type for {n}"
        for rel in [n for n in names if n.endswith(".rels")]:
            base = rel.replace("_rels/", "").removesuffix(".rels")
            folder = base.rsplit("/", 1)[0] if "/" in base else ""
            xml = z.read(rel).decode("utf-8")
            for target, mode in re.findall(r'Target="([^"]+)"(?:\s+TargetMode="([^"]+)")?', xml):
                if mode == "External":
                    continue
                parts = (target.lstrip("/") if target.startswith("/") else f"{folder}/{target}" if folder else target).split("/")
                stack: list[str] = []
                for part in parts:
                    if part == "..":
                        stack.pop()
                    elif part and part != ".":
                        stack.append(part)
                assert "/".join(stack) in names, f"{rel}: missing {target}"


@pytest.mark.parametrize("mode", ["layout", "editable"])
def test_pdf_to_pptx_to_pdf(tmp_path, mode):
    from core.convert.office_to_pdf import office_to_pdf
    from core.convert.pdf_to_pptx import pdf_to_pptx

    src = _source_pdf(tmp_path / "src.pdf", [A4, A4])
    pdf = open_document(src)
    try:
        pptx = pdf_to_pptx(pdf, tmp_path / f"{mode}.pptx", mode=mode)
    finally:
        pdf.close()
    check_ooxml_package(pptx)
    back = office_to_pdf(pptx, tmp_path / f"{mode}-back.pdf")
    sizes = _sizes(back)
    assert len(sizes) == 2 and all(abs(w - 595) <= 2 and abs(h - 842) <= 2 for w, h in sizes)
    patch = _patch_colour(back, 0, fitz.Rect(100, 140, 220, 200))
    assert all(abs(a - b) <= 30 for a, b in zip(patch, (0, 102, 204))), patch
    if mode == "editable":
        with fitz.open(back) as d:
            assert "Round trip page 1" in " ".join(d[0].get_text().split())


def test_pdf_to_docx_to_pdf_keeps_mixed_section_sizes(tmp_path):
    from core.convert.office_to_pdf import office_to_pdf
    from core.convert.pdf_to_docx import pdf_to_docx

    src = _source_pdf(tmp_path / "mixed.pdf", [A4, A3L, LEGAL])
    pdf = open_document(src)
    try:
        engines = ["text"] + (["layout"] if __import__("core.convert.pdf_to_docx", fromlist=["x"]).layout_engine_available() else [])
        for engine in engines:
            docx = pdf_to_docx(pdf, tmp_path / f"{engine}.docx", engine=engine)
            check_ooxml_package(docx)
            back = office_to_pdf(docx, tmp_path / f"{engine}-back.pdf")
            sizes = _sizes(back)
            assert len(sizes) >= 3, (engine, sizes)
            assert [(w > h) for w, h in sizes[:3]] == [False, True, False], (engine, sizes)
            for (w, h), (ew, eh) in zip(sizes[:3], (A4, A3L, LEGAL)):
                assert abs(w - ew) <= 3 and abs(h - eh) <= 3, (engine, sizes)
            with fitz.open(back) as d:
                text = " ".join(" ".join(p.get_text() for p in d).split())
            assert all(f"Round trip page {i}" in text for i in (1, 2, 3)), (engine, text[:200])
            with fitz.open(back) as d:
                assert d.metadata.get("title") == "Round trip", (engine, d.metadata)
    finally:
        pdf.close()


def _make_pptx(path: Path) -> Path:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu, Pt
    from PIL import Image

    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(int(7.5 * 914400)), Emu(int(10 * 914400))  # custom portrait
    layout = prs.slide_layouts[6]
    s1 = prs.slides.add_slide(layout)
    tb = s1.shapes.add_textbox(Emu(457200), Emu(457200), Emu(5486400), Emu(914400))
    tb.text_frame.text = "Portrait slide text"
    tb.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
    shp = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(457200), Emu(1828800), Emu(1828800), Emu(1371600))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor(0, 102, 204)
    shp.line.fill.background()
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (200, 30, 30)).save(buf, "PNG")
    buf.seek(0)
    s1.shapes.add_picture(buf, Emu(3657600), Emu(1828800), Emu(1828800), Emu(914400))
    s2 = prs.slides.add_slide(layout)
    data = CategoryChartData()
    data.categories = ["A", "B", "C"]
    data.add_series("S", (1, 3, 2))
    s2.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Emu(457200), Emu(457200), Emu(5486400), Emu(3657600), data)
    rows = s2.shapes.add_table(2, 2, Emu(457200), Emu(4572000), Emu(3657600), Emu(914400)).table
    rows.cell(0, 0).text = "Cell A1"
    prs.core_properties.title = "Deck title"
    prs.save(path)
    return path


def test_pptx_to_pdf_to_pptx(tmp_path):
    from core.convert.office_to_pdf import office_to_pdf
    from core.convert.pdf_to_pptx import pdf_to_pptx

    deck = _make_pptx(tmp_path / "deck.pptx")
    pdf_path = office_to_pdf(deck, tmp_path / "deck.pdf")
    sizes = _sizes(pdf_path)
    assert sizes == [(540, 720), (540, 720)]  # 7.5 × 10 in portrait slides
    with fitz.open(pdf_path) as d:
        assert "Portrait slide text" in d[0].get_text() and "Cell A1" in d[1].get_text()
        assert d[0].get_images() and d.metadata.get("title") == "Deck title"
    patch = _patch_colour(pdf_path, 0, fitz.Rect(40, 140, 160, 230))
    assert all(abs(a - b) <= 30 for a, b in zip(patch, (0, 102, 204))), patch
    pdf = open_document(pdf_path)
    try:
        back = pdf_to_pptx(pdf, tmp_path / "back.pptx")
    finally:
        pdf.close()
    from pptx import Presentation

    prs = Presentation(back.as_posix())
    assert (round(prs.slide_width / 12700), round(prs.slide_height / 12700)) == (540, 720)
    assert len(prs.slides) == 2 and prs.core_properties.title == "Deck title"


def _make_docx(path: Path) -> Path:
    from docx import Document
    from docx.enum.section import WD_ORIENT, WD_SECTION
    from docx.shared import Mm, RGBColor
    from PIL import Image

    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Mm(210), Mm(297)
    s.header.paragraphs[0].text = "Header text"
    s.footer.paragraphs[0].text = "Footer text"
    p = doc.add_paragraph()
    r = p.add_run("Coloured body text")
    r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "Table cell"
    buf = io.BytesIO()
    Image.new("RGB", (120, 60), (20, 160, 60)).save(buf, "PNG")
    buf.seek(0)
    doc.add_picture(buf, width=Mm(60))
    s2 = doc.add_section(WD_SECTION.NEW_PAGE)
    s2.orientation = WD_ORIENT.LANDSCAPE
    s2.page_width, s2.page_height = Mm(420), Mm(297)
    doc.add_paragraph("Landscape A3 section")
    doc.core_properties.title = "Report title"
    doc.core_properties.author = "Writer"
    doc.save(path)
    return path


def test_docx_to_pdf_to_docx(tmp_path):
    from docx import Document

    from core.convert.office_to_pdf import office_to_pdf
    from core.convert.pdf_to_docx import pdf_to_docx

    src = _make_docx(tmp_path / "report.docx")
    pdf_path = office_to_pdf(src, tmp_path / "report.pdf")
    sizes = _sizes(pdf_path)
    assert sizes[0] == (595, 842) and sizes[-1] == (1191, 842)
    with fitz.open(pdf_path) as d:
        first = d[0].get_text()
        assert "Header text" in first and "Footer text" in first and "Table cell" in first
        assert d[0].get_images() and d.metadata.get("title") == "Report title" and d.metadata.get("author") == "Writer"
    pdf = open_document(pdf_path)
    try:
        back = pdf_to_docx(pdf, tmp_path / "back.docx", engine="text")
    finally:
        pdf.close()
    secs = Document(back.as_posix()).sections
    assert [(round(s.page_width.pt), round(s.page_height.pt)) for s in secs] == sizes
    props = Document(back.as_posix()).core_properties
    assert props.title == "Report title" and props.author == "Writer"
