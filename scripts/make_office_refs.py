"""Build Office reference documents with python-docx / openpyxl / python-pptx (Linux QA).

Mirrors the content of scripts/make_office_refs.ps1 without Microsoft Office COM.
Usage: python scripts/make_office_refs.py --out <folder>
"""

from __future__ import annotations

import argparse
from pathlib import Path

JP = "日本語のテキスト"
MIX = "Order 2026-17 注文番号 Hello"


def _picture(out: Path) -> Path:
    from PIL import Image, ImageDraw

    png = out / "picture.png"
    img = Image.new("RGB", (240, 120), (30, 90, 200))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 80, 80], fill=(255, 0, 0))
    img.save(png)
    return png


def make_docx(out: Path, png: Path) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Inches

    doc = Document()
    doc.add_heading("Quarterly Report Heading", level=1)
    doc.add_paragraph("Body paragraph one with ordinary words for the reference check.")
    doc.add_paragraph(JP)
    doc.add_paragraph(MIX)
    table = doc.add_table(rows=3, cols=3)
    cells = [["Item", "Qty", "Price"], ["Apple", "12", "1.25"], ["Pear", "7", "0.80"]]
    for r, row in enumerate(cells):
        for c, val in enumerate(row):
            table.rows[r].cells[c].text = val
    doc.add_picture(str(png), width=Inches(2.5))
    doc.add_page_break()
    doc.add_paragraph("Second page in landscape orientation.")
    # New section landscape
    new_section = doc.add_section()
    new_section.orientation = WD_ORIENT.LANDSCAPE
    new_section.page_width, new_section.page_height = new_section.page_height, new_section.page_width
    doc.add_paragraph("Landscape section text.")
    doc.save(out / "ref.docx")


def make_xlsx(out: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Border, Side
    from openpyxl.worksheet.page import PageMargins

    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["B1"], ws["C1"], ws["D1"] = "Item", "Qty", "Price", JP
    ws["A2"], ws["B2"], ws["C2"], ws["D2"] = "Apple", 12, 1.25, MIX
    ws["A3"], ws["B3"], ws["C3"] = "Pear", 7, 0.8
    thin = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    for row in ws["A1:D3"]:
        for cell in row:
            cell.border = thin
    ws.page_setup.orientation = "landscape"
    ws.page_margins = PageMargins()
    wb.save(out / "ref.xlsx")


def make_pptx(out: Path, png: Path) -> None:
    from pptx import Presentation
    from pptx.util import Emu, Inches, Pt

    # 16:9
    prs = Presentation()
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    blank = prs.slide_layouts[6]

    s1 = prs.slides.add_slide(blank)
    box = s1.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
    tf = box.text_frame
    tf.text = "Slide One Title"
    tf.paragraphs[0].font.size = Pt(36)
    box2 = s1.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(9), Inches(1))
    box2.text_frame.text = f"{JP} / {MIX}"

    s2 = prs.slides.add_slide(blank)
    rows, cols = 3, 3
    table = s2.shapes.add_table(rows, cols, Inches(0.5), Inches(0.8), Inches(6), Inches(2)).table
    data = [["Item", "Qty", "Price"], ["Apple", "12", "1.25"], ["Pear", "7", "0.80"]]
    for r in range(rows):
        for c in range(cols):
            table.cell(r, c).text = data[r][c]

    s3 = prs.slides.add_slide(blank)
    s3.shapes.add_picture(str(png), Inches(0.8), Inches(0.8), width=Inches(3.2))
    prs.save(out / "ref.pptx")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    png = _picture(args.out)
    make_docx(args.out, png)
    make_xlsx(args.out)
    make_pptx(args.out, png)
    for p in sorted(args.out.iterdir()):
        print(f"{p.name}\t{p.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
