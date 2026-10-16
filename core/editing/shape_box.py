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
