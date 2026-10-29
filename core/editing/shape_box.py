"""Editable vector shape overlays (rectangle, ellipse, line, arrow, freehand)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.editing.geometry import Point, Rect


class ShapeKind(str, Enum):
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    FREEHAND = "freehand"


class StrokeStyle(str, Enum):
    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"
    DASH_DOT = "dash_dot"
    LONG_DASH = "long_dash"


# (value, label) for menus
STROKE_STYLES: list[tuple[str, str]] = [
    ("solid", "Solid"), ("dashed", "Dashed"), ("dotted", "Dotted"), ("dash_dot", "Dash-dot"),
    ("long_dash", "Long dash"),
]
# Line end ("arrow head") styles: (value, label)
HEAD_STYLES: list[tuple[str, str]] = [
    ("none", "None"), ("filled", "Filled arrow"), ("open", "Open arrow"), ("stealth", "Sharp arrow"),
    ("circle", "Dot"), ("bar", "Bar"),
]
HEAD_STYLE_VALUES = {v for v, _ in HEAD_STYLES}


def dash_pattern(style: str, width: float) -> list[float] | None:
    """Dash pattern in points (on, off, …) for a line ``width`` points thick; None for a solid line.
    The same numbers are used on screen and in the saved PDF."""
    w = max(0.5, float(width))
    patterns = {
        "dashed": [4 * w, 2.5 * w],
        "dotted": [0.01, 2 * w],  # round caps make the zero-length dashes dots
        "dash_dot": [5 * w, 2 * w, 0.01, 2 * w],
        "long_dash": [9 * w, 3 * w],
    }
    p = patterns.get(str(getattr(style, "value", style)))
    return [max(0.01, v) for v in p] if p else None


# A line (or arrow) whose ends are closer than this, in points, has no direction or length: it is
# what a click without dragging used to create. Drawn with round caps it shows as a dot. Any real
# line, however short, is far longer (the window needs a drag of at least 3 screen pixels).
DEGENERATE_LINE_PT = 0.01


def is_degenerate_line(shape: Any) -> bool:
    """True for a line / arrow shape whose two end points coincide."""
    try:
        dx = float(shape.x1) - float(shape.x0)
        dy = float(shape.y1) - float(shape.y0)
    except (AttributeError, TypeError, ValueError):
        return False
    return (dx * dx + dy * dy) ** 0.5 < DEGENERATE_LINE_PT


def head_length(width: float, head_size: float = 0.0) -> float:
    """Length of an arrow head in points: ``head_size`` when set, else in proportion to the line."""
    return float(head_size) if head_size and head_size > 0 else max(6.0, 4.0 * float(width) + 3.0)


def line_geometry(x0: float, y0: float, x1: float, y1: float, *, width: float, start: str = "none",
                  end: str = "none", head_size: float = 0.0):
    """Where to draw a line or arrow: the (possibly shortened) line and each end's mark.

    Returns ``(line_from, line_to, marks)`` with points as (x, y) and marks as
    ``(style, points)`` — a polygon (filled / stealth / bar: filled; open: polyline) or, for
    ``circle``, ``[(cx, cy), (r, r)]``. Filled heads shorten the line so it does not show through the
    tip; the same geometry is used on screen and when saving, so they look the same.
    """
    import math

    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (x0, y0), (x1, y1), []
    ux, uy = dx / length, dy / length
    hl = min(head_length(width, head_size), length * 0.45 if (start != "none" and end != "none") else length * 0.9)
    marks = []
    a, b = [x0, y0], [x1, y1]

    def mark(style: str, tip: tuple[float, float], ox: float, oy: float, line_end: list[float]) -> None:
        # (ox, oy): unit vector pointing from the tip back along the line
        px, py = -oy, ox  # perpendicular
        tx, ty = tip
        half = hl * 0.42
        if style in ("filled", "open", "stealth"):
            bx, by = tx + ox * hl, ty + oy * hl
            left = (bx + px * half, by + py * half)
            right = (bx - px * half, by - py * half)
            if style == "stealth":
                notch = (tx + ox * hl * 0.65, ty + oy * hl * 0.65)
                marks.append(("stealth", [tip, left, notch, right]))
                line_end[0], line_end[1] = notch
            elif style == "filled":
                marks.append(("filled", [tip, left, right]))
                line_end[0], line_end[1] = bx, by
            else:
                marks.append(("open", [left, tip, right]))
                # a thick line would poke out past the open tip
                line_end[0], line_end[1] = tx + ox * min(hl * 0.5, width * 0.6), ty + oy * min(hl * 0.5, width * 0.6)
        elif style == "circle":
            r = max(1.5 * width, hl * 0.28)
            marks.append(("circle", [(tx, ty), (r, r)]))
        elif style == "bar":
            bw = max(0.6 * width, 1.0)
            h = hl * 0.45
            c1 = (tx + px * h, ty + py * h)
            c2 = (tx - px * h, ty - py * h)
            marks.append(("bar", [(c1[0] + ox * bw / 2, c1[1] + oy * bw / 2), (c2[0] + ox * bw / 2, c2[1] + oy * bw / 2),
                                  (c2[0] - ox * bw / 2, c2[1] - oy * bw / 2), (c1[0] - ox * bw / 2, c1[1] - oy * bw / 2)]))

    if end in HEAD_STYLE_VALUES and end != "none":
        mark(end, (x1, y1), -ux, -uy, b)
    if start in HEAD_STYLE_VALUES and start != "none":
        mark(start, (x0, y0), ux, uy, a)
    return (a[0], a[1]), (b[0], b[1]), marks


@dataclass
class ShapeBox:
    page_index: int
    rect: Rect
    kind: ShapeKind = ShapeKind.RECTANGLE
    stroke_color: str = "#2563eb"
    stroke_width: float = 1.5
    stroke_style: StrokeStyle = StrokeStyle.SOLID
    fill_color: str = "#00000000"  # transparent default
    fill_opacity: float = 1.0
    opacity: float = 1.0
    rotation: float = 0.0
    lock_aspect: bool = False
    # Line/arrow endpoints in page space (when kind is line/arrow)
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    # Freehand stroke points [(x,y), ...]
    points: list[tuple[float, float]] = field(default_factory=list)
    z_index: int = 0
    object_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Line ends (lines and arrows): see HEAD_STYLES; head_size 0 = in proportion to the line width
    start_head: str = "none"
    end_head: str = ""  # "" = the default: a filled head for an arrow, none for a line
    head_size: float = 0.0

    def heads(self) -> tuple[str, str]:
        """(start, end) line-end styles as drawn (an explicit "none" is respected)."""
        start = self.start_head or "none"
        end = self.end_head or ("filled" if self.kind == ShapeKind.ARROW else "none")
        return start, end

    def fit_points_to_rect(self, new_rect: Rect) -> None:
        """Freehand: scale the stroke's points with its box (resizing used to move only the box)."""
        new = new_rect.normalized()
        old = self.rect
        if self.kind == ShapeKind.FREEHAND and self.points and old.w > 1e-6 and old.h > 1e-6:
            self.points = [(new.x + (x - old.x) / old.w * new.w, new.y + (y - old.y) / old.h * new.h)
                           for x, y in self.points]
        self.rect = new

    def fit_to_rect(self, new_rect: Rect) -> None:
        """Change the shape's box; line ends and freehand points follow it."""
        if self.kind in (ShapeKind.LINE, ShapeKind.ARROW):
            self.fit_line_to_rect(new_rect)
        elif self.kind == ShapeKind.FREEHAND:
            self.fit_points_to_rect(new_rect)
        else:
            self.rect = new_rect.normalized()

    def fit_line_to_rect(self, new_rect: Rect) -> None:
        """Move / stretch a line's two ends with its box, keeping its direction (a box resize or a
        move's undo used to turn every line into top-left → bottom-right)."""
        if self.kind not in (ShapeKind.LINE, ShapeKind.ARROW):
            return
        old = Rect.from_points(Point(self.x0, self.y0), Point(self.x1, self.y1))
        new = new_rect.normalized()
        # sync_rect_from_line pads the ends' box by 2 pt on every side; lines saved by earlier versions
        # may have a box exactly around their ends (no padding)
        cur = self.rect
        padded = abs(cur.x - (old.x - 2.0)) < 0.05 and abs(cur.w - (old.w + 4.0)) < 0.1
        m = 2.0 if padded else 0.0
        nx, nw = (new.x + m, new.w - 2 * m) if new.w >= 2 * m else (new.x + new.w / 2, 0.0)
        ny, nh = (new.y + m, new.h - 2 * m) if new.h >= 2 * m else (new.y + new.h / 2, 0.0)
        if not padded:
            nx, nw, ny, nh = new.x, new.w, new.y, new.h
        new = Rect(nx, ny, nw, nh)

        def fx(x: float) -> float:
            return new.x + ((x - old.x) / old.w * new.w if old.w > 1e-6 else new.w / 2 if new.w > 1e-6 else 0.0)

        def fy(y: float) -> float:
            return new.y + ((y - old.y) / old.h * new.h if old.h > 1e-6 else new.h / 2 if new.h > 1e-6 else 0.0)

        self.x0, self.y0, self.x1, self.y1 = fx(self.x0), fy(self.y0), fx(self.x1), fy(self.y1)
        self.rect = new_rect.normalized()

    def sync_rect_from_line(self) -> None:
        if self.kind not in (ShapeKind.LINE, ShapeKind.ARROW):
            return
        self.rect = Rect.from_points(Point(self.x0, self.y0), Point(self.x1, self.y1)).inflate(2.0)

    def sync_line_from_rect(self) -> None:
        """Keep endpoints roughly aligned when rect is moved (translation)."""
        if self.kind not in (ShapeKind.LINE, ShapeKind.ARROW):
            return
        # When only translated via live_translate, endpoints move with dx/dy applied externally.

    def copy(self) -> "ShapeBox":
        c = ShapeBox(
            page_index=self.page_index,
            rect=Rect(*self.rect.as_tuple()),
            kind=self.kind,
            stroke_color=self.stroke_color,
            stroke_width=self.stroke_width,
            stroke_style=self.stroke_style,
            fill_color=self.fill_color,
            fill_opacity=self.fill_opacity,
            opacity=self.opacity,
            rotation=self.rotation,
            lock_aspect=self.lock_aspect,
            x0=self.x0,
            y0=self.y0,
            x1=self.x1,
            y1=self.y1,
            points=list(self.points),
            z_index=self.z_index,
            object_id=str(uuid.uuid4()),
            start_head=self.start_head,
            end_head=self.end_head,
            head_size=self.head_size,
        )
        return c

    def clone_same_id(self) -> "ShapeBox":
        c = self.copy()
        c.object_id = self.object_id
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "shape_box",
            "object_id": self.object_id,
            "page_index": self.page_index,
            "rect": list(self.rect.as_tuple()),
            "kind": self.kind.value,
            "stroke_color": self.stroke_color,
            "stroke_width": self.stroke_width,
            "stroke_style": self.stroke_style.value,
            "fill_color": self.fill_color,
            "fill_opacity": self.fill_opacity,
            "opacity": self.opacity,
            "rotation": self.rotation,
            "lock_aspect": self.lock_aspect,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "points": [list(p) for p in self.points],
            "z_index": self.z_index,
            "start_head": self.start_head,
            "end_head": self.end_head,
            "head_size": self.head_size,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ShapeBox":
        r = data.get("rect") or [0, 0, 100, 60]
        pts = data.get("points") or []
        return ShapeBox(
            object_id=str(data.get("object_id") or uuid.uuid4()),
            page_index=int(data.get("page_index", 0)),
            rect=Rect(float(r[0]), float(r[1]), float(r[2]), float(r[3])),
            kind=ShapeKind(data.get("kind", ShapeKind.RECTANGLE.value)),
            stroke_color=str(data.get("stroke_color") or "#2563eb"),
            stroke_width=float(data.get("stroke_width", 1.5)),
            stroke_style=StrokeStyle(data.get("stroke_style", StrokeStyle.SOLID.value)),
            fill_color=str(data.get("fill_color") or "#00000000"),
            fill_opacity=float(data.get("fill_opacity", 1.0)),
            opacity=float(data.get("opacity", 1.0)),
            rotation=float(data.get("rotation", 0.0)),
            lock_aspect=bool(data.get("lock_aspect", False)),
            x0=float(data.get("x0", 0)),
            y0=float(data.get("y0", 0)),
            x1=float(data.get("x1", 0)),
            y1=float(data.get("y1", 0)),
            points=[(float(p[0]), float(p[1])) for p in pts],
            z_index=int(data.get("z_index", 0)),
            start_head=str(data.get("start_head") or "none"),
            # arrows saved before line ends could be chosen had an open head
            end_head=str(data["end_head"]) if "end_head" in data else ("open" if data.get("kind") == "arrow" else ""),
            head_size=float(data.get("head_size", 0.0) or 0.0),
        )


def constrain_rect_aspect(origin: Point, current: Point, *, square: bool) -> Rect:
    """Build rect from drag; if square, force equal sides (from origin)."""
    dx = current.x - origin.x
    dy = current.y - origin.y
    if square:
        side = max(abs(dx), abs(dy))
        dx = side if dx >= 0 else -side
        dy = side if dy >= 0 else -side
    return Rect.from_points(origin, Point(origin.x + dx, origin.y + dy))


def constrain_line_angle(origin: Point, current: Point, *, snap: bool) -> Point:
    """Snap line end to 45° increments when snap is True."""
    if not snap:
        return current
    import math

    dx = current.x - origin.x
    dy = current.y - origin.y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return current
    ang = math.atan2(dy, dx)
    step = math.pi / 4.0
    snapped = round(ang / step) * step
    length = math.hypot(dx, dy)
    return Point(origin.x + length * math.cos(snapped), origin.y + length * math.sin(snapped))
