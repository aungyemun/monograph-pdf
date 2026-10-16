"""Page-level abstractions in PDF coordinate space (points, 1/72 inch)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PageContentKind(str, Enum):
    TEXT = "text"
    IMAGE_SCANNED = "image_scanned"
    MIXED = "mixed"
    EMPTY = "empty"


@dataclass(frozen=True)
class PageInfo:
    """Immutable page metadata. Dimensions are in PDF points (unscaled)."""

    index: int
    width_pt: float
    height_pt: float
    rotation: int
    content_kind: PageContentKind
    has_text: bool
    has_images: bool
    char_count: int
    image_count: int

    @property
    def display_width_pt(self) -> float:
        """Width after page /Rotate is applied for layout."""
        if self.rotation % 180 == 90:
            return self.height_pt
        return self.width_pt

    @property
    def display_height_pt(self) -> float:
        if self.rotation % 180 == 90:
            return self.width_pt
        return self.height_pt
