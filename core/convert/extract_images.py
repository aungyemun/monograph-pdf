"""Extract embedded images from a PDF (high confidence)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import PdfDocument
from core.safe_paths import safe_child


def extract_embedded_images(
    document: PdfDocument,
    output_dir: Path,
    *,
    pages: list[int] | None = None,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    indices = list(range(doc.page_count)) if pages is None else list(pages)
    written: list[Path] = []
    seen: set[int] = set()

    for pi in indices:
        if pi < 0 or pi >= doc.page_count:
            raise IndexError(f"page out of range: {pi}")
        page = doc.load_page(pi)
        for img in page.get_images(full=True) or []:
            xref = int(img[0])
            if xref in seen:
                continue
            seen.add(xref)
            try:
                extracted = doc.extract_image(xref)
            except Exception:  # noqa: BLE001
                continue
            if not extracted or not extracted.get("image"):
                continue
            # The type name comes from the PDF: keep letters and digits only
            ext = "".join(c for c in str(extracted.get("ext") or "").lower() if c.isascii() and c.isalnum())[:8] or "bin"
            out = safe_child(output_dir, f"img_p{pi + 1}_x{xref}.{ext}")
            out.write_bytes(extracted["image"])
            written.append(out)
    return written
