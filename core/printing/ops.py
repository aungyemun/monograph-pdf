"""Prepare pages for QPrinter — overlays baked for WYSIWYG; export PDF stays independent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from core.document import PdfDocument, open_document
from core.convert.pdf_to_images import pdf_pages_to_images
from core.organize.page_ops import parse_page_ranges


class ColorMode(str, Enum):
    COLOR = "color"
    GRAYSCALE = "grayscale"


class PageScaling(str, Enum):
    FIT = "fit"  # scale every page to the printable area
    ACTUAL = "actual"  # 100 %, centred (large pages are cropped)
    SHRINK = "shrink"  # 100 %, but shrink pages that are larger than the printable area


def place_page(
    page_w: float,
    page_h: float,
    area_w: float,
    area_h: float,
    scaling: PageScaling | str = PageScaling.FIT,
) -> tuple[float, float, float, float]:
    """Where a page lands inside the printable area: (x, y, w, h), all in the same unit.

    The aspect ratio is always kept and the page is centred. Used by the print preview and the
    print job alike, so the preview shows exactly what comes out of the printer.
    """
    if page_w <= 0 or page_h <= 0 or area_w <= 0 or area_h <= 0:
        return 0.0, 0.0, 0.0, 0.0
    fit = min(area_w / page_w, area_h / page_h)
    mode = PageScaling(scaling)
    if mode == PageScaling.FIT:
        k = fit
    elif mode == PageScaling.SHRINK:
        k = min(1.0, fit)
    else:
        k = 1.0
    w, h = page_w * k, page_h * k
    return (area_w - w) / 2, (area_h - h) / 2, w, h


def auto_landscape(page_w: float, page_h: float) -> bool:
    """Auto orientation: landscape paper for pages wider than they are tall."""
    return page_w > page_h * 1.02


@dataclass
class PrintOptions:
    page_range: str = ""  # empty = all; 1-based "1-3,5"
    dpi: int = 300
    landscape: bool = False
    scale_percent: int = 100  # 100 = fit handled by printer UI
    color_mode: ColorMode = ColorMode.COLOR


@dataclass
class PrintSource:
    """Document used for rasterizing print pages (may be a temp bake of overlays)."""

    document: PdfDocument
    temp_path: Path | None = None
    owns_document: bool = False

    def close(self) -> None:
        if self.owns_document:
            try:
                self.document.close()
            except Exception:  # noqa: BLE001
                pass
        if self.temp_path is not None:
            try:
                self.temp_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass


def resolve_print_pages(document: PdfDocument, options: PrintOptions) -> list[int]:
    if not (options.page_range or "").strip():
        return list(range(document.page_count))
    return parse_page_ranges(options.page_range, document.page_count)


def print_needs_bake(edit: Any | None) -> bool:
    """True when unsaved overlays/forms must be burned in so print matches the canvas.

    Any unsaved change counts (typed form entries, field formatting, text boxes, shapes, images,
    tables, replaced text): printing then uses a temporary baked copy, never the file on disk.
    """
    if edit is None:
        return False
    if getattr(edit, "dirty", False):
        return True
    if getattr(edit, "objects", None) and edit.objects:
        return True
    if getattr(edit, "shapes", None) and edit.shapes:
        return True
    if getattr(edit, "images", None) and edit.images:
        return True
    if getattr(edit, "tables", None) and edit.tables:
        return True
    if getattr(edit, "native_replacements", None) and edit.native_replacements:
        return True
    for field in (getattr(edit, "fields", None) or {}).values():
        if getattr(field, "is_candidate", False):
            continue
        if (
            getattr(field, "value_dirty", False)
            or getattr(field, "appearance_dirty", False)
            or getattr(field, "style_dirty", False)
        ):
            return True
        if not getattr(field, "is_acroform", True):
            return True
    return False


def _print_temp_path() -> Path:
    from app.paths import TEMP_DIR

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR / f"print-bake-{uuid.uuid4().hex}.pdf"


def prepare_current_source(document: PdfDocument, edit: Any | None = None, *, flatten: bool = False) -> PrintSource:
    """The document as it is shown, including every unsaved change: text boxes, shapes, images,
    tables, typed form entries and field formatting, replaced text and page changes.

    Without unsaved changes this is the open document itself. Otherwise it is a temporary
    baked copy (removed by ``close()``; the file on disk is never touched), without password
    protection so exports can read it. Used by printing and by every export / conversion.
    """
    if not print_needs_bake(edit):
        return PrintSource(document=document, temp_path=None, owns_document=False)

    from engines.bake_edits import bake_via_backend

    dest = _print_temp_path()
    prev_flatten = bool(getattr(edit, "flatten_on_save", False))
    try:
        bake_via_backend(edit, dest, flatten=flatten or prev_flatten, keep_encryption=False)
    finally:
        try:
            edit.flatten_on_save = prev_flatten
        except Exception:  # noqa: BLE001
            pass

    baked = open_document(dest)
    return PrintSource(document=baked, temp_path=dest, owns_document=True)


def prepare_print_source(document: PdfDocument, edit: Any | None = None) -> PrintSource:
    """Like ``prepare_current_source``, flattened so field appearances print reliably."""
    return prepare_current_source(document, edit, flatten=True)


def effective_print_dpi(printer: Any | None = None, *, fallback: int = 300, floor: int = 220, ceiling: int = 400) -> int:
    """Pick a sharp print DPI from the printer without creating enormous bitmaps."""
    res = fallback
    if printer is not None:
        try:
            reported = int(printer.resolution())
            if reported >= 72:
                res = reported
        except Exception:  # noqa: BLE001
            pass
    return max(floor, min(ceiling, res))


def render_page_png_for_print(
    document: PdfDocument,
    page_index: int,
    *,
    dpi: int = 300,
    color_mode: ColorMode = ColorMode.COLOR,
) -> bytes:
    """Rasterize one page at print DPI; optional grayscale for black-and-white jobs."""
    zoom = max(0.5, float(dpi) / 72.0)
    png = document.render_pixmap_png(page_index, zoom=zoom)
    if color_mode != ColorMode.GRAYSCALE:
        return png
    return _png_to_grayscale(png)


def _png_to_grayscale(png: bytes) -> bytes:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if img.mode != "L":
        img = img.convert("L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_pages_for_print(
    document: PdfDocument,
    output_dir: Path,
    options: PrintOptions,
) -> list[Path]:
    pages = resolve_print_pages(document, options)
    paths = pdf_pages_to_images(
        document,
        output_dir,
        pages=pages,
        fmt="png",
        dpi=options.dpi,
        name_prefix="print",
    )
    if options.color_mode == ColorMode.GRAYSCALE:
        for path in paths:
            path.write_bytes(_png_to_grayscale(path.read_bytes()))
    return paths


def iter_print_page_images(
    source: PrintSource,
    pages: list[int],
    *,
    dpi: int,
    color_mode: ColorMode,
) -> Iterator[tuple[int, bytes]]:
    for page_index in pages:
        yield page_index, render_page_png_for_print(
            source.document,
            page_index,
            dpi=dpi,
            color_mode=color_mode,
        )
