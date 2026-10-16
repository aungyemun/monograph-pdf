"""Machine-readable structural audit of a PDF (forms, fonts, images, boxes)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.forms.capabilities import inspect_pdf_capabilities
from core.page_geometry import label_page_size


@dataclass
class ImageAudit:
    page_index: int
    xref: int
    width_px: int
    height_px: int
    colorspace: str
    bpc: int | None
    filter: str
    display_width_pt: float | None = None
    display_height_pt: float | None = None
    effective_dpi_x: float | None = None
    effective_dpi_y: float | None = None


@dataclass
class PageAudit:
    index: int
    width_pt: float
    height_pt: float
    rotation: int
    orientation: str
    paper: str
    mediabox: list[float]
    cropbox: list[float]
    trimbox: list[float] | None = None
    bleedbox: list[float] | None = None
    artbox: list[float] | None = None
    annot_count: int = 0
    widget_count: int = 0
    image_count: int = 0
    xobject_count: int = 0
    char_count: int = 0


@dataclass
class PdfAudit:
    filename: str
    path: str
    byte_size: int
    pdf_version: str
    page_count: int
    encrypted: bool
    needs_pass: bool
    permissions: int | None = None
    forms: dict[str, Any] = field(default_factory=dict)
    embedded_fonts: list[str] = field(default_factory=list)
    subset_fonts: list[str] = field(default_factory=list)
    type0_fonts: list[str] = field(default_factory=list)
    pages: list[PageAudit] = field(default_factory=list)
    images: list[ImageAudit] = field(default_factory=list)
    signature_count: int = 0
    has_ocg: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _box(page: Any, name: str) -> list[float] | None:
    try:
        r = getattr(page, name, None)
        if r is None:
            return None
        return [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]
    except Exception:  # noqa: BLE001
        return None


def _image_filter(doc: Any, xref: int) -> str:
    try:
        obj = doc.xref_object(xref) or ""
        for token in ("/DCTDecode", "/JPXDecode", "/FlateDecode", "/CCITTFaxDecode", "/JBIG2Decode"):
            if token in obj:
                return token.lstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def audit_pdf(doc: Any, *, path: Path | str, password_used: bool = False) -> PdfAudit:
    """Inspect an open PyMuPDF document. Does not modify it."""
    path = Path(path)
    byte_size = path.stat().st_size if path.is_file() else 0
    version = ""
    try:
        version = str(getattr(doc, "metadata", {}) or {}).get("format") or ""
        if not version:
            # e.g. from doc header
            version = f"PDF {getattr(doc, 'pdf_version', lambda: '')() if callable(getattr(doc, 'pdf_version', None)) else ''}"
    except Exception:  # noqa: BLE001
        version = ""
    try:
        meta = doc.metadata or {}
        version = version or str(meta.get("format") or "")
    except Exception:  # noqa: BLE001
        pass

    encrypted = bool(getattr(doc, "is_encrypted", False))
    needs_pass = bool(getattr(doc, "needs_pass", False))
    perms = None
    try:
        perms = int(doc.permissions)
    except Exception:  # noqa: BLE001
        perms = None

    caps = inspect_pdf_capabilities(doc, path=path)
    fonts = list(caps.embedded_fonts)
    subset = [f for f in fonts if "+" in f]
    type0 = [f for f in fonts if caps.type0_font_count and True]  # refined below

    type0_names: list[str] = []
    try:
        for xref in range(1, doc.xref_length()):
            try:
                subtype = doc.xref_get_key(xref, "Subtype")
                if subtype and "Type0" in str(subtype[1]):
                    base = doc.xref_get_key(xref, "BaseFont")
                    label = str(base[1]).lstrip("/") if base and base[0] != "null" else f"font@{xref}"
                    type0_names.append(label)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    type0 = type0_names

    has_ocg = False
    try:
        cat = doc.pdf_catalog()
        oc = doc.xref_get_key(cat, "OCProperties")
        has_ocg = bool(oc and oc[0] != "null")
    except Exception:  # noqa: BLE001
        pass

    pages: list[PageAudit] = []
    images: list[ImageAudit] = []
    sig_count = 0

    for i in range(doc.page_count):
        page = doc.load_page(i)
        rect = page.rect
        rot = int(page.rotation or 0)
        paper = label_page_size(rect.width, rect.height)
        annots = 0
        widgets = 0
        try:
            annots = len(list(page.annots() or []))
        except Exception:  # noqa: BLE001
            annots = 0
        try:
            wlist = list(page.widgets() or [])
            widgets = len(wlist)
            for w in wlist:
                if int(getattr(w, "field_type", -1)) == 6:  # signature
                    sig_count += 1
        except Exception:  # noqa: BLE001
            widgets = 0

        xobj = 0
        try:
            raw = page.get_xobjects() or []
            xobj = len(raw)
        except Exception:  # noqa: BLE001
            xobj = 0

        text = ""
        try:
            text = page.get_text("text") or ""
        except Exception:  # noqa: BLE001
            text = ""

        page_images = []
        try:
            page_images = page.get_images(full=True) or []
        except Exception:  # noqa: BLE001
            page_images = []

        # Image placement rects for effective DPI
        img_info_list = []
        try:
            img_info_list = page.get_image_info(xrefs=True) or []
        except Exception:  # noqa: BLE001
            img_info_list = []
        info_by_xref = {}
        for info in img_info_list:
            try:
                info_by_xref[int(info.get("xref", 0))] = info
            except Exception:  # noqa: BLE001
                continue

        for img in page_images:
            xref = int(img[0])
            try:
                pix = __import__("fitz").Pixmap(doc, xref)
                w_px, h_px = int(pix.width), int(pix.height)
                cs = str(getattr(pix, "colorspace", None) or "")
                bpc = int(getattr(pix, "n", 0) or 0)
            except Exception:  # noqa: BLE001
                w_px = int(img[2]) if len(img) > 2 else 0
                h_px = int(img[3]) if len(img) > 3 else 0
                cs = ""
                bpc = None
            disp_w = disp_h = None
            dpi_x = dpi_y = None
            info = info_by_xref.get(xref)
            if info:
                bbox = info.get("bbox")
                if bbox and len(bbox) >= 4:
                    disp_w = abs(float(bbox[2]) - float(bbox[0]))
                    disp_h = abs(float(bbox[3]) - float(bbox[1]))
                    if disp_w > 0.01 and w_px:
                        dpi_x = w_px / (disp_w / 72.0)
                    if disp_h > 0.01 and h_px:
                        dpi_y = h_px / (disp_h / 72.0)
            images.append(
                ImageAudit(
                    page_index=i,
                    xref=xref,
                    width_px=w_px,
                    height_px=h_px,
                    colorspace=cs,
                    bpc=bpc,
                    filter=_image_filter(doc, xref),
                    display_width_pt=disp_w,
                    display_height_pt=disp_h,
                    effective_dpi_x=dpi_x,
                    effective_dpi_y=dpi_y,
                )
            )

        pages.append(
            PageAudit(
                index=i,
                width_pt=float(rect.width),
                height_pt=float(rect.height),
                rotation=rot,
                orientation=paper.orientation,
                paper=paper.display,
                mediabox=_box(page, "mediabox") or [0, 0, float(rect.width), float(rect.height)],
                cropbox=_box(page, "cropbox") or [0, 0, float(rect.width), float(rect.height)],
                trimbox=_box(page, "trimbox"),
                bleedbox=_box(page, "bleedbox"),
                artbox=_box(page, "artbox"),
                annot_count=annots,
                widget_count=widgets,
                image_count=len(page_images),
                xobject_count=xobj,
                char_count=len(text),
            )
        )

    notes: list[str] = []
    if password_used:
        notes.append("Opened with password (credential not stored)")
    if caps.xfa.value != "none":
        notes.append(f"XFA={caps.xfa.value}: interactive XFA editing unsupported")
    if caps.som_like_name_count:
        notes.append(f"{caps.som_like_name_count} SOM-like field names (metadata only)")

    return PdfAudit(
        filename=path.name,
        path=str(path),
        byte_size=byte_size,
        pdf_version=version or "unknown",
        page_count=doc.page_count,
        encrypted=encrypted,
        needs_pass=needs_pass,
        permissions=perms,
        forms=caps.to_dict(),
        embedded_fonts=fonts,
        subset_fonts=subset,
        type0_fonts=type0,
        pages=pages,
        images=images,
        signature_count=sig_count,
        has_ocg=has_ocg,
        notes=notes,
    )


def _json_safe(obj: Any) -> Any:
    """Drop lone surrogates from PDF strings so UTF-8 JSON encoding succeeds."""
    if isinstance(obj, str):
        return obj.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def write_audit(audit: PdfAudit, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_safe(audit.to_dict())
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
