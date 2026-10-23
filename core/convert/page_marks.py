"""Headers, footers, page numbers, watermarks and backgrounds ("page marks"), offline.

Every mark is drawn upright on a scratch page of the page's *displayed* size and placed on the
real page as one Form XObject turned back by the page's /Rotate, so it reads correctly and sits
on the intended edge on rotated pages too. The page's own content is never rewritten.

Each placed XObject carries a private key (``/MonographPDFMark /Header`` etc.) and belongs to
an optional-content group (shown as a layer in viewers that list layers). That makes marks added
by Monograph PDF identifiable: they can be replaced or removed later without touching any other
content. Marks added by other software, by earlier Monograph PDF versions, or after a viewer has
merged the page's content streams cannot be identified and are left alone (the result reports
how many were removed).
"""

from __future__ import annotations

import datetime as _dt
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from core.document import PdfDocument

MARK_KEY = "MonographPDFMark"
KIND_HEADER_FOOTER = "HeaderFooter"
KIND_WATERMARK = "Watermark"
KIND_BACKGROUND = "Background"
ALL_KINDS = (KIND_HEADER_FOOTER, KIND_WATERMARK, KIND_BACKGROUND)
LAYER_NAMES = {
    KIND_HEADER_FOOTER: "Monograph PDF: Header and footer",
    KIND_WATERMARK: "Monograph PDF: Watermark",
    KIND_BACKGROUND: "Monograph PDF: Background",
}
TOKENS = ("{page}", "{total}", "{date}", "{bates}")
SAFE_IMAGE_FORMATS = ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"]
MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression-bomb sized pictures

_INVOKE_RE = re.compile(rb"\s*q\s+/([^\s/\[\]()<>{}%]+)\s+Do\s+Q\s*")


# --------------------------------------------------------------------------- specifications


@dataclass
class HeaderFooterSpec:
    """Six text slots. ``{page}``, ``{total}``, ``{date}`` and ``{bates}`` are replaced; other text is literal.

    ``{bates}`` is a fixed-width page identifier for legal / records work: prefix + the page's
    position in the document counted from ``bates_start``, zero-padded to ``bates_digits`` + suffix
    (e.g. ``CASE-000001``)."""

    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = ""
    footer_right: str = ""
    font_size: float = 9.0
    color: tuple[float, float, float] = (0.2, 0.2, 0.2)
    margin_top: float = 36.0  # header baseline, from the top edge (pt)
    margin_bottom: float = 22.0  # footer baseline, from the bottom edge (pt)
    margin_left: float = 36.0
    margin_right: float = 36.0
    start_number: int = 1  # number shown on the first page of the document
    date_format: str = "%Y-%m-%d"
    date: _dt.date | None = None  # fixed date (tests); today when None
    bates_prefix: str = ""
    bates_suffix: str = ""
    bates_start: int = 1
    bates_digits: int = 6

    def bates(self, page_index: int) -> str:
        """Identifier of the page at 0-based ``page_index`` in the document."""
        digits = max(1, min(int(self.bates_digits), 12))
        return f"{self.bates_prefix}{int(self.bates_start) + int(page_index):0{digits}d}{self.bates_suffix}"

    def slots(self) -> dict[str, str]:
        return {
            "header_left": self.header_left, "header_center": self.header_center, "header_right": self.header_right,
            "footer_left": self.footer_left, "footer_center": self.footer_center, "footer_right": self.footer_right,
        }

    def is_empty(self) -> bool:
        return not any(v.strip() for v in self.slots().values())


@dataclass
class WatermarkSpec:
    text: str = ""
    image_path: Path | None = None  # used instead of text when set
    font_size: float = 48.0
    color: tuple[float, float, float] = (0.55, 0.55, 0.55)
    opacity: float = 0.25
    rotation: float = 45.0  # degrees, counter-clockwise as seen on screen
    image_scale: float = 0.5  # picture width as a fraction of the page width
    position: str = "center"  # center | top | bottom
    behind: bool = False  # True: drawn under the page content


