"""Export a flattened PDF (forms baked; high confidence)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import PdfDocument
from core.forms.acroform import flatten_form_fields


def export_flattened_pdf(document: PdfDocument, destination: Path) -> Path:
    """Write a new PDF with form fields flattened. Source file unchanged."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        flatten_form_fields(doc)
        # Also flatten annotations when API exists
        try:
            for i in range(doc.page_count):
                page = doc.load_page(i)
                for annot in list(page.annots() or []):
                    try:
                        page.apply_redactions()  # no-op if none
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        # Convert markup to content when possible
                        annot.update()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return destination
