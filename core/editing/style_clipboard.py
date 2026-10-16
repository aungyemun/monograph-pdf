"""Copy Style / Paste Style + Auto Match Nearby Text foundation."""

from __future__ import annotations

from dataclasses import dataclass

from core.editing.geometry import Rect
from core.editing.text_box import TextAlign, SizeMode, TextBox, VAlign
from core.editing.text_style import TextStyle


@dataclass
class CopiedStyle:
    style: TextStyle
    align: TextAlign
    valign: VAlign
    size_mode: SizeMode


_CLIP: CopiedStyle | None = None


def copy_style(box: TextBox) -> CopiedStyle:
    global _CLIP
    _CLIP = CopiedStyle(
        style=box.style.copy(),
        align=box.align,
        valign=box.valign,
        size_mode=box.size_mode,
    )
    return _CLIP


def paste_style(box: TextBox, clip: CopiedStyle | None = None) -> None:
    src = clip or _CLIP
    if src is None:
        return
    box.style = src.style.copy()
    box.align = src.align
    box.valign = src.valign
    box.size_mode = src.size_mode


def get_clipboard() -> CopiedStyle | None:
    return _CLIP


def auto_match_nearby(
    page_boxes: list[TextBox],
    at: Rect,
    *,
    max_distance: float = 48.0,
) -> TextBox | None:
    """Foundation: pick nearest existing text box on the page by center distance."""
    best: TextBox | None = None
    best_d = max_distance
    for b in page_boxes:
        dx = b.rect.cx - at.cx
        dy = b.rect.cy - at.cy
        d = (dx * dx + dy * dy) ** 0.5
        if d < best_d:
            best_d = d
            best = b
    return best