@dataclass
class BackgroundSpec:
    color: tuple[float, float, float] | None = (1.0, 1.0, 0.9)
    image_path: Path | None = None  # drawn over the colour when both are set
    image_fit: str = "fit"  # fit (keep proportions, centred) | stretch (fill the page)
    opacity: float = 1.0


@dataclass
class MarksResult:
    destination: Path
    pages_marked: int = 0
    removed: dict[str, int] = field(default_factory=dict)
    retained_objects: int = 0  # removed from view but still stored (resources shared by other pages)
    font_size_reduced_on: list[int] = field(default_factory=list)  # pages where text was shrunk to fit


# --------------------------------------------------------------------------- helpers


def _fonts() -> tuple[fitz.Font, fitz.Font]:
    return fitz.Font("helv"), fitz.Font("cjk")


def _runs(text: str) -> list[tuple[str, fitz.Font]]:
    from core.forms.appearance import _runs as runs

    helv, cjk = _fonts()
    return runs(text, helv, cjk)


def text_width(text: str, size: float) -> float:
    return sum(f.text_length(t, fontsize=size) for t, f in _runs(text))


def expand_tokens(text: str, *, page: int, total: int, date: str, bates: str = "") -> str:
    return (text.replace("{page}", str(page)).replace("{total}", str(total)).replace("{date}", date)
            .replace("{bates}", bates))


def _write_line(page: fitz.Page, text: str, x: float, baseline: float, size: float,
                color: tuple[float, float, float], opacity: float = 1.0,
                morph: tuple[fitz.Point, fitz.Matrix] | None = None) -> None:
    tw = fitz.TextWriter(page.rect)
    for chunk, font in _runs(text):
        tw.append((x, baseline), chunk, font=font, fontsize=size)
        x += font.text_length(chunk, fontsize=size)
    tw.write_text(page, color=color, opacity=opacity, morph=morph)


def _load_image(path: Path, opacity: float) -> tuple[bytes, int, int]:
    """PNG bytes of a picture with the opacity applied (only everyday raster formats are decoded)."""
    from PIL import Image

    with Image.open(Path(path), formats=SAFE_IMAGE_FORMATS) as im:
        if im.width * im.height > MAX_IMAGE_PIXELS:
            raise ValueError(f"The picture is too large ({im.width} × {im.height} pixels).")
        im.load()
        rgba = im.convert("RGBA")
    if opacity < 0.999:
        a = rgba.split()[-1].point(lambda p: int(p * max(0.0, min(1.0, opacity))))
        rgba.putalpha(a)
    buf = io.BytesIO()
    rgba.save(buf, format="PNG")
    return buf.getvalue(), rgba.width, rgba.height


def _ocg(doc: fitz.Document, kind: str) -> int:
    name = LAYER_NAMES[kind]
    for xref, info in (doc.get_ocgs() or {}).items():
        if info.get("name") == name:
            return xref
    return doc.add_ocg(name, on=True)


def _place(page: fitz.Page, scratch: fitz.Document, kind: str, *, behind: bool, pno: int = 0) -> None:
    """Put scratch page ``pno`` (displayed size, upright) on ``page`` and tag the new XObject.

    One scratch document serves all pages of a kind, so fonts and pictures it uses are copied into
    the output once and shared by every page (PyMuPDF keeps one graft map per source document).
    """
    doc = page.parent
    before = {x[0] for x in page.get_xobjects()}
    target = page.rect * page.derotation_matrix
    target.normalize()
    page.show_pdf_page(target, scratch, pno, rotate=int(page.rotation), keep_proportion=False,
                       overlay=not behind, oc=_ocg(doc, kind))
    new = [x[0] for x in page.get_xobjects() if x[0] not in before]
    for xref in new:
        doc.xref_set_key(xref, MARK_KEY, f"/{kind}")


# --------------------------------------------------------------------------- drawing


