"""Metadata-preserving PDF copy (high confidence)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import PdfDocument


def copy_pdf_preserving_metadata(document: PdfDocument, destination: Path) -> Path:
    """
    Write a full copy of the live document including the info dictionary.
    Source path is never modified.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        meta = src.metadata or {}
        doc.set_metadata(
            {
                "title": meta.get("title") or "",
                "author": meta.get("author") or "",
                "subject": meta.get("subject") or "",
                "keywords": meta.get("keywords") or "",
                "creator": meta.get("creator") or "",
                "producer": meta.get("producer") or "",
            }
        )
        encrypt = fitz.PDF_ENCRYPT_KEEP if src.is_encrypted else fitz.PDF_ENCRYPT_NONE
        doc.save(
            destination.as_posix(),
            garbage=3,
            deflate=True,
            encryption=encrypt,
            incremental=False,
        )
    finally:
        doc.close()
    return destination
