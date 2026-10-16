"""PDF-space geometry (points). Display transforms live in the UI layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def translated(self, dx: float, dy: float) -> "Point":
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def normalized(self) -> "Rect":
        x, y, w, h = self.x, self.y, self.w, self.h
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        return Rect(x, y, w, h)

    def translated(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def with_size(self, w: float, h: float) -> "Rect":
        return Rect(self.x, self.y, max(1.0, w), max(1.0, h))

    def contains(self, p: Point) -> bool:
        return self.x <= p.x <= self.x1 and self.y <= p.y <= self.y1

    def inflate(self, m: float) -> "Rect":
        return Rect(self.x - m, self.y - m, self.w + 2 * m, self.h + 2 * m)

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x1 < other.x or other.x1 < self.x or self.y1 < other.y or other.y1 < self.y
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    @staticmethod
    def from_points(a: Point, b: Point) -> "Rect":
        return Rect(a.x, a.y, b.x - a.x, b.y - a.y).normalized()
