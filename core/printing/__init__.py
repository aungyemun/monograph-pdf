"""Native Windows printing helpers (optional — not required for PDF export)."""

from core.printing.ops import (
    ColorMode,
    PageScaling,
    PrintOptions,
    PrintSource,
    auto_landscape,
    effective_print_dpi,
    place_page,
    prepare_current_source,
    prepare_print_source,
    print_needs_bake,
    render_page_png_for_print,
    render_pages_for_print,
    resolve_print_pages,
)

__all__ = [
    "ColorMode",
    "PageScaling",
    "PrintOptions",
    "PrintSource",
    "auto_landscape",
    "effective_print_dpi",
    "place_page",
    "prepare_current_source",
    "prepare_print_source",
    "print_needs_bake",
    "render_page_png_for_print",
    "render_pages_for_print",
    "resolve_print_pages",
]
