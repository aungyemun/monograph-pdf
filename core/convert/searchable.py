"""Scanned PDF → searchable PDF via offline OCR (high confidence when tessdata present)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.document import PdfDocument
from core.ocr.pipeline import OcrOptions, run_ocr

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]


def scanned_to_searchable_pdf(
    document: PdfDocument,
    destination: Path,
    *,
    pages: list[int] | None = None,
    languages: str = "eng+jpn",
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
) -> Path:
    """
    OCR pages that need it (or explicit pages) and write searchable output.
    Does not download models; uses project tessdata.
    """
    opts = OcrOptions(
        languages=languages,
        pages=pages,
        skip_native_text=pages is None,
        make_searchable=True,
        reconstruct_visual=False,
    )
    result = run_ocr(
        document,
        opts,
        progress=progress,
        cancel=cancel,
        destination=Path(destination),
    )
    if result.output_path is None:
        raise RuntimeError("Searchable PDF was not written")
    return result.output_path
