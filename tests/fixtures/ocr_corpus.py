"""A wider OCR evaluation set, generated offline (no personal documents, no network).

These are *synthetic scans*: text rendered with PyMuPDF fonts, rasterised, then degraded (blur, noise,
skew, low resolution) where noted. They are NOT photographs or real office scans — real-scan accuracy
is not measured by this set. Each case carries its verified reference text.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageFilter

JP = fitz.Font("cjk")


@dataclass
class Case:
    name: str
    lang: str
    reference: str
    path: Path
    note: str = ""


def _page_image(lines, *, size_pt=12.0, dpi=150, w=480, h=220, cjk_lines=(), table=None, rotate=0) -> Image.Image:
    d = fitz.open()
    p = d.new_page(width=w, height=h)
    p.insert_font(fontname="jpf", fontbuffer=JP.buffer)
    y = 40.0
    for i, text in enumerate(lines):
        x = 30.0
        run, is_cjk, runs = "", None, []
        for ch in text:
            c = ord(ch) > 0x2E00
            if is_cjk is None or c == is_cjk:
                run += ch
            else:
                runs.append((run, is_cjk))
                run = ch
            is_cjk = c
        if run:
            runs.append((run, bool(is_cjk)))
        for t, cjk in runs:
            fn = "jpf" if cjk else "helv"
            p.insert_text((x, y), t, fontsize=size_pt, fontname=fn)
            x += JP.text_length(t, fontsize=size_pt) if cjk else fitz.get_text_length(t, fontname=fn, fontsize=size_pt)
        y += size_pt * 1.9
    if table:
        x0, y0, cw, rh = 30.0, y + 6, table["cw"], size_pt * 2.0
        for r, row in enumerate(table["rows"]):
            for c, cell in enumerate(row):
                p.draw_rect(fitz.Rect(x0 + c * cw, y0 + r * rh, x0 + (c + 1) * cw, y0 + (r + 1) * rh), color=(0, 0, 0), width=0.6)
                p.insert_text((x0 + c * cw + 4, y0 + r * rh + size_pt * 1.35), cell, fontsize=size_pt, fontname="helv")
    pm = p.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
    d.close()
    return img.rotate(-rotate, expand=True, fillcolor="white") if rotate else img


def _degrade(img: Image.Image, *, blur=0.0, noise=0, skew_deg=0.0, seed=7) -> Image.Image:
    if skew_deg:
        img = img.rotate(skew_deg, resample=Image.Resampling.BICUBIC, fillcolor="white")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        rnd = random.Random(seed)
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                n = rnd.randint(-noise, noise)
                r, g, b = px[x, y]
                px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return img


def _to_pdf(img: Image.Image, dpi: int, path: Path) -> None:
    d = fitz.open()
    p = d.new_page(width=img.width * 72 / dpi, height=img.height * 72 / dpi)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    p.insert_image(p.rect, stream=buf.getvalue())
    d.save(path.as_posix())
    d.close()


def build(out: Path) -> list[Case]:
    out.mkdir(parents=True, exist_ok=True)
    cases: list[Case] = []

    def add(name, lang, lines, ref=None, *, dpi=150, size=12.0, degrade=None, note="", **kw):
        img = _page_image(lines, size_pt=size, dpi=dpi, **kw)
        if degrade:
            img = _degrade(img, **degrade)
        path = out / f"{name}.pdf"
        _to_pdf(img, dpi, path)
        cases.append(Case(name, lang, ref if ref is not None else " ".join(lines), path, note))

    add("en_paragraph", "eng", ["The committee reviewed the annual budget", "and approved the proposed changes to", "the schedule for the next quarter."])
    add("en_small_8pt", "eng", ["Small print: terms and conditions apply to", "all purchases made before 31 December."], dpi=200, size=8.0)
    add("en_scientific", "eng", ["Spectrophotometric determination of", "dihydrofolate reductase inhibition", "(IC50 = 3.2 nM, n = 6, p < 0.05)."],
        note="technical vocabulary")
    add("en_math_ascii", "eng", ["E = mc^2", "x = (-b +/- sqrt(b^2 - 4ac)) / 2a", "sum(i=1..n) i = n(n+1)/2"], note="math written in ASCII")
    add("en_table", "eng", ["Quarterly figures"], ref="Quarterly figures Item Qty Price Apple 12 1.25 Pear 7 0.80",
        table={"cw": 110, "rows": [["Item", "Qty", "Price"], ["Apple", "12", "1.25"], ["Pear", "7", "0.80"]]}, note="ruled table")
    add("jp_paragraph", "jpn", ["日本語の文章を認識します。", "東京都千代田区の住所です。", "令和六年十月十六日"])
    add("jp_with_ri", "jpn", ["日本語", "日曜日の会議"], note="lines starting with 日")
    add("mixed_en_jp", "eng+jpn", ["Order number 2026-17", "注文番号の確認をお願いします。"])
    add("en_rotated_90", "eng", ["Rotated page text sample line"], rotate=90, note="page turned 90°")
    add("en_lowres_100dpi", "eng", ["Low resolution scan of ordinary text."], dpi=100, note="100 dpi")
    add("en_noisy_skewed", "eng", ["Noisy skewed scan of ordinary text", "with blur and a one degree tilt."],
        degrade={"blur": 0.7, "noise": 28, "skew_deg": 1.0}, note="blur + noise + 1° skew")
    add("jp_noisy", "jpn", ["日本語の文章を認識します。", "東京都千代田区の住所です。"], degrade={"blur": 0.6, "noise": 24}, note="blur + noise")
    return cases
