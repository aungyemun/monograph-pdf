"""Generate small legal PDF fixtures under tests/samples (run from project root)."""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"
GENERATED = ROOT / "tests" / "outputs" / "generated"


def write_text_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 72), f"Monograph PDF fixture page {i + 1}")
        page.insert_text((72, 100), "Selectable sample text for search: alpha-bravo-charlie")
        page.insert_text((72, 128), "Lorem ipsum dolor sit amet.")
    doc.save(path.as_posix())
    doc.close()


def write_many_pages(path: Path, pages: int = 40) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=400, height=500)
        page.insert_text((40, 40), f"Large lifecycle page {i + 1}/{pages}")
    doc.save(path.as_posix())
    doc.close()


def write_image_page(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    # Solid pixmap as "scanned" content with no text (RGB, no alpha)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), 0)
    pix.set_rect(pix.irect, (180, 180, 200))
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path.as_posix())
    doc.close()


def write_password_pdf(path: Path, user_pw: str = "secret") -> None:
    base = GENERATED / "_tmp_plain.pdf"
    GENERATED.mkdir(parents=True, exist_ok=True)
    write_text_pdf(base, pages=1)
    doc = fitz.open(base)
    # owner+user password; permissions keep print/copy typical defaults
    doc.save(
        path.as_posix(),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=user_pw,
        owner_pw="owner-" + user_pw,
        permissions=int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ANNOTATE),
    )
    doc.close()
    base.unlink(missing_ok=True)


def write_malformed(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\nthis is not a valid pdf stream\n%%EOF\n\x00\x01\x02")


def main() -> int:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    write_text_pdf(SAMPLES / "sample_text.pdf", pages=3)
    write_many_pages(SAMPLES / "sample_large.pdf", pages=40)
    write_image_page(SAMPLES / "sample_image_page.pdf")
    write_password_pdf(SAMPLES / "sample_password.pdf", user_pw="secret")
    write_malformed(SAMPLES / "sample_malformed.pdf")
    print(f"Wrote fixtures to {SAMPLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
