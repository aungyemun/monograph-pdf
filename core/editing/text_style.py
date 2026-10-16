"""Text style properties for TextBox objects (serializable)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class TextStyle:
    font_family: str = "sans-serif"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    text_color: str = "#000000"
    # Colours are #RRGGBB or #AARRGGBB (alpha first, as Qt reads them). New text boxes have no
    # fill and no frame — like typed text in Acrobat; the Properties panel adds them when wanted.
    background_color: str = "#00000000"
    border_color: str = "#00000000"
    border_width: float = 0.0
    opacity: float = 1.0
    rotation: float = 0.0  # degrees
    character_spacing: float = 0.0  # extra tracking in points
    line_spacing: float = 1.2  # multiplier
    padding: float = 4.0
    wrap: bool = True

    def copy(self) -> "TextStyle":
        return TextStyle(**asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TextStyle":
        known = {f.name for f in fields(TextStyle)}
        return TextStyle(**{k: v for k, v in data.items() if k in known})
