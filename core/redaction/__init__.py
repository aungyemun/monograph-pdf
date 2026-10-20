"""True PDF content redaction (not opaque overlays)."""

from core.redaction.ops import (
    RedactionMark,
    RedactionReport,
    UNCHECKED_ATTACHMENT,
    Residue,
    apply_redactions,
    apply_redactions_report,
    find_residue,
    mark_pages,
    mark_region,
    mark_text,
    marked_terms,
    preview_redaction_count,
    scrub_residue,
)

__all__ = [
    "RedactionMark",
    "RedactionReport",
    "Residue",
    "UNCHECKED_ATTACHMENT",
    "apply_redactions",
    "apply_redactions_report",
    "find_residue",
    "mark_pages",
    "marked_terms",
    "scrub_residue",
    "mark_region",
    "mark_text",
    "preview_redaction_count",
]
