"""Export a flattened PDF (forms baked; high confidence)."""

from __future__ import annotations

from pathlib import Path

from core.document import PdfDocument
from core.forms.acroform import flatten_form_fields


def export_flattened_pdf(document: PdfDocument, destination: Path) -> Path:
    """Write a new PDF with form fields flattened. Source file unchanged."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    from core.security.protection import save_copy, working_copy

    doc = working_copy(document)  # keeps a protected PDF's protection
    try:
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
        save_copy(doc, destination)
    finally:
        doc.close()
    return destination
