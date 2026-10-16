"""First-class Text Box editable object."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.editing.geometry import Rect
from core.editing.text_style import TextStyle


class TextAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VAlign(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class SizeMode(str, Enum):
    """Text box sizing behavior (inspector / toolbar labels map to these values)."""

    FIXED = "fixed"  # fixed box; overflow warning
    AUTO_HEIGHT = "auto_height"  # wrap + grow height (preferred default)
    AUTO_SIZE = "auto_size"  # grow width and height to fit text
    SHRINK_TO_FIT = "shrink_to_fit"  # Fit Text: shrink font to fit fixed box


class WritingMode(str, Enum):
    """Horizontal is implemented; VERTICAL_RL is architectural for Japanese."""

    HORIZONTAL_TB = "horizontal-tb"
    VERTICAL_RL = "vertical-rl"  # foundation only — layout path reserved


@dataclass
class TextBox:
    page_index: int
    rect: Rect
    text: str = ""
    style: TextStyle = field(default_factory=TextStyle)
    align: TextAlign = TextAlign.LEFT
    valign: VAlign = VAlign.TOP
    size_mode: SizeMode = SizeMode.AUTO_HEIGHT
    writing_mode: WritingMode = WritingMode.HORIZONTAL_TB
    z_index: int = 0
    object_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # When this overlay replaces native PDF text (redaction workflow)
    replaces_native: bool = False
    native_span_id: str | None = None
    overflow: bool = False
    font_substituted: bool = False
    resolved_font: str = ""

    def copy(self) -> "TextBox":
        return TextBox(
            page_index=self.page_index,
            rect=Rect(*self.rect.as_tuple()),
            text=self.text,
            style=self.style.copy(),
            align=self.align,
            valign=self.valign,
            size_mode=self.size_mode,
            writing_mode=self.writing_mode,
            z_index=self.z_index,
            object_id=str(uuid.uuid4()),
            replaces_native=self.replaces_native,
            native_span_id=self.native_span_id,
            overflow=self.overflow,
            font_substituted=self.font_substituted,
            resolved_font=self.resolved_font,
        )

    def clone_same_id(self) -> "TextBox":
        """Deep copy preserving object_id (for undo snapshots)."""
        c = self.copy()
        c.object_id = self.object_id
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "page_index": self.page_index,
            "rect": list(self.rect.as_tuple()),
            "text": self.text,
            "style": self.style.to_dict(),
            "align": self.align.value,
            "valign": self.valign.value,
            "size_mode": self.size_mode.value,
            "writing_mode": self.writing_mode.value,
            "z_index": self.z_index,
            "replaces_native": self.replaces_native,
            "native_span_id": self.native_span_id,
            "overflow": self.overflow,
            "font_substituted": self.font_substituted,
            "resolved_font": self.resolved_font,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TextBox":
        r = data.get("rect") or [0, 0, 100, 40]
        return TextBox(
            object_id=str(data.get("object_id") or uuid.uuid4()),
            page_index=int(data.get("page_index", 0)),
            rect=Rect(float(r[0]), float(r[1]), float(r[2]), float(r[3])),
            text=str(data.get("text") or ""),
            style=TextStyle.from_dict(data.get("style") or {}),
            align=TextAlign(data.get("align", TextAlign.LEFT.value)),
            valign=VAlign(data.get("valign", VAlign.TOP.value)),
            size_mode=SizeMode(data.get("size_mode", SizeMode.AUTO_HEIGHT.value)),
            writing_mode=WritingMode(data.get("writing_mode", WritingMode.HORIZONTAL_TB.value)),
            z_index=int(data.get("z_index", 0)),
            replaces_native=bool(data.get("replaces_native", False)),
            native_span_id=data.get("native_span_id"),
            overflow=bool(data.get("overflow", False)),
            font_substituted=bool(data.get("font_substituted", False)),
            resolved_font=str(data.get("resolved_font") or ""),
        )
