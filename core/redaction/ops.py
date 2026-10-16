"""Mark and apply true content redaction via PyMuPDF apply_redactions()."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from core.document import PdfDocument
from core.editing.geometry import Rect


@dataclass
class RedactionMark:
    page_index: int
    rect: Rect
    text: str = ""


def mark_region(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
    text: str = "",
) -> RedactionMark:
    """Add a redaction annotation (preview) — content not yet removed until apply."""
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    r = fitz.Rect(rect.x, rect.y, rect.x1, rect.y1)
    kwargs = {"fill": fill}
    if text:
        kwargs["text"] = text
    page.add_redact_annot(r, **kwargs)
    document.invalidate_pages()
    return RedactionMark(page_index=page_index, rect=rect, text=text)


def mark_text(
    document: PdfDocument,
    page_index: int,
    query: str,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
) -> list[RedactionMark]:
    """Mark all occurrences of query on a page for redaction."""
    if not query:
        return []
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    marks: list[RedactionMark] = []
    for r in page.search_for(query) or []:
        # Inflate slightly so glyph edges are covered
        rr = fitz.Rect(r)
        rr.x0 -= 1
        rr.y0 -= 1
        rr.x1 += 1
        rr.y1 += 1
        page.add_redact_annot(rr, fill=fill)
        marks.append(
            RedactionMark(
                page_index=page_index,
                rect=Rect(float(rr.x0), float(rr.y0), float(rr.width), float(rr.height)),
                text=query,
            )
        )
    if marks:
        document.invalidate_pages()
    return marks


def preview_redaction_count(document: PdfDocument) -> int:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    count = 0
    for i in range(doc.page_count):
        page = doc.load_page(i)
        for annot in page.annots() or []:
            try:
                if annot.type and (
                    annot.type[0] == getattr(fitz, "PDF_ANNOT_REDACT", 12)
                    or str(annot.type[1]).lower() == "redact"
                ):
                    count += 1
            except Exception:  # noqa: BLE001
                continue
    return count


def apply_redactions(
    document: PdfDocument,
    destination: Path,
    *,
    images: int | bool = True,
    graphics: int | bool = True,
    text: int | bool = True,
) -> Path:
    """
    Apply true content redaction and write destination.
    Uses page.apply_redactions() so underlying text/images are removed — not covered by rectangles.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001

    for i in range(src.page_count):
        page = src.load_page(i)
        try:
            # PyMuPDF: text=True/1 removes text under redaction areas
            page.apply_redactions()
        except Exception:  # noqa: BLE001
            try:
                page.apply_redactions(images=2, graphics=2, text=0)
            except Exception:  # noqa: BLE001
                raise

    document.invalidate_pages()
    # Write via full rewrite of the live (now redacted) document
    src.save(
        destination.as_posix(),
        garbage=4,
        deflate=True,
        encryption=fitz.PDF_ENCRYPT_NONE if not src.is_encrypted else fitz.PDF_ENCRYPT_KEEP,
        incremental=False,
    )
    return destination
