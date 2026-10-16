"""True PDF content redaction (not opaque overlays)."""

from core.redaction.ops import (
    RedactionMark,
    apply_redactions,
    mark_region,
    mark_text,
    preview_redaction_count,
)

__all__ = [
    "RedactionMark",
    "apply_redactions",
    "mark_region",
    "mark_text",
    "preview_redaction_count",
]
