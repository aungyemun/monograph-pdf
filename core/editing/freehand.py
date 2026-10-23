"""Freehand strokes: remove the mouse's jitter and draw the stroke as smooth curves.

The mouse delivers a point every few pixels, with small wobbles; joined by straight segments the
stroke looks jagged. :func:`simplify` drops points that lie (within a tolerance) on the line between
their neighbours, and :func:`smooth_segments` turns the remaining points into cubic Bézier curves
that pass through the midpoints of the segments (a quadratic B-spline), so the stroke is smooth and
still follows the hand. The same curves are drawn on screen and written into the saved PDF.
"""

from __future__ import annotations

import math

Pt = tuple[float, float]


def _dist_to_segment(p: Pt, a: Pt, b: Pt) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points: list[Pt], tolerance: float = 0.6) -> list[Pt]:
    """Ramer–Douglas–Peucker simplification (iterative; ``tolerance`` in points)."""
    pts = [(float(x), float(y)) for x, y in points]
    # drop exact repeats first (a held mouse repeats its position)
    dedup = [pts[0]] if pts else []
    for p in pts[1:]:
        if abs(p[0] - dedup[-1][0]) > 1e-6 or abs(p[1] - dedup[-1][1]) > 1e-6:
            dedup.append(p)
    if len(dedup) < 3:
        return dedup
    keep = [False] * len(dedup)
    keep[0] = keep[-1] = True
    stack = [(0, len(dedup) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = -1.0, -1
        for k in range(i + 1, j):
            d = _dist_to_segment(dedup[k], dedup[i], dedup[j])
            if d > best:
                best, idx = d, k
        if best > tolerance and idx > 0:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(dedup, keep) if k]


def smooth_segments(points: list[Pt]) -> list[tuple[Pt, Pt, Pt, Pt]]:
    """Cubic Bézier segments (start, control 1, control 2, end) through the stroke.

    Starts at the first point, ends at the last, and between them curves through each segment's
    midpoint with the original points as (quadratic) control points.
    """
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return []
    if len(pts) == 2:
        a, b = pts
        return [(a, a, b, b)]
    mids = [((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2) for i in range(len(pts) - 1)]
    out: list[tuple[Pt, Pt, Pt, Pt]] = []
    start = pts[0]
    # first: straight to the first midpoint
    out.append((start, start, mids[0], mids[0]))
    for i in range(1, len(pts) - 1):
        q0, c, q1 = mids[i - 1], pts[i], mids[i]
        # quadratic (q0, c, q1) as a cubic
        c1 = (q0[0] + 2 / 3 * (c[0] - q0[0]), q0[1] + 2 / 3 * (c[1] - q0[1]))
        c2 = (q1[0] + 2 / 3 * (c[0] - q1[0]), q1[1] + 2 / 3 * (c[1] - q1[1]))
        out.append((q0, c1, c2, q1))
    end = pts[-1]
    out.append((mids[-1], mids[-1], end, end))
    return out
