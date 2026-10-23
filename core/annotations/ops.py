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
    xref: int = 0
    author: str = ""
    modified: str = ""
    color: str = ""  # #rrggbb of the stroke colour, if any
    opacity: float = 1.0
    is_reply_or_popup: bool = False
    marked_text: str = ""  # the words a highlight / underline / strikethrough covers


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
    nm: str | None = None,
    opacity: float = 1.0,
) -> int:
    """Add a highlight; returns the annotation xref. ``nm`` gives it a stable identity (/NM) so undo
    and redo find it again even when its xref changes."""
    page = _page(document, page_index)
    quads = [_fitz_rect(r) for r in rects]
    if not quads:
        raise ValueError("no highlight regions")
    annot = page.add_highlight_annot(quads)
    annot.set_colors(stroke=color)
    if opacity < 0.999:
        annot.set_opacity(max(0.05, opacity))
    if content:
        annot.set_info(content=content)
    annot.update()
    if nm:
        _set_nm(document, int(annot.xref), nm)
    document.invalidate_pages()
    return int(annot.xref)


def add_underline(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (0, 0, 1),
    content: str = "",
    opacity: float = 1.0,
) -> int:
    page = _page(document, page_index)
    annot = page.add_underline_annot([_fitz_rect(r) for r in rects])
    annot.set_colors(stroke=color)
    if opacity < 0.999:
        annot.set_opacity(max(0.05, opacity))
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()
    return int(annot.xref)


def add_strikeout(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (1, 0, 0),
    content: str = "",
    opacity: float = 1.0,
) -> int:
    page = _page(document, page_index)
    annot = page.add_strikeout_annot([_fitz_rect(r) for r in rects])
    annot.set_colors(stroke=color)
    if opacity < 0.999:
        annot.set_opacity(max(0.05, opacity))
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()
    return int(annot.xref)


def add_squiggly(
    document: PdfDocument,
    page_index: int,
    rects: Sequence[Rect],
    *,
    color: tuple[float, float, float] = (0.86, 0.15, 0.15),
    content: str = "",
    opacity: float = 1.0,
) -> int:
    """Squiggly (wavy) underline text markup."""
    page = _page(document, page_index)
    annot = page.add_squiggly_annot([_fitz_rect(r) for r in rects])
    annot.set_colors(stroke=color)
    if opacity < 0.999:
        annot.set_opacity(max(0.05, opacity))
    if content:
        annot.set_info(content=content)
    annot.update()
    document.invalidate_pages()
    return int(annot.xref)


def _set_nm(document: PdfDocument, xref: int, nm: str) -> None:
    document._backend._doc.xref_set_key(xref, "NM", fitz.get_pdf_str(nm))  # noqa: SLF001


def new_annotation_id() -> str:
    import uuid

    return "mpdf-" + uuid.uuid4().hex[:16]


def find_annotation(document: PdfDocument, page_index: int, nm: str):
    """The live annotation on the page whose /NM is ``nm`` (or None)."""
    page = _page(document, page_index)
    for annot in page.annots() or []:
        if (annot.info or {}).get("id") == nm:
            return annot
    return None


def delete_annotation_by_nm(document: PdfDocument, page_index: int, nm: str) -> bool:
    page = _page(document, page_index)
    for annot in list(page.annots() or []):
        if (annot.info or {}).get("id") == nm:
            page.delete_annot(annot)
            document.invalidate_pages()
            return True
    return False


ERASABLE = ("Highlight", "Underline", "StrikeOut", "Squiggly", "Ink")