def _draw_header_footer(sp: fitz.Page, spec: HeaderFooterSpec, *, number: int, total: int, date: str,
                        bates: str = "") -> bool:
    """Returns True when some text had to be made smaller to fit between the margins."""
    w, h = sp.rect.width, sp.rect.height
    avail = max(10.0, w - spec.margin_left - spec.margin_right)
    shrunk = False
    for slot, raw in spec.slots().items():
        if not raw.strip():
            continue
        text = expand_tokens(raw, page=number, total=total, date=date, bates=bates)
        size = float(spec.font_size)
        tw = text_width(text, size)
        if tw > avail:
            size = max(4.0, size * avail / tw)
            tw = text_width(text, size)
            shrunk = True
        where, align = slot.split("_")
        baseline = spec.margin_top if where == "header" else h - spec.margin_bottom
        if align == "left":
            x = spec.margin_left
        elif align == "center":
            x = (w - tw) / 2
        else:
            x = w - spec.margin_right - tw
        _write_line(sp, text, x, baseline, size, tuple(spec.color))
    return shrunk


def _anchor(sp: fitz.Page, position: str) -> fitz.Point:
    w, h = sp.rect.width, sp.rect.height
    y = {"top": h * 0.2, "bottom": h * 0.8}.get(position, h / 2)
    return fitz.Point(w / 2, y)


def _put_image(sp: fitz.Page, rect: fitz.Rect, data: bytes, cache: dict, key: str) -> None:
    """Insert a picture; later pages of the same scratch document reuse the same image object."""
    xref = cache.get(key)
    if xref:
        sp.insert_image(rect, xref=xref, keep_proportion=False)
    else:
        cache[key] = sp.insert_image(rect, stream=data, keep_proportion=False)


def _draw_watermark(sp: fitz.Page, spec: WatermarkSpec, image: tuple[bytes, int, int] | None,
                    cache: dict | None = None) -> bool:
    w, h = sp.rect.width, sp.rect.height
    c = _anchor(sp, spec.position)
    ang = float(spec.rotation)
    if image is not None:
        data, pw, ph = image
        bw = max(1.0, w * max(0.05, min(1.0, spec.image_scale)))
        bh = bw * ph / pw
        rad = math.radians(ang)
        ext_w = abs(bw * math.cos(rad)) + abs(bh * math.sin(rad))
        ext_h = abs(bw * math.sin(rad)) + abs(bh * math.cos(rad))
        k = min(1.0, (w * 0.95) / ext_w, (h * 0.95) / ext_h)  # keep the turned picture on the page
        bw, bh, ext_w, ext_h = bw * k, bh * k, ext_w * k, ext_h * k
        cache = {} if cache is None else cache
        if abs(ang) < 1e-6:
            _put_image(sp, fitz.Rect(c.x - bw / 2, c.y - bh / 2, c.x + bw / 2, c.y + bh / 2), data, cache, "wm")
        else:  # arbitrary angle: the picture on its own page (one shared page), placed turned
            pic = cache.get("wm_pic")
            if pic is None:
                pic = cache["wm_pic"] = fitz.open()
                pp = pic.new_page(width=pw, height=ph)
                pp.insert_image(pp.rect, stream=data, keep_proportion=False)
            sp.show_pdf_page(fitz.Rect(c.x - ext_w / 2, c.y - ext_h / 2, c.x + ext_w / 2, c.y + ext_h / 2),
                             pic, 0, rotate=-ang, keep_proportion=False)
        return k < 1.0
    text = spec.text.strip()
    if not text:
        return False
    size = float(spec.font_size)
    rad = math.radians(ang)
    tw = text_width(text, size)
    # Longest run along the text direction that stays inside the page (85 % margin)
    cos, sin = abs(math.cos(rad)), abs(math.sin(rad))
    limits = []
    if cos > 1e-6:
        limits.append(w / cos)
    if sin > 1e-6:
        limits.append(h / sin)
    along = min(limits) * 0.85
    shrunk = False
    if tw > along:
        size = size * along / tw
        tw = text_width(text, size)
        shrunk = True
    # Baseline centred on the anchor; the text is turned about the anchor (positive = counter-clockwise)
    x0, base = c.x - tw / 2, c.y + size * 0.35
    morph = (c, fitz.Matrix(ang)) if abs(ang) > 1e-6 else None
    _write_line(sp, text, x0, base, size, tuple(spec.color), opacity=float(spec.opacity), morph=morph)
    return shrunk


