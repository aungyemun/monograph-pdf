"""Stamp library: genuine PDF /Stamp annotations with Monograph PDF's own appearance.

Presets (Approved, Rejected, Reviewed, Draft, Final, Confidential, Pending, Completed, Experimental,
For Review), custom text stamps and picture stamps. The appearance is drawn by Monograph PDF (a framed
label, or the picture) — no third-party stamp artwork — and written as the annotation's normal
appearance stream, so every PDF reader shows it the same way. Opacity (/CA), rotation (appearance
/Matrix) and size can be changed later: the stamp's own parameters are kept in the private key
/MonographStamp and the appearance is redrawn from them.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

import fitz

from core.document import PdfDocument

PRIVATE_KEY = "MonographStamp"


@dataclass(frozen=True)
class StampPreset:
    label: str
    color: str  # #rrggbb


PRESETS: tuple[StampPreset, ...] = (
    StampPreset("APPROVED", "#15803d"),
    StampPreset("REJECTED", "#b91c1c"),
    StampPreset("REVIEWED", "#1d4ed8"),
    StampPreset("DRAFT", "#6b7280"),
    StampPreset("FINAL", "#15803d"),
    StampPreset("CONFIDENTIAL", "#b91c1c"),
    StampPreset("PENDING", "#b45309"),
    StampPreset("COMPLETED", "#15803d"),
    StampPreset("EXPERIMENTAL", "#7c3aed"),
    StampPreset("FOR REVIEW", "#1d4ed8"),
)


@dataclass
class StampSpec:
    """What a stamp shows. ``image_path`` makes a picture stamp (text is then its description)."""

    text: str = "APPROVED"
    color: str = "#15803d"
    subtitle: str = ""  # e.g. a date or a name, drawn small under the label
    opacity: float = 1.0
    rotation: float = 0.0  # degrees, clockwise as on screen
    image_path: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def from_json(text: str) -> "StampSpec":
        data = json.loads(text)
        known = set(StampSpec.__dataclass_fields__)
        return StampSpec(**{k: v for k, v in data.items() if k in known})


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0.1, 0.1, 0.1)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _draw_label(page: fitz.Page, rect: fitz.Rect, text: str, color: str, *, bold: bool = True) -> None:
    from core.forms.appearance import draw_text

    entry = SimpleNamespace(value=text, runs=[], font_family="Helvetica", font_size=0.0, bold=bold, italic=False,
                            text_color=color, align="center", valign="middle", multiline=False)
    draw_text(page, rect, entry, pad=0.0, multiline=False)


def draw_appearance(spec: StampSpec, width: float, height: float) -> fitz.Document:
    """A one-page PDF of ``width`` x ``height`` with the stamp drawn upright (caller closes it)."""
    scratch = fitz.open()
    page = scratch.new_page(width=width, height=height)
    if spec.image_path:
        page.insert_image(page.rect, filename=str(spec.image_path), keep_proportion=True)
    else:
        rgb = _rgb(spec.color)
        line = max(1.0, min(width, height) * 0.06)
        outer = fitz.Rect(line / 2, line / 2, width - line / 2, height - line / 2)
        page.draw_rect(outer, color=rgb, width=line, radius=0.18)
        inner = outer + (line * 1.4, line * 1.4, -line * 1.4, -line * 1.4)
        if inner.width > 4 and inner.height > 4:
            page.draw_rect(inner, color=rgb, width=max(0.5, line * 0.35), radius=0.12)
        text_area = inner + (line, line * 0.3, -line, -line * 0.3)
        if spec.subtitle and text_area.height > 14:
            split = text_area.y0 + text_area.height * 0.68
            _draw_label(page, fitz.Rect(text_area.x0, text_area.y0, text_area.x1, split), spec.text, spec.color)
            _draw_label(page, fitz.Rect(text_area.x0, split, text_area.x1, text_area.y1), spec.subtitle,
                        spec.color, bold=False)
        else:
            _draw_label(page, text_area, spec.text, spec.color)
    scratch.subset_fonts()
    return scratch


def turned_rect(rect: fitz.Rect, angle: float) -> fitz.Rect:
    """The outline of ``rect`` turned by ``angle`` about its centre."""
    a = math.radians(angle)
    w, h = rect.width, rect.height
    bw = abs(w * math.cos(a)) + abs(h * math.sin(a))
    bh = abs(w * math.sin(a)) + abs(h * math.cos(a))
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    return fitz.Rect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def _write_appearance(doc: fitz.Document, xref: int, spec: StampSpec, width: float, height: float) -> None:
    """Make the stamp drawing the annotation's /AP /N (a form XObject of the upright size; a turn is the
    appearance /Matrix, which readers fit into /Rect)."""
    scratch = draw_appearance(spec, width, height)
    pages_before = doc.page_count
    try:
        doc.insert_pdf(scratch)
        temp = doc[doc.page_count - 1]
        body = b"".join(doc.xref_stream(x) or b"" for x in temp.get_contents())
        res_kind, res = doc.xref_get_key(temp.xref, "Resources")
        if res_kind == "xref":
            res = doc.xref_object(int(res.split()[0]), compressed=True)
        kind, value = doc.xref_get_key(xref, "AP/N")
        if kind == "xref":
            ap = int(value.split()[0])
        else:
            ap = doc.get_new_xref()
            doc.update_object(ap, "<<>>")
        doc.update_object(ap, f"<</Type/XObject/Subtype/Form/BBox[0 0 {width:.4f} {height:.4f}]>>")
        doc.update_stream(ap, body)
        doc.xref_set_key(ap, "Resources", res or "<<>>")
        # clockwise on screen = negative angle in PDF space (y up)
        a = math.radians(-spec.rotation)
        if abs(spec.rotation) % 360 > 0.01:
            doc.xref_set_key(ap, "Matrix", f"[{math.cos(a):.6f} {math.sin(a):.6f} {-math.sin(a):.6f} {math.cos(a):.6f} 0 0]")
        doc.xref_set_key(xref, "AP", f"<</N {ap} 0 R>>")
    finally:
        while doc.page_count > pages_before:
            doc.delete_page(doc.page_count - 1)
        scratch.close()


def _apply(document: PdfDocument, page: fitz.Page, annot: fitz.Annot, spec: StampSpec, upright: fitz.Rect) -> None:
    doc = page.parent
    xref = int(annot.xref)
    annot.set_rect(turned_rect(upright, spec.rotation) if abs(spec.rotation) % 360 > 0.01 else upright)
    _write_appearance(doc, xref, spec, upright.width, upright.height)
    doc.xref_set_key(xref, "CA", f"{max(0.0, min(1.0, spec.opacity)):.3f}")
    doc.xref_set_key(xref, "Contents", fitz.get_pdf_str(spec.text if not spec.image_path else (spec.text or "Picture stamp")))
    doc.xref_set_key(xref, "Subj", fitz.get_pdf_str("Stamp"))
    doc.xref_set_key(xref, "Name", "/MonographStamp")
    meta = dict(asdict(spec))
    meta["upright"] = [upright.width, upright.height]
    doc.xref_set_key(xref, PRIVATE_KEY, fitz.get_pdf_str(json.dumps(meta, ensure_ascii=False, sort_keys=True)))
    document.invalidate_pages()


def add_custom_stamp(document: PdfDocument, page_index: int, rect: fitz.Rect, spec: StampSpec) -> int:
    """Add a stamp annotation (``rect`` in unrotated page space, upright size). Returns its xref."""
    if spec.image_path and not Path(spec.image_path).is_file():
        raise FileNotFoundError(spec.image_path)
    page = document._backend._doc.load_page(page_index)  # noqa: SLF001
    annot = page.add_stamp_annot(fitz.Rect(rect), stamp=0)
    _apply(document, page, annot, spec, fitz.Rect(rect))
    return int(annot.xref)


def stamp_spec(document: PdfDocument, xref: int) -> tuple[StampSpec, tuple[float, float]] | None:
    """The parameters of a Monograph PDF stamp (None for other stamps)."""
    doc = document._backend._doc  # noqa: SLF001
    kind, value = doc.xref_get_key(int(xref), PRIVATE_KEY)
    if kind != "string":
        return None
    try:
        data = json.loads(value)
        upright = tuple(data.pop("upright", (0, 0)))
        spec = StampSpec(**{k: v for k, v in data.items() if k in StampSpec.__dataclass_fields__})
        return spec, (float(upright[0]), float(upright[1]))
    except (ValueError, TypeError):
        return None


def update_stamp(document: PdfDocument, page_index: int, xref: int, *, spec: StampSpec | None = None,
                 center: tuple[float, float] | None = None, size: tuple[float, float] | None = None) -> None:
    """Change a Monograph PDF stamp's look, opacity, rotation, position (centre) or upright size."""
    found = stamp_spec(document, xref)
    if found is None:
        raise ValueError("not a Monograph PDF stamp")
    old_spec, (w, h) = found
    spec = spec or old_spec
    page = document._backend._doc.load_page(page_index)  # noqa: SLF001
    annot = next(a for a in page.annots() if int(a.xref) == int(xref))
    r = annot.rect
    cx, cy = center if center else ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    w, h = size if size else (w, h)
    upright = fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    _apply(document, page, annot, spec, upright)
