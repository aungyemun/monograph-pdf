"""Candidate field detection for non-fillable forms (review-only until accepted)."""

from __future__ import annotations

from typing import Any

import fitz

from core.editing.geometry import Rect
from core.forms.fields import FieldType, FormField
from core.page_space import point_to_display, rect_to_display, rect_to_page


def _nearby_label(page: fitz.Page, rect: fitz.Rect, max_dist: float = 36.0) -> tuple[str, float]:
    """Find likely label text left of or above an empty rectangle."""
    blocks = page.get_text("blocks") or []
    best = ""
    best_score = 0.0
    for b in blocks:
        if len(b) < 5 or b[6] != 0:  # text blocks only
            continue
        bd = rect_to_display(page, (b[0], b[1], b[2], b[3]))
        bx0, by0, bx1, by1, text = bd.x0, bd.y0, bd.x1, bd.y1, str(b[4]).strip()
        if not text or len(text) > 80:
            continue
        # Left of field, vertically overlapping
        if bx1 <= rect.x0 + 2 and abs((by0 + by1) / 2 - (rect.y0 + rect.y1) / 2) < max_dist:
            dist = rect.x0 - bx1
            score = max(0.0, 1.0 - dist / max_dist) * 0.9
            if score > best_score:
                best_score = score
                best = text.replace("\n", " ")
        # Above field
        if by1 <= rect.y0 + 2 and abs((bx0 + bx1) / 2 - (rect.x0 + rect.x1) / 2) < rect.width:
            dist = rect.y0 - by1
            score = max(0.0, 1.0 - dist / max_dist) * 0.8
            if score > best_score:
                best_score = score
                best = text.replace("\n", " ")
    return best, best_score


def _is_checkbox_like(rect: fitz.Rect) -> bool:
    return 8 <= rect.width <= 28 and 8 <= rect.height <= 28 and abs(rect.width - rect.height) < 8


def detect_field_candidates(doc: fitz.Document, page_index: int | None = None) -> list[FormField]:
    """
    Geometry/text/line heuristics for empty fill areas.
    Detection never modifies the document — returns candidates for review only.
    """
    pages = range(doc.page_count) if page_index is None else [page_index]
    candidates: list[FormField] = []

    for pi in pages:
        page = doc.load_page(pi)
        # Skip pages that already have real widgets (still allow empty zones elsewhere)
        existing_rects: list[fitz.Rect] = []
        try:
            for w in page.widgets() or []:
                existing_rects.append(rect_to_display(page, w.rect))
        except Exception:  # noqa: BLE001
            pass

        drawings = page.get_drawings() or []
        rects: list[fitz.Rect] = []
        underlines: list[fitz.Rect] = []

        for d in drawings:
            for item in d.get("items") or []:
                kind = item[0]
                if kind == "re":
                    r = rect_to_display(page, item[1])
                    if 40 <= r.width <= page.rect.width * 0.9 and 12 <= r.height <= 80:
                        rects.append(r)
                    elif _is_checkbox_like(r):
                        rects.append(r)
                elif kind == "l":
                    p1, p2 = point_to_display(page, item[1].x, item[1].y), point_to_display(page, item[2].x, item[2].y)
                    if abs(p1.y - p2.y) < 1.5 and abs(p1.x - p2.x) >= 40:
                        # Horizontal underline → field above the line
                        x0, x1 = min(p1.x, p2.x), max(p1.x, p2.x)
                        y = p1.y
                        underlines.append(fitz.Rect(x0, y - 16, x1, y))

        # Vector path rectangles sometimes appear as closed paths — also use underline zones
        seen: list[fitz.Rect] = []

        def overlaps_existing(r: fitz.Rect) -> bool:
            for er in existing_rects + seen:
                inter = er & r
                # PyMuPDF may return Rect or area float depending on version
                if isinstance(inter, (int, float)):
                    area = float(inter)
                else:
                    area = float(abs(inter))
                if area > 0.5 * min(float(abs(er)), float(abs(r)) or 1.0):
                    return True
            return False

        for r in rects + underlines:
            if r.get_area() < 80 or overlaps_existing(r):
                continue
            # Reject if substantial text already inside
            inside = page.get_text("text", clip=rect_to_page(page, r)).strip()
            if len(inside) > 2 and r not in underlines:
                continue
            label, conf = _nearby_label(page, r)
            if _is_checkbox_like(r):
                ftype = FieldType.CHECKBOX
                conf = max(conf, 0.55)
            else:
                ftype = FieldType.TEXT
                low = label.lower()
                if any(k in low for k in ("date", "日付", "年月日")):
                    ftype = FieldType.DATE
                elif any(k in low for k in ("sign", "署名", "印")):
                    ftype = FieldType.SIGNATURE
                    conf = max(conf, 0.5)
                elif r.height >= 40:
                    ftype = FieldType.MULTILINE
                conf = max(conf, 0.45 if label else 0.35)

            candidates.append(
                FormField(
                    page_index=pi,
                    rect=Rect(float(r.x0), float(r.y0), float(r.width), float(r.height)),
                    field_type=ftype,
                    name=label or f"candidate_{pi}_{len(candidates)}",
                    is_candidate=True,
                    is_acroform=False,
                    candidate_label=label,
                    candidate_confidence=round(conf, 3),
                )
            )
            seen.append(r)

    return candidates
