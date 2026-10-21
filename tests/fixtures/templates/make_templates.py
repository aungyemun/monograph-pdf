"""Professional-looking template PDFs for every kind of Monograph PDF test.

Run:  env\\Scripts\\python.exe tests\\fixtures\\templates\\make_templates.py [--out <folder>]

Writes ``pdf/*.pdf`` and ``manifest.json`` next to this file (or into --out). Everything is generated with
PyMuPDF only: no external fonts (Base-14 plus the Droid Sans Fallback font that ships inside PyMuPDF), no personal
data, no network. All people, companies and numbers are fictional. ``README.md`` explains which template serves
which kind of test; ``tests/integration/test_templates.py`` checks every file against the manifest.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
A4 = (595.276, 841.89)
A4L = (A4[1], A4[0])
LETTER = (612.0, 792.0)
A3L = (1190.551, 841.89)
A5 = (419.528, 595.276)
NAVY = (0.09, 0.19, 0.38)
TEAL = (0.05, 0.46, 0.45)
ORANGE = (0.90, 0.45, 0.10)
GREY = (0.45, 0.47, 0.52)
LIGHT = (0.94, 0.95, 0.97)
ZEBRA = (0.97, 0.98, 0.99)
RULE = (0.75, 0.78, 0.83)
RED = (0.75, 0.12, 0.12)
BLACK = (0.08, 0.09, 0.11)
PASSWORD = "monograph"
DROID = fitz.Font("cjk")

LOREM = (
    "Monograph PDF is exercised with documents that look like the ones people really open: invoices, reports, "
    "papers, forms and scans. The sentences here are neutral filler written for testing; they describe nothing real. "
    "Selecting, highlighting, searching and editing should behave the same on every line of every page."
)
LOREM2 = (
    "A second paragraph keeps line breaks, spacing and wrapping honest. It contains numbers such as 1,234.50 and "
    "dates such as 2026-10-17, a hyphenated-compound, an e-mail address (sample@example.org) and a URL "
    "(https://example.org/path) so that text extraction and search have varied tokens to work with."
)


# ------------------------------------------------------------------------------------------------ helpers
def _fit_box(page, rect, text, *, size=10.0, font="helv", color=BLACK, align=0, min_size=5.0):
    """insert_textbox that shrinks the font until the text fits (a negative return value draws nothing)."""
    s = size
    while s >= min_size:
        rc = page.insert_textbox(rect, text, fontsize=s, fontname=font, color=color, align=align)
        if rc >= 0:
            return s
        s -= 0.5
    raise RuntimeError(f"text does not fit {rect}: {text[:40]!r}")


def _droid(page):
    page.insert_font(fontname="droid", fontbuffer=DROID.buffer)
    return "droid"


def band(page, title, subtitle="", *, color=NAVY, height=70.0, accent=TEAL):
    w = page.rect.width
    page.draw_rect(fitz.Rect(0, 0, w, height), color=None, fill=color)
    page.draw_rect(fitz.Rect(0, height, w, height + 4), color=None, fill=accent)
    page.insert_text((40, 32), title, fontsize=20, fontname="hebo", color=(1, 1, 1))
    if subtitle:
        page.insert_text((40, 52), subtitle, fontsize=10, fontname="helv", color=(0.82, 0.88, 0.95))


def footer(page, n, total, label):
    w, h = page.rect.width, page.rect.height
    page.draw_line((40, h - 42), (w - 40, h - 42), color=RULE, width=0.6)
    page.insert_text((40, h - 28), label, fontsize=8, fontname="helv", color=GREY)
    txt = f"Page {n} of {total}"
    page.insert_text((w - 40 - fitz.get_text_length(txt, "helv", 8), h - 28), txt, fontsize=8, fontname="helv", color=GREY)


def heading(page, y, text, *, size=14, x=40, color=NAVY):
    page.insert_text((x, y), text, fontsize=size, fontname="hebo", color=color)
    page.draw_line((x, y + 4), (x + 60, y + 4), color=TEAL, width=2)
    return y + size + 12


def table(page, x, y, widths, rows, *, header=True, size=9, row_h=20.0, align=None, zebra=True, header_fill=NAVY,
          negative_red=False):
    """Ruled table drawn as filled rectangles plus line segments (the form table detectors read). Returns bottom y."""
    align = align or ["l"] * len(widths)
    total_w = sum(widths)
    for r, row in enumerate(rows):
        top = y + r * row_h
        if header and r == 0:
            page.draw_rect(fitz.Rect(x, top, x + total_w, top + row_h), color=None, fill=header_fill)
        elif zebra and r % 2 == 0:
            page.draw_rect(fitz.Rect(x, top, x + total_w, top + row_h), color=None, fill=ZEBRA)
        cx = x
        for c, cell in enumerate(row):
            is_head = header and r == 0
            font = "hebo" if is_head else "helv"
            color = (1, 1, 1) if is_head else (RED if negative_red and str(cell).startswith("-") else BLACK)
            tw = fitz.get_text_length(str(cell), font, size)
            tx = cx + 6 if align[c] == "l" else (cx + widths[c] - 6 - tw if align[c] == "r" else cx + (widths[c] - tw) / 2)
            page.insert_text((tx, top + row_h / 2 + size * 0.35), str(cell), fontsize=size, fontname=font, color=color)
            cx += widths[c]
    bottom = y + len(rows) * row_h
    for r in range(len(rows) + 1):
        page.draw_line((x, y + r * row_h), (x + total_w, y + r * row_h), color=RULE, width=0.6)
    cx = x
    for w in [0] + list(widths):
        cx += w
        page.draw_line((cx, y), (cx, bottom), color=RULE, width=0.6)
    return bottom


def bar_chart(page, rect, labels, values, *, title="", color=TEAL):
    page.draw_rect(rect, color=RULE, fill=(1, 1, 1), width=0.8)
    if title:
        page.insert_text((rect.x0 + 10, rect.y0 + 16), title, fontsize=10, fontname="hebo", color=NAVY)
    left, bottom, top = rect.x0 + 34, rect.y1 - 24, rect.y0 + 30
    vmax = max(values) * 1.15
    for k in range(5):
        yy = bottom - (bottom - top) * k / 4
        page.draw_line((left, yy), (rect.x1 - 10, yy), color=(0.88, 0.9, 0.93), width=0.5)
        page.insert_text((rect.x0 + 6, yy + 3), f"{vmax * k / 4:.0f}", fontsize=7, fontname="helv", color=GREY)
    n = len(values)
    slot = (rect.x1 - 10 - left) / n
    for i, (lab, v) in enumerate(zip(labels, values)):
        x0 = left + i * slot + slot * 0.2
        x1 = left + (i + 1) * slot - slot * 0.2
        h = (bottom - top) * v / vmax
        page.draw_rect(fitz.Rect(x0, bottom - h, x1, bottom), color=None, fill=color if i % 2 == 0 else NAVY)
        page.insert_text((x0, bottom + 12), lab, fontsize=7, fontname="helv", color=GREY)


def line_chart(page, rect, series, *, title=""):
    page.draw_rect(rect, color=RULE, fill=(1, 1, 1), width=0.8)
    if title:
        page.insert_text((rect.x0 + 10, rect.y0 + 16), title, fontsize=10, fontname="hebo", color=NAVY)
    left, right, bottom, top = rect.x0 + 30, rect.x1 - 12, rect.y1 - 20, rect.y0 + 30
    for k in range(5):
        yy = bottom - (bottom - top) * k / 4
        page.draw_line((left, yy), (right, yy), color=(0.88, 0.9, 0.93), width=0.5)
    colors = [TEAL, ORANGE, NAVY]
    for si, ys in enumerate(series):
        pts = [fitz.Point(left + (right - left) * i / (len(ys) - 1), bottom - (bottom - top) * v) for i, v in enumerate(ys)]
        page.draw_polyline(pts, color=colors[si % 3], width=1.8)
        for p in pts:
            page.draw_circle(p, 2.2, color=colors[si % 3], fill=(1, 1, 1), width=1.2)


def _gradient_image(w, h, c1, c2, *, noise=0, seed=1, shapes=False) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        base = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        for x in range(w):
            n = rnd.randint(-noise, noise) if noise else 0
            px[x, y] = tuple(max(0, min(255, v + n)) for v in base)
    if shapes:
        d = ImageDraw.Draw(img)
        for _ in range(6):
            x0, y0 = rnd.randint(0, w - 40), rnd.randint(0, h - 40)
            d.ellipse((x0, y0, x0 + rnd.randint(20, 90), y0 + rnd.randint(20, 90)), outline=(255, 255, 255), width=3)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _doc():
    d = fitz.open()
    d.set_metadata({"title": "", "author": "Monograph PDF test templates", "creator": "make_templates.py", "producer": "PyMuPDF"})
    return d


# ------------------------------------------------------------------------------------------------ templates
def t_invoice():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "INVOICE", "Northwind Studio Ltd. (fictional)  ·  Invoice no. INV-2026-0417")
    y = 110
    for x, title, lines in ((40, "Bill to", ["Contoso Research GmbH", "Attn: Accounts Payable", "12 Example Street", "10115 Berlin, Germany"]),
                            (320, "Invoice details", ["Issue date: 2026-10-17", "Due date: 2026-11-16", "Terms: Net 30", "Currency: EUR"])):
        p.insert_text((x, y), title.upper(), fontsize=8, fontname="hebo", color=TEAL)
        for i, ln in enumerate(lines):
            p.insert_text((x, y + 16 + i * 13), ln, fontsize=10, fontname="helv", color=BLACK)
    rows = [["Item", "Description", "Qty", "Unit price", "Amount"]]
    items = [("DS-100", "Document design workshop", 2, 480.00), ("DS-210", "Template library (annual)", 1, 1250.00),
             ("SV-015", "On-site review, per day", 3, 720.00), ("SV-040", "Accessibility audit", 1, 960.00),
             ("LC-007", "Licence seat, per month", 12, 18.50)]
    total = 0.0
    for code, desc, q, price in items:
        amt = q * price
        total += amt
        rows.append([code, desc, str(q), f"{price:,.2f}", f"{amt:,.2f}"])
    bottom = table(p, 40, 210, [70, 230, 50, 90, 90], rows, align=["l", "l", "c", "r", "r"], row_h=24, size=9.5)
    vat = total * 0.19
    for i, (lab, val, bold) in enumerate((("Subtotal", total, False), ("VAT 19%", vat, False), ("Total due", total + vat, True))):
        f = "hebo" if bold else "helv"
        yy = bottom + 24 + i * 20
        if bold:
            p.draw_rect(fitz.Rect(320, yy - 14, 555, yy + 6), color=None, fill=LIGHT)
        p.insert_text((330, yy), lab, fontsize=10.5, fontname=f, color=NAVY if bold else BLACK)
        txt = f"{val:,.2f} EUR"
        p.insert_text((545 - fitz.get_text_length(txt, f, 10.5), yy), txt, fontsize=10.5, fontname=f, color=NAVY if bold else BLACK)
    p.insert_text((40, bottom + 30), "Payment details", fontsize=10, fontname="hebo", color=NAVY)
    for i, ln in enumerate(("IBAN DE00 0000 0000 0000 0000 00 (fictional)", "BIC EXAMPLEXXX", "Reference: INV-2026-0417")):
        p.insert_text((40, bottom + 46 + i * 13), ln, fontsize=9.5, fontname="helv", color=BLACK)
    footer(p, 1, 1, "Northwind Studio Ltd. · fictional sample invoice for software testing")
    return d, {"pages": [{"size": A4, "text": ["INVOICE", "Total due", "INV-2026-0417"], "table": {"rows": 6, "cols": 5}}]}


def t_report():
    d = _doc()
    toc = []
    p = d.new_page(width=A4[0], height=A4[1])
    p.draw_rect(p.rect, color=None, fill=NAVY)
    p.draw_rect(fitz.Rect(0, 520, A4[0], 530), color=None, fill=TEAL)
    p.insert_text((60, 300), "Annual Operations Report", fontsize=34, fontname="hebo", color=(1, 1, 1))
    p.insert_text((60, 340), "Fiscal year 2026  ·  fictional data for testing", fontsize=14, fontname="helv", color=(0.82, 0.88, 0.95))
    p.insert_text((60, 770), "Prepared by the Quality Team  ·  Confidential sample", fontsize=10, fontname="helv", color=(0.82, 0.88, 0.95))
    toc.append([1, "Cover", 1])
    # contents page
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Contents")
    secs = [("1  Summary", 3), ("2  Results by quarter", 4), ("3  Risks and actions", 5), ("4  Appendix", 6)]
    for i, (name, pg) in enumerate(secs):
        yy = 130 + i * 30
        p.insert_text((60, yy), name, fontsize=13, fontname="helv", color=BLACK)
        p.insert_text((500, yy), str(pg), fontsize=13, fontname="helv", color=GREY)
        p.draw_line((60 + fitz.get_text_length(name, "helv", 13) + 8, yy), (490, yy), color=RULE, width=0.6, dashes="[1 3] 0")
    toc.append([1, "Contents", 2])
    footer(p, 2, 6, "Annual Operations Report 2026")
    # summary
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "1  Summary")
    y = heading(p, 120, "Key messages")
    for ln in ("Revenue grew 8.4% year on year, ahead of plan.", "Customer-reported defects fell by one third.",
               "Three of four strategic projects are on schedule.", "Hiring remains the main constraint for the next quarter."):
        p.draw_circle((48, y - 3), 2.4, color=None, fill=TEAL)
        p.insert_text((58, y), ln, fontsize=10.5, fontname="helv", color=BLACK)
        y += 18
    y = heading(p, y + 14, "Background")
    _fit_box(p, fitz.Rect(40, y - 4, 555, y + 90), LOREM, size=10.5)
    _fit_box(p, fitz.Rect(40, y + 96, 555, y + 190), LOREM2, size=10.5)
    bar_chart(p, fitz.Rect(40, y + 210, 300, y + 400), ["Q1", "Q2", "Q3", "Q4"], [118, 131, 127, 149], title="Revenue (kEUR)")
    line_chart(p, fitz.Rect(315, y + 210, 555, y + 400), [[0.2, 0.35, 0.5, 0.7, 0.8], [0.15, 0.2, 0.3, 0.45, 0.5]], title="Defects per release")
    toc.append([1, "1 Summary", 3])
    footer(p, 3, 6, "Annual Operations Report 2026")
    # results table
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "2  Results by quarter")
    y = heading(p, 120, "Operating figures")
    rows = [["Metric", "Q1", "Q2", "Q3", "Q4", "Year"], ["Revenue (kEUR)", "118", "131", "127", "149", "525"],
            ["Operating cost (kEUR)", "96", "101", "99", "108", "404"], ["Margin (%)", "18.6", "22.9", "22.0", "27.5", "23.0"],
            ["Headcount", "41", "43", "46", "47", "47"], ["Open defects", "52", "38", "31", "27", "27"]]
    b = table(p, 40, y, [170, 70, 70, 70, 70, 70], rows, align=["l", "r", "r", "r", "r", "r"], row_h=22)
    _fit_box(p, fitz.Rect(40, b + 20, 555, b + 130), LOREM, size=10.5)
    toc.append([1, "2 Results by quarter", 4])
    footer(p, 4, 6, "Annual Operations Report 2026")
    # risks
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "3  Risks and actions")
    y = heading(p, 120, "Register")
    rows = [["ID", "Risk", "Owner", "Level"], ["R-01", "Key supplier delay", "Procurement", "High"], ["R-02", "Hiring shortfall", "People", "High"],
            ["R-03", "Data migration slip", "Platform", "Medium"], ["R-04", "Regulatory change", "Legal", "Low"]]
    table(p, 40, y, [50, 250, 120, 95], rows, row_h=22)
    toc.append([1, "3 Risks and actions", 5])
    footer(p, 5, 6, "Annual Operations Report 2026")
    # appendix
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "4  Appendix")
    y = heading(p, 120, "Glossary")
    for i, (term, desc) in enumerate((("KPI", "Key performance indicator"), ("QoQ", "Quarter on quarter"), ("SLA", "Service level agreement"))):
        p.insert_text((40, y + i * 18), term, fontsize=10.5, fontname="hebo", color=NAVY)
        p.insert_text((110, y + i * 18), desc, fontsize=10.5, fontname="helv", color=BLACK)
    toc.append([1, "4 Appendix", 6])
    footer(p, 6, 6, "Annual Operations Report 2026")
    d.set_toc(toc)
    return d, {"pages": 6, "toc": len(toc), "text": ["Annual Operations Report", "Revenue", "Risks and actions"]}


def t_paper():
    d = _doc()
    dr = None
    for pi in range(2):
        d.new_page(width=A4[0], height=A4[1])
    p = d[0]
    dr = _droid(p)
    p.insert_text((40, 60), "Spectral Estimation of Sparse Signals under Structured Noise", fontsize=17, fontname="hebo", color=NAVY)
    p.insert_text((40, 80), "A. Researcher, B. Example (fictional authors)  ·  Journal of Illustrative Methods, 2026", fontsize=9, fontname="helv", color=GREY)
    p.draw_rect(fitz.Rect(40, 94, 555, 168), color=None, fill=LIGHT)
    _fit_box(p, fitz.Rect(48, 98, 547, 166), "Abstract. We study the estimation of sparse spectra when the noise is structured. Using a regularised "
             "least-squares formulation we obtain an estimator with error bounds that scale as O(s log n / m). Simulations (n = 512) "
             "confirm the bound within 7%. Keywords: sparse recovery, spectral estimation, noise.", size=8.5)
    col = [(40, 275), (300, 555)]
    body = (LOREM + " " + LOREM2) * 2
    y = 190
    for x0, x1 in col:
        yy = 188
        p.insert_text((x0, yy), "1  Introduction", fontsize=11, fontname="hebo", color=NAVY)
        _fit_box(p, fitz.Rect(x0, yy + 6, x1, yy + 190), body, size=8.8)
        yy += 200
        p.insert_text((x0, yy), "2  Method", fontsize=11, fontname="hebo", color=NAVY)
        eq = ["x* = argmin |y - Ax|^2 + λ|x|_1", "E|x* - x|^2 ≤ C σ^2 s log(n) / m", "S(f) = ∑ a_k δ(f - f_k),  k = 1..s"]
        for i, e in enumerate(eq):
            p.insert_text((x0 + 8, yy + 22 + i * 18), e, fontsize=9.5, fontname=dr, color=BLACK)
            p.insert_text((x1 - 22, yy + 22 + i * 18), f"({i + 1})", fontsize=9, fontname="helv", color=GREY)
        _fit_box(p, fitz.Rect(x0, yy + 80, x1, yy + 250), body[:420], size=8.8)
        break
    # second column body
    x0, x1 = col[1]
    _fit_box(p, fitz.Rect(x0, 194, x1, 380), body, size=8.8)
    p.insert_text((x0, 400), "3  Results", fontsize=11, fontname="hebo", color=NAVY)
    # figure: scatter plot with axes
    fig = fitz.Rect(x0, 410, x1, 590)
    p.draw_rect(fig, color=RULE, fill=(1, 1, 1), width=0.8)
    rnd = random.Random(4)
    for k in range(5):
        p.draw_line((fig.x0 + 26, fig.y1 - 22 - k * 28), (fig.x1 - 8, fig.y1 - 22 - k * 28), color=(0.88, 0.9, 0.93), width=0.4)
    pts = []
    for i in range(40):
        xx = fig.x0 + 30 + i * 5.2
        yy = fig.y1 - 24 - (math.log(i + 2) * 28 + rnd.uniform(-6, 6))
        pts.append(fitz.Point(xx, yy))
        p.draw_circle(fitz.Point(xx, yy), 1.6, color=TEAL, fill=TEAL)
    p.draw_polyline([fitz.Point(fig.x0 + 30 + i * 5.2, fig.y1 - 24 - math.log(i + 2) * 28) for i in range(40)], color=ORANGE, width=1.4)
    p.insert_text((fig.x0 + 6, fig.y0 + 12), "Fig. 1  Error vs. samples (m)", fontsize=8, fontname="hebo", color=NAVY)
    p.insert_text((fig.x1 - 80, fig.y1 - 6), "samples m →", fontsize=7, fontname="helv", color=GREY)
    footer(p, 1, 2, "Journal of Illustrative Methods · fictional sample paper")
    p = d[1]
    _droid(p)
    p.insert_text((40, 60), "3.1  Table of errors", fontsize=11, fontname="hebo", color=NAVY)
    rows = [["n", "s", "m", "Bound", "Observed"], ["128", "6", "64", "0.412", "0.388"], ["256", "8", "96", "0.356", "0.331"],
            ["512", "12", "160", "0.301", "0.284"], ["1024", "16", "256", "0.262", "0.249"]]
    table(p, 40, 70, [60, 60, 60, 90, 90], rows, align=["r"] * 5, row_h=20, size=9)
    p.insert_text((40, 200), "References", fontsize=11, fontname="hebo", color=NAVY)
    refs = ["[1] Example A. Sparse recovery revisited. J. Illustr. Methods 12, 1–20 (2020).",
            "[2] Sample B., Test C. Structured noise models. Proc. Fictional Conf. 3, 45–52 (2022).",
            "[3] Placeholder D. Notes on spectral estimation. Tech. Rep. 17 (2025)."]
    for i, r in enumerate(refs):
        _fit_box(p, fitz.Rect(40, 210 + i * 26, 555, 236 + i * 26), r, size=9)
    footer(p, 2, 2, "Journal of Illustrative Methods · fictional sample paper")
    return d, {"pages": 2, "text": ["Spectral Estimation", "Abstract", "References"], "equations": True}


def t_form():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Membership Application", "Fictional association · please complete all sections")

    def label(x, y, t):
        p.insert_text((x, y), t, fontsize=8.5, fontname="hebo", color=NAVY)

    def sect(y, t):
        p.draw_rect(fitz.Rect(40, y, 555, y + 18), color=None, fill=LIGHT)
        p.insert_text((46, y + 12.5), t, fontsize=10, fontname="hebo", color=TEAL)

    def widget(name, kind, rect, **kw):
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect = name, kind, fitz.Rect(rect)
        w.border_color, w.fill_color = (0.55, 0.6, 0.7), (0.97, 0.98, 1)
        w.border_width = 0.8
        for k, v in kw.items():
            setattr(w, k, v)
        p.add_widget(w)

    sect(95, "1  Personal details")
    for (x, y, lab, name, wd) in ((40, 130, "First name", "first_name", 230), (300, 130, "Last name", "last_name", 255),
                                  (40, 175, "E-mail", "email", 230), (300, 175, "Phone", "phone", 255)):
        label(x, y, lab)
        widget(name, fitz.PDF_WIDGET_TYPE_TEXT, (x, y + 4, x + wd, y + 24), text_fontsize=10)
    label(40, 220, "Date of birth (YYYY-MM-DD)")
    widget("dob", fitz.PDF_WIDGET_TYPE_TEXT, (40, 224, 200, 244), text_fontsize=10)
    label(300, 220, "Country")
    widget("country", fitz.PDF_WIDGET_TYPE_COMBOBOX, (300, 224, 555, 244), choice_values=["Germany", "Japan", "Myanmar", "United States", "Other"], field_value="Japan", text_fontsize=10)
    sect(262, "2  Membership")
    label(40, 296, "Plan")
    for i, (val, txt) in enumerate((("basic", "Basic"), ("plus", "Plus"), ("patron", "Patron"))):
        widget("plan", fitz.PDF_WIDGET_TYPE_RADIOBUTTON, (46 + i * 110, 304, 58 + i * 110, 316), field_value="Off")
        p.insert_text((64 + i * 110, 314), txt, fontsize=10, fontname="helv", color=BLACK)
    label(40, 342, "Interests")
    for i, (n, txt) in enumerate((("int_events", "Events"), ("int_news", "Newsletter"), ("int_vol", "Volunteering"))):
        widget(n, fitz.PDF_WIDGET_TYPE_CHECKBOX, (46 + i * 130, 350, 58 + i * 130, 362))
        p.insert_text((64 + i * 130, 360), txt, fontsize=10, fontname="helv", color=BLACK)
    label(40, 388, "Topics (choose several)")
    widget("topics", fitz.PDF_WIDGET_TYPE_LISTBOX, (40, 392, 250, 452), choice_values=["Design", "Research", "Teaching", "Tools"])
    label(300, 388, "Comments")
    widget("comments", fitz.PDF_WIDGET_TYPE_TEXT, (300, 392, 555, 452), field_flags=fitz.PDF_TX_FIELD_IS_MULTILINE, text_fontsize=10)
    sect(470, "3  Declaration")
    _fit_box(p, fitz.Rect(40, 494, 555, 540), "I confirm that the information given is correct and agree to the association's (fictional) terms of "
             "membership. This form is a test document; nothing entered here is stored or sent anywhere.", size=9.5)
    label(40, 574, "Signature")
    widget("signature", fitz.PDF_WIDGET_TYPE_SIGNATURE, (40, 580, 300, 625))
    label(330, 574, "Date")
    widget("sign_date", fitz.PDF_WIDGET_TYPE_TEXT, (330, 580, 555, 600), text_fontsize=10)
    footer(p, 1, 1, "Fictional association · sample AcroForm for software testing")
    return d, {"pages": 1, "widgets": ["first_name", "last_name", "email", "phone", "dob", "country", "plan", "int_events", "topics", "comments", "signature", "sign_date"]}


def t_contract():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Service Agreement", "Between Northwind Studio Ltd. and Contoso Research GmbH (both fictional)")
    clauses = [("1. Scope", LOREM), ("2. Fees and payment", "Fees are invoiced monthly. Undisputed invoices are payable within thirty (30) days of the invoice date. " + LOREM2),
               ("3. Confidentiality", LOREM), ("4. Term and termination", "This agreement starts on 2026-11-01 and runs for twelve (12) months. " + LOREM2)]
    y = 108
    for title, body in clauses:
        p.insert_text((40, y), title, fontsize=11, fontname="hebo", color=NAVY)
        _fit_box(p, fitz.Rect(40, y + 6, 555, y + 92), body, size=9.8)
        y += 104
    p.insert_text((40, 560), "Signatures", fontsize=11, fontname="hebo", color=NAVY)
    for i, who in enumerate(("For Northwind Studio Ltd.", "For Contoso Research GmbH")):
        x = 40 + i * 270
        p.draw_line((x, 640), (x + 230, 640), color=BLACK, width=0.8)
        p.insert_text((x, 654), who, fontsize=9, fontname="helv", color=GREY)
        p.insert_text((x, 668), "Name / date", fontsize=8, fontname="helv", color=GREY)
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect = f"signature_{i + 1}", fitz.PDF_WIDGET_TYPE_SIGNATURE, fitz.Rect(x, 585, x + 230, 636)
        p.add_widget(w)
    footer(p, 1, 1, "Fictional contract for signature-handling tests · unsigned (no cryptographic signature present)")
    return d, {"pages": 1, "signature_fields": 2, "text": ["Service Agreement", "Confidentiality"]}


def t_japanese():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    dr = _droid(p)
    p.draw_rect(fitz.Rect(0, 0, A4[0], 74), color=None, fill=NAVY)
    p.insert_text((40, 46), "お知らせ　年次点検のご案内", fontsize=20, fontname=dr, color=(1, 1, 1))
    lines = ["平成ではなく令和八年十月十七日", "関係者各位", "", "下記のとおり、定期点検を実施いたします。ご協力をお願い申し上げます。",
             "日時：二〇二六年十一月四日（水）午前九時から正午まで", "場所：本館三階 会議室Ａ", "持ち物：筆記用具、社員証", "", "なお、これは試験用の架空の文書です。"]
    for i, ln in enumerate(lines):
        p.insert_text((50, 120 + i * 26), ln, fontsize=12, fontname=dr, color=BLACK)
    rows = [["項目", "内容", "担当"], ["受付", "三階ロビー", "総務部"], ["点検", "設備・防災", "施設課"], ["報告", "後日メールで送付", "品質管理"]]
    # Japanese table drawn with the same ruled-line style
    x, y, widths, rh = 50, 380, [110, 210, 110], 26
    for r, row in enumerate(rows):
        top = y + r * rh
        if r == 0:
            p.draw_rect(fitz.Rect(x, top, x + sum(widths), top + rh), color=None, fill=NAVY)
        cx = x
        for c, cell in enumerate(row):
            p.insert_text((cx + 8, top + 18), cell, fontsize=11, fontname=dr, color=(1, 1, 1) if r == 0 else BLACK)
            cx += widths[c]
    for r in range(len(rows) + 1):
        p.draw_line((x, y + r * rh), (x + sum(widths), y + r * rh), color=RULE, width=0.6)
    cx = x
    for w in [0] + widths:
        cx += w
        p.draw_line((cx, y), (cx, y + len(rows) * rh), color=RULE, width=0.6)
    p.insert_text((40, 800), "第 1 ページ / 全 1 ページ　（架空の試験文書）", fontsize=9, fontname=dr, color=GREY)
    d.subset_fonts()
    return d, {"pages": 1, "text": ["お知らせ", "年次点検", "定期点検"], "embedded_fonts": True}


def t_bilingual():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    dr = _droid(p)
    band(p, "Welcome Letter · ご挨拶", "English and Japanese in one document")
    p.insert_text((40, 120), "Dear Ms. Sample,", fontsize=11, fontname="helv", color=BLACK)
    _fit_box(p, fitz.Rect(40, 130, 555, 260), "Thank you for joining our program. Your orientation starts on 2026-11-04 at 9:00. Please bring your "
             "ID card and a notebook. If you have any questions, write to sample@example.org.", size=11)
    p.insert_text((40, 290), "サンプル様", fontsize=11, fontname=dr, color=BLACK)
    for i, ln in enumerate(("プログラムへのご参加ありがとうございます。", "オリエンテーションは二〇二六年十一月四日の九時から始まります。", "身分証明書とノートをお持ちください。",
                            "ご不明な点は sample@example.org までご連絡ください。")):
        p.insert_text((40, 316 + i * 22), ln, fontsize=11, fontname=dr, color=BLACK)
    p.insert_text((40, 440), "Order 2026-17 注文番号 Hello  ·  Mixed: 価格 ¥1,200 (税込 1,320 JPY)", fontsize=11, fontname=dr, color=BLACK)
    d.subset_fonts()
    return d, {"pages": 1, "text": ["Welcome Letter", "Order 2026-17", "プログラム"], "embedded_fonts": True}


def t_statement():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Account Statement", "Account 0000-1234 (fictional)  ·  October 2026")
    y = heading(p, 110, "Transactions")
    rows = [["Date", "Description", "Debit", "Credit", "Balance"]]
    bal = 2500.0
    rnd = random.Random(11)
    for i in range(14):
        amt = round(rnd.uniform(15, 420), 2)
        if i % 4 == 3:
            bal += amt * 2
            rows.append([f"2026-10-{i + 2:02d}", "Transfer in", "", f"{amt * 2:,.2f}", f"{bal:,.2f}"])
        else:
            bal -= amt
            rows.append([f"2026-10-{i + 2:02d}", ("Card payment", "Standing order", "Direct debit")[i % 3], f"{amt:,.2f}", "", f"{bal:,.2f}"])
    b = table(p, 40, y, [80, 190, 80, 80, 85], rows, align=["l", "l", "r", "r", "r"], row_h=20, size=9)
    y = heading(p, b + 30, "Summary")
    rows = [["Item", "Amount"], ["Opening balance", "2,500.00"], ["Total debits", "-2,314.37"], ["Total credits", "1,480.12"], ["Closing balance", f"{bal:,.2f}"]]
    table(p, 40, y, [200, 120], rows, align=["l", "r"], row_h=20, negative_red=True)
    footer(p, 1, 1, "Fictional account statement · table-extraction test document")
    return d, {"pages": 1, "tables": 2}


def t_brochure():
    d = _doc()
    p = d.new_page(width=A4L[0], height=A4L[1])
    p.insert_image(fitz.Rect(0, 0, A4L[0], 330), stream=_gradient_image(842, 330, (20, 60, 120), (10, 140, 140), noise=4, shapes=True))
    p.draw_rect(fitz.Rect(0, 330, A4L[0], 338), color=None, fill=ORANGE)
    p.insert_text((50, 150), "Design for everyone", fontsize=40, fontname="hebo", color=(1, 1, 1))
    p.insert_text((52, 186), "A fictional product brochure used to test rendering, highlighting over images and slide export", fontsize=13, fontname="helv", color=(0.9, 0.95, 1))
    cols = [("Fast", "Opens large files in a blink and keeps the view smooth while you work."), ("Private", "Everything stays on your computer: no uploads and no telemetry."),
            ("Precise", "Fonts, sizes and positions stay exactly where you put them.")]
    for i, (h, t) in enumerate(cols):
        x = 50 + i * 255
        p.draw_rect(fitz.Rect(x, 370, x + 235, 540), color=RULE, fill=(0.97, 0.98, 1), width=0.8)
        p.draw_circle(fitz.Point(x + 30, 400), 14, color=None, fill=[TEAL, ORANGE, NAVY][i])
        p.insert_text((x + 54, 406), h, fontsize=15, fontname="hebo", color=NAVY)
        _fit_box(p, fitz.Rect(x + 14, 420, x + 222, 530), t, size=10.5)
    p.insert_image(fitz.Rect(560, 360, 800, 520), stream=_gradient_image(240, 160, (240, 160, 60), (200, 60, 90), noise=6, seed=3, shapes=True))
    p.insert_text((50, 560), "© Fictional Company · brochure.example.org", fontsize=9, fontname="helv", color=GREY)
    return d, {"pages": 1, "size": A4L, "images": 2, "text": ["Design for everyone", "Private"]}


def _scan_from_page(build_text, *, dpi=300, noise=0, skew=0.0, blur=0.0, seed=2):
    src = fitz.open()
    sp = src.new_page(width=A4[0], height=A4[1])
    build_text(sp)
    pix = sp.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if skew:
        img = img.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        rnd = random.Random(seed)
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                px[x, y] = max(0, min(255, px[x, y] + rnd.randint(-noise, noise)))
    import io

    buf = io.BytesIO()
    img.convert("L").save(buf, format="JPEG", quality=82, dpi=(dpi, dpi))
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    p.insert_image(p.rect, stream=buf.getvalue())
    return d


def _memo_text(sp):
    sp.insert_text((60, 90), "MEMORANDUM", fontsize=24, fontname="hebo", color=BLACK)
    sp.draw_line((60, 100), (535, 100), color=BLACK, width=1.2)
    for i, (k, v) in enumerate((("To:", "All department heads"), ("From:", "Facilities Office"), ("Date:", "17 October 2026"), ("Subject:", "Scheduled maintenance window"))):
        sp.insert_text((60, 134 + i * 20), k, fontsize=11, fontname="hebo", color=BLACK)
        sp.insert_text((130, 134 + i * 20), v, fontsize=11, fontname="helv", color=BLACK)
    _fit_box(sp, fitz.Rect(60, 240, 535, 420), "The main building will be closed for maintenance on Saturday 7 November from 08:00 to 18:00. "
             "Please save your work, shut down workstations on Friday evening and remove perishable items from shared refrigerators. "
             "Access cards will not work during the window. Contact the facilities desk on extension 4417 for urgent needs.", size=12)
    sp.insert_text((60, 460), "Thank you for your cooperation.", fontsize=12, fontname="helv", color=BLACK)


def t_scanned():
    return _scan_from_page(_memo_text, dpi=300), {"pages": 1, "scanned": True, "scan_text": "MEMORANDUM", "images": 1}


def t_scanned_noisy():
    return _scan_from_page(_memo_text, dpi=200, noise=22, skew=1.3, blur=0.8), {"pages": 1, "scanned": True, "scan_text": "MEMORANDUM", "images": 1}


def t_mixed():
    d = _doc()
    specs = [("A4 portrait", A4, 0), ("US Letter", LETTER, 0), ("A3 landscape", A3L, 0), ("A5 portrait", A5, 0),
             ("A4 rotated 90", A4, 90), ("A4 rotated 180", A4, 180), ("A4 rotated 270", A4, 270)]
    for name, size, rot in specs:
        p = d.new_page(width=size[0], height=size[1])
        p.draw_rect(fitz.Rect(20, 20, size[0] - 20, size[1] - 20), color=NAVY, width=1.5)
        p.draw_rect(fitz.Rect(20, 20, size[0] - 20, 70), color=None, fill=NAVY)
        p.insert_text((36, 52), f"{name}  ·  {int(size[0])} × {int(size[1])} pt", fontsize=16, fontname="hebo", color=(1, 1, 1))
        p.insert_text((36, 110), "TOP-LEFT of the unrotated page (anchor text)", fontsize=11, fontname="helv", color=BLACK)
        p.draw_polyline([fitz.Point(60, 160), fitz.Point(160, 160), fitz.Point(60, 260)], color=ORANGE, fill=ORANGE, closePath=True)
        p.insert_text((36, size[1] - 36), "BOTTOM of the unrotated page", fontsize=11, fontname="helv", color=GREY)
        if rot:
            p.set_rotation(rot)
    return d, {"pages": len(specs), "rotations": [s[2] for s in specs], "sizes": [list(s[1]) for s in specs]}


def t_annotated():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Review copy", "Annotations of many kinds (fictional)")
    _fit_box(p, fitz.Rect(40, 110, 555, 230), LOREM + " " + LOREM2, size=11)
    _fit_box(p, fitz.Rect(40, 250, 555, 360), LOREM2 + " " + LOREM, size=11)
    for needle, color in (("Selecting, highlighting", (1, 0.95, 0.2)), ("regularly", (0.6, 1, 0.6))):
        for r in p.search_for(needle)[:1]:
            a = p.add_highlight_annot(r)
            a.set_colors(stroke=color)
            a.update()
    for r in p.search_for("hyphenated-compound")[:1]:
        p.add_underline_annot(r).update()
    for r in p.search_for("e-mail address")[:1]:
        p.add_strikeout_annot(r).update()
    p.add_text_annot(fitz.Point(520, 118), "Please check the wording of this paragraph.", icon="Comment")
    a = p.add_freetext_annot(fitz.Rect(300, 400, 555, 440), "Free-text callout: approved", fontsize=11, text_color=NAVY, fill_color=(1, 1, 0.85), border_color=NAVY)
    a.update()
    p.add_rect_annot(fitz.Rect(40, 400, 260, 450)).update()
    c = p.add_circle_annot(fitz.Rect(60, 470, 160, 530))
    c.set_colors(stroke=RED)
    c.update()
    ln = p.add_line_annot(fitz.Point(200, 500), fitz.Point(400, 540))
    ln.set_colors(stroke=ORANGE)
    ln.update()
    ink = p.add_ink_annot([[(60, 600), (110, 580), (160, 610), (210, 585)]])
    ink.set_colors(stroke=(0.1, 0.3, 0.9))
    ink.set_border(width=2.5)
    ink.update()
    p.add_stamp_annot(fitz.Rect(380, 580, 540, 640), stamp=0).update()
    footer(p, 1, 1, "Annotated review copy · for annotation, highlight and export tests")
    return d, {"pages": 1, "annots": ["Highlight", "Highlight", "Underline", "StrikeOut", "Text", "FreeText", "Square", "Circle", "Line", "Ink", "Stamp"]}


def t_highlight_playground():
    """One page with every kind of surface a highlighter meets: text, margins, image, table, chart, colour block, dark graphic."""
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Highlight playground", "Text · blank margins · image · table · chart · colour fields · dark graphics")
    _fit_box(p, fitz.Rect(70, 100, 525, 190), LOREM, size=11)
    _fit_box(p, fitz.Rect(70, 200, 525, 290), LOREM2, size=11)
    p.insert_image(fitz.Rect(70, 305, 300, 430), stream=_gradient_image(230, 125, (250, 220, 120), (60, 120, 200), noise=3, seed=6, shapes=True))
    p.insert_text((70, 446), "Figure A – picture with texture", fontsize=8.5, fontname="helv", color=GREY)
    table(p, 320, 305, [70, 70, 70], [["A", "B", "C"], ["1", "2", "3"], ["4", "", "6"], ["7", "8", ""]], row_h=24, size=10, align=["c"] * 3)
    bar_chart(p, fitz.Rect(70, 470, 300, 620), ["N", "E", "S", "W"], [30, 52, 44, 61], title="Chart")
    p.draw_rect(fitz.Rect(320, 470, 525, 545), color=None, fill=(0.80, 0.93, 0.80))
    p.insert_text((330, 500), "Text on a green field", fontsize=12, fontname="helv", color=BLACK)
    p.draw_rect(fitz.Rect(320, 555, 525, 620), color=None, fill=(0.10, 0.12, 0.16))
    p.insert_text((330, 590), "White text on dark", fontsize=12, fontname="helv", color=(1, 1, 1))
    p.draw_circle(fitz.Point(120, 690), 36, color=NAVY, fill=ORANGE, width=2)
    p.draw_polyline([fitz.Point(200, 720), fitz.Point(260, 660), fitz.Point(320, 720)], color=TEAL, fill=TEAL, closePath=True)
    p.insert_text((350, 700), "Blank area to the right and below is intentionally empty.", fontsize=9, fontname="helv", color=GREY)
    footer(p, 1, 1, "Highlight playground · fictional")
    return d, {"pages": 1, "images": 1, "text": ["Highlight playground", "Figure A", "White text on dark"]}


def t_transparency():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Transparency and overlap", "Layered translucent shapes over text")
    _fit_box(p, fitz.Rect(60, 110, 540, 260), LOREM + " " + LOREM2, size=12)
    for i, (c, x) in enumerate(((TEAL, 100), (ORANGE, 180), (NAVY, 260))):
        p.draw_circle(fitz.Point(x + 40, 330), 60, color=None, fill=c, fill_opacity=0.45)
    p.draw_rect(fitz.Rect(60, 420, 540, 470), color=None, fill=(1, 0.9, 0.1), fill_opacity=0.5)
    p.insert_text((70, 452), "Text under a 50% yellow band", fontsize=16, fontname="hebo", color=BLACK)
    footer(p, 1, 1, "Transparency groups · for rendering and annotation-over-graphics tests")
    return d, {"pages": 1, "text": ["Transparency and overlap"]}


def t_images():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Image-heavy page", "Photographic-style images (generated)")
    seeds = [((250, 200, 140), (40, 90, 160)), ((60, 160, 110), (230, 230, 90)), ((200, 80, 80), (40, 40, 100)), ((90, 90, 90), (240, 240, 240))]
    for i, (c1, c2) in enumerate(seeds):
        r = fitz.Rect(40 + (i % 2) * 265, 110 + (i // 2) * 250, 40 + (i % 2) * 265 + 250, 110 + (i // 2) * 250 + 230)
        p.insert_image(r, stream=_gradient_image(500, 460, c1, c2, noise=14, seed=i + 5, shapes=True))
        p.insert_text((r.x0, r.y1 + 14), f"Plate {i + 1}", fontsize=9, fontname="helv", color=GREY)
    footer(p, 1, 1, "Image-heavy page · optimisation and image-export tests")
    return d, {"pages": 1, "images": 4}


def t_long():
    d = _doc()
    toc = []
    n = 200
    for i in range(n):
        p = d.new_page(width=A4[0], height=A4[1])
        if i % 10 == 0:
            toc.append([1, f"Part {i // 10 + 1}", i + 1])
        band(p, f"Chapter {i // 10 + 1}", f"Section {i + 1}", height=50)
        _fit_box(p, fitz.Rect(50, 90, 545, 300), LOREM + " " + LOREM2, size=11)
        _fit_box(p, fitz.Rect(50, 310, 545, 520), (LOREM2 + " " + LOREM) * 1, size=11)
        footer(p, i + 1, n, "Long document · performance test")
    d.set_toc(toc)
    return d, {"pages": n, "toc": len(toc)}


def t_empty():
    d = _doc()
    d.new_page(width=A4[0], height=A4[1])
    return d, {"pages": 1, "text": []}


def t_cropbox():
    d = _doc()
    p = d.new_page(width=612, height=792)
    p.draw_rect(fitz.Rect(10, 10, 602, 782), color=RED, width=2)
    p.insert_text((70, 100), "CropBox is inset from the MediaBox (50, 60, 562, 732)", fontsize=14, fontname="hebo", color=NAVY)
    p.insert_text((70, 130), "Only this inner region should be visible and measured.", fontsize=11, fontname="helv", color=BLACK)
    p.draw_circle(fitz.Point(306, 400), 90, color=NAVY, fill=LIGHT, width=2)
    p.set_cropbox(fitz.Rect(50, 60, 562, 732))
    return d, {"pages": 1, "cropbox": [50, 60, 562, 732], "mediabox": [0, 0, 612, 792]}


def t_fonts():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Fonts", "Base-14 faces and an embedded subset font")
    y = 110
    for name, fn in (("Helvetica", "helv"), ("Helvetica Bold", "hebo"), ("Helvetica Oblique", "heit"), ("Times Roman", "tiro"), ("Times Bold", "tibo"),
                     ("Courier", "cour"), ("Courier Bold", "cobo"), ("Symbol", "symb")):
        p.insert_text((40, y), f"{name}: The quick brown fox jumps over the lazy dog 0123456789", fontsize=12, fontname=fn, color=BLACK)
        y += 26
    dr = _droid(p)
    p.insert_text((40, y + 10), "Embedded subset (Droid Sans Fallback): The quick brown fox — 日本語 — ∑ ∫ ± √ π", fontsize=12, fontname=dr, color=BLACK)
    d.subset_fonts()
    return d, {"pages": 1, "text": ["Helvetica", "Embedded subset"], "embedded_fonts": True}


def t_two_column_text():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Newsletter", "Two columns with headings and a pull quote")
    for x0, x1 in ((40, 285), (310, 555)):
        _fit_box(p, fitz.Rect(x0, 110, x1, 420), (LOREM + " " + LOREM2) * 2, size=10)
    p.draw_rect(fitz.Rect(40, 440, 555, 520), color=None, fill=LIGHT)
    p.draw_rect(fitz.Rect(40, 440, 46, 520), color=None, fill=TEAL)
    _fit_box(p, fitz.Rect(60, 452, 540, 510), "“Good documents are the ones nobody notices: everything is where you expect it.”", size=15, font="heit", color=NAVY)
    footer(p, 1, 1, "Two-column layout · text-flow and conversion tests")
    return d, {"pages": 1, "text": ["Newsletter"]}


# ------------------------------------------------------------------------------------------------ v0.3.0 templates
SLIDE169 = (960.0, 540.0)
SLIDE43 = (720.0, 540.0)
A1 = (1683.78, 2383.94)


def _jpeg(w, h, *, seed=1, quality=90) -> bytes:
    """A photo-like JPEG (smooth gradients, soft blobs and grain) that compresses like a real photograph."""
    import io

    rnd = random.Random(seed)
    r = Image.linear_gradient("L").resize((w, h))
    g = Image.radial_gradient("L").resize((w, h)).rotate(30 + seed * 17)
    b = Image.linear_gradient("L").rotate(90).resize((w, h))
    img = Image.merge("RGB", (r, g, b))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x0, y0 = rnd.randint(0, w), rnd.randint(0, h)
        rad = rnd.randint(w // 40, w // 8)
        d.ellipse((x0 - rad, y0 - rad, x0 + rad, y0 + rad),
                  fill=(rnd.randint(30, 230), rnd.randint(30, 230), rnd.randint(30, 230)))
    img = img.filter(ImageFilter.GaussianBlur(max(2, w // 300)))
    random.seed(seed)
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    img = Image.blend(img, noise, 0.12)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


def _micrograph(w, h, *, seed=1, channel=(40, 220, 90)) -> bytes:
    """Synthetic fluorescence micrograph: dark field with blurred nuclei in one colour, plus a scale bar."""
    import io

    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (4, 6, 8))
    d = ImageDraw.Draw(img)
    for _ in range(70):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        rad = rnd.randint(6, 16)
        k = rnd.uniform(0.4, 1.0)
        d.ellipse((x - rad, y - rad * 0.8, x + rad, y + rad * 0.8), fill=tuple(int(c * k) for c in channel))
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    d = ImageDraw.Draw(img)
    d.rectangle((w - 70, h - 16, w - 20, h - 12), fill=(235, 235, 235))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def t_slides():
    d = _doc()
    total = 5
    p = d.new_page(width=SLIDE169[0], height=SLIDE169[1])
    p.draw_rect(p.rect, color=None, fill=NAVY)
    p.draw_rect(fitz.Rect(0, 380, SLIDE169[0], 388), color=None, fill=TEAL)
    p.insert_text((70, 250), "Quarterly Research Review", fontsize=44, fontname="hebo", color=(1, 1, 1))
    p.insert_text((72, 300), "Programme update · Q3 2026 · fictional data for testing", fontsize=18, fontname="helv",
                  color=(0.82, 0.88, 0.95))
    p.insert_text((72, 440), "Monograph Lab (fictional)", fontsize=14, fontname="helv", color=(0.82, 0.88, 0.95))
    p = d.new_page(width=SLIDE169[0], height=SLIDE169[1])
    band(p, "Highlights", "What changed this quarter", height=80)
    bullets = ["Three cohorts completed on schedule", "Imaging pipeline moved to 4K tiles",
               "Median turnaround down from 9 to 6 days", "Two protocols revised after review"]
    for i, b in enumerate(bullets):
        p.draw_circle(fitz.Point(66, 150 + i * 56), 5, color=None, fill=TEAL)
        p.insert_text((84, 157 + i * 56), b, fontsize=22, fontname="helv", color=BLACK)
    p.insert_image(fitz.Rect(600, 120, 900, 420), stream=_jpeg(600, 600, seed=4, quality=85))
    footer(p, 2, total, "Quarterly Research Review · fictional")
    p = d.new_page(width=SLIDE169[0], height=SLIDE169[1])
    band(p, "Throughput", "Samples processed per month", height=80)
    bar_chart(p, fitz.Rect(60, 110, 520, 470), ["Apr", "May", "Jun", "Jul", "Aug", "Sep"], [42, 55, 51, 63, 70, 77],
              title="Samples")
    line_chart(p, fitz.Rect(540, 110, 900, 470), [[0.2, 0.35, 0.3, 0.5, 0.62, 0.7], [0.1, 0.2, 0.28, 0.33, 0.4, 0.52]],
               title="Yield")
    footer(p, 3, total, "Quarterly Research Review · fictional")
    p = d.new_page(width=SLIDE43[0], height=SLIDE43[1])
    band(p, "Budget (4:3 slide)", "A different page size in the same deck", height=80)
    table(p, 50, 120, [220, 130, 130, 130], [["Line", "Plan", "Actual", "Variance"], ["Consumables", "42,000", "39,850", "-2,150"],
          ["Sequencing", "65,000", "68,400", "3,400"], ["Imaging", "18,500", "18,100", "-400"], ["Travel", "6,000", "4,250", "-1,750"]],
          align=["l", "r", "r", "r"], row_h=34, size=13, negative_red=True)
    footer(p, 4, total, "Quarterly Research Review · fictional")
    p = d.new_page(width=SLIDE169[0], height=SLIDE169[1])
    p.draw_rect(p.rect, color=None, fill=TEAL)
    p.insert_text((70, 280), "Questions?", fontsize=54, fontname="hebo", color=(1, 1, 1))
    p.insert_text((72, 330), "slides.example.org (fictional)", fontsize=18, fontname="helv", color=(0.9, 0.97, 0.96))
    return d, {"pages": 5, "text": ["Quarterly Research Review", "Budget (4:3 slide)", "Questions?"],
               "page_sizes": [list(SLIDE169)] * 3 + [list(SLIDE43), list(SLIDE169)]}


def t_lab_protocol():
    d = _doc()
    total = 3
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "SOP-IMG-014  Immunofluorescence staining", "Fictional laboratory protocol · version 3.2 · for software testing")
    y = heading(p, 110, "1  Purpose and scope")
    _fit_box(p, fitz.Rect(40, y, 555, y + 52), "Standard procedure for immunofluorescence staining of fixed brain sections "
             "(fictional). Applies to cryosections of 20-40 um thickness. Keep slides protected from light after step 6.", size=10)
    y = heading(p, y + 70, "2  Reagents")
    y = table(p, 40, y, [170, 120, 110, 115], [["Reagent", "Supplier (fictional)", "Catalogue no.", "Working dilution"],
              ["Anti-Iba1 (rabbit)", "Example Bio", "EB-0019", "1:500"], ["Anti-GFAP (chicken)", "Sample Reagents", "SR-4410", "1:1000"],
              ["Goat anti-rabbit AF488", "Example Bio", "EB-7731", "1:800"], ["DAPI", "Sample Reagents", "SR-0002", "1 ug/mL"],
              ["Normal goat serum", "Example Bio", "EB-1200", "5 % (v/v)"]], row_h=22, size=9)
    y = heading(p, y + 30, "3  Procedure")
    steps = ["Wash sections 3 x 5 min in PBS (pH 7.4) at room temperature.", "Permeabilise in 0.3 % Triton X-100 in PBS for 15 min.",
             "Block in 5 % normal goat serum for 1 h at 20-25 C.", "Incubate with primary antibodies overnight at 4 C.",
             "Wash 3 x 10 min in PBS.", "Incubate with secondary antibodies for 2 h, protected from light.",
             "Counterstain with DAPI for 10 min; wash 2 x 5 min.", "Mount with anti-fade medium; store at 4 C in the dark."]
    for i, st in enumerate(steps, 1):
        p.insert_text((48, y + 4), f"{i}.", fontsize=10, fontname="hebo", color=TEAL)
        _fit_box(p, fitz.Rect(66, y - 7, 555, y + 18), st, size=10)
        y += 24
    p.draw_rect(fitz.Rect(40, y + 10, 555, y + 60), color=ORANGE, fill=(1, 0.96, 0.9), width=1)
    _fit_box(p, fitz.Rect(52, y + 18, 545, y + 56), "CAUTION  Paraformaldehyde is toxic. Work in a fume hood and wear gloves. "
             "This warning is part of a fictional test document.", size=9.5, font="hebo", color=(0.55, 0.25, 0.0))
    footer(p, 1, total, "SOP-IMG-014 · fictional")
    p = d.new_page(width=A4[0], height=A4[1])
    y = heading(p, 60, "4  Representative images")
    chans = [(40, 220, 90), (230, 60, 60), (60, 120, 240), (220, 200, 40)]
    labels = ["A  Iba1 (green)", "B  GFAP (red)", "C  DAPI (blue)", "D  Merge"]
    for i in range(4):
        x = 40 + (i % 2) * 262
        yy = y + (i // 2) * 250
        p.insert_image(fitz.Rect(x, yy, x + 250, yy + 210), stream=_micrograph(500, 420, seed=10 + i, channel=chans[i]))
        p.insert_text((x, yy + 228), labels[i], fontsize=9.5, fontname="hebo", color=NAVY)
    _fit_box(p, fitz.Rect(40, y + 510, 555, y + 580), "Figure 1. Fictional confocal images of mouse hippocampus (CA1), 20x objective. "
             "Scale bar 50 um. Images are synthetic and generated for software testing only.", size=9, font="heit", color=GREY)
    footer(p, 2, total, "SOP-IMG-014 · fictional")
    p = d.new_page(width=A4L[0], height=A4L[1])
    band(p, "5  Differential expression (example)", "Aged vs young microglia · fictional values · FDR < 0.05")
    rows = [["Gene", "log2 fold change", "baseMean", "p-value", "padj", "Direction"]]
    genes = [("Apoe", 2.41, 5120.4, 1.2e-12), ("Cst7", 3.05, 812.7, 4.5e-10), ("Lgals3", 1.88, 1490.2, 2.1e-8),
             ("Itgax", 2.67, 233.9, 7.7e-8), ("P2ry12", -1.42, 9830.1, 3.3e-7), ("Tmem119", -1.15, 7210.6, 1.9e-6),
             ("Cx3cr1", -0.92, 6650.0, 8.4e-5), ("Spp1", 2.12, 418.3, 2.6e-4)]
    for g, fc, bm, pv in genes:
        rows.append([g, f"{fc:+.2f}", f"{bm:,.1f}", f"{pv:.1e}", f"{min(1.0, pv * 40):.1e}", "up" if fc > 0 else "down"])
    table(p, 40, 110, [120, 130, 120, 120, 120, 110], rows, align=["l", "r", "r", "r", "r", "c"], row_h=24, size=10)
    bar_chart(p, fitz.Rect(40, 360, 780, 545), [r[0] for r in rows[1:]], [abs(float(r[1])) * 10 for r in rows[1:]],
              title="|log2 FC| x 10")
    footer(p, 3, total, "SOP-IMG-014 · fictional")
    return d, {"pages": 3, "text": ["SOP-IMG-014", "Representative images", "Differential expression"], "images": 4}


def t_photo_album():
    d = _doc()
    for i in range(3):
        p = d.new_page(width=A4L[0], height=A4L[1])
        p.insert_image(fitz.Rect(30, 30, A4L[0] - 30, A4L[1] - 80), stream=_jpeg(1800, 1150, seed=21 + i, quality=93))
        p.insert_text((30, A4L[1] - 50), f"Field site {i + 1} - synthetic photograph for compression tests", fontsize=12,
                      fontname="helv", color=BLACK)
        footer(p, i + 1, 3, "Photo album · fictional")
    return d, {"pages": 3, "text": ["Field site 1"], "images": 3}


def t_poster_a1():
    d = _doc()
    p = d.new_page(width=A1[0], height=A1[1])
    w = A1[0]
    p.draw_rect(fitz.Rect(0, 0, w, 260), color=None, fill=NAVY)
    p.draw_rect(fitz.Rect(0, 260, w, 272), color=None, fill=TEAL)
    p.insert_text((80, 140), "Microglial ageing signatures in a fictional cohort", fontsize=64, fontname="hebo", color=(1, 1, 1))
    p.insert_text((82, 210), "A. Example, B. Sample  ·  Example Institute, Sample University (fictional)", fontsize=30,
                  fontname="helv", color=(0.82, 0.88, 0.95))
    colw = (w - 80 * 2 - 60 * 2) / 3
    titles = ["Background", "Methods", "Results", "Conclusions"]
    for c in range(3):
        x = 80 + c * (colw + 60)
        y = 340
        for blk in range(3):
            p.insert_text((x, y), titles[(c + blk) % 4], fontsize=36, fontname="hebo", color=NAVY)
            p.draw_line((x, y + 10), (x + 160, y + 10), color=TEAL, width=4)
            _fit_box(p, fitz.Rect(x, y + 30, x + colw, y + 300), LOREM + " " + LOREM2, size=20)
            if blk == 1:
                p.insert_image(fitz.Rect(x, y + 320, x + colw, y + 640), stream=_micrograph(800, 520, seed=30 + c))
                y += 340
            y += 360
    bar_chart(p, fitz.Rect(80, 1900, w - 80, 2250), ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"],
              [3, 5, 4, 7, 9, 8, 11, 12], title="Weekly counts")
    p.insert_text((80, 2320), "Poster A1 (594 x 841 mm) · fictional content for large-page rendering, printing and compression tests",
                  fontsize=18, fontname="helv", color=GREY)
    return d, {"pages": 1, "size": list(A1), "text": ["Microglial ageing signatures"]}


def t_review_threads():
    d = _doc()
    p = d.new_page(width=A4[0], height=A4[1])
    band(p, "Manuscript draft - internal review", "Comment threads, replies, sticky notes and markup (fictional)")
    y = heading(p, 110, "Abstract")
    _fit_box(p, fitz.Rect(40, y, 555, y + 120), LOREM + " " + LOREM2, size=10.5)
    y = heading(p, y + 140, "Introduction")
    _fit_box(p, fitz.Rect(40, y, 555, y + 120), LOREM2 + " " + LOREM, size=10.5)

    def mark(kind, needle, author, content):
        hits = p.search_for(needle)
        if not hits:
            raise RuntimeError(f"review template: {needle!r} not on the page")
        a = getattr(p, f"add_{kind}_annot")(hits[0])
        a.set_info(title=author, content=content)
        a.update()
        return a, hits[0]

    h, r = mark("highlight", "Selecting, highlighting", "Reviewer A", "Please define these operations earlier.")
    reply = p.add_text_annot(fitz.Point(560, r.y0), "Agreed - moved to section 1.")
    reply.set_info(title="Author")
    reply.set_irt_xref(h.xref)
    reply.update()
    mark("underline", "hyphenated-compound", "Reviewer B", "Hyphenation style per journal guide?")
    mark("strikeout", "neutral filler", "Reviewer A", "Delete.")
    mark("squiggly", "sample@example.org", "Reviewer A", "Use an institutional address.")
    note = p.add_text_annot(fitz.Point(500, 120), "Overall: minor revision. Check figure numbering.")
    note.set_info(title="Editor")
    note.update()
    ft = p.add_freetext_annot(fitz.Rect(330, 700, 555, 760), "Figure 2 is missing a scale bar.", fontsize=10,
                              text_color=(0.6, 0.1, 0.1), fill_color=(1, 0.97, 0.85))
    ft.set_info(title="Reviewer B")
    ft.update()
    footer(p, 1, 1, "Review copy · fictional")
    return d, {"pages": 1, "text": ["Manuscript draft"], "annotations_min": 7}


BUILDERS = [
    # (file, builder, title, test types, purpose)
    ("invoice_a4", t_invoice, "Invoice (A4)", ["tables", "Excel export", "text editing", "print"], "A typical business invoice: ruled item table with right-aligned amounts, totals block, footer."),
    ("business_report", t_report, "Annual report (6 pages, bookmarks)", ["navigation", "bookmarks", "Word conversion", "page operations", "charts"], "Cover, contents, charts, tables and a risk register with a bookmark outline."),
    ("scientific_paper_two_column", t_paper, "Scientific paper (2 pages)", ["text selection", "highlighting", "math symbols", "figures", "references"], "Two-column paper with equations (Unicode), a vector figure, a table and references."),
    ("application_form_acroform", t_form, "Application form (AcroForm)", ["forms", "field formatting", "tab order", "flatten"], "Text, multi-line, combo, list, radio group, checkboxes, date and signature fields."),
    ("contract_unsigned_signature_fields", t_contract, "Contract with signature fields", ["signatures", "signed-document warnings", "visual signatures"], "Clauses and two signature fields; carries no cryptographic signature."),
    ("japanese_notice", t_japanese, "Japanese notice", ["Japanese text", "embedded fonts", "OCR", "conversion"], "Fully Japanese page with a ruled table; embedded subset CJK font."),
    ("bilingual_en_ja_letter", t_bilingual, "English/Japanese letter", ["mixed language", "font fallback", "search", "OCR"], "Latin and Japanese on the same lines."),
    ("account_statement_tables", t_statement, "Account statement", ["table extraction", "numbers to Excel", "negative values"], "Two ruled tables with money columns and a summary."),
    ("brochure_landscape", t_brochure, "Brochure (A4 landscape)", ["landscape", "images", "PowerPoint export", "highlight over images"], "Gradient hero image, three feature cards, picture."),
    ("scanned_memo_300dpi", t_scanned, "Scanned memo (300 dpi)", ["OCR", "searchable PDF", "image-only pages"], "Image-only page: no text layer until OCR."),
    ("scanned_memo_noisy_skewed", t_scanned_noisy, "Scanned memo (noisy, skewed)", ["OCR robustness", "low quality scans"], "The same memo at 200 dpi with noise, blur and a 1.3° tilt."),
    ("mixed_sizes_and_rotations", t_mixed, "Mixed sizes and rotated pages", ["rotation", "page size", "organize", "print", "PowerPoint sizing"], "A4, Letter, A3 landscape, A5 and A4 pages rotated 90/180/270."),
    ("annotated_review_copy", t_annotated, "Annotated review copy", ["annotations", "highlights", "export", "flatten"], "Highlight, underline, strikeout, note, free text, shapes, ink and stamp."),
    ("highlight_playground", t_highlight_playground, "Highlight playground", ["highlighting", "free-area marking", "images", "tables", "dark backgrounds"], "Text, blank margins, picture, table, chart, colour fields and dark graphics on one page."),
    ("transparency_overlap", t_transparency, "Transparency and overlap", ["rendering", "annotation over graphics"], "Translucent shapes over text."),
    ("image_heavy", t_images, "Image-heavy page", ["optimisation", "image export", "memory"], "Four textured images."),
    ("fonts_specimen", t_fonts, "Font specimen", ["fonts", "font substitution", "unicode"], "Base-14 faces plus an embedded subset font with symbols."),
    ("newsletter_two_column", t_two_column_text, "Two-column newsletter", ["text flow", "Word conversion", "selection across columns"], "Two text columns and a pull quote."),
    ("long_document_200_pages", t_long, "200-page document", ["performance", "memory", "navigation", "rotation speed"], "200 pages with a 20-entry bookmark outline."),
    ("empty_page", t_empty, "Empty page", ["edge cases", "blank page handling"], "One page without content."),
    ("cropbox_offset", t_cropbox, "CropBox inside MediaBox", ["geometry", "CropBox offsets", "coordinates"], "Visible area is smaller than the MediaBox and does not start at the origin."),
    ("slide_deck_mixed_aspect", t_slides, "Slide deck (16:9 with one 4:3 slide)", ["PDF to PowerPoint", "page-size groups", "print scaling", "thumbnails"], "Title, bullet, chart, table and closing slides; one slide has a different page size."),
    ("lab_protocol_figures_tables", t_lab_protocol, "Laboratory protocol (figures, tables, landscape page)", ["Word conversion", "Excel export", "image export", "highlighting", "mixed orientation"], "Numbered SOP with a reagent table, a 2x2 micrograph figure and a landscape results table."),
    ("photo_album_compression", t_photo_album, "Photo album (large JPEG photos)", ["Compress PDF", "target size", "image quality", "memory"], "Three landscape pages, each a high-resolution photo-like JPEG."),
    ("poster_a1_large_format", t_poster_a1, "Conference poster (A1)", ["large pages", "zoom and tiles", "print to A4/A3", "compression"], "One A1 page with columns of text, micrographs and a chart."),
    ("review_comment_threads", t_review_threads, "Review copy with comment threads", ["Comments panel", "replies", "markup types", "sticky notes"], "Highlight with a reply, underline, strikeout, squiggly, sticky note and free-text comment by several authors."),
]


def build(out: Path) -> dict:
    pdf_dir = out / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"password": PASSWORD, "documents": {}}
    for name, fn, title, tests, purpose in BUILDERS:
        doc, expect = fn()
        path = pdf_dir / f"{name}.pdf"
        doc.save(path.as_posix(), garbage=3, deflate=True)
        pages = doc.page_count
        doc.close()
        if isinstance(expect.get("pages"), list):
            expect.update(expect.pop("pages")[0])
        expect["pages"] = pages
        manifest["documents"][name] = {"file": f"pdf/{name}.pdf", "title": title, "test_types": tests, "purpose": purpose, "expect": expect}
    # security variants of the invoice
    src = fitz.open((pdf_dir / "invoice_a4.pdf").as_posix())
    src.save((pdf_dir / "password_protected_aes256.pdf").as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=PASSWORD, owner_pw=PASSWORD + "-owner")
    perm = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT
    src.save((pdf_dir / "permissions_restricted.pdf").as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="", owner_pw=PASSWORD + "-owner", permissions=perm)
    src.close()
    manifest["documents"]["password_protected_aes256"] = {"file": "pdf/password_protected_aes256.pdf", "title": "Password-protected invoice (AES-256)", "test_types": ["encryption", "password prompt", "wrong password"],
                                                           "purpose": f"Open password is '{PASSWORD}'.", "expect": {"pages": 1, "encrypted": True, "password": PASSWORD}}
    manifest["documents"]["permissions_restricted"] = {"file": "pdf/permissions_restricted.pdf", "title": "Restricted permissions (no copy, no edit)", "test_types": ["permissions", "owner password"],
                                                       "purpose": "Opens without a password; copying and modifying are not permitted.", "expect": {"pages": 1, "encrypted": True, "can_copy": False}}
    # a damaged file for error-handling tests
    good = (pdf_dir / "invoice_a4.pdf").read_bytes()
    (pdf_dir / "damaged_truncated.pdf").write_bytes(good[: len(good) // 2])
    manifest["documents"]["damaged_truncated"] = {"file": "pdf/damaged_truncated.pdf", "title": "Truncated (damaged) file", "test_types": ["error handling", "repair", "invalid files"],
                                                  "purpose": "Half of a valid PDF: must be refused or repaired safely, never crash.", "expect": {"damaged": True}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv: list[str]) -> int:
    out = HERE
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1]).resolve()
    m = build(out)
    print(f"{len(m['documents'])} template PDFs written to {out / 'pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
