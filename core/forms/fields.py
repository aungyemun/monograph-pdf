"""Form field model (AcroForm-backed or detection-candidate overlays)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.editing.geometry import Rect


class FieldType(str, Enum):
    TEXT = "text"
    MULTILINE = "multiline"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    DATE = "date"
    SIGNATURE = "signature"  # visual placeholder only — not a cryptographic signature


@dataclass
class FormField:
    page_index: int
    rect: Rect
    field_type: FieldType
    name: str = ""
    value: str = ""
    options: list[str] = field(default_factory=list)  # dropdown / radio export values
    checked: bool = False
    multiline: bool = False
    font_family: str = "sans-serif"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    align: str = "left"  # left|center|right
    valign: str = ""  # top|middle|bottom; "" = natural (single line: middle, multi-line: top)
    text_color: str = "#000000"
    # Mixed formatting inside the text (rich text): [{"text", "family", "size", "bold", "italic",
    # "color"}], None = the field's own setting. Empty = the whole entry uses the field's style.
    runs: list[dict] = field(default_factory=list)
    fill_color: str = "#ffffff"
    border_color: str = "#333333"
    border_width: float = 1.0
    readonly: bool = False
    required: bool = False
    # AcroForm linkage
    is_acroform: bool = False
    xref: int | None = None
    has_appearance: bool = False  # widget has /AP stream in the PDF
    original_value: str = ""  # sanitized /V at load time
    # Overlay dirty flags — unmodified AcroForm must not replace page /AP
    value_dirty: bool = False
    appearance_dirty: bool = False
    style_dirty: bool = False  # font / colour / alignment / wrap changed in the inspector
    # Tooltip / alternate name (/TU) — metadata only, never painted as content
    alternate_name: str = ""
    # Detection candidate (never written unless user accepts)
    is_candidate: bool = False
    candidate_label: str = ""
    candidate_confidence: float = 0.0
    # Signature fields: UI treats as visual ink area only
    signature_note: str = "Visual signature field — not a cryptographic digital signature"
    object_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    z_index: int = 0

    def copy(self) -> "FormField":
        return FormField.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "page_index": self.page_index,
            "rect": list(self.rect.as_tuple()),
            "field_type": self.field_type.value,
            "name": self.name,
            "value": self.value,
            "options": list(self.options),
            "checked": self.checked,
            "multiline": self.multiline,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "align": self.align,
            "valign": self.valign,
            "text_color": self.text_color,
            "runs": [dict(r) for r in self.runs],
            "fill_color": self.fill_color,
            "border_color": self.border_color,
            "border_width": self.border_width,
            "pdf_style": True,  # colours read from the PDF (drafts before 0.1.4 used app defaults)
            "readonly": self.readonly,
            "required": self.required,
            "is_acroform": self.is_acroform,
            "xref": self.xref,
            "has_appearance": self.has_appearance,
            "original_value": self.original_value,
            "value_dirty": self.value_dirty,
            "appearance_dirty": self.appearance_dirty,
            "style_dirty": self.style_dirty,
            "alternate_name": self.alternate_name,
            "is_candidate": self.is_candidate,
            "candidate_label": self.candidate_label,
            "candidate_confidence": self.candidate_confidence,
            "z_index": self.z_index,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FormField":
        r = data.get("rect") or [0, 0, 100, 24]
        fill = str(data.get("fill_color") or "#ffffff")
        border = str(data.get("border_color") or "#333333")
        border_w = float(data.get("border_width", 1))
        if data.get("is_acroform") and not data.get("pdf_style"):
            # Older drafts stored the app's defaults (white fill, dark border) for PDF fields,
            # which drew a box the PDF doesn't have. Show only the page's own appearance.
            fill, border, border_w = "#00000000", "#00000000", 0.0
        return FormField(
            object_id=str(data.get("object_id") or uuid.uuid4()),
            page_index=int(data.get("page_index", 0)),
            rect=Rect(float(r[0]), float(r[1]), float(r[2]), float(r[3])),
            field_type=FieldType(data.get("field_type", FieldType.TEXT.value)),
            name=str(data.get("name") or ""),
            value=str(data.get("value") or ""),
            options=list(data.get("options") or []),
            checked=bool(data.get("checked", False)),
            multiline=bool(data.get("multiline", False)),
            font_family=str(data.get("font_family") or "sans-serif"),
            font_size=float(data.get("font_size", 11)),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            align=str(data.get("align") or "left"),
            valign=str(data.get("valign") or ""),
            text_color=str(data.get("text_color") or "#000000"),
            runs=[dict(r) for r in (data.get("runs") or []) if isinstance(r, dict)],
            fill_color=fill,
            border_color=border,
            border_width=border_w,
            readonly=bool(data.get("readonly", False)),
            required=bool(data.get("required", False)),
            is_acroform=bool(data.get("is_acroform", False)),
            xref=data.get("xref"),
            has_appearance=bool(data.get("has_appearance", False)),
            original_value=str(data.get("original_value") or ""),
            value_dirty=bool(data.get("value_dirty", False)),
            appearance_dirty=bool(data.get("appearance_dirty", False)),
            style_dirty=bool(data.get("style_dirty", False)),
            alternate_name=str(data.get("alternate_name") or ""),
            is_candidate=bool(data.get("is_candidate", False)),
            candidate_label=str(data.get("candidate_label") or ""),
            candidate_confidence=float(data.get("candidate_confidence") or 0),
            z_index=int(data.get("z_index", 0)),
        )


def effective_valign(field: Any) -> str:
    """Where the text sits vertically: the chosen position, else middle (one line) / top (wrapped)."""
    v = str(getattr(field, "valign", "") or "")
    if v in ("top", "middle", "bottom"):
        return v
    return "top" if getattr(field, "multiline", False) else "middle"

