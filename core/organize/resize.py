"""Change the paper size of PDF pages and fit the existing content to the new size.

Each page is resized in place: the page's content stream is wrapped in one transform
(scale + centre) and clipped to the original visible area, and every annotation — form
fields, links, comments, highlights — is moved and scaled with it. Nothing is rasterised,
text stays selectable and form fields keep working. Page rotation is preserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import fitz

_MM = 72.0 / 25.4

# Portrait (width, height) in points
PAPER_SIZES: dict[str, tuple[float, float]] = {
    "A3": (297 * _MM, 420 * _MM),
    "A4": (210 * _MM, 297 * _MM),
    "A5": (148 * _MM, 210 * _MM),
    "A6": (105 * _MM, 148 * _MM),
    "B4 (JIS)": (257 * _MM, 364 * _MM),
    "B5 (JIS)": (182 * _MM, 257 * _MM),
    "B4 (ISO)": (250 * _MM, 353 * _MM),
    "B5 (ISO)": (176 * _MM, 250 * _MM),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
    "Tabloid": (792.0, 1224.0),
    "Executive": (522.0, 756.0),
    "Postcard (JP)": (100 * _MM, 148 * _MM),
}


class FitMode(str, Enum):
    FIT = "fit"  # keep proportions, whole page visible (may add white space)
    FILL = "fill"  # keep proportions, fill the page (may crop edges)
    STRETCH = "stretch"  # fill exactly (may distort)
    ACTUAL = "actual"  # keep the original size, centred (may crop or add space)


class Orientation(str, Enum):
    AUTO = "auto"  # follow each page's own orientation
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


@dataclass(frozen=True)
class ResizeResult:
    pages_changed: int
    destination: Path


def size_label(width_pt: float, height_pt: float) -> str:
    return f"{width_pt / _MM:.0f} × {height_pt / _MM:.0f} mm"


def _target_size(paper: tuple[float, float], orientation: Orientation, visible: fitz.Rect) -> tuple[float, float]:
    w, h = min(paper), max(paper)
    if orientation == Orientation.LANDSCAPE or (
        orientation == Orientation.AUTO and visible.width > visible.height
    ):
        return h, w
    return w, h


def _scales(mode: FitMode, src_w: float, src_h: float, avail_w: float, avail_h: float) -> tuple[float, float]:
    if mode == FitMode.STRETCH:
        return avail_w / src_w, avail_h / src_h
    if mode == FitMode.ACTUAL:
        return 1.0, 1.0
    sx, sy = avail_w / src_w, avail_h / src_h
    s = min(sx, sy) if mode == FitMode.FIT else max(sx, sy)
    return s, s


_NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _nums(value: str) -> list[float]:
    return [float(x) for x in _NUM.findall(value)]


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _transform_annotations(doc: fitz.Document, page: fitz.Page, a: float, d: float, e: float, f: float) -> None:
    """Apply x' = a·x + e, y' = d·y + f (PDF user space) to every annotation on ``page``."""

    def tx(vals: list[float]) -> list[float]:
        out = []
        for i, v in enumerate(vals):
            out.append(a * v + e if i % 2 == 0 else d * v + f)
        return out

    xrefs = [x[0] if isinstance(x, (tuple, list)) else x for x in (page.annot_xrefs() or [])]
    for xref in xrefs:
        kind, rect = doc.xref_get_key(xref, "Rect")
        if kind == "array":
            r = tx(_nums(rect))
            if len(r) == 4:
                x0, y0, x1, y1 = min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])
                doc.xref_set_key(xref, "Rect", f"[{_fmt(x0)} {_fmt(y0)} {_fmt(x1)} {_fmt(y1)}]")
        for key in ("QuadPoints", "Vertices", "L", "CL"):
            kind, val = doc.xref_get_key(xref, key)
            if kind == "array":
                doc.xref_set_key(xref, key, "[" + " ".join(_fmt(v) for v in tx(_nums(val))) + "]")
        kind, ink = doc.xref_get_key(xref, "InkList")
        if kind == "array":
            strokes = re.findall(r"\[([^\[\]]*)\]", ink)
            parts = ["[" + " ".join(_fmt(v) for v in tx(_nums(s))) + "]" for s in strokes]
            doc.xref_set_key(xref, "InkList", "[" + " ".join(parts) + "]")


def resize_page(
    doc: fitz.Document,
    page_index: int,
    paper: tuple[float, float],
    *,
    mode: FitMode = FitMode.FIT,
    orientation: Orientation = Orientation.AUTO,
    margin_pt: float = 0.0,
) -> None:
    page = doc.load_page(page_index)
    rotation = page.rotation % 360
    visible = page.rect  # rotated, what the reader sees
    crop = page.cropbox  # unrotated, MuPDF top-left coordinates
    mediabox = page.mediabox
    # Crop box in PDF (bottom-left) user space
    cx0 = crop.x0
    cy0 = mediabox.height - crop.y1 + mediabox.y0
    cw, ch = crop.width, crop.height

    tw_vis, th_vis = _target_size(paper, orientation, visible)
    # Work in unrotated space: a 90/270° page has its width and height swapped
    tw, th = (th_vis, tw_vis) if rotation in (90, 270) else (tw_vis, th_vis)
    margin = max(0.0, float(margin_pt)) if mode in (FitMode.FIT, FitMode.STRETCH) else 0.0
    avail_w, avail_h = max(1.0, tw - 2 * margin), max(1.0, th - 2 * margin)
    sx, sy = _scales(mode, cw, ch, avail_w, avail_h)
    ox = (tw - cw * sx) / 2
    oy = (th - ch * sy) / 2
    # x' = sx·(x − cx0) + ox ; y' = sy·(y − cy0) + oy
    e, f = ox - sx * cx0, oy - sy * cy0

    page.clean_contents()
    xrefs = page.get_contents()
    body = b"".join(doc.xref_stream(x) or b"" for x in xrefs)
    prefix = (
        f"q {_fmt(sx)} 0 0 {_fmt(sy)} {_fmt(e)} {_fmt(f)} cm "
        f"{_fmt(cx0)} {_fmt(cy0)} {_fmt(cw)} {_fmt(ch)} re W n\n"
    ).encode()
    if xrefs:
        doc.update_stream(xrefs[0], prefix + body + b"\nQ\n")
        for extra in xrefs[1:]:
            doc.update_stream(extra, b"")
    _transform_annotations(doc, page, sx, sy, e, f)
    page.set_mediabox(fitz.Rect(0, 0, tw, th))  # also resets the crop box to the new page


def resize_pdf(
    source: Path,
    destination: Path,
    paper: tuple[float, float],
    *,
    mode: FitMode = FitMode.FIT,
    orientation: Orientation = Orientation.AUTO,
    margin_pt: float = 0.0,
    pages: list[int] | None = None,
    password: str | None = None,
) -> ResizeResult:
    """Write a copy of ``source`` with the chosen pages resized to ``paper``."""
    source, destination = Path(source), Path(destination)
    doc = fitz.open(source)
    try:
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise PermissionError("This PDF is password-protected. Unlock it first.")
        targets = sorted(set(range(doc.page_count) if pages is None else pages))
        for i in targets:
            if 0 <= i < doc.page_count:
                resize_page(doc, i, paper, mode=mode, orientation=orientation, margin_pt=margin_pt)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(f".{destination.stem}.resizing.pdf")
        doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()
    tmp.replace(destination)
    return ResizeResult(pages_changed=len(targets), destination=destination)
