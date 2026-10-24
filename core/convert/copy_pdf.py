"""Metadata-preserving PDF copy (high confidence)."""

from __future__ import annotations

from pathlib import Path

from core.document import PdfDocument


def copy_pdf_preserving_metadata(document: PdfDocument, destination: Path) -> Path:
    """
    Write a full copy of the live document: pages with their unsaved changes, document information,
    bookmarks, form fields, attachments — and the password protection of a protected PDF (same
    passwords and permissions; it used to be written unprotected). Source path is never modified.
    """
    from core.security.protection import save_copy, working_copy

    doc = working_copy(document)
    try:
        save_copy(doc, Path(destination), incremental=False)
    finally:
        doc.close()
    return Path(destination)
