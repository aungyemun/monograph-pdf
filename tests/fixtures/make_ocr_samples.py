"""Synthetic scanned-page fixtures for offline OCR tests (no confidential data)."""

from __future__ import annotations

from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"


def _render_text_pixmap(lines: list[str], *, fontsize: int, dpi: int, width: float, height: float) -> fitz.Pixmap:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
    y = 48
    for line in lines:
        # Draw run by run: Latin text in Helvetica, Japanese in MuPDF's built-in CJK font, each at its
        # natural width (a textbox in the CJK font spaces Latin letters out and wraps them).
        x = 36.0
        run, is_cjk = "", None
        runs: list[tuple[str, bool]] = []
        for ch in line:
            cjk = ord(ch) > 0x2E80
            if is_cjk is None or cjk == is_cjk:
                run += ch
            else:
                runs.append((run, bool(is_cjk)))
                run = ch
            is_cjk = cjk
        if run:
            runs.append((run, bool(is_cjk)))
        for text, cjk in runs:
            fontname = "japan" if cjk else "helv"
            page.insert_text((x, y), text, fontsize=fontsize, fontname=fontname)
            x += fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)
        y += fontsize + 18
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    doc.close()
    return pix


def _image_only_pdf(path: Path, pix: fitz.Pixmap, *, rotate: int = 0) -> None:
    """Write a single-page PDF that contains only a raster image (no native text)."""
    work = pix
    if rotate:
        # Rotate pixmap via a temporary page matrix
        tmp = fitz.open()
        tw = pix.width * 72 / 150.0
        th = pix.height * 72 / 150.0
        tp = tmp.new_page(width=tw, height=th)
        tp.insert_image(tp.rect, pixmap=pix)
        mat = fitz.Matrix(1, 1).prerotate(rotate)
        work = tp.get_pixmap(matrix=mat, alpha=False)
        tmp.close()

    page_w = work.width * 72 / 150.0
    page_h = work.height * 72 / 150.0
    doc = fitz.open()
    page = doc.new_page(width=max(page_w, 72), height=max(page_h, 72))
    page.insert_image(page.rect, pixmap=work)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path.as_posix())
    doc.close()


def write_english_scan(path: Path) -> None:
    pix = _render_text_pixmap(
        ["HELLO OCR ENGLISH", "Sample scan page ALPHA"],
        fontsize=28,
        dpi=180,
        width=480,
        height=220,
    )
    _image_only_pdf(path, pix)


def write_japanese_scan(path: Path) -> None:
    pix = _render_text_pixmap(
        ["日本語OCRテスト", "東京サンプル"],
        fontsize=28,
        dpi=180,
        width=480,
        height=220,
    )
    _image_only_pdf(path, pix)


def write_mixed_scan(path: Path) -> None:
    pix = _render_text_pixmap(
        ["Mixed OCR English and 日本語", "Tokyo Sample 2026"],
        fontsize=24,
        dpi=180,
        width=520,
        height=220,
    )
    _image_only_pdf(path, pix)


def write_rotated_scan(path: Path) -> None:
    pix = _render_text_pixmap(["ROTATED OCR TEXT"], fontsize=28, dpi=180, width=400, height=160)
    _image_only_pdf(path, pix, rotate=90)


def write_blank_scan(path: Path) -> None:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 240), 0)
    pix.set_rect(pix.irect, (255, 255, 255))
    _image_only_pdf(path, pix)


def write_lowres_scan(path: Path) -> None:
    pix = _render_text_pixmap(["LOW RES OCR"], fontsize=16, dpi=72, width=280, height=120)
    _image_only_pdf(path, pix)


def main() -> int:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    write_english_scan(SAMPLES / "ocr_english_scan.pdf")
    write_japanese_scan(SAMPLES / "ocr_japanese_scan.pdf")
    write_mixed_scan(SAMPLES / "ocr_mixed_scan.pdf")
    write_rotated_scan(SAMPLES / "ocr_rotated_scan.pdf")
    write_blank_scan(SAMPLES / "ocr_blank_scan.pdf")
    write_lowres_scan(SAMPLES / "ocr_lowres_scan.pdf")
    print(f"Wrote OCR fixtures to {SAMPLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