def _draw_background(sp: fitz.Page, spec: BackgroundSpec, image: tuple[bytes, int, int] | None,
                     cache: dict | None = None) -> None:
    op = max(0.0, min(1.0, float(spec.opacity)))
    if spec.color is not None:
        sp.draw_rect(sp.rect, color=None, fill=tuple(spec.color), fill_opacity=op, width=0)
    if image is not None:
        data, pw, ph = image
        r = sp.rect
        if spec.image_fit != "stretch":  # keep proportions, centred (computed here: insert_image's
            k = min(r.width / pw, r.height / ph)  # keep_proportion is not reliable for every picture)
            iw, ih = pw * k, ph * k
            r = fitz.Rect((r.width - iw) / 2, (r.height - ih) / 2, (r.width + iw) / 2, (r.height + ih) / 2)
        _put_image(sp, r, data, {} if cache is None else cache, "bg")


# --------------------------------------------------------------------------- inspection / removal


def _page_marks(page: fitz.Page) -> list[tuple[int, str, int, str]]:
    """(content xref, kind, xobject xref, resource name) for every identifiable mark on the page."""
    doc = page.parent
    names = {}
    for xref, name, invoker, *_ in page.get_xobjects():
        if invoker == 0:
            names[name] = xref
    out = []
    for cx in page.get_contents():
        data = doc.xref_stream(cx) or b""
        m = _INVOKE_RE.fullmatch(data)
        if not m:
            continue
        name = m.group(1).decode("latin-1")
        xo = names.get(name)
        if not xo:
            continue
        kind, val = doc.xref_get_key(xo, MARK_KEY)
        if kind == "name" and val.lstrip("/") in ALL_KINDS:
            out.append((cx, val.lstrip("/"), xo, name))
    return out


def lock_page_marks(doc: fitz.Document, kinds: set[str] | None = None) -> int:
    """Make identifiable Monograph PDF marks of ``kinds`` (watermarks by default) ordinary page
    content: they leave their layer (a viewer can no longer hide them by switching the layer off)
    and lose their identifying key (Remove Watermark no longer finds them). Used when a watermarked
    document is protected; works on a working copy. Returns the number of pages changed."""
    kinds = set(kinds or {KIND_WATERMARK})
    pages = 0
    for page in doc:
        marks = [m for m in _page_marks(page) if m[1] in kinds]
        for _cx, _kind, xo, _name in marks:
            doc.xref_set_key(xo, "OC", "null")
            doc.xref_set_key(xo, MARK_KEY, "null")
        if marks:
            pages += 1
    if pages:  # drop the now empty layers from the layer list
        try:
            names = {LAYER_NAMES[k] for k in kinds if k in LAYER_NAMES}
            empty = [x for x, info in (doc.get_ocgs() or {}).items() if info.get("name") in names]
            cat = doc.pdf_catalog()
            for key in ("OCProperties/OCGs", "OCProperties/D/ON", "OCProperties/D/OFF", "OCProperties/D/Order"):
                kind, val = doc.xref_get_key(cat, key)
                if kind != "array":
                    continue
                for x in empty:
                    val = re.sub(rf"(?<!\d){x} 0 R", "", val)
                doc.xref_set_key(cat, key, " ".join(val.split()))
        except Exception:  # noqa: BLE001 — an unused layer entry is harmless
            pass
    return pages


def count_marks(document: PdfDocument | fitz.Document) -> dict[str, int]:
    """Number of pages carrying each kind of identifiable Monograph PDF mark."""
    doc = document if isinstance(document, fitz.Document) else document._backend._doc  # noqa: SLF001
    counts = {k: 0 for k in ALL_KINDS}
    for page in doc:
        for kind in {k for _c, k, _x, _n in _page_marks(page)}:
            counts[kind] += 1
    return counts


