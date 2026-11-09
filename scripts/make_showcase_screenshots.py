"""Screenshots and website illustrations of Monograph PDF made from the real application window.

Usage (Windows, from the project folder):
    env\\Scripts\\python.exe scripts\\make_showcase_screenshots.py [--out docs\\images] [--web docs\\website\\images]

* Builds professional-looking **synthetic** sample documents (fictional organizations, people and
  numbers; no real or personal document is ever opened).
* Opens them in ``MainWindow`` with throw-away settings (``MONOGRAPH_PDF_*`` folders in a new temporary
  folder: your own settings, recent files and documents are never touched) on Qt's ``offscreen``
  platform, so nothing appears on the screen and no other window can be captured. Any clipboard use
  stays inside the process.
* Saves window captures made by Qt itself (``--out``, plain screenshots for the README and the docs)
  and, from the same captures, framed illustrations for a website plus a 1280 x 640 social-preview
  card (``--web``).
* Prints every file it writes; never opens a file dialog (so no local folder appears in a capture).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(tempfile.mkdtemp(prefix="monograph_showcase_"))
for _name in ("USER_DATA_DIR", "RUNTIME_DIR", "UPDATES_DIR", "DIAGNOSTICS_DIR"):
    os.environ["MONOGRAPH_PDF_" + _name] = str(WORK / _name.lower())  # never the real profile
os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.5")  # crisp captures: 1440 x 900 window -> 2160 x 1350 px
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

SIZE = (1440, 900)
NAVY = (0.12, 0.23, 0.41)
TEAL = (0.06, 0.46, 0.43)
GREY = (0.36, 0.38, 0.42)
LIGHT = (0.93, 0.96, 0.96)
ORG = "Lumen Bay Environmental Laboratory"  # fictional


# -- sample documents (all content is invented) -----------------------------------------------------

def _header(page, title: str, section: str) -> None:
    page.draw_rect(fitz.Rect(0, 0, page.rect.width, 6), color=None, fill=TEAL)
    page.insert_text((56, 40), ORG, fontsize=8.5, color=GREY)
    page.insert_text((page.rect.width - 56 - fitz.get_text_length(section, "helv", 8.5), 40), section,
                     fontsize=8.5, color=GREY)
    page.insert_text((56, 92), title, fontsize=22, color=NAVY, fontname="hebo")
    page.draw_line((56, 104), (page.rect.width - 56, 104), color=TEAL, width=1.2)


def _footer(page, n: int) -> None:
    page.insert_text((56, page.rect.height - 30), "Coastal Water Quality Report 2026  ·  sample document",
                     fontsize=8, color=GREY)
    del n  # no printed page number: the Header & Footer illustration adds one in its preview


LEFT = ("Water quality along the Lumen Bay coastline improved for the third year in a row. Across "
        "the twelve monitoring stations, the median nitrate concentration fell by 14 percent compared "
        "with 2025, and dissolved oxygen stayed above the protection threshold at every station "
        "throughout the summer.\n\n"
        "The strongest improvement was measured near the river mouth, where the upgraded treatment "
        "plant began full operation in March. Stations on the open coast changed little, as expected.")
RIGHT = ("Two stations in the harbour still exceed the turbidity guideline after heavy rainfall. "
         "Sediment from construction sites upstream is the most likely cause; a sampling campaign "
         "after storm events is planned for spring 2027.\n\n"
         "We recommend continuing the monthly programme unchanged, adding automatic turbidity "
         "sensors at the two harbour stations and publishing the station data as open data.")


def make_report(path: Path) -> Path:
    doc = fitz.open()
    # 1 cover
    p = doc.new_page()
    p.draw_rect(fitz.Rect(0, 0, p.rect.width, 300), color=None, fill=NAVY)
    p.draw_rect(fitz.Rect(0, 300, p.rect.width, 308), color=None, fill=TEAL)
    p.insert_text((56, 120), ORG.upper(), fontsize=10, color=(0.75, 0.85, 0.9))
    p.insert_text((56, 190), "Coastal Water Quality", fontsize=34, color=(1, 1, 1), fontname="hebo")
    p.insert_text((56, 232), "Report 2026", fontsize=34, color=(1, 1, 1), fontname="hebo")
    p.insert_text((56, 268), "Annual monitoring results  ·  twelve stations  ·  January to October",
                  fontsize=12, color=(0.85, 0.92, 0.95))
    for i, (num, label) in enumerate((("14 %", "less nitrate than 2025"), ("12 / 12", "stations with enough oxygen"),
                                      ("1,440", "samples analysed"))):
        r = fitz.Rect(56 + i * 165, 360, 56 + i * 165 + 150, 450)
        p.draw_rect(r, color=None, fill=LIGHT)
        p.insert_text((r.x0 + 14, r.y0 + 44), num, fontsize=24, color=TEAL, fontname="hebo")
        p.insert_text((r.x0 + 14, r.y0 + 70), label, fontsize=9.5, color=GREY)
    p.insert_textbox(fitz.Rect(56, 490, 540, 620),
                     "Prepared by the Monitoring Team for the Lumen Bay Coastal Council. All names, "
                     "stations and values in this document are fictional and serve as an example.",
                     fontsize=10.5, color=GREY, lineheight=1.4)
    p.insert_text((56, 780), "November 2026", fontsize=10, color=GREY)
    # 2 summary, two columns
    p = doc.new_page()
    _header(p, "Executive summary", "1  Summary")
    p.insert_textbox(fitz.Rect(56, 124, 285, 560), LEFT, fontsize=10.5, lineheight=1.5)
    p.insert_textbox(fitz.Rect(310, 124, 539, 560), RIGHT, fontsize=10.5, lineheight=1.5)
    box = fitz.Rect(56, 470, 539, 560)
    p.draw_rect(box, color=None, fill=LIGHT)
    p.draw_rect(fitz.Rect(56, 470, 60, 560), color=None, fill=TEAL)
    p.insert_textbox(box + (18, 14, -14, -8),
                     "Key finding: nitrate levels are now below the 2030 target at ten of twelve stations.",
                     fontsize=12, color=NAVY, fontname="hebo", lineheight=1.4)
    _footer(p, 2)
    # 3 chart and table
    p = doc.new_page()
    _header(p, "Nitrate by month", "2  Results")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    v25 = [2.9, 3.1, 3.0, 2.7, 2.5, 2.2, 2.0, 2.1, 2.4, 2.6]
    v26 = [2.6, 2.7, 2.5, 2.2, 2.0, 1.8, 1.7, 1.8, 2.0, 2.2]
    x0, y0, h = 90, 380, 220
    for g in range(0, 5):
        y = y0 - g * h / 4
        p.draw_line((x0, y), (530, y), color=(0.85, 0.87, 0.9), width=0.6)
        p.insert_text((62, y + 3), f"{g * 0.8:.1f}", fontsize=7.5, color=GREY)
    for i, m in enumerate(months):
        bx = x0 + 8 + i * 44
        for j, (vals, col) in enumerate(((v25, (0.7, 0.76, 0.84)), (v26, TEAL))):
            bh = vals[i] / 3.2 * h
            p.draw_rect(fitz.Rect(bx + j * 15, y0 - bh, bx + j * 15 + 13, y0), color=None, fill=col)
        p.insert_text((bx + 4, y0 + 14), m, fontsize=8, color=GREY)
    p.draw_rect(fitz.Rect(330, 128, 340, 138), color=None, fill=(0.7, 0.76, 0.84))
    p.insert_text((345, 137), "2025", fontsize=8.5, color=GREY)
    p.draw_rect(fitz.Rect(385, 128, 395, 138), color=None, fill=TEAL)
    p.insert_text((400, 137), "2026", fontsize=8.5, color=GREY)
    p.insert_text((62, 130), "mg/L", fontsize=8, color=GREY)
    p.insert_text((56, 420), "Figure 1. Median nitrate concentration of all stations, mg/L.", fontsize=9,
                  color=GREY, fontname="heit")
    rows = [("Station", "Nitrate mg/L", "Oxygen mg/L", "Turbidity NTU"), ("River mouth", "1.6", "8.1", "4.2"),
            ("North beach", "1.9", "8.4", "2.1"), ("Harbour east", "2.4", "7.2", "11.8"),
            ("Harbour west", "2.3", "7.4", "10.9"), ("Open coast", "1.7", "8.6", "1.4")]
    ty = 460
    for k, row in enumerate(rows):
        if k == 0:
            p.draw_rect(fitz.Rect(56, ty - 14, 539, ty + 6), color=None, fill=NAVY)
        elif k % 2 == 0:
            p.draw_rect(fitz.Rect(56, ty - 14, 539, ty + 6), color=None, fill=LIGHT)
        for c, cell in enumerate(row):
            p.insert_text((66 + c * 120, ty), cell, fontsize=9.5,
                          color=(1, 1, 1) if k == 0 else (0.1, 0.1, 0.1), fontname="hebo" if k == 0 else "helv")
        ty += 22
    p.insert_text((56, ty + 10), "Table 1. Station medians, January to October 2026 (fictional data).",
                  fontsize=9, color=GREY, fontname="heit")
    _footer(p, 3)
    # 4 Japanese summary
    p = doc.new_page()
    _header(p, "Summary in Japanese", "3  日本語要約")
    p.insert_text((56, 140), "沿岸水質報告書 2026 ― 要約", fontsize=16, color=NAVY, fontname="japan")
    jp = ("ルーメン湾沿岸の水質は三年連続で改善しました。十二か所の観測地点における硝酸塩濃度の中央値は、"
          "前年と比べて十四パーセント低下し、夏季を通じてすべての地点で溶存酸素が基準値を上回りました。"
          "\n\n港内の二地点では、大雨の後に濁度が指針値を超えています。上流の工事現場からの土砂が主な原因と"
          "考えられるため、二〇二七年春に降雨後の追加調査を実施する予定です。"
          "\n\n本書に記載された名称・地点・数値はすべて架空のサンプルです。")
    p.insert_textbox(fitz.Rect(56, 160, 539, 420), jp, fontsize=11, fontname="japan", lineheight=1.8)
    _footer(p, 4)
    # 5 methods
    p = doc.new_page()
    _header(p, "Methods", "4  Methods")
    p.insert_textbox(fitz.Rect(56, 124, 539, 400),
                     "Samples were taken monthly at a depth of one metre, cooled to 4 °C and analysed within "
                     "24 hours. Nitrate was measured by ion chromatography, dissolved oxygen with an optical "
                     "probe on site, and turbidity with a calibrated nephelometer. All values are medians of "
                     "duplicate samples. Quality control followed the laboratory's accredited procedures.",
                     fontsize=10.5, lineheight=1.5)
    _footer(p, 5)
    doc.set_toc([[1, "Coastal Water Quality Report 2026", 1], [1, "Executive summary", 2],
                 [1, "Nitrate by month", 3], [2, "Figure 1", 3], [2, "Table 1", 3],
                 [1, "Summary in Japanese", 4], [1, "Methods", 5]])
    doc.set_metadata({"title": "Coastal Water Quality Report 2026", "author": "Monitoring Team (sample)",
                      "subject": "Synthetic sample document"})
    doc.save(path)
    doc.close()
    return path


def make_review(path: Path, report: Path) -> Path:
    """The report with review markup (real PDF annotations): highlight, underline, sticky notes, a
    text box with an arrow."""
    doc = fitz.open(report)
    page = doc[1]
    for needle, kind in (("fell by 14 percent", "hl"), ("exceed the turbidity guideline", "ul"),
                         ("automatic turbidity", "hl")):
        hits = page.search_for(needle)
        if hits:
            a = (page.add_highlight_annot if kind == "hl" else page.add_underline_annot)(hits)
            a.set_info(title="M. Okada")
            a.update()
    for pt, text, who in (((292, 150), "Please add the 2025 value for comparison.", "M. Okada"),
                          ((544, 300), "Which construction sites? Name them in the appendix.", "R. Silva")):
        n = page.add_text_annot(pt, text)
        n.set_info(title=who)
        n.update()
    target = page.search_for("spring 2027")[0]
    box = fitz.Rect(330, 370, 539, 398)
    ft = page.add_freetext_annot(box, "Confirm the date with the council", fontsize=10,
                                 text_color=NAVY, fill_color=(1, 0.97, 0.82))
    ft.set_info(title="R. Silva")
    ft.update()
    ar = page.add_line_annot((box.x0 + 40, box.y0), ((target.x0 + target.x1) / 2, target.y1 + 2))
    ar.set_colors(stroke=(0.8, 0.25, 0.2))
    ar.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
    ar.set_border(width=1.4)
    ar.update()
    doc.save(path)
    doc.close()
    return path


def make_form(path: Path) -> Path:
    doc = fitz.open()
    p = doc.new_page()
    _header(p, "Symposium registration", "Coastal Science Symposium 2026")
    p.insert_text((56, 128), "Please complete the fields below. Fields can be filled and saved in Monograph PDF.",
                  fontsize=9.5, color=GREY)

    def text_field(name, label, y, value="", x1=539):
        p.insert_text((56, y + 15), label, fontsize=10.5)
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect = name, fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(210, y, x1, y + 22)
        w.field_value, w.text_fontsize = value, 11
        w.text_font = "japan" if any(ord(c) > 0x3000 for c in value) else "Helv"
        p.add_widget(w)

    text_field("name", "Full name", 160, "Hana Yamada")
    text_field("name_jp", "Name (Japanese)", 196, "山田 花子")
    text_field("org", "Organization", 232, "Harbour Point Institute (fictional)")
    text_field("email", "Email", 268, "h.yamada@example.org")
    p.insert_text((56, 319), "Session", fontsize=10.5)
    w = fitz.Widget()
    w.field_name, w.field_type = "session", fitz.PDF_WIDGET_TYPE_COMBOBOX
    w.choice_values = ["Water quality", "Coastal ecology", "Data and sensors"]
    w.rect, w.field_value, w.text_fontsize = fitz.Rect(210, 304, 400, 326), "Data and sensors", 11
    p.add_widget(w)
    p.insert_text((56, 368), "Workshops", fontsize=10.5)
    for i, (label, on) in enumerate((("Open data in practice", True), ("Sensor calibration", True),
                                     ("Field sampling safety", False))):
        w = fitz.Widget()
        w.field_name, w.field_type = f"ws{i}", fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect, w.field_value = fitz.Rect(210, 356 + i * 26, 224, 370 + i * 26), on
        p.add_widget(w)
        p.insert_text((232, 368 + i * 26), label, fontsize=10.5)
    text_field("notes", "Notes", 450, "Arriving on the evening of 11 March.", 539)
    p.insert_text((56, 520), "All names and organizations on this form are fictional.", fontsize=8.5, color=GREY)
    doc.save(path)
    doc.close()
    return path


def make_agreement(path: Path) -> Path:
    doc = fitz.open()
    p = doc.new_page()
    _header(p, "Consulting services agreement", "Sample contract")
    body = ("This agreement is made between Harbour Point Institute, 12 Quay Street, Lumen Bay (the Client) "
            "and Ridgeway Data Services, account no. 4410-2207-9931 (the Consultant).\n\n"
            "1. Services. The Consultant will review the monitoring programme and deliver a written "
            "assessment by 30 January 2027.\n\n"
            "2. Fees. The Client will pay a fixed fee of 18,500 to account no. 4410-2207-9931 within 30 days "
            "of receiving the assessment.\n\n"
            "3. Confidentiality. Station data and the contact details of field staff, such as Daniel "
            "Mercer (mobile 0400 555 0123), must not be disclosed.\n\n"
            "All parties, addresses and numbers in this sample are fictional.")
    p.insert_textbox(fitz.Rect(56, 124, 539, 600), body, fontsize=10.5, lineheight=1.55)
    _footer(p, 1)
    doc.save(path)
    doc.close()
    return path


# -- website illustrations --------------------------------------------------------------------------

def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in (("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf",)) + ("arial.ttf",):
        f = windir / name
        if f.exists():
            return ImageFont.truetype(str(f), size)
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def framed(src: Path, dst: Path, *, headline: str, sub: str, callouts=(), dark: bool = False,
           canvas=(2400, 1600)) -> None:
    """A website illustration for readers who have never used a PDF editor: a plain-language headline and
    explanation, the capture on a soft gradient with rounded corners and a shadow, small numbered markers
    next to the real buttons and areas (``callouts``: (x, y, label) in capture pixels) and a legend under
    the capture that explains each number. Markers never cover the feature they explain."""
    from PIL import Image, ImageDraw, ImageFilter

    W, H = canvas
    top, bottom = ((0x1b, 0x2a, 0x3a), (0x0f, 0x17, 0x22)) if dark else ((0xf3, 0xf8, 0xf7), (0xd9, 0xea, 0xe8))
    ink, soft = ((0xf4, 0xf7, 0xfa), (0xb8, 0xc7, 0xd3)) if dark else ((0x10, 0x24, 0x3e), (0x45, 0x55, 0x66))
    accent = (0x0f, 0x76, 0x6e) if not dark else (0x2d, 0xb3, 0xa6)
    bg = Image.new("RGB", canvas, top)
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    d.text((W // 2, 92), headline, font=_font(64, bold=True), fill=ink, anchor="mm")
    d.text((W // 2, 168), sub, font=_font(34), fill=soft, anchor="mm")
    head, legend_h = 236, (120 if callouts else 40)
    shot = Image.open(src).convert("RGB")
    scale = min((W - 220) / shot.width, (H - head - legend_h - 50) / shot.height)
    shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
    x, y = (W - shot.width) // 2, head + 10
    r = 22
    shadow = Image.new("L", canvas, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + 18, x + shot.width, y + shot.height + 18), r, fill=110)
    bg.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(28)))
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width - 1, shot.height - 1), r, fill=255)
    bg.paste(shot, (x, y), mask)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((x, y, x + shot.width - 1, y + shot.height - 1), r,
                        outline=(0x3a, 0x4a, 0x5c) if dark else (0xc9, 0xd6, 0xd8), width=2)

    def badge(cx: float, cy: float, n: int, size: int = 30) -> None:
        d.ellipse((cx - size - 5, cy - size - 5, cx + size + 5, cy + size + 5), fill=(255, 255, 255))
        d.ellipse((cx - size, cy - size, cx + size, cy + size), fill=accent)
        d.text((cx, cy), str(n), font=_font(int(size * 1.15), bold=True), fill=(255, 255, 255), anchor="mm")

    for n, (cx, cy, _label, *ring) in enumerate(callouts, 1):
        if ring:  # a ring around a small target such as a toolbar button
            rx, ry, rr = x + ring[0] * scale, y + ring[1] * scale, ring[2] * scale
            d.ellipse((rx - rr - 3, ry - rr - 3, rx + rr + 3, ry + rr + 3), outline=(255, 255, 255), width=10)
            d.ellipse((rx - rr, ry - rr, rx + rr, ry + rr), outline=accent, width=5)
        badge(x + cx * scale, y + cy * scale, n)
    if callouts:  # legend: (1) label   (2) label ...
        lf = _font(34, bold=False)
        items = [(n, c[2], 30 + 14 + d.textlength(c[2], font=lf)) for n, c in enumerate(callouts, 1)]
        gap = 70
        total = sum(w for *_, w in items) + gap * (len(items) - 1) + 30
        cx = (W - total) / 2 + 30
        cy = y + shot.height + 30 + legend_h / 2
        for n, label, w in items:
            badge(cx, cy, n, size=26)
            d.text((cx + 44, cy), label, font=lf, fill=ink, anchor="lm")
            cx += w + gap
    bg.save(dst, optimize=True)


def social_card(src: Path, logo: Path, dst: Path) -> None:
    """1280 x 640 repository social preview: logo, name, tagline and a cropped screenshot."""
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 1280, 640
    bg = Image.new("RGB", (W, H), (0x0f, 0x2a, 0x3d))
    d = ImageDraw.Draw(bg)
    for x in range(W):
        t = x / (W - 1)
        d.line([(x, 0), (x, H)], fill=(int(0x0f + 0x02 * t), int(0x2a + 0x2a * t), int(0x3d + 0x10 * t)))
    if logo.exists():
        lg = Image.open(logo).convert("RGBA").resize((112, 112), Image.LANCZOS)
        bg.paste(lg, (72, 86), lg)
    d.text((72, 228), "Monograph PDF", font=_font(64, bold=True), fill=(255, 255, 255))
    for i, line in enumerate(("Offline, privacy-first PDF editor", "for Windows — open source (AGPL-3.0)")):
        d.text((74, 318 + i * 42), line, font=_font(30), fill=(0xcf, 0xe6, 0xe4))
    d.text((74, 520), "Edit · Forms · OCR · Protect · Copy text", font=_font(22),
           fill=(0x9f, 0xc4, 0xc2))
    shot = Image.open(src).convert("RGB")
    crop = shot.crop((0, 0, int(shot.width * 0.72), int(shot.height * 0.82)))
    crop = crop.resize((620, int(620 * crop.height / crop.width)), Image.LANCZOS)
    x, y = 640, 110
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + 12, x + crop.width, y + crop.height + 12), 16, fill=140)
    bg.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(18)))
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, crop.width - 1, crop.height - 1), 16, fill=255)
    bg.paste(crop, (x, y), mask)
    bg.save(dst, optimize=True)


# -- captures ---------------------------------------------------------------------------------------

SHOTS = {  # file: (headline, explanation) — written for people who have never used a PDF editor
    "monograph-pdf-ui.png": ("Everything on your own computer",
                             "Open, read and organise PDF documents — nothing is uploaded anywhere"),
    "monograph-pdf-select-text.png": ("Copy text straight from the page",
                                      "Drag over the words you need and paste them into Word, e-mail or a browser"),
    "monograph-pdf-select-text-japanese.png": ("Works with Japanese too",
                                               "Japanese text is copied exactly, without extra spaces"),
    "monograph-pdf-editing-comments.png": ("Review documents together",
                                           "Highlight, add notes and see every comment in one list"),
    "monograph-pdf-forms.png": ("Fill in forms without printing",
                                "Type into the fields, tick the boxes, save — done"),
    "monograph-pdf-page-thumbnails.png": ("See every page at a glance",
                                          "Small pictures of all pages help you find your way in long documents"),
    "monograph-pdf-redaction.png": ("Remove private information for good",
                                    "Mark names and numbers; applying the redaction deletes them from the file"),
    "monograph-pdf-password-protect.png": ("Protect a PDF with a password",
                                           "Strong AES-256 encryption — choose who may open, print or change it"),
    "monograph-pdf-header-footer.png": ("Add page numbers and headers",
                                        "See the result in the preview before anything is changed"),
    "monograph-pdf-viewer-dark.png": ("Easy on the eyes, day and night",
                                      "A dark theme for comfortable reading in the evening"),
    "monograph-pdf-start-dark.png": ("Start in seconds",
                                     "Recent files and the most common tasks on one start page"),
}
CALLOUTS: dict[str, list] = {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "images"))
    ap.add_argument("--web", default=str(ROOT / "docs" / "website" / "images"))
    a = ap.parse_args()
    out, web = Path(a.out), Path(a.web)
    out.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from core.text_selection import TextPosition
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-showcase"])
    app = QApplication.instance()
    win = MainWindow()
    win.resize(*SIZE)
    win.show()

    def settle(ms: int = 1500) -> None:
        for _ in range(6):
            app.processEvents()
        QTest.qWait(ms)

    def shot(name: str, widget=None) -> Path:
        path = out / name
        (widget or win).grab().save(str(path))
        print("wrote", path)
        return path

    def open_doc(path: Path) -> None:
        if win._edit is not None:  # noqa: SLF001 — captures never save
            win._edit.dirty = False  # noqa: SLF001
        if win._document is not None:  # noqa: SLF001
            win.close_document(save_session=False)
        assert win.open_path(path), path
        settle(600)

    from PySide6.QtCore import QPoint

    from core.editing.geometry import Point

    dpr = win.grab().devicePixelRatio() or 1.0

    def at_widget(widget, fx: float = 0.5, fy: float = 0.5):
        p = widget.mapTo(win, QPoint(int(widget.width() * fx), int(widget.height() * fy)))
        return p.x() * dpr, p.y() * dpr

    def at_pdf(page: int, x: float, y: float):
        inner = win._canvas._canvas  # noqa: SLF001
        q = inner.pdf_to_widget_f(page, Point(x, y))
        p = inner.mapTo(win, q.toPoint())
        return p.x() * dpr, p.y() * dpr

    def call(name: str, *items) -> None:
        """items: (marker_xy, label[, ring_x, ring_y, ring_radius]); the marker sits beside the feature,
        the label goes in the legend; an optional ring circles a small target."""
        CALLOUTS[name] = [(*it[0], it[1], *it[2:]) for it in items]

    def beside(xy, dx: float = 0, dy: float = 0):
        return xy[0] + dx * dpr, xy[1] + dy * dpr

    def nav_width(px: int, inspector: int = 300) -> None:
        total = sum(win._splitter.sizes())  # noqa: SLF001
        win._splitter.setSizes([px, total - px - inspector, inspector])  # noqa: SLF001

    report = make_report(WORK / "Coastal Water Quality Report 2026.pdf")
    review = make_review(WORK / "Coastal Water Quality Report 2026 (review).pdf", report)
    form = make_form(WORK / "Symposium Registration.pdf")
    agreement = make_agreement(WORK / "Consulting Services Agreement (sample).pdf")

    # start page, dark
    win._set_theme("dark")  # noqa: SLF001
    win.statusBar().clearMessage()
    settle()
    shot("monograph-pdf-start-dark.png")

    # workspace (light) and dark viewer
    open_doc(report)
    nav_width(300)
    win._left.show_bookmarks()  # noqa: SLF001
    win._left._bookmarks.setCurrentRow(0)  # noqa: SLF001
    win.act_fit_width.trigger()
    for theme, name in (("light", "monograph-pdf-ui.png"), ("dark", "monograph-pdf-viewer-dark.png")):
        win._set_theme(theme)  # noqa: SLF001
        win.statusBar().clearMessage()
        settle(1800)
        shot(name)
    win._set_theme("light")  # noqa: SLF001
    win._set_theme("light")  # noqa: SLF001
    settle(1200)
    bm = win._left._bookmarks  # noqa: SLF001
    first = bm.visualItemRect(bm.item(0))
    call("monograph-pdf-ui.png",
         (beside(at_widget(bm, 0, 0), first.right() - 40, first.center().y()), "Chapters at a click"),
         (at_pdf(0, 28, 180), "Your document, fully offline"),
         (at_widget(win._inspector, 0.62, 0.16), "Document details"))  # noqa: SLF001
    call("monograph-pdf-viewer-dark.png")

    # Select Text: the left column paragraph and the first lines of the right column (page 2)
    win._canvas.go_to_page(1)  # noqa: SLF001
    win.act_text_select_tool.trigger()
    settle(800)
    ctl = win._canvas._canvas.text_select  # noqa: SLF001
    doc = win._document._backend._doc  # noqa: SLF001
    pt = ctl.cache.get(doc, 1)
    full = pt.text(0, len(pt.glyphs))
    a = full.find("Water quality")
    b = full.find("plant began full operation in March.") + len("plant began full operation in March.")

    def pos(char_index: int) -> int:  # character offset in the copied text -> glyph index
        k = 0
        for gi in range(len(pt.glyphs)):
            if len(pt.text(0, gi + 1)) > char_index:
                return gi
            k = gi
        return k + 1

    ctl.selection.set(TextPosition(1, pos(a)), TextPosition(1, pos(b)))
    win._copy()  # noqa: SLF001 — offscreen: the clipboard is the process's own
    settle(900)
    shot("monograph-pdf-select-text.png")
    sel = ctl.selected_page_rects(1)
    button = at_widget(win._main_bar.widgetForAction(win.act_text_select_tool))  # noqa: SLF001
    call("monograph-pdf-select-text.png",
         (beside(button, 0, 44), "Choose Select Text", *button, 22 * dpr),
         (at_pdf(1, 30, (sel[-1][1] + sel[-1][3]) / 2) if sel else at_pdf(1, 30, 330), "Drag over the words"),
         (beside(at_widget(win.statusBar(), 0, 0.5), 200, 0), "Copied — paste it anywhere"))

    # Select Text in Japanese (page 4)
    win._canvas.go_to_page(3)  # noqa: SLF001
    settle(800)
    pj = ctl.cache.get(doc, 3)
    full = pj.text(0, len(pj.glyphs))
    s = full.find("ルーメン湾")
    e = full.find("上回りました。") + len("上回りました。")
    pt = pj
    ctl.selection.set(TextPosition(3, pos(s)), TextPosition(3, pos(e)))
    win._copy()  # noqa: SLF001
    settle(900)
    shot("monograph-pdf-select-text-japanese.png")
    sj = ctl.selected_page_rects(3)
    call("monograph-pdf-select-text-japanese.png",
         (at_pdf(3, 30, (sj[-1][1] + sj[-1][3]) / 2) if sj else at_pdf(3, 30, 220),
          "Japanese text, copied exactly"))
    ctl.clear()
    win.act_select_tool.trigger()

    # page thumbnails on the chart page
    win._left.setCurrentIndex(0)  # noqa: SLF001
    win._canvas.go_to_page(2)  # noqa: SLF001
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-page-thumbnails.png")
    call("monograph-pdf-page-thumbnails.png",
         (at_widget(win._left, 0.80, 0.16), "Click a page to jump to it"))  # noqa: SLF001

    # dialogs through their real menu commands; grabbed, then cancelled (nothing is saved)
    def capture_modal(action, name: str) -> None:
        state = {"tries": 0, "done": False}

        def grab() -> None:
            w = QApplication.activeModalWidget()
            if w is None:
                state["tries"] += 1
                if state["tries"] < 50:
                    QTimer.singleShot(100, grab)
                return
            QTest.qWait(900)
            shot(name, w)
            state["done"] = True
            w.reject()

        QTimer.singleShot(300, grab)
        action.trigger()
        if not state["done"]:
            raise RuntimeError(f"{name}: the dialog did not open")

    capture_modal(win.act_header_footer, "monograph-pdf-header-footer.png")
    capture_modal(win.act_sec_protect, "monograph-pdf-password-protect.png")

    # review markup with the Comments panel
    open_doc(review)
    win._canvas.go_to_page(1)  # noqa: SLF001
    win._show_comments_panel()  # noqa: SLF001
    win.act_fit_width.trigger()
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-editing-comments.png")
    rdoc = win._document._backend._doc  # noqa: SLF001
    hl = rdoc[1].search_for("fell by 14 percent")
    call("monograph-pdf-editing-comments.png",
         (at_widget(win._left, 0.64, 0.118), "Every comment in one list"),  # noqa: SLF001
         (at_pdf(1, 28, (hl[0].y0 + hl[0].y1) / 2) if hl else at_pdf(1, 28, 160), "Highlighted text"),
         (at_pdf(1, 548, 372), "A note for the team"))

    # forms
    open_doc(form)
    win._left.setCurrentIndex(0)  # noqa: SLF001 — Pages tab
    if not win.act_highlight_fields.isChecked():
        win.act_highlight_fields.trigger()
    win.act_fit_width.trigger()
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-forms.png")
    call("monograph-pdf-forms.png",
         (at_pdf(0, 552, 171), "Type into a field"),
         (at_pdf(0, 372, 363), "Tick a box"),
         (at_pdf(0, 414, 315), "Pick from a list"))
    win.act_highlight_fields.trigger()  # leave the view option as it was

    # redaction marks (not applied; nothing is saved)
    open_doc(agreement)
    from core.redaction import mark_text

    for needle in ("4410-2207-9931", "Daniel Mercer", "0400 555 0123", "12 Quay Street"):
        mark_text(win._document, 0, needle)  # noqa: SLF001
    win._refresh_page_view(0)  # noqa: SLF001
    win.act_fit_width.trigger()
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-redaction.png")
    adoc = win._document._backend._doc  # noqa: SLF001
    acc = adoc[0].search_for("4410-2207-9931")
    call("monograph-pdf-redaction.png",
         (at_pdf(0, 28, (acc[0].y0 + acc[0].y1) / 2) if acc else at_pdf(0, 28, 160),
          "Marked to be removed for good"))

    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()

    # website illustrations and the social preview card
    for name, (headline, sub) in SHOTS.items():
        framed(out / name, web / name.replace(".png", "-framed.png"), headline=headline, sub=sub,
               callouts=CALLOUTS.get(name, []), dark="dark" in name)
        print("wrote", web / name.replace(".png", "-framed.png"))
    social_card(out / "monograph-pdf-select-text.png", ROOT / "resources" / "icons" / "source" / "monograph_pdf_logo_512.png",
                web / "monograph-pdf-social-preview.png")
    print("wrote", web / "monograph-pdf-social-preview.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
