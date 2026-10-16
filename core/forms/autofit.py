"""Automatic font-size fitting for AcroForm fields (PDF size 0 / Auto)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.forms.fields import FormField

_MIN_AUTO = 6.0
_MAX_AUTO = 14.0


def effective_form_font_size(field: "FormField", text: str | None = None) -> float:
    """
    Resolve display font size for a field.

    Explicit size (>0) is returned as-is.
    Auto (0): pick a readable size that fits short values; shrink for long ones
    down to ``_MIN_AUTO`` (then overflow is caller's responsibility).
    """
    explicit = float(getattr(field, "font_size", 0) or 0)
    if explicit > 0:
        return explicit

    content = text if text is not None else str(getattr(field, "value", "") or "")
    h = max(8.0, float(getattr(field.rect, "h", 14) or 14))
    w = max(8.0, float(getattr(field.rect, "w", 40) or 40))
    # Natural size ~ 65% of field height, capped
    natural = max(_MIN_AUTO, min(_MAX_AUTO, h * 0.65))
    if not content:
        return natural
    if getattr(field, "multiline", False):
        return natural
    # Rough width budget: ~0.55em average
    est = len(content) * natural * 0.55
    if est <= w * 0.92:
        return natural
    scaled = natural * (w * 0.92) / max(est, 1.0)
    return max(_MIN_AUTO, min(natural, scaled))


def form_text_overflows(field: "FormField", text: str | None = None) -> bool:
    """True when Auto fit still cannot fit at minimum size."""
    content = text if text is not None else str(getattr(field, "value", "") or "")
    if not content or getattr(field, "multiline", False):
        return False
    if float(getattr(field, "font_size", 0) or 0) > 0:
        return False
    size = effective_form_font_size(field, content)
    w = max(8.0, float(field.rect.w))
    est = len(content) * size * 0.55
    return est > w * 0.98 and size <= _MIN_AUTO + 0.05
