"""In-memory page structure operations on PdfDocument (source file untouched until Save)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import fitz

from core.document import DocumentError, InvalidPdfError, PasswordRequiredError, PdfDocument


@dataclass(frozen=True)
class PageRange:
    start: int  # inclusive, 0-based
    end: int  # inclusive, 0-based

    def indices(self) -> list[int]:
        if self.end < self.start:
            return []
        return list(range(self.start, self.end + 1))


@dataclass(frozen=True)
class PageSizeInfo:
    page_index: int
    width_pt: float
    height_pt: float
    rotation: int
    cropbox: tuple[float, float, float, float]  # x0,y0,x1,y1
    mediabox: tuple[float, float, float, float]


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """
    Parse '1,3-5,8' (1-based, inclusive) into sorted unique 0-based indices.
    Raises ValueError on bad input.
    """
    if page_count <= 0:
        return []
    spec = (spec or "").strip()
    if not spec:
        return []
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if start < 1 or end < 1 or end < start:
                raise ValueError(f"Invalid range: {part}")
            for n in range(start, end + 1):
                if n > page_count:
                    raise ValueError(f"Page {n} out of range (1..{page_count})")
                out.add(n - 1)
        else:
            n = int(part)
            if n < 1 or n > page_count:
                raise ValueError(f"Page {n} out of range (1..{page_count})")
            out.add(n - 1)
    return sorted(out)


def _doc(document: PdfDocument) -> fitz.Document:
    backend = document._backend  # noqa: SLF001
    if backend is None or backend._doc is None or backend._doc.is_closed:  # noqa: SLF001
        raise DocumentError("Document is closed")
    return backend._doc  # noqa: SLF001


def _require_assemble(document: PdfDocument) -> None:
    """
    Structural ops run on the unlocked in-memory document.
    PDF permission bits are advisory for this offline editor; signature impact is
    warned in the UI. Refuse only when the handle is closed.
    """
    _doc(document)  # raises DocumentError if closed


def invalidate_page_cache(document: PdfDocument) -> None:
    document.invalidate_pages()


def inspect_page_sizes(document: PdfDocument) -> list[PageSizeInfo]:
    d = _doc(document)
    result: list[PageSizeInfo] = []
    for i in range(d.page_count):
        page = d.load_page(i)
        mb = page.mediabox
        cb = page.cropbox
        result.append(
            PageSizeInfo(
                page_index=i,
                width_pt=float(page.rect.width),
                height_pt=float(page.rect.height),
                rotation=int(page.rotation),
                cropbox=(float(cb.x0), float(cb.y0), float(cb.x1), float(cb.y1)),
                mediabox=(float(mb.x0), float(mb.y0), float(mb.x1), float(mb.y1)),
            )
        )
    return result


def insert_blank_page(
    document: PdfDocument,
    at_index: int,
    *,
    width: float | None = None,
    height: float | None = None,
) -> int:
    """Insert a blank page at at_index (0-based). Returns new page index."""
    _require_assemble(document)
    d = _doc(document)
    n = d.page_count
    if at_index < 0 or at_index > n:
        raise IndexError(f"insert index out of range: {at_index}")
    if width is None or height is None:
        if n > 0:
            ref = d.load_page(min(at_index, n - 1) if at_index > 0 else 0)
            width = width or float(ref.rect.width)
            height = height or float(ref.rect.height)
        else:
            width = width or 595.0
            height = height or 842.0
    d.new_page(pno=at_index, width=width, height=height)
    invalidate_page_cache(document)
    return at_index


def insert_pdf_pages(
    document: PdfDocument,
    source: Path | PdfDocument,
    *,
    at_index: int,
    source_pages: Sequence[int] | None = None,
    password: str | None = None,
) -> int:
    """Insert pages from another PDF before at_index. Returns count inserted. Source file preserved."""
    _require_assemble(document)
    d = _doc(document)
    n = d.page_count
    if at_index < 0 or at_index > n:
        raise IndexError(f"insert index out of range: {at_index}")

    own_src = False
    if isinstance(source, PdfDocument):
        src_doc = _doc(source)
    else:
        src_doc = _open_external(Path(source), password=password)
        own_src = True
    try:
        if source_pages is None:
            from_page, to_page = 0, src_doc.page_count - 1
            count = src_doc.page_count
            d.insert_pdf(src_doc, from_page=from_page, to_page=to_page, start_at=at_index)
        else:
            pages = list(source_pages)
            for p in pages:
                if p < 0 or p >= src_doc.page_count:
                    raise IndexError(f"source page out of range: {p}")
            # Insert in reverse so indices stay stable relative to at_index
            for offset, p in enumerate(pages):
                d.insert_pdf(src_doc, from_page=p, to_page=p, start_at=at_index + offset)
            count = len(pages)
    finally:
        if own_src:
            src_doc.close()
    invalidate_page_cache(document)
    return count


def delete_pages(document: PdfDocument, pages: Sequence[int]) -> int:
    _require_assemble(document)
    d = _doc(document)
    unique = sorted({int(p) for p in pages}, reverse=True)
    for p in unique:
        if p < 0 or p >= d.page_count:
            raise IndexError(f"page out of range: {p}")
        d.delete_page(p)
    invalidate_page_cache(document)
    return len(unique)


def duplicate_pages(document: PdfDocument, pages: Sequence[int], *, after: bool = True) -> list[int]:
    """Duplicate listed pages; inserts copies immediately after (or before) each source."""
    _require_assemble(document)
    d = _doc(document)
    # Work high-to-low so earlier duplicates don't shift later sources incorrectly when after=True
    sources = sorted({int(p) for p in pages})
    for p in sources:
        if p < 0 or p >= d.page_count:
            raise IndexError(f"page out of range: {p}")
    # Build temp copy of selected pages then insert
    tmp = fitz.open()
    try:
        for p in sources:
            tmp.insert_pdf(d, from_page=p, to_page=p)
        inserted_at: list[int] = []
        # Insert copies after the last selected (simple, predictable): after max(sources)
        insert_at = (max(sources) + 1) if after else min(sources)
        d.insert_pdf(tmp, start_at=insert_at)
        for i in range(tmp.page_count):
            inserted_at.append(insert_at + i)
    finally:
        tmp.close()
    invalidate_page_cache(document)
    return inserted_at


def replace_page(
    document: PdfDocument,
    page_index: int,
    source: Path | PdfDocument,
    *,
    source_page: int = 0,
    password: str | None = None,
) -> None:
    """Replace one page with a page from another PDF. Source file preserved."""
    _require_assemble(document)
    d = _doc(document)
    if page_index < 0 or page_index >= d.page_count:
        raise IndexError(f"page out of range: {page_index}")
    own_src = False
    if isinstance(source, PdfDocument):
        src_doc = _doc(source)
    else:
        src_doc = _open_external(Path(source), password=password)
        own_src = True
    try:
        if source_page < 0 or source_page >= src_doc.page_count:
            raise IndexError(f"source page out of range: {source_page}")
        d.delete_page(page_index)
        d.insert_pdf(src_doc, from_page=source_page, to_page=source_page, start_at=page_index)
    finally:
        if own_src:
            src_doc.close()
    invalidate_page_cache(document)


def reorder_pages(document: PdfDocument, new_order: Sequence[int]) -> None:
    """Reorder all pages; new_order is a permutation of 0..n-1."""
    _require_assemble(document)
    d = _doc(document)
    n = d.page_count
    order = list(new_order)
    if len(order) != n or sorted(order) != list(range(n)):
        raise ValueError("new_order must be a permutation of all page indices")
    if order == list(range(n)):
        return
    tmp = fitz.open()
    try:
        for i in order:
            tmp.insert_pdf(d, from_page=i, to_page=i)
        # Replace content: delete all then insert
        while d.page_count:
            d.delete_page(0)
        d.insert_pdf(tmp)
    finally:
        tmp.close()
    invalidate_page_cache(document)


def move_page(document: PdfDocument, from_index: int, to_index: int) -> None:
    """Move a single page to a new index (0-based destination before shift)."""
    d = _doc(document)
    n = d.page_count
    if from_index < 0 or from_index >= n:
        raise IndexError(f"from_index out of range: {from_index}")
    if to_index < 0 or to_index >= n:
        raise IndexError(f"to_index out of range: {to_index}")
    if from_index == to_index:
        return
    order = list(range(n))
    item = order.pop(from_index)
    order.insert(to_index, item)
    reorder_pages(document, order)


def rotate_pages(document: PdfDocument, pages: Sequence[int], degrees: int) -> None:
    """Add rotation (multiple of 90) to listed pages."""
    _require_assemble(document)
    if degrees % 90 != 0:
        raise ValueError("rotation must be a multiple of 90")
    d = _doc(document)
    for p in pages:
        if p < 0 or p >= d.page_count:
            raise IndexError(f"page out of range: {p}")
        page = d.load_page(int(p))
        page.set_rotation((int(page.rotation) + int(degrees)) % 360)
    document.refresh_pages(pages)  # only these pages changed: no need to re-read the whole document


def crop_page(
    document: PdfDocument,
    page_index: int,
    crop: tuple[float, float, float, float],
    *,
    relative_to_mediabox: bool = True,
) -> None:
    """
    Set CropBox for a page. crop is (x0, y0, x1, y1) in PDF points.
    Visually clips the page; original media retained unless later flattened.
    """
    _require_assemble(document)
    d = _doc(document)
    if page_index < 0 or page_index >= d.page_count:
        raise IndexError(f"page out of range: {page_index}")
    page = d.load_page(page_index)
    x0, y0, x1, y1 = crop
    rect = fitz.Rect(x0, y0, x1, y1)
    if relative_to_mediabox:
        mb = page.mediabox
        rect = fitz.Rect(
            max(mb.x0, rect.x0),
            max(mb.y0, rect.y0),
            min(mb.x1, rect.x1),
            min(mb.y1, rect.y1),
        )
    if rect.is_empty or rect.width < 1 or rect.height < 1:
        raise ValueError("crop rectangle is empty")
    page.set_cropbox(rect)
    invalidate_page_cache(document)


def extract_pages(
    document: PdfDocument,
    pages: Sequence[int],
    destination: Path,
) -> Path:
    """Write selected pages to a new PDF. Source document unchanged on disk."""
    d = _doc(document)
    indices = sorted({int(p) for p in pages})
    if not indices:
        raise ValueError("no pages to extract")
    for p in indices:
        if p < 0 or p >= d.page_count:
            raise IndexError(f"page out of range: {p}")
    from core.security.protection import is_protected, save_copy, working_copy

    if is_protected(d):
        # the pages of a protected PDF stay protected (same passwords and permissions)
        out = working_copy(document)
        try:
            out.select(indices)
            save_copy(out, Path(destination))
        finally:
            out.close()
        return Path(destination)
    out = fitz.open()
    try:
        for p in indices:
            out.insert_pdf(d, from_page=p, to_page=p)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        out.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        out.close()
    return destination


def copy_pages_between(
    source: PdfDocument,
    destination: PdfDocument,
    pages: Sequence[int],
    *,
    at_index: int | None = None,
) -> int:
    """Copy pages from source doc into destination (both open in memory). Sources on disk preserved."""
    _require_assemble(destination)
    src = _doc(source)
    dst = _doc(destination)
    insert_at = dst.page_count if at_index is None else at_index
    if insert_at < 0 or insert_at > dst.page_count:
        raise IndexError(f"at_index out of range: {insert_at}")
    count = 0
    for offset, p in enumerate(pages):
        pi = int(p)
        if pi < 0 or pi >= src.page_count:
            raise IndexError(f"source page out of range: {pi}")
        dst.insert_pdf(src, from_page=pi, to_page=pi, start_at=insert_at + offset)
        count += 1
    invalidate_page_cache(destination)
    return count


def _open_external(path: Path, *, password: str | None = None) -> fitz.Document:
    path = Path(path)
    if not path.is_file():
        raise InvalidPdfError(f"File not found: {path}")
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise InvalidPdfError(f"Cannot open PDF: {exc}") from exc
    if doc.is_encrypted or doc.needs_pass:
        if not password:
            doc.close()
            raise PasswordRequiredError("Password required")
        if not doc.authenticate(password):
            doc.close()
            raise PasswordRequiredError("Incorrect password")
    if doc.page_count < 0:
        doc.close()
        raise InvalidPdfError("Invalid PDF structure")
    return doc


def warning_for_signatures(document: PdfDocument) -> str | None:
    meta = document.metadata()
    if meta.has_digital_signatures:
        return (
            "This document appears to contain digital signature fields or signature "
            "dictionaries. Reordering, rotating, inserting, deleting, or combining pages will "
            "invalidate cryptographic signatures."
        )
    return None
