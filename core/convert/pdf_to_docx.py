"""PDF → Word (DOCX).

Engines
-------
``layout`` (default)  pdf2docx — rebuilds each page as editable Word content and keeps
                      the original layout: fonts, sizes, colours, paragraphs, tables,
                      images, columns and page size. Fully offline, bundled.
``word``              Microsoft Word's own PDF Reflow (only when Word is installed) —
                      best for long flowing text you want to re-edit heavily.
``text``              Plain paragraphs only (legacy fallback; always available).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from core.document import PdfDocument

FIDELITY_NOTICE = (
    "Layout-preserving conversion: text, fonts, colors, tables, images and page size are "
    "rebuilt as editable Word content. Very complex pages (overlapping text boxes, unusual "
    "fonts, scanned images without OCR) may need small touch-ups in Word."
)

ENGINES = ("layout", "word", "text")


def layout_engine_available() -> bool:
    try:
        import pdf2docx  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def word_engine_available() -> bool:
    from core.convert.office_bridge import office_availability

    return office_availability().word


def _live_pdf_bytes(document: PdfDocument) -> bytes:
    """Current in-memory state (page edits, rotations, annotations), decrypted."""
    import fitz

    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    return doc.tobytes(garbage=1, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)


def _pdf_to_docx_text(document: PdfDocument, destination: Path, pages: list[int] | None) -> Path:
    from docx import Document as DocxDocument

    docx = DocxDocument()
    indices = list(range(document.page_count)) if pages is None else list(pages)
    for i, pi in enumerate(indices):
        if pi < 0 or pi >= document.page_count:
            raise IndexError(f"page out of range: {pi}")
        if i > 0:
            docx.add_page_break()
        text = document.page_text(pi) or ""
        if not text.strip():
            docx.add_paragraph("[No extractable text on this page — run OCR first]")
        else:
            for block in text.split("\n"):
                docx.add_paragraph(block)
    docx.save(destination.as_posix())
    return destination


def _pdf_to_docx_layout(
    document: PdfDocument,
    destination: Path,
    pages: list[int] | None,
    progress: Callable[[int, int], None] | None,
) -> Path:
    import logging

    from pdf2docx import Converter

    logging.getLogger("root").setLevel(logging.WARNING)
    data = _live_pdf_bytes(document)
    cv = Converter(stream=data)
    try:
        kwargs = {"multi_processing": False}
        if pages is not None:
            kwargs["pages"] = [int(p) for p in pages]
        if progress is not None:
            progress(0, 1)
        cv.convert(destination.as_posix(), **kwargs)
        if progress is not None:
            progress(1, 1)
    finally:
        cv.close()
    return destination


def _pdf_to_docx_word(document: PdfDocument, destination: Path, pages: list[int] | None) -> Path:
    import fitz

    from core.convert.office_bridge import convert_pdf_to_docx_with_word

    with tempfile.TemporaryDirectory(prefix="monographpdf-word-") as tmp:
        src = Path(tmp) / "source.pdf"
        data = _live_pdf_bytes(document)
        if pages is not None:
            full = fitz.open(stream=data, filetype="pdf")
            part = fitz.open()
            for p in pages:
                part.insert_pdf(full, from_page=int(p), to_page=int(p))
            data = part.tobytes(garbage=1, deflate=True)
            part.close()
            full.close()
        src.write_bytes(data)
        return convert_pdf_to_docx_with_word(src, destination)


def pdf_to_docx(
    document: PdfDocument,
    destination: Path,
    *,
    pages: list[int] | None = None,
    engine: str = "layout",
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; choose one of {ENGINES}")
    if engine == "layout" and not layout_engine_available():
        engine = "text"
    if engine == "word":
        return _pdf_to_docx_word(document, destination, pages)
    if engine == "layout":
        return _pdf_to_docx_layout(document, destination, pages, progress)
    return _pdf_to_docx_text(document, destination, pages)
