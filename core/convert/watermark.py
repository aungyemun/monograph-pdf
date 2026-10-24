"""Watermark, header/footer and page-number tools (offline) — compatibility functions.

These keep the original signatures and defaults; the drawing is done by
``core.convert.page_marks``, which places every mark upright on the *displayed* page (rotated
pages included) and tags it so it can be replaced or removed later. Each call adds to what is
already there (``replace_existing=False``), as before.
"""

from __future__ import annotations

from pathlib import Path

from core.convert.page_marks import HeaderFooterSpec, WatermarkSpec, apply_page_marks
from core.document import PdfDocument


def apply_watermark(
    document: PdfDocument,
    destination: Path,
    *,
    text: str,
    opacity: float = 0.25,
    rotate: float = 45.0,
    fontsize: float = 48.0,
    pages: list[int] | None = None,
    color: tuple[float, float, float] = (0.55, 0.55, 0.55),
) -> Path:
    spec = WatermarkSpec(text=text, opacity=opacity, rotation=rotate, font_size=fontsize, color=tuple(color))
    apply_page_marks(document, destination, watermark=spec, pages=pages, replace_existing=False)
    return Path(destination)


def apply_headers_footers(
    document: PdfDocument,
    destination: Path,
    *,
    header: str = "",
    footer: str = "",
    fontsize: float = 9.0,
    margin: float = 36.0,
    pages: list[int] | None = None,
) -> Path:
    spec = HeaderFooterSpec(header_left=header,
                            footer_left=footer, font_size=fontsize, color=(0.2, 0.2, 0.2),
                            margin_top=margin, margin_bottom=margin * 0.6, margin_left=margin, margin_right=margin)
    if spec.is_empty():  # nothing to add: an unchanged copy, as before
        _plain_copy(document, Path(destination))
    else:
        apply_page_marks(document, destination, header_footer=spec, pages=pages, replace_existing=False)
    return Path(destination)


def _plain_copy(document: PdfDocument, destination: Path) -> None:
    from core.convert.copy_pdf import copy_pdf_preserving_metadata

    copy_pdf_preserving_metadata(document, destination)


def apply_page_numbers(
    document: PdfDocument,
    destination: Path,
    *,
    fmt: str = "{page} / {total}",
    fontsize: float = 10.0,
    margin: float = 36.0,
    pages: list[int] | None = None,
) -> Path:
    spec = HeaderFooterSpec(footer_right=fmt, font_size=fontsize, color=(0.15, 0.15, 0.15),
                            margin_bottom=margin * 0.6, margin_left=margin, margin_right=margin)
    apply_page_marks(document, destination, header_footer=spec, pages=pages, replace_existing=False)
    return Path(destination)
