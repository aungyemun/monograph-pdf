"""Create native PDF annotations via PyMuPDF (not painted overlays)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import fitz

from core.document import PdfDocument
from core.editing.geometry import Point, Rect


class AnnotKind(str, Enum):
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    STRIKEOUT = "strikeout"
    TEXT = "text"
    CALLOUT = "callout"
    INK = "ink"
    LINE = "line"
    ARROW = "arrow"
    RECT = "rect"
    ELLIPSE = "ellipse"
    STAMP = "stamp"


class StampKind(str, Enum):
    """Built-in MuPDF stamp icons (no custom licensed artwork required)."""

    APPROVED = "Approved"
    CONFIDENTIAL = "Confidential"
    DRAFT = "Draft"
    FINAL = "Final"
    FOR_COMMENT = "ForComment"
    NOT_APPROVED = "NotApproved"
    EXPERIMENTAL = "Experimental"
    AS_IS = "AsIs"
    EXPIRED = "Expired"
    NOT_FOR_PUBLIC = "NotForPublicRelease"
    FOR_PUBLIC = "ForPublicRelease"
    SOLD = "Sold"
    DEPARTMENTAL = "Departmental"
    TOP_SECRET = "TopSecret"

    def to_mupdf(self) -> int:
        mapping = {
            StampKind.APPROVED: getattr(fitz, "STAMP_Approved", 0),
            StampKind.AS_IS: getattr(fitz, "STAMP_AsIs", 1),
            StampKind.CONFIDENTIAL: getattr(fitz, "STAMP_Confidential", 2),
            StampKind.DEPARTMENTAL: getattr(fitz, "STAMP_Departmental", 3),
            StampKind.EXPERIMENTAL: getattr(fitz, "STAMP_Experimental", 4),
            StampKind.EXPIRED: getattr(fitz, "STAMP_Expired", 5),
            StampKind.FINAL: getattr(fitz, "STAMP_Final", 6),
            StampKind.FOR_COMMENT: getattr(fitz, "STAMP_ForComment", 7),
            StampKind.FOR_PUBLIC: getattr(fitz, "STAMP_ForPublicRelease", 8),
            StampKind.NOT_APPROVED: getattr(fitz, "STAMP_NotApproved", 9),
            StampKind.NOT_FOR_PUBLIC: getattr(fitz, "STAMP_NotForPublicRelease", 10),
            StampKind.SOLD: getattr(fitz, "STAMP_Sold", 11),
            StampKind.DRAFT: getattr(fitz, "STAMP_Draft", 12),
            StampKind.TOP_SECRET: getattr(fitz, "STAMP_TopSecret", 13),
        }
        return int(mapping.get(self, getattr(fitz, "STAMP_Draft", 12)))


@dataclass
class AnnotInfo:
    page_index: int
    kind: str
    rect: tuple[float, float, float, float]
    content: str = ""


def _page(document: PdfDocument, page_index: int) -> fitz.Page:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    if page_index < 0 or page_index >= doc.page_count:
        raise IndexError(f"page out of range: {page_index}")
    return doc.load_page(page_index)


def _fitz_rect(r: Rect) -> fitz.Rect:
    return fitz.Rect(r.x, r.y, r.x1, r.y1)


def add_highlight(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (1, 1, 0),
    content: str = "",
) -> None:
    page = _page(document, page_index)
    quads = [_fitz_rect(r) for r in rects]
    if not quads:
        raise ValueError("no highlight regions")
    annot = page.add_highlight_annot(quads)
    annot.set_colors(stroke=color)
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()


def add_underline(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (0, 0, 1),
    content: str = "",
) -> None:
    page = _page(document, page_index)
    annot = page.add_underline_annot([_fitz_rect(r) for r in rects])
    annot.set_colors(stroke=color)
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()


def add_strikeout(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (1, 0, 0),
    content: str = "",
) -> None:
    page = _page(document, page_index)
    annot = page.add_strikeout_annot([_fitz_rect(r) for r in rects])
    annot.set_colors(stroke=color)
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()


def add_text_comment(
    document: PdfDocument,
    page_index: int,
    point: Point,
    text: str,
    *,
    icon: str = "Comment",
) -> None:
    page = _page(document, page_index)
    annot = page.add_text_annot(fitz.Point(point.x, point.y), text, icon=icon)
    annot.update()
    document.invalidate_pages()


def add_callout(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    text: str,
    *,
    callout_point: Point | None = None,
) -> None:
    """Free-text annotation with optional callout line (best-effort)."""
    page = _page(document, page_index)
    fr = _fitz_rect(rect)
    annot = page.add_freetext_annot(fr, text, fontsize=10, fontname="helv", border_color=(0, 0, 0))
    if callout_point is not None:
        try:
            # Callout: end point of leader line
            annot.set_border(width=1)
            annot.set_info(content=text)
            # PyMuPDF callout via set_line_ends / ink — use line from callout to rect
            p = fitz.Point(callout_point.x, callout_point.y)
            mid = fitz.Point(fr.x0, (fr.y0 + fr.y1) / 2)
            line = page.add_line_annot(p, mid)
            line.set_colors(stroke=(0, 0, 0))
            line.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
            line.update()
        except Exception:  # noqa: BLE001
            pass
    annot.update()
    document.invalidate_pages()


def add_freehand(
    document: PdfDocument,
    page_index: int,
    strokes: Sequence[Sequence[Point]],
    *,
    color: tuple[float, float, float] = (0, 0, 0),
    width: float = 1.5,
) -> None:
    page = _page(document, page_index)
    # MuPDF expects sequence of sequence of float pairs
    ink = [[(float(p.x), float(p.y)) for p in stroke] for stroke in strokes if stroke]
    if not ink:
        raise ValueError("no ink points")
    annot = page.add_ink_annot(ink)
    annot.set_border(width=width)
    annot.set_colors(stroke=color)
    annot.update()
    document.invalidate_pages()


def add_line_arrow(
    document: PdfDocument,
    page_index: int,
    start: Point,
    end: Point,
    *,
    arrow: bool = True,
    color: tuple[float, float, float] = (0, 0, 0),
    width: float = 1.0,
) -> None:
    page = _page(document, page_index)
    annot = page.add_line_annot(fitz.Point(start.x, start.y), fitz.Point(end.x, end.y))
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    if arrow:
        annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
    annot.update()
    document.invalidate_pages()


def add_rectangle(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    *,
    color: tuple[float, float, float] = (1, 0, 0),
    fill: tuple[float, float, float] | None = None,
    width: float = 1.0,
) -> None:
    page = _page(document, page_index)
    annot = page.add_rect_annot(_fitz_rect(rect))
    annot.set_colors(stroke=color, fill=fill)
    annot.set_border(width=width)
    annot.update()
    document.invalidate_pages()


def add_ellipse(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    *,
    color: tuple[float, float, float] = (0, 0, 1),
    fill: tuple[float, float, float] | None = None,
    width: float = 1.0,
) -> None:
    page = _page(document, page_index)
    annot = page.add_circle_annot(_fitz_rect(rect))
    annot.set_colors(stroke=color, fill=fill)
    annot.set_border(width=width)
    annot.update()
    document.invalidate_pages()


def add_stamp(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    stamp: StampKind = StampKind.DRAFT,
) -> None:
    """Built-in PDF stamp icons — no third-party stamp artwork required."""
    page = _page(document, page_index)
    annot = page.add_stamp_annot(_fitz_rect(rect), stamp=stamp.to_mupdf())
    annot.update()
    document.invalidate_pages()


def list_annotations(document: PdfDocument) -> list[AnnotInfo]:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    out: list[AnnotInfo] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        for annot in page.annots() or []:
            r = annot.rect
            info = annot.info or {}
            out.append(
                AnnotInfo(
                    page_index=i,
                    kind=str(annot.type[1] if annot.type else "annot"),
                    rect=(float(r.x0), float(r.y0), float(r.x1), float(r.y1)),
                    content=str(info.get("content") or ""),
                )
            )
    return out