def annotations_at(
    document: PdfDocument, page_index: int, point: Point, *, tolerance_pt: float = 2.0
) -> list[dict]:
    """Erasable markup annotations under ``point`` (unrotated page space), topmost last.

    A text markup is hit inside any of its quads; an ink annotation within half its stroke width of the
    path. Each result: {"xref", "kind", "nm", "rect"}."""
    import math

    page = _page(document, page_index)
    px, py = float(point.x), float(point.y)
    hits: list[dict] = []
    for annot in page.annots() or []:
        kind = annot.type[1]
        if kind not in ERASABLE:
            continue
        hit = False
        if kind == "Ink":
            half = max(0.5, float((annot.border or {}).get("width") or 1.0)) / 2.0 + tolerance_pt * 0.5
            for stroke in annot.vertices or []:
                pts = [(float(p[0]), float(p[1])) for p in stroke]
                segs = list(zip(pts, pts[1:])) if len(pts) > 1 else [(pts[0], pts[0])]
                for (x0, y0), (x1, y1) in segs:
                    dx, dy = x1 - x0, y1 - y0
                    seg = dx * dx + dy * dy
                    t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg))
                    if math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)) <= half:
                        hit = True
                        break
                if hit:
                    break
        else:
            v = annot.vertices or []
            for i in range(0, len(v) - 3, 4):
                xs = [p[0] for p in v[i : i + 4]]
                ys = [p[1] for p in v[i : i + 4]]
                if min(xs) - 0.5 <= px <= max(xs) + 0.5 and min(ys) - 0.5 <= py <= max(ys) + 0.5:
                    hit = True
                    break
        if hit:
            r = annot.rect
            hits.append({"xref": int(annot.xref), "kind": kind, "nm": (annot.info or {}).get("id") or "",
                         "rect": (float(r.x0), float(r.y0), float(r.x1), float(r.y1))})
    return hits


def annotations_along(
    document: PdfDocument, page_index: int, points: list[Point], *, radius_pt: float = 5.0
) -> list[dict]:
    """Every erasable markup annotation touched by an eraser drawn through ``points`` (unrotated page
    space) with a tip of ``radius_pt``; each once, topmost last. One point = everything under it.

    The path is sampled about every 1.5 pt, so a quick stroke that jumps between mouse positions
    still erases what lies between them."""
    import math

    if not points:
        return []
    samples: list[Point] = [points[0]]
    for a, b in zip(points, points[1:]):
        steps = max(1, int(math.hypot(b.x - a.x, b.y - a.y) / 1.5))
        samples.extend(Point(a.x + (b.x - a.x) * i / steps, a.y + (b.y - a.y) * i / steps) for i in range(1, steps + 1))
    found: dict[int, dict] = {}
    order: list[int] = []
    for pt in samples:
        for hit in annotations_at(document, page_index, pt, tolerance_pt=radius_pt * 2.0):
            if hit["xref"] not in found:
                found[hit["xref"]] = hit
                order.append(hit["xref"])
    # quads are tested against the tip's centre; widen the box test by the tip as well
    if radius_pt > 0.5:
        page = _page(document, page_index)
        for annot in page.annots() or []:
            if annot.type[1] not in ERASABLE or int(annot.xref) in found or annot.type[1] == "Ink":
                continue
            v = annot.vertices or []
            for i in range(0, len(v) - 3, 4):
                xs = [p[0] for p in v[i: i + 4]]
                ys = [p[1] for p in v[i: i + 4]]
                if any(min(xs) - radius_pt <= s.x <= max(xs) + radius_pt and min(ys) - radius_pt <= s.y <= max(ys) + radius_pt
                       for s in samples):
                    r = annot.rect
                    found[int(annot.xref)] = {"xref": int(annot.xref), "kind": annot.type[1],
                                              "nm": (annot.info or {}).get("id") or "",
                                              "rect": (float(r.x0), float(r.y0), float(r.x1), float(r.y1))}
                    order.append(int(annot.xref))
                    break
    return [found[x] for x in order]