def _resources_shared(doc: fitz.Document, page: fitz.Page) -> bool:
    kind, val = doc.xref_get_key(page.xref, "Resources")
    if kind != "xref":
        return kind == "null"  # inherited from the page tree: treat as shared
    for other in doc:
        if other.number != page.number and doc.xref_get_key(other.xref, "Resources") == ("xref", val):
            return True
    return False


def _remove_on_page(page: fitz.Page, kinds: set[str]) -> tuple[int, int]:
    """Remove identifiable marks of ``kinds``. Returns (removed, retained objects)."""
    doc = page.parent
    marks = [m for m in _page_marks(page) if m[1] in kinds]
    if not marks:
        return 0, 0
    drop = {m[0] for m in marks}
    keep = [x for x in page.get_contents() if x not in drop]
    doc.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in keep) + "]")
    retained = 0
    shared = _resources_shared(doc, page)
    remaining = b"".join(doc.xref_stream(x) or b"" for x in keep)
    for _cx, _kind, _xo, name in marks:
        still_used = re.search(rb"/" + re.escape(name.encode("latin-1")) + rb"(?![^\s/\[\]()<>{}%])", remaining)
        if shared or still_used:
            retained += 1
            continue
        res_kind, res_val = doc.xref_get_key(page.xref, "Resources")
        holder = int(res_val.split()[0]) if res_kind == "xref" else page.xref
        path = f"XObject/{name}" if res_kind == "xref" else f"Resources/XObject/{name}"
        doc.xref_set_key(holder, path, "null")
    return len(marks), retained


# --------------------------------------------------------------------------- public API


def _indices(doc: fitz.Document, pages: list[int] | None) -> list[int]:
    if pages is None:
        return list(range(doc.page_count))
    out = sorted({int(p) for p in pages})
    bad = [p for p in out if p < 0 or p >= doc.page_count]
    if bad:
        raise ValueError(f"Page {bad[0] + 1} does not exist (the document has {doc.page_count} pages).")
    return out


def mark_document(doc: fitz.Document, *, header_footer: HeaderFooterSpec | None = None,
                  watermark: WatermarkSpec | None = None, background: BackgroundSpec | None = None,
                  pages: list[int] | None = None, replace_existing: bool = True,
                  result: MarksResult | None = None) -> MarksResult:
    """Apply marks to an open (working) document in place."""
    result = result or MarksResult(destination=Path())
    indices = _indices(doc, pages)
    total = doc.page_count
    wm_image = _load_image(watermark.image_path, watermark.opacity) if watermark and watermark.image_path else None
    bg_image = _load_image(background.image_path, background.opacity) if background and background.image_path else None
    hf = header_footer if header_footer and not header_footer.is_empty() else None
    wm = watermark if watermark and (watermark.image_path or watermark.text.strip()) else None
    bg = background if background and (background.color is not None or background.image_path) else None
    if not (hf or wm or bg):
        raise ValueError("Nothing to add: enter some text or choose a picture or colour.")
    date = ""
    if hf:
        date = (hf.date or _dt.date.today()).strftime(hf.date_format or "%Y-%m-%d")
    replace = {k for k, s in ((KIND_HEADER_FOOTER, hf), (KIND_WATERMARK, wm), (KIND_BACKGROUND, bg)) if s}
    if replace_existing:
        for i in indices:
            removed, retained = _remove_on_page(doc.load_page(i), replace)
            result.retained_objects += retained
            if removed:
                result.removed["replaced"] = result.removed.get("replaced", 0) + removed
    # 1. Draw every page's marks on one scratch document per kind (scratch page n <-> indices[n])
    kinds = [(KIND_BACKGROUND, bg), (KIND_WATERMARK, wm), (KIND_HEADER_FOOTER, hf)]
    scratch = {k: fitz.open() for k, spec in kinds if spec}
    cache: dict = {}
    try:
        shrunk_pages: set[int] = set()
        for i in indices:
            page = doc.load_page(i)
            w, h = page.rect.width, page.rect.height
            if bg:
                _draw_background(scratch[KIND_BACKGROUND].new_page(width=w, height=h), bg, bg_image, cache)
            if wm and _draw_watermark(scratch[KIND_WATERMARK].new_page(width=w, height=h), wm, wm_image, cache):
                shrunk_pages.add(i)
            if hf and _draw_header_footer(scratch[KIND_HEADER_FOOTER].new_page(width=w, height=h), hf,
                                          number=i + hf.start_number, total=total + hf.start_number - 1, date=date,
                                          bates=hf.bates(i)):
                shrunk_pages.add(i)
        # 2. Fonts cut down once per kind, then shared by all pages
        for k in (KIND_WATERMARK, KIND_HEADER_FOOTER):
            if k in scratch and not (k == KIND_WATERMARK and wm_image):
                scratch[k].subset_fonts()
        # 3. Place: background underneath, watermark in front of or behind, header/footer in front
        for n, i in enumerate(indices):
            page = doc.load_page(i)
            if bg:
                _place(page, scratch[KIND_BACKGROUND], KIND_BACKGROUND, behind=True, pno=n)
            if wm:
                _place(page, scratch[KIND_WATERMARK], KIND_WATERMARK, behind=wm.behind, pno=n)
            if hf:
                _place(page, scratch[KIND_HEADER_FOOTER], KIND_HEADER_FOOTER, behind=False, pno=n)
            result.pages_marked += 1
        result.font_size_reduced_on = sorted(shrunk_pages)
    finally:
        for sd in scratch.values():
            sd.close()
        if cache.get("wm_pic") is not None:
            cache["wm_pic"].close()
    return result


