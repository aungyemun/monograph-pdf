"""Visual (non-cryptographic) signature placement on PDF pages."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import fitz

from core.document import PdfDocument
from core.editing.geometry import Point, Rect
from core.forms.fields import FieldType


class SignatureKind(str, Enum):
    TYPED = "typed_visual"
    DRAWN = "drawn_visual"
    IMAGE = "image_visual"
    # Cryptographic not implemented without local cert workflow packaging
    CRYPTOGRAPHIC = "cryptographic_unsupported"


def signature_disclaimer() -> str:
    return (
        "This inserts a VISUAL signature only (typed, drawn, or image). "
        "It is NOT a cryptographic digital signature backed by a certificate. "
        "Cryptographic signing is not available in this build without a packaged "
        "local certificate workflow. Editing a digitally signed PDF may invalidate "
        "existing certificate signatures."
    )


def _fit_fontsize(text: str, fontname: str, rect: fitz.Rect, start: float) -> float:
    size = start
    while size > 6 and (fitz.get_text_length(text, fontname=fontname, fontsize=size) > rect.width * 0.96 or size > rect.height * 0.8):
        size -= 0.5
    return size


def insert_typed_signature(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    name: str,
    *,
    image_png: bytes | None = None,
    fontsize: float = 28.0,
    color: tuple[float, float, float] = (0.05, 0.1, 0.45),
    create_acroform_field: bool = False,
) -> None:
    """Place a typed name as a visual signature.

    The UI renders the name in a handwriting font to a transparent PNG (``image_png``); it is
    placed to fit the box, keeping its proportions. Without an image the name is written in an
    italic serif face, sized to fit. Nothing else (no frame, no caption) is added to the page.
    """
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    r = fitz.Rect(rect.x, rect.y, rect.x1, rect.y1)
    if image_png:
        page.insert_image(r, stream=image_png, keep_proportion=True, overlay=True)
    else:
        latin = all(ord(c) < 0x100 for c in name)
        fname = "tiit" if latin else "japan"  # the italic serif has no Japanese glyphs
        if latin:
            size = _fit_fontsize(name, "tiit", r, fontsize)
            width = fitz.get_text_length(name, fontname="tiit", fontsize=size)
        else:
            cjk = fitz.Font("cjk")
            size = fontsize
            while size > 6 and (cjk.text_length(name, fontsize=size) > r.width * 0.96 or size > r.height * 0.8):
                size -= 0.5
            width = cjk.text_length(name, fontsize=size)
        x = r.x0 + max(0.0, (r.width - width) / 2)
        y = r.y0 + (r.height + size * 0.7) / 2
        page.insert_text((x, y), name, fontsize=size, fontname=fname, color=color)
    if create_acroform_field:
        try:
            from core.forms.acroform import create_widget_on_page
            from core.forms.fields import FormField

            field = FormField(
                page_index=page_index,
                rect=rect,
                field_type=FieldType.SIGNATURE,
                name=f"VisualSig_{page_index}",
                value="",
            )
            create_widget_on_page(doc, field)
        except Exception:  # noqa: BLE001
            pass
    document.invalidate_pages()


def insert_drawn_signature(
    document: PdfDocument,
    page_index: int,
    strokes: list[list[Point]],
    *,
    color: tuple[float, float, float] = (0.05, 0.05, 0.35),
    width: float = 1.8,
) -> None:
    """Ink strokes as visual signature."""
    from core.annotations.ops import add_freehand

    add_freehand(document, page_index, strokes, color=color, width=width)


def insert_image_signature(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    image_path: Path,
) -> None:
    """Place an image as visual signature."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    r = fitz.Rect(rect.x, rect.y, rect.x1, rect.y1)
    # Fit inside the box without stretching the signature
    page.insert_image(r, filename=path.as_posix(), keep_proportion=True, overlay=True)
    document.invalidate_pages()