def snapshot_annotation(document: PdfDocument, page_index: int, xref: int) -> dict | None:
    """Everything needed to recreate a markup annotation exactly (type, geometry, colour, opacity, identity)."""
    page = _page(document, page_index)
    for annot in page.annots() or []:
        if int(annot.xref) != int(xref):
            continue
        kind = annot.type[1]
        info = annot.info or {}
        snap = {
            "kind": kind,
            "colors": dict(annot.colors or {}),
            "opacity": float(annot.opacity),
            "nm": info.get("id") or "",
            "subject": info.get("subject") or "",
            "content": info.get("content") or "",
            "width": float((annot.border or {}).get("width") or 1.0),
            "rect": tuple(annot.rect),
        }
        if kind == "Ink":
            snap["strokes"] = [[(float(p[0]), float(p[1])) for p in st] for st in (annot.vertices or [])]
            bm = document._backend._doc.xref_get_key(int(xref), "BM")  # noqa: SLF001
            snap["blend"] = bm[1].lstrip("/") if bm and bm[0] != "null" else ""
        else:
            v = [(float(p[0]), float(p[1])) for p in (annot.vertices or [])]
            snap["quads"] = [v[i : i + 4] for i in range(0, len(v) - 3, 4)]
        return snap
    return None


def restore_annotation(document: PdfDocument, page_index: int, snap: dict) -> int:
    """Recreate an annotation from ``snapshot_annotation`` data with the same identity (/NM). Returns the new xref."""
    page = _page(document, page_index)
    kind = snap["kind"]
    stroke = snap["colors"].get("stroke") or (1, 1, 0)
    if kind == "Ink":
        annot = page.add_ink_annot(snap["strokes"])
        annot.set_border(width=snap["width"])
    else:
        quads = [fitz.Quad(*[fitz.Point(*p) for p in q]) for q in snap["quads"]]
        adder = {"Highlight": page.add_highlight_annot, "Underline": page.add_underline_annot,
                 "StrikeOut": page.add_strikeout_annot, "Squiggly": page.add_squiggly_annot}[kind]
        annot = adder(quads)
    annot.set_colors(stroke=tuple(stroke))
    if snap["opacity"] >= 0:
        annot.set_opacity(snap["opacity"])
    if snap.get("subject") or snap.get("content"):
        annot.set_info(subject=snap.get("subject", ""), content=snap.get("content", ""))
    if kind == "Ink" and snap.get("blend"):
        annot.update(blend_mode=snap["blend"])
    else:
        annot.update()
    if snap.get("nm"):
        _set_nm(document, int(annot.xref), snap["nm"])
    document.invalidate_pages()
    return int(annot.xref)


def delete_annotation_by_xref(document: PdfDocument, page_index: int, xref: int) -> bool:
    """Remove one annotation by xref. Returns True if something was deleted."""
    page = _page(document, page_index)
    for annot in list(page.annots() or []):
        if int(annot.xref) == int(xref):
            page.delete_annot(annot)
            document.invalidate_pages()
            return True
    return False


def text_rects_along_stroke(
    document: PdfDocument,
    page_index: int,
    points: Sequence[Point],
    *,
    radius_pt: float = 1.5,
) -> list[Rect]:
    """Text the pen actually passed over: per text line, from the first to the last character
    the stroke touches (within ``radius_pt``), so a partial word is highlighted as drawn and a
    stroke across one line never picks up the line above or below."""
    if len(points) < 1:
        return []
    page = _page(document, page_index)
    pts = _densify([(float(p.x), float(p.y)) for p in points])
    out: list[Rect] = []
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lx0, ly0, lx1, ly1 = line["bbox"]
            # Only strokes that reach this line's band can select anything on it.
            if not any(ly0 - radius_pt <= y <= ly1 + radius_pt and lx0 - radius_pt <= x <= lx1 + radius_pt
                       for x, y in pts):
                continue
            chars = [c for span in line.get("spans", []) for c in span.get("chars", [])]
            hit = [
                i for i, c in enumerate(chars)
                if _char_touched(c["bbox"], ly0, ly1, pts, radius_pt)
            ]
            if not hit:
                continue
            first, last = hit[0], hit[-1]
            while first < last and chars[first]["c"].isspace():
                first += 1
            while last > first and chars[last]["c"].isspace():
                last -= 1
            if chars[first]["c"].isspace():
                continue
            x0 = chars[first]["bbox"][0]
            x1 = chars[last]["bbox"][2]
            if x1 - x0 > 0.5:
                out.append(Rect(x0, ly0, x1 - x0, ly1 - ly0))
    return out


