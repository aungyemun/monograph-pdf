"""Alignment guides and snapping for editable objects."""

from __future__ import annotations

from dataclasses import dataclass

from core.editing.geometry import Rect
from core.editing.text_box import TextBox


@dataclass
class SnapGuide:
    orientation: str  # "v" or "h"
    position: float  # x for v, y for h (PDF points)
    kind: str  # left/center/right/top/middle/bottom/page


@dataclass
class SnapResult:
    dx: float
    dy: float
    guides: list[SnapGuide]


def snap_rect(
    moving: Rect,
    *,
    page_width: float,
    page_height: float,
    others: list[TextBox],
    threshold: float = 4.0,
) -> SnapResult:
    """Snap moving rect edges/centers to page and peer edges within threshold."""
    targets_x = [0.0, page_width / 2.0, page_width]
    targets_y = [0.0, page_height / 2.0, page_height]
    kinds_x = ["page-left", "page-center", "page-right"]
    kinds_y = ["page-top", "page-middle", "page-bottom"]
    for o in others:
        targets_x.extend([o.rect.x, o.rect.cx, o.rect.x1])
        targets_y.extend([o.rect.y, o.rect.cy, o.rect.y1])
        kinds_x.extend(["left", "center", "right"])
        kinds_y.extend(["top", "middle", "bottom"])

    movers_x = [(moving.x, "left"), (moving.cx, "center"), (moving.x1, "right")]
    movers_y = [(moving.y, "top"), (moving.cy, "middle"), (moving.y1, "bottom")]

    best_dx = 0.0
    best_dy = 0.0
    best_ax = threshold + 1
    best_ay = threshold + 1
    guides: list[SnapGuide] = []

    for mx, _ in movers_x:
        for tx, kind in zip(targets_x, kinds_x):
            d = tx - mx
            if abs(d) < best_ax:
                best_ax = abs(d)
                best_dx = d
                guides = [g for g in guides if g.orientation != "v"]
                if abs(d) <= threshold:
                    guides.append(SnapGuide("v", tx, kind))

    for my, _ in movers_y:
        for ty, kind in zip(targets_y, kinds_y):
            d = ty - my
            if abs(d) < best_ay:
                best_ay = abs(d)
                best_dy = d
                guides = [g for g in guides if g.orientation != "h"]
                if abs(d) <= threshold:
                    guides.append(SnapGuide("h", ty, kind))

    if best_ax > threshold:
        best_dx = 0.0
        guides = [g for g in guides if g.orientation != "v"]
    if best_ay > threshold:
        best_dy = 0.0
        guides = [g for g in guides if g.orientation != "h"]

    return SnapResult(best_dx, best_dy, guides)
