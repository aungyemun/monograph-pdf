"""Undoable page rotation that carries the editor's overlays with the page.

Rotating a page changes only its ``/Rotate`` entry; the page content is never rewritten. Overlay
objects (text boxes, pictures, shapes, form fields, tables) live in display space, so they are
moved with the page: positions are turned about the page, shapes and form fields turn with it,
while text boxes, pictures and tables keep their size and are only re-positioned (pictures also
turn). Undo / redo restore every geometry exactly.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from core.commands import Command
from core.editing.geometry import Rect


def _turn_point(x: float, y: float, w: float, h: float, degrees: int) -> tuple[float, float]:
    """Display point on a w × h page after turning the page ``degrees`` clockwise."""
    d = degrees % 360
    if d == 90:
        return h - y, x
    if d == 180:
        return w - x, h - y
    if d == 270:
        return y, w - x
    return x, y


def _turn_rect(r: Rect, w: float, h: float, degrees: int) -> Rect:
    x0, y0 = _turn_point(r.x, r.y, w, h, degrees)
    x1, y1 = _turn_point(r.x1, r.y1, w, h, degrees)
    return Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))


def _turn_centered(r: Rect, w: float, h: float, degrees: int) -> Rect:
    """Same size, centre carried with the page."""
    cx, cy = _turn_point(r.cx, r.cy, w, h, degrees)
    return Rect(cx - r.w / 2.0, cy - r.h / 2.0, r.w, r.h)


def turn_overlays(edit: Any, page_index: int, w: float, h: float, degrees: int) -> None:
    """Move every overlay of ``page_index`` for a clockwise page turn (w × h = size before)."""
    d = degrees % 360
    if d == 0:
        return
    for box in edit.objects.values():
        if box.page_index == page_index:
            box.rect = _turn_centered(box.rect, w, h, d)
    for img in getattr(edit, "images", {}).values():
        if img.page_index == page_index:
            img.rect = _turn_centered(img.rect, w, h, d)
            img.rotation = (float(getattr(img, "rotation", 0.0)) + d) % 360.0
    for shape in getattr(edit, "shapes", {}).values():
        if shape.page_index != page_index:
            continue
        shape.rect = _turn_rect(shape.rect, w, h, d)
        shape.x0, shape.y0 = _turn_point(shape.x0, shape.y0, w, h, d)
        shape.x1, shape.y1 = _turn_point(shape.x1, shape.y1, w, h, d)
        shape.points = [_turn_point(px, py, w, h, d) for px, py in shape.points]
    for field in edit.fields.values():
        if getattr(field, "page_index", None) == page_index:
            field.rect = _turn_rect(field.rect, w, h, d)
    for table in edit.tables.values():
        if getattr(table, "page_index", None) == page_index:
            table.bounds = _turn_centered(table.bounds, w, h, d)
    for sid, plan in list(edit._native_replacements.items()):  # noqa: SLF001
        rect = plan.get("rect")
        if not rect or not str(sid).startswith(f"p{page_index}-"):
            continue
        turned = _turn_rect(Rect(*rect), w, h, d)
        edit._native_replacements[sid] = {**plan, "rect": turned.as_tuple()}  # noqa: SLF001


class RotatePagesCommand(Command):
    """Turn pages by a multiple of 90° (clockwise positive); undo restores page and overlays."""

    def __init__(
        self,
        document: Any,
        edit: Any,
        pages: list[int],
        degrees: int,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        if degrees % 90 != 0:
            raise ValueError("rotation must be a multiple of 90")
        self.document = document
        self.edit = edit
        self.pages = sorted({int(p) for p in pages})
        self.degrees = int(degrees)
        self.on_changed = on_changed
        self._snapshot_data: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "Rotate Pages"

    def _snapshot(self) -> dict[str, Any]:
        e = self.edit
        return {
            "objects": {k: copy.deepcopy(v.rect) for k, v in e.objects.items()},
            "images": {k: (copy.deepcopy(v.rect), v.rotation) for k, v in e.images.items()},
            "shapes": {
                k: (copy.deepcopy(v.rect), v.x0, v.y0, v.x1, v.y1, list(v.points)) for k, v in e.shapes.items()
            },
            "fields": {k: copy.deepcopy(v.rect) for k, v in e.fields.items()},
            "tables": {k: copy.deepcopy(v.bounds) for k, v in e.tables.items()},
            "native": copy.deepcopy(e._native_replacements),  # noqa: SLF001
        }

    def _restore(self, snap: dict[str, Any]) -> None:
        e = self.edit
        for k, r in snap["objects"].items():
            if k in e.objects:
                e.objects[k].rect = copy.deepcopy(r)
        for k, (r, rot) in snap["images"].items():
            if k in e.images:
                e.images[k].rect = copy.deepcopy(r)
                e.images[k].rotation = rot
        for k, (r, x0, y0, x1, y1, pts) in snap["shapes"].items():
            if k in e.shapes:
                s = e.shapes[k]
                s.rect, s.x0, s.y0, s.x1, s.y1, s.points = copy.deepcopy(r), x0, y0, x1, y1, list(pts)
        for k, r in snap["fields"].items():
            if k in e.fields:
                e.fields[k].rect = copy.deepcopy(r)
        for k, r in snap["tables"].items():
            if k in e.tables:
                e.tables[k].bounds = copy.deepcopy(r)
        e._native_replacements = copy.deepcopy(snap["native"])  # noqa: SLF001

    def execute(self) -> None:
        from core.organize.page_ops import rotate_pages

        doc = self.document._backend._doc  # noqa: SLF001
        sizes = {}
        for p in self.pages:
            rect = doc.load_page(p).rect
            sizes[p] = (float(rect.width), float(rect.height))
        # Snapshot before the first run only: a redo replays from the same starting geometry.
        if self._snapshot_data is None:
            self._snapshot_data = self._snapshot()
        else:
            self._restore(self._snapshot_data)
        for p in self.pages:
            w, h = sizes[p]
            turn_overlays(self.edit, p, w, h, self.degrees)
        rotate_pages(self.document, self.pages, self.degrees)
        self._changed()

    def undo(self) -> None:
        from core.organize.page_ops import rotate_pages

        assert self._snapshot_data is not None
        rotate_pages(self.document, self.pages, -self.degrees)
        self._restore(self._snapshot_data)
        self._changed()

    def _changed(self) -> None:
        self.edit.mark_dirty()
        if self.on_changed is not None:
            self.on_changed()
