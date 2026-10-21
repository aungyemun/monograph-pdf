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


# --- visual signatures as movable pictures (0.3.0) ------------------------------------------------
#
# A signature placed from the Sign menu is a picture overlay (core/editing/image_box.py, role
# "signature"): it can be moved, resized, deleted and undone until the document is saved, and is then
# written into the page like any placed picture. It is a picture of a signature — not a
# certificate-based digital signature — and proves nothing about who placed it.


def strokes_to_png(strokes: list[list[tuple[float, float]]], *, color: tuple[float, float, float] = (0.05, 0.05, 0.35),
                   line_width: float = 3.0, max_side: int = 900) -> bytes:
    """Drawn strokes (any coordinates) as a transparent PNG, anti-aliased (drawn 4x, then reduced)."""
    import io

    from PIL import Image, ImageDraw

    pts = [p for s in strokes for p in s]
    if not pts:
        raise ValueError("no strokes")
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = max(maxx - minx, 1.0), max(maxy - miny, 1.0)
    scale = max_side / max(w, h)
    pad = line_width * 2
    ss = 4
    size = (int((w * scale + 2 * pad) * ss), int((h * scale + 2 * pad) * ss))
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    rgba = tuple(int(c * 255) for c in color) + (255,)
    lw = max(1, int(line_width * ss))
    for stroke in strokes:
        xy = [((x - minx) * scale * ss + pad * ss, (y - miny) * scale * ss + pad * ss) for x, y in stroke]
        if len(xy) == 1:
            x, y = xy[0]
            draw.ellipse((x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2), fill=rgba)
            continue
        draw.line(xy, fill=rgba, width=lw, joint="curve")
        for x, y in (xy[0], xy[-1]):
            draw.ellipse((x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2), fill=rgba)
    im = im.resize((max(1, size[0] // ss), max(1, size[1] // ss)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def fit_rect(image_w: int, image_h: int, box: Rect, *, default: tuple[float, float] = (180.0, 60.0)) -> Rect:
    """The largest rectangle with the picture's proportions centred in ``box`` (a click — a tiny box —
    gets ``default`` size centred on it)."""
    if box.w < 12 or box.h < 8:
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        box = Rect(cx - default[0] / 2, cy - default[1] / 2, default[0], default[1])
    if image_w <= 0 or image_h <= 0:
        return box
    s = min(box.w / image_w, box.h / image_h)
    w, h = image_w * s, image_h * s
    return Rect(box.x + (box.w - w) / 2, box.y + (box.h - h) / 2, w, h)


def signature_box(page_index: int, display_rect: Rect, png_path: Path):
    """A picture overlay holding a visual signature, fitted into ``display_rect`` (display space)."""
    from PIL import Image

    from core.editing.image_box import ImageBox

    with Image.open(Path(png_path).as_posix(), formats=["PNG"]) as im:
        iw, ih = im.size
    return ImageBox(page_index=page_index, rect=fit_rect(iw, ih, display_rect), source_path=str(png_path),
                    role="signature")
