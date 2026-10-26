"""Generate small legal PDF fixtures under tests/samples (run from project root)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"
GENERATED = ROOT / "tests" / "outputs" / "generated"


def _atomic_save(doc: fitz.Document, path: Path, **save_kw) -> None:
    """Write via a temp file then replace. If *path* is locked (viewer open), keep existing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".pdf", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        doc.save(tmp.as_posix(), **save_kw)
        try:
            os.replace(tmp, path)
        except OSError as exc:
            # Windows: live GUI / browser may lock sample_*.pdf during validation.
            if path.is_file():
                print(f"keep existing {path.name} (locked: {exc})")
            else:
                raise
    finally:
        tmp.unlink(missing_ok=True)


def write_text_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 72), f"Monograph PDF fixture page {i + 1}")
        page.insert_text((72, 100), "Selectable sample text for search: alpha-bravo-charlie")
        page.insert_text((72, 128), "Lorem ipsum dolor sit amet.")
    _atomic_save(doc, path)
    doc.close()


def write_many_pages(path: Path, pages: int = 40) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=400, height=500)
        page.insert_text((40, 40), f"Large lifecycle page {i + 1}/{pages}")
    _atomic_save(doc, path)
    doc.close()


def write_image_page(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    # Solid pixmap as "scanned" content with no text (RGB, no alpha)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), 0)
    pix.set_rect(pix.irect, (180, 180, 200))
    page.insert_image(page.rect, pixmap=pix)
    _atomic_save(doc, path)
    doc.close()


def write_password_pdf(path: Path, user_pw: str = "secret") -> None:
    base = GENERATED / "_tmp_plain.pdf"
    GENERATED.mkdir(parents=True, exist_ok=True)
    write_text_pdf(base, pages=1)
    doc = fitz.open(base)
    # owner+user password; permissions keep print/copy typical defaults
    _atomic_save(
        doc,
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=user_pw,
        owner_pw="owner-" + user_pw,
        permissions=int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ANNOTATE),
    )
    doc.close()
    base.unlink(missing_ok=True)


def write_malformed(path: Path) -> None:
    data = b"%PDF-1.4\nthis is not a valid pdf stream\n%%EOF\n\x00\x01\x02"
    try:
        path.write_bytes(data)
    except OSError as exc:
        if path.is_file():
            print(f"keep existing {path.name} (locked: {exc})")
        else:
            raise


def _should_write(path: Path, *, force: bool) -> bool:
    """Shared fixtures stay put unless missing or an explicit regen is requested."""
    return force or not path.is_file() or path.stat().st_size <= 0


def main(*, force: bool | None = None) -> int:
    """Create sample PDFs under tests/samples.

    By default existing fixtures are left alone so a live GUI or browser holding
    ``sample_text.pdf`` cannot break the suite. Set ``MONOGRAPH_REGEN_SAMPLES=1``
    (or pass ``force=True``) to rewrite them.
    """
    if force is None:
        force = os.environ.get("MONOGRAPH_REGEN_SAMPLES", "").strip().lower() in ("1", "true", "yes")
    SAMPLES.mkdir(parents=True, exist_ok=True)
    targets = [
        (SAMPLES / "sample_text.pdf", lambda p: write_text_pdf(p, pages=3)),
        (SAMPLES / "sample_large.pdf", lambda p: write_many_pages(p, pages=40)),
        (SAMPLES / "sample_image_page.pdf", write_image_page),
        (SAMPLES / "sample_password.pdf", lambda p: write_password_pdf(p, user_pw="secret")),
        (SAMPLES / "sample_malformed.pdf", write_malformed),
    ]
    wrote = 0
    for path, writer in targets:
        if _should_write(path, force=force):
            try:
                writer(path)
                wrote += 1
            except OSError as exc:
                # Parallel GUI / locked fixture: keep going so the suite can still run.
                if path.is_file():
                    print(f"keep existing {path.name} (locked: {exc})")
                else:
                    raise
        else:
            print(f"keep existing {path.name}")
    print(f"Wrote {wrote} fixture(s) to {SAMPLES} (force={force})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
