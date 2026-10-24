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
    GRAYSCALE = "grayscale"  # shades of gray
    MONOCHROME = "monochrome"  # black and white only (no gray): pictures are dithered


class PageScaling(str, Enum):
    FIT = "fit"  # scale every page to the printable area
    ACTUAL = "actual"  # 100 %, centred (large pages are cropped)
    SHRINK = "shrink"  # 100 %, but shrink pages that are larger than the printable area
    CUSTOM = "custom"  # a chosen percentage, centred (cropped if larger than the printable area)


def place_page(
    page_w: float,
    page_h: float,
    area_w: float,
    area_h: float,
    scaling: PageScaling | str = PageScaling.FIT,
    percent: float = 100.0,
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
    elif mode == PageScaling.CUSTOM:
        k = max(0.05, min(4.0, float(percent) / 100.0))
    else:
        k = 1.0
    w, h = page_w * k, page_h * k
    return (area_w - w) / 2, (area_h - h) / 2, w, h


PAGES_PER_SHEET = (1, 2, 4, 6, 9)


def sheet_grid(n_up: int, area_w: float, area_h: float) -> tuple[int, int]:
    """(columns, rows) for ``n_up`` pages on one sheet, the longer side of the area getting more."""
    n_up = n_up if n_up in PAGES_PER_SHEET else 1
    small, large = {1: (1, 1), 2: (1, 2), 4: (2, 2), 6: (2, 3), 9: (3, 3)}[n_up]
    return (large, small) if area_w >= area_h else (small, large)


def layout_sheet(page_sizes: list[tuple[float, float]], n_up: int, area_w: float, area_h: float,
                 scaling: PageScaling | str = PageScaling.FIT, percent: float = 100.0,
                 gap: float = 8.0) -> list[tuple[float, float, float, float]]:
    """Placement (x, y, w, h) of each page of one sheet inside the printable area. One page per
    sheet follows ``scaling``; several pages per sheet are each fitted into their cell, in reading
    order (left to right, then down)."""
    if n_up <= 1:
        return [place_page(page_sizes[0][0], page_sizes[0][1], area_w, area_h, scaling, percent)] if page_sizes else []
    cols, rows = sheet_grid(n_up, area_w, area_h)
    cw = (area_w - gap * (cols - 1)) / cols
    ch = (area_h - gap * (rows - 1)) / rows
    out = []
    for i, (pw, ph) in enumerate(page_sizes[: cols * rows]):
        c, r = i % cols, i // cols
        x, y, w, h = place_page(pw, ph, cw, ch, PageScaling.FIT)
        out.append((c * (cw + gap) + x, r * (ch + gap) + y, w, h))
    return out


def group_sheets(pages: list[int], n_up: int) -> list[list[int]]:
    n = max(1, n_up)
    return [pages[i:i + n] for i in range(0, len(pages), n)]


def sheet_landscape(page_sizes: list[tuple[float, float]], n_up: int) -> bool:
    """Automatic paper orientation for a sheet: match the page for 1, 4 and 9 per sheet; turn the
    paper the other way for 2 and 6 per sheet (two portrait pages fit side by side on landscape)."""
    if not page_sizes:
        return False
    land = auto_landscape(*page_sizes[0])
    return (not land) if n_up in (2, 6) else land


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


PROTECTED_TEMP_PREFIX = "print-bake-p-"


def _print_temp_path(*, from_protected: bool = False) -> Path:
    """A new temporary file for a baked copy. A copy made from a password-protected PDF is marked
    (``print-bake-p-``) so that one left behind by a crash is removed at the next start of Monograph
    PDF regardless of its age (core/organize/temputil.py), not only after a day."""
    from app.paths import TEMP_DIR

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    prefix = PROTECTED_TEMP_PREFIX if from_protected else "print-bake-"
    return TEMP_DIR / f"{prefix}{uuid.uuid4().hex}.pdf"


def _is_protected_document(document) -> bool:
    try:
        from core.security.protection import is_protected

        return is_protected(document._backend._doc)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False


def prepare_current_source(
    document: PdfDocument, edit: Any | None = None, *, flatten: bool = False, flatten_comments: bool = True,
    keep_encryption: bool = False,
) -> PrintSource:
    """The document as it is shown, including every unsaved change: text boxes, shapes, images,
    tables, typed form entries and field formatting, replaced text and page changes.

    Without unsaved changes this is the open document itself. Otherwise it is a temporary
    baked copy (removed by ``close()``; the file on disk is never touched), without password
    protection so exports can read it. Used by printing and by every export / conversion.
    """
    if not print_needs_bake(edit):
        return PrintSource(document=document, temp_path=None, owns_document=False)

    from engines.bake_edits import bake_via_backend

    dest = _print_temp_path(from_protected=_is_protected_document(document))
    prev_flatten = bool(getattr(edit, "flatten_on_save", False))
    try:
        edit.flatten_comments = flatten_comments
        bake_via_backend(edit, dest, flatten=flatten or prev_flatten, keep_encryption=keep_encryption)
    except BaseException:
        dest.unlink(missing_ok=True)  # never leave a (possibly decrypted) copy behind
        raise
    finally:
        try:
            edit.flatten_on_save = prev_flatten
            edit.flatten_comments = True
        except Exception:  # noqa: BLE001
            pass

    backend = getattr(document, "_backend", None)
    password = getattr(backend, "_password", None) if keep_encryption else None
    try:
        try:
            baked = open_document(dest, password=password)
        except Exception:  # noqa: BLE001 — a copy kept protected opens with the document's password
            baked = open_document(dest)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    if keep_encryption and backend is not None:
        # the permissions password entered for the document also counts for its temporary copy
        baked._backend._owner_unlocked = bool(getattr(backend, "_owner_unlocked", False))  # noqa: SLF001
    return PrintSource(document=baked, temp_path=dest, owns_document=True)


def prepare_print_source(document: PdfDocument, edit: Any | None = None) -> PrintSource:
    """Like ``prepare_current_source``, with form fields flattened so their appearances print
    reliably. Comments stay annotations, so the print job can include or leave them out."""
    return prepare_current_source(document, edit, flatten=True, flatten_comments=False)


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


def _is_comment(annot) -> bool:
    import fitz

    return annot.type[0] not in (fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_POPUP)


def _render_without_comments(document: PdfDocument, page_index: int, zoom: float) -> bytes | None:
    """PNG of the page with comments and markup left out (form fields still print), or None when
    the page has no comments."""
    import fitz

    src = document._backend._doc  # noqa: SLF001
    page = src.load_page(page_index)
    if not any(_is_comment(a) for a in page.annots()):
        return None
    one = fitz.open()
    try:
        one.insert_pdf(src, from_page=page_index, to_page=page_index)
        p = one.load_page(0)
        for annot in [a for a in p.annots() if _is_comment(a)]:
            p.delete_annot(annot)
        return p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
    finally:
        one.close()


def render_page_png_for_print(
    document: PdfDocument,
    page_index: int,
    *,
    dpi: int = 300,
    color_mode: ColorMode = ColorMode.COLOR,
    comments: bool = True,
) -> bytes:
    """Rasterize one page at print DPI; optional grayscale for black-and-white jobs.
    ``comments=False`` leaves out comments and markup (notes, highlights, shapes, stamps);
    form fields and the page itself still print."""
    zoom = max(0.5, float(dpi) / 72.0)
    png = None if comments else _render_without_comments(document, page_index, zoom)
    if png is None:
        png = document.render_pixmap_png(page_index, zoom=zoom)
    return apply_color_mode(png, color_mode)


def order_print_pages(pages: list[int], *, subset: str = "all", reverse: bool = False) -> list[int]:
    """Apply an odd / even page-number subset (page numbers are 1-based) and reverse order."""
    if subset == "odd":
        pages = [p for p in pages if (p + 1) % 2 == 1]
    elif subset == "even":
        pages = [p for p in pages if (p + 1) % 2 == 0]
    return list(reversed(pages)) if reverse else list(pages)


def _png_to_grayscale(png: bytes) -> bytes:
    return apply_color_mode(png, ColorMode.GRAYSCALE)


def apply_color_mode(png: bytes, mode: ColorMode | str) -> bytes:
    """The rendered page for the chosen colour mode (the document itself is never changed).

    Grayscale keeps shades of gray. Black and white uses only black and white pixels: Floyd–Steinberg
    dithering keeps photographs, microscopy images and charts recognisable, while text and thin lines,
    rendered at print resolution, stay solid."""
    mode = ColorMode(mode)
    if mode == ColorMode.COLOR:
        return png
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png))
    img = img.convert("L")
    if mode == ColorMode.MONOCHROME:
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
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
    if options.color_mode != ColorMode.COLOR:
        for path in paths:
            path.write_bytes(apply_color_mode(path.read_bytes(), options.color_mode))
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


def save_pages_as_pdf(document: PdfDocument, pages: list[int], destination: Path, *, comments: bool = True) -> Path:
    """Application "Save as PDF" from the print dialog: the chosen pages, in print order, copied as PDF
    pages — text stays text and pictures keep their resolution (nothing is rasterised). Print-only
    settings (paper, scaling, colour, pages per sheet) do not apply. Written atomically."""
    import fitz

    src = document._backend._doc  # noqa: SLF001
    out = fitz.open()
    try:
        for index in pages:
            out.insert_pdf(src, from_page=index, to_page=index, annots=True)
            if not comments:
                page = out[-1]
                for annot in [a for a in page.annots() if _is_comment(a)]:
                    page.delete_annot(annot)
        destination = Path(destination)
        tmp = destination.with_name(destination.name + ".part")
        out.save(tmp.as_posix(), garbage=3, deflate=True)
    finally:
        out.close()
    tmp.replace(destination)
    return destination