FREE_HIGHLIGHT_WIDTH = 11.0
FREE_HIGHLIGHT_OPACITY = 0.4
FREE_HIGHLIGHT_SUBJECT = "Free-area highlight"


def classify_stroke(
    document: PdfDocument,
    page_index: int,
    points: Sequence[Point],
    *,
    radius_pt: float = 1.5,
    min_free_len: float = 4.0,
) -> tuple[list[Rect], list[list[tuple[float, float]]]]:
    """Split one pen stroke into text highlights and free-area runs (page space).

    Parts of the stroke over a character of a text line become text highlights (as with
    ``text_rects_along_stroke``); every other part (blank margin, picture, table cell, scan)
    becomes a free run for an ink-style highlight. A stroke may produce both."""
    if not points:
        return [], []
    page = _page(document, page_index)
    dense = _densify([(float(p.x), float(p.y)) for p in points], step=1.0)
    bands: list[tuple[float, float, float, float]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            if any(s.get("text", "").strip() for s in line.get("spans", [])):
                bands.append(tuple(line["bbox"]))

    def on_text(x: float, y: float) -> bool:
        return any(x0 - radius_pt <= x <= x1 + radius_pt and y0 - radius_pt <= y <= y1 + radius_pt
                   for x0, y0, x1, y1 in bands)

    text_pts: list[Point] = []
    runs: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for x, y in dense:
        if on_text(x, y):
            text_pts.append(Point(x, y))
            if cur:
                runs.append(cur)
                cur = []
        else:
            cur.append((x, y))
    if cur:
        runs.append(cur)
    rects = text_rects_along_stroke(document, page_index, text_pts) if text_pts else []
    free: list[list[tuple[float, float]]] = []
    for run in runs:
        length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(run, run[1:]))
        if length >= min_free_len:
            free.append(_thin(run))
    return rects, free


def _thin(run: list[tuple[float, float]], keep: float = 3.0) -> list[tuple[float, float]]:
    """Fewer ink points (every ~3 pt) while keeping the first and last."""
    out = [run[0]]
    for p in run[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= keep:
            out.append(p)
    if len(run) > 1:
        out.append(run[-1])
    return out


def add_free_highlight(
    document: PdfDocument,
    page_index: int,
    runs: Sequence[Sequence[tuple[float, float]]],
    *,
    color: tuple[float, float, float] = (1, 1, 0),
    width: float = FREE_HIGHLIGHT_WIDTH,
    opacity: float = FREE_HIGHLIGHT_OPACITY,
    nm: str | None = None,
) -> int:
    """Marker-style highlight over any area: a translucent, multiplied ink annotation. Returns its xref."""
    page = _page(document, page_index)
    ink = [[(float(x), float(y)) for x, y in run] for run in runs if len(run) >= 2]
    if not ink:
        raise ValueError("no ink points")
    annot = page.add_ink_annot(ink)
    annot.set_border(width=width)
    annot.set_colors(stroke=color)
    annot.set_opacity(opacity)
    annot.set_info(subject=FREE_HIGHLIGHT_SUBJECT)
    annot.update(blend_mode="Multiply")
    if nm:
        _set_nm(document, int(annot.xref), nm)
    document.invalidate_pages()
    return int(annot.xref)


def _densify(pts: list[tuple[float, float]], step: float = 0.75) -> list[tuple[float, float]]:
    """Samples along every stroke segment so fast pen movement cannot skip characters."""
    if len(pts) < 2:
        return list(pts)
    dense = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(max(abs(x1 - x0), abs(y1 - y0)) / step))
        for k in range(1, n + 1):
            t = k / n
            dense.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return dense


