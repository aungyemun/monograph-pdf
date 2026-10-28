"""Form field *display* rules — page appearance must never show internal names."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.forms.fields import FieldType

if TYPE_CHECKING:
    from core.forms.fields import FormField

# XFA SOM / fully-qualified AcroForm paths must stay metadata-only.
_SOM_RE = re.compile(
    r"^(topmostSubform|form|subform)\b|\[\d+\]\.",
    re.IGNORECASE,
)


def looks_like_internal_field_id(text: str) -> bool:
    """True when *text* looks like an XFA SOM path or internal field identifier."""
    s = (text or "").strip()
    if not s:
        return False
    if "topmostSubform" in s:
        return True
    if _SOM_RE.search(s) and ("[" in s or "]." in s):
        return True
    # Common Adobe LiveCycle / Designer style paths
    if s.count("[") >= 1 and s.count("]") >= 1 and "." in s and len(s) > 24:
        return True
    return False


def sanitize_field_value(name: str, value: str) -> str:
    """
    Normalize widget /V for editor use.

    Never treat the field name, tooltip, or SOM path as a user-visible value.
    """
    raw = str(value or "")
    nm = str(name or "")
    if not raw:
        return ""
    if nm and raw == nm:
        return ""
    if looks_like_internal_field_id(raw):
        return ""
    return raw


def visible_field_content(field: "FormField") -> str:
    """
    Text/glyph content allowed on the canvas overlay for a field.

    Empty string means: leave the PDF page appearance alone (no synthesized label).
    Never returns field.name, /TU, or XFA SOM paths.
    """
    if field.is_candidate:
        # Candidates may show a short review label in Forms mode only (caller gates mode).
        return (field.candidate_label or "").strip()

    if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
        # Checkbox/radio chrome is drawn only when the overlay is active (dirty/user field).
        return "☑" if field.checked else "☐"

    if field.field_type == FieldType.SIGNATURE:
        # Only for user-created visual signature overlays — not AcroForm /AP.
        if field.is_acroform and not getattr(field, "value_dirty", False):
            return ""
        return "[Signature — visual only]"

    if field.field_type == FieldType.DROPDOWN:
        val = sanitize_field_value(field.name, field.value)
        if val:
            return val
        if not field.is_acroform or getattr(field, "value_dirty", False):
            return field.options[0] if field.options else ""
        return ""

    return sanitize_field_value(field.name, field.value)


def should_paint_field_overlay(
    field: "FormField",
    *,
    forms_mode: bool,
    highlight_fillable: bool = False,
) -> str:
    """
    Return overlay policy for a field:

    - ``none``: do not paint fill/text (trust PDF /AP / page render)
    - ``chrome``: outline only (Forms mode discoverability / selection)
    - ``highlight``: UI-only fillable hint (never baked into Save/Export)
    - ``content``: paint fill + visible_field_content (user overlays or dirty values)
    - ``candidate``: detection candidate chrome
    """
    if field.is_candidate:
        return "candidate" if forms_mode else "none"

    dirty = bool(getattr(field, "value_dirty", False) or getattr(field, "appearance_dirty", False))
    user_placed = not field.is_acroform

    if user_placed or dirty:
        return "content"

    # Unmodified AcroForm: never synthesize content; optional chrome / highlight.
    if forms_mode:
        return "chrome"
    if highlight_fillable and not getattr(field, "readonly", False):
        return "highlight"
    return "none"


# Field kinds whose overlay draws the whole value (text). Their saved appearance shows the old value.
_TEXT_LIKE = (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE, FieldType.DROPDOWN)


def stale_appearance_widgets(fields) -> tuple[int, ...]:
    """Widget xrefs whose saved appearance (/AP) no longer matches what the window shows.

    An existing PDF text field that is being changed (new value, style or position) is painted by
    the canvas overlay (``should_paint_field_overlay`` -> ``content``). Its appearance stream in the
    open document still holds the previously saved text; rendering it under the overlay showed the
    old and the new value on top of each other until the next Save regenerated the appearance.
    Those widgets are left out of the on-screen page rendering. Nothing in the document changes."""
    out: set[int] = set()
    for field in fields or ():
        if not getattr(field, "is_acroform", False) or getattr(field, "is_candidate", False):
            continue
        if field.field_type not in _TEXT_LIKE:
            continue
        if not (getattr(field, "value_dirty", False) or getattr(field, "appearance_dirty", False)):
            continue
        xref = int(getattr(field, "xref", 0) or 0)
        if xref > 0:
            out.add(xref)
    return tuple(sorted(out))