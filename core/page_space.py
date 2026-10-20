"""One place for the two coordinate spaces of a PDF page.

PyMuPDF reports text, words, drawings, search hits, annotations and form widgets in the page's
*unrotated* space (the space of its MediaBox/CropBox, y down). The viewer, the overlays and every
editing tool work in *display* space: the page as shown after ``/Rotate`` is applied. Anything that
crosses the boundary goes through these helpers so a page turned by 90°, 180° or 270° keeps text,
selections, annotations and form fields aligned.
"""

from __future__ import annotations

import fitz


def rect_to_display(page: fitz.Page, rect) -> fitz.Rect:
    """Unrotated page-space rectangle → display space (as shown after /Rotate)."""
    r = fitz.Rect(rect)
    if not page.rotation:
        return r
    r = r * page.rotation_matrix
    r.normalize()
    return r


def rect_to_page(page: fitz.Page, rect) -> fitz.Rect:
    """Display-space rectangle → unrotated page space (where MuPDF reads and writes)."""
    r = fitz.Rect(rect)
    if not page.rotation:
        return r
    r = r * page.derotation_matrix
    r.normalize()
    return r


def point_to_display(page: fitz.Page, x: float, y: float) -> fitz.Point:
    p = fitz.Point(x, y)
    return p * page.rotation_matrix if page.rotation else p


def point_to_page(page: fitz.Page, x: float, y: float) -> fitz.Point:
    p = fitz.Point(x, y)
    return p * page.derotation_matrix if page.rotation else p