def _char_touched(bbox, ly0: float, ly1: float, pts, radius: float) -> bool:
    x0, _y0, x1, _y1 = bbox
    # Vertical extent is the whole line band so glyph heights do not change what is hit.
    for x, y in pts:
        if x0 - radius <= x <= x1 + radius and ly0 - radius <= y <= ly1 + radius:
            return True
    return False


def add_text_comment(
    document: PdfDocument,
    page_index: int,
    point: Point,
    text: str,
    *,
    icon: str = "Comment",
    color: tuple[float, float, float] | None = None,
    author: str = "",
) -> int:
    """Sticky note; returns its xref."""
    page = _page(document, page_index)
    annot = page.add_text_annot(fitz.Point(point.x, point.y), text, icon="Comment")
    from core.annotations.note_style import NOTE_ICON_NAMES

    # MuPDF knows only some icon names; /Name is set directly (our own appearance draws every icon)
    document._backend._doc.xref_set_key(int(annot.xref), "Name", f"/{icon if icon in NOTE_ICON_NAMES else 'Comment'}")  # noqa: SLF001
    if color is not None:
        annot.set_colors(stroke=color)
    if author:
        annot.set_info(title=author)
    annot.update()
    _set_nm(document, int(annot.xref), new_annotation_id())
    from core.annotations.note_style import style_sticky_note

    style_sticky_note(document, page_index, int(annot.xref))  # clean bubble instead of MuPDF's square icon
    document.invalidate_pages()
    return int(annot.xref)


def add_callout(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    text: str,
    *,
    callout_point: Point | None = None,
) -> list[int]:
    """Free-text annotation with optional callout line (best-effort); returns the xrefs created."""
    page = _page(document, page_index)
    fr = _fitz_rect(rect)
    annot = page.add_freetext_annot(fr, text, fontsize=10, fontname="helv", border_color=(0, 0, 0))
    made = [int(annot.xref)]
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
            made.append(int(line.xref))
        except Exception:  # noqa: BLE001
            pass
    annot.update()
    document.invalidate_pages()
    return made


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
) -> int:
    """Built-in PDF stamp icons — no third-party stamp artwork required."""
    page = _page(document, page_index)
    annot = page.add_stamp_annot(_fitz_rect(rect), stamp=stamp.to_mupdf())
    annot.update()
    document.invalidate_pages()
    return int(annot.xref)


def list_annotations(document: PdfDocument) -> list[AnnotInfo]:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    out: list[AnnotInfo] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        for annot in page.annots() or []:
            r = annot.rect
            info = annot.info or {}
            stroke = (annot.colors or {}).get("stroke") or []
            color = "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in stroke[:3]) if len(stroke) >= 3 else ""
            kind = str(annot.type[1] if annot.type else "annot")
            irt = doc.xref_get_key(annot.xref, "IRT")[0] != "null"
            marked = ""
            if kind in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
                try:
                    v = annot.vertices or []
                    parts = []
                    for q in range(0, len(v) - 3, 4):
                        quad = fitz.Quad(v[q: q + 4])
                        parts.append(page.get_textbox(quad.rect).strip())
                    marked = " ".join(" ".join(p.split()) for p in parts if p)
                except Exception:  # noqa: BLE001 — the label is a convenience only
                    marked = ""
            out.append(
                AnnotInfo(
                    page_index=i,
                    kind=kind,
                    rect=(float(r.x0), float(r.y0), float(r.x1), float(r.y1)),
                    content=str(info.get("content") or ""),
                    xref=int(annot.xref),
                    author=str(info.get("title") or ""),
                    modified=str(info.get("modDate") or ""),
                    color=color,
                    opacity=float(annot.opacity) if annot.opacity >= 0 else 1.0,
                    is_reply_or_popup=irt or kind == "Popup",
                    marked_text=marked,
                )
            )
    return out
