"""PDF annotation tools (native MuPDF annotations)."""

from core.annotations.ops import (
    AnnotKind,
    StampKind,
    add_callout,
    add_ellipse,
    add_freehand,
    add_highlight,
    add_line_arrow,
    add_rectangle,
    add_stamp,
    add_strikeout,
    add_text_comment,
    add_underline,
    list_annotations,
)

__all__ = [
    "AnnotKind",
    "StampKind",
    "add_callout",
    "add_ellipse",
    "add_freehand",
    "add_highlight",
    "add_line_arrow",
    "add_rectangle",
    "add_stamp",
    "add_strikeout",
    "add_text_comment",
    "add_underline",
    "list_annotations",
]
