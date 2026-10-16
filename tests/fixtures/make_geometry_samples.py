"""Synthetic fixtures: mixed page sizes, rotations, many pages, password, images."""

from __future__ import annotations

from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"

# PDF points
A4 = (595.28, 841.89)
A5 = (419.53, 595.28)
LETTER = (612.0, 792.0)
LEGAL = (612.0, 1008.0)
CUSTOM = (500.0, 700.0)


def write_mixed_page_sizes(path: Path) -> None:
    doc = fitz.open()
    specs = [
        (*A4, 0, "A4 portrait"),
        (*A5, 0, "A5 portrait"),
        (LETTER[1], LETTER[0], 0, "Letter landscape"),  # swap for landscape box
        (*LEGAL, 0, "Legal portrait"),
        (*CUSTOM, 0, "Custom"),
    ]
    for w, h, rot, label in specs:
        page = doc.new_page(width=w, height=h)
        page.set_rotation(rot)
        page.insert_text((36, 48), f"Mixed sizes: {label}", fontsize=12)
        page.insert_text((36, 68), f"{w:.1f} x {h:.1f} pt", fontsize=10)
    doc.save(path.as_posix())
    doc.close()


def write_rotated_pages(path: Path) -> None:
    doc = fitz.open()
    for rot in (0, 90, 180, 270):
        page = doc.new_page(width=A4[0], height=A4[1])
        page.insert_text((72, 72), f"Rotation sample {rot} deg", fontsize=14)
        page.insert_text((72, 100), "日本語とEnglish mixed", fontsize=12)
        page.set_rotation(rot)
    doc.save(path.as_posix())
    doc.close()


def write_many_pages(path: Path, count: int = 50) -> None:
    doc = fitz.open()
    for i in range(count):
        page = doc.new_page(width=A4[0], height=A4[1])
        page.insert_text((72, 72), f"Page {i + 1} / {count}", fontsize=14)
        page.insert_text((72, 96), "Synthetic many-page fixture", fontsize=10)
    doc.save(path.as_posix(), deflate=True, garbage=3)
    doc.close()


def write_mixed_font_runs(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_text((72, 72), "Application ", fontsize=14, fontname="helv")
    # CJK via insert_htmlbox / textbox when possible
    try:
        page.insert_htmlbox(
            fitz.Rect(72, 90, 500, 140),
            "<span style='font-size:14pt'>申請者 2026 English</span>",
        )
    except Exception:  # noqa: BLE001
        page.insert_text((72, 110), "Applicant 2026", fontsize=14)
    page.insert_text((72, 160), "Mixed-font fixture — fictional", fontsize=10)
    doc.save(path.as_posix())
    doc.close()


def write_raster_images(path: Path) -> None:
    """High-res and low-res embedded rasters for DPI policy tests."""
    doc = fitz.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_text((72, 48), "Raster DPI fixture", fontsize=12)

    # High-res image (~300 DPI in a 2-inch box)
    hi = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 400), 1)
    hi.set_rect(hi.irect, (200, 220, 240, 255))
    page.insert_image(fitz.Rect(72, 80, 72 + 144, 80 + 96), pixmap=hi)

    # Low-res image (~72 DPI)
    lo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 72, 72), 1)
    lo.set_rect(lo.irect, (240, 200, 200, 255))
    page.insert_image(fitz.Rect(72, 220, 72 + 72, 220 + 72), pixmap=lo)

    doc.save(path.as_posix())
    doc.close()


def write_crop_vs_media(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_text((72, 72), "CropBox vs MediaBox fixture", fontsize=12)
    # Shrink cropbox
    page.set_cropbox(fitz.Rect(36, 36, A4[0] - 36, A4[1] - 36))
    doc.save(path.as_posix())
    doc.close()


def main() -> int:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    write_mixed_page_sizes(SAMPLES / "sample_mixed_page_sizes.pdf")
    write_rotated_pages(SAMPLES / "sample_rotated_pages.pdf")
    write_many_pages(SAMPLES / "sample_many_pages_50.pdf", 50)
    write_many_pages(SAMPLES / "sample_many_pages_10.pdf", 10)
    write_mixed_font_runs(SAMPLES / "sample_mixed_fonts.pdf")
    write_raster_images(SAMPLES / "sample_raster_dpi.pdf")
    write_crop_vs_media(SAMPLES / "sample_cropbox.pdf")
    print(f"Wrote geometry fixtures to {SAMPLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
