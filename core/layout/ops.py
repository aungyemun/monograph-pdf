"""Explicit geometry layout ops. Never promises Word-style PDF reflow."""

from __future__ import annotations

from enum import Enum

from core.editing.geometry import Rect


class LayoutPolicy(str, Enum):
    """
    PRESERVE: explicit/manual geometry only — highest reliability.
    SMART: controlled adjustment of clearly related objects where safe.
    """

    PRESERVE = "preserve_layout"
    SMART = "smart_layout"


def align_rects(rects: dict[str, Rect], edge: str) -> dict[str, Rect]:
    """Align left/right/top/bottom/center. Returns new rects keyed by id."""
    if len(rects) < 2:
        return dict(rects)
    items = list(rects.items())
    if edge == "left":
        target = min(r.x for _, r in items)
        return {i: Rect(target, r.y, r.w, r.h) for i, r in items}
    if edge == "right":
        target = max(r.x1 for _, r in items)
        return {i: Rect(target - r.w, r.y, r.w, r.h) for i, r in items}
    if edge == "top":
        target = min(r.y for _, r in items)
        return {i: Rect(r.x, target, r.w, r.h) for i, r in items}
    if edge == "bottom":
        target = max(r.y1 for _, r in items)
        return {i: Rect(r.x, target - r.h, r.w, r.h) for i, r in items}
    if edge == "center_h":
        target = sum(r.cx for _, r in items) / len(items)
        return {i: Rect(target - r.w / 2, r.y, r.w, r.h) for i, r in items}
    if edge == "center_v":
        target = sum(r.cy for _, r in items) / len(items)
        return {i: Rect(r.x, target - r.h / 2, r.w, r.h) for i, r in items}
    return dict(rects)


def distribute_rects(rects: dict[str, Rect], axis: str) -> dict[str, Rect]:
    """Distribute selected objects evenly along horizontal or vertical axis."""
    if len(rects) < 3:
        return dict(rects)
    items = list(rects.items())
    if axis == "horizontal":
        items.sort(key=lambda t: t[1].x)
        left = items[0][1].x
        right = items[-1][1].x1
        total_w = sum(r.w for _, r in items)
        gap = (right - left - total_w) / (len(items) - 1)
        x = left
        out: dict[str, Rect] = {}
        for i, r in items:
            out[i] = Rect(x, r.y, r.w, r.h)
            x += r.w + gap
        return out
    items.sort(key=lambda t: t[1].y)
    top = items[0][1].y
    bottom = items[-1][1].y1
    total_h = sum(r.h for _, r in items)
    gap = (bottom - top - total_h) / (len(items) - 1)
    y = top
    out = {}
    for i, r in items:
        out[i] = Rect(r.x, y, r.w, r.h)
        y += r.h + gap
    return out


def smart_nudge_related(
    moved_id: str,
    before: Rect,
    after: Rect,
    others: dict[str, Rect],
    *,
    threshold: float = 6.0,
) -> dict[str, Rect]:
    """
    Smart Layout foundation: only nudge objects that shared an edge alignment
    with the moved object before the move. Never moves unrelated content.
    """
    dx = after.x - before.x
    dy = after.y - before.y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return {}
    updates: dict[str, Rect] = {}
    for oid, rect in others.items():
        if oid == moved_id:
            continue
        related = False
        # Shared vertical edge (left/right aligned previously)
        if abs(rect.x - before.x) <= threshold or abs(rect.x1 - before.x1) <= threshold:
            related = True
        if abs(rect.y - before.y) <= threshold or abs(rect.y1 - before.y1) <= threshold:
            related = True
        if not related:
            continue
        # Only apply the component that matches the shared constraint
        ndx = dx if abs(rect.x - before.x) <= threshold or abs(rect.x1 - before.x1) <= threshold else 0.0
        ndy = dy if abs(rect.y - before.y) <= threshold or abs(rect.y1 - before.y1) <= threshold else 0.0
        if abs(ndx) > 0 or abs(ndy) > 0:
            updates[oid] = rect.translated(ndx, ndy)
    return updates
