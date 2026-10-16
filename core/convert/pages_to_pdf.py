"""Selected pages → new PDF (high confidence)."""

from __future__ import annotations

from pathlib import Path

from core.document import PdfDocument
from core.organize.page_ops import extract_pages


def pages_to_pdf(document: PdfDocument, pages: list[int], destination: Path) -> Path:
    return extract_pages(document, pages, destination)