def _working_copy(document: PdfDocument) -> fitz.Document:
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    doc.insert_pdf(src)
    return doc


def apply_page_marks(document: PdfDocument, destination: Path, **kwargs) -> MarksResult:
    """Write a copy of ``document`` with the marks to ``destination`` (the source is not changed)."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = _working_copy(document)
    try:
        result = mark_document(doc, result=MarksResult(destination=destination), **kwargs)
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return result


def remove_page_marks(document: PdfDocument, destination: Path, kinds: set[str] | None = None,
                      pages: list[int] | None = None) -> MarksResult:
    """Write a copy without the identifiable Monograph PDF marks of ``kinds`` (all kinds by default)."""
    kinds = set(kinds or ALL_KINDS)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = _working_copy(document)
    result = MarksResult(destination=destination)
    try:
        for i in _indices(doc, pages):
            page = doc.load_page(i)
            for kind in kinds:
                removed, retained = _remove_on_page(page, {kind})
                if removed:
                    result.removed[kind] = result.removed.get(kind, 0) + removed
                result.retained_objects += retained
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return result


def render_preview(document: PdfDocument | fitz.Document, page_index: int, *, dpi: float = 40.0, **kwargs) -> fitz.Pixmap:
    """Pixmap of one page with the marks applied (nothing is written to disk)."""
    src = document if isinstance(document, fitz.Document) else document._backend._doc  # noqa: SLF001
    kwargs = dict(kwargs)
    kwargs.pop("pages", None)
    hf: HeaderFooterSpec | None = kwargs.get("header_footer")
    if hf is not None:  # number the page as it is numbered in the whole document
        hf = HeaderFooterSpec(**dict(hf.__dict__))
        number, total = page_index + hf.start_number, src.page_count + hf.start_number - 1
        for slot in hf.slots():
            setattr(hf, slot, getattr(hf, slot).replace("{page}", str(number)).replace("{total}", str(total))
                    .replace("{bates}", hf.bates(page_index)))
        kwargs["header_footer"] = hf
    one = fitz.open()
    try:
        one.insert_pdf(src, from_page=page_index, to_page=page_index)
        try:
            mark_document(one, **kwargs)
        except ValueError:
            pass  # nothing to add yet: show the plain page
        return one.load_page(0).get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    finally:
        one.close()
