"""PDF → plain text (high confidence for extractable text)."""

from __future__ import annotations

from pathlib import Path

from core.document import PdfDocument


def pdf_to_plain_text(
    document: PdfDocument,
    destination: Path | None = None,
    *,
    pages: list[int] | None = None,
    page_separator: str = "\n\n---\n\n",
) -> str:
    indices = list(range(document.page_count)) if pages is None else list(pages)
    parts: list[str] = []
    for i in indices:
        if i < 0 or i >= document.page_count:
            raise IndexError(f"page out of range: {i}")
        parts.append(document.page_text(i) or "")
    text = page_separator.join(parts)
    if destination is not None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return text
