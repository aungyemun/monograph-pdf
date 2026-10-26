"""Per-document AcroForm / XFA capability detection (metadata only — not painted)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class XfaKind(str, Enum):
    NONE = "none"
    STATIC = "static"
    DYNAMIC = "dynamic"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class FormSupportLevel(str, Enum):
    NONE = "none"
    FULL = "full"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass
class PdfFormCapabilities:
    """Machine-readable form/font capability summary for diagnostics."""

    path: str = ""
    pdf_type: str = "pdf"
    is_form_pdf: bool = False
    acroform: bool = False
    widget_count: int = 0
    xfa: XfaKind = XfaKind.NONE
    xfa_packet_names: list[str] = field(default_factory=list)
    need_appearances: bool | None = None
    widgets_with_ap: int = 0
    widgets_without_ap: int = 0
    empty_value_count: int = 0
    som_like_name_count: int = 0
    embedded_font_count: int = 0
    embedded_fonts: list[str] = field(default_factory=list)
    type0_font_count: int = 0
    interactive_editing: FormSupportLevel = FormSupportLevel.NONE
    view_fidelity_note: str = ""
    known_limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["xfa"] = self.xfa.value
        d["interactive_editing"] = self.interactive_editing.value
        return d

    def summary_lines(self) -> list[str]:
        return [
            f"PDF type: {self.pdf_type}",
            f"AcroForm: {'yes' if self.acroform else 'no'} ({self.widget_count} widgets)",
            f"XFA: {self.xfa.value}",
            f"Embedded fonts: {self.embedded_font_count}",
            f"Widgets with /AP: {self.widgets_with_ap}",
            f"NeedAppearances: {self.need_appearances}",
            f"Interactive form editing: {self.interactive_editing.value}",
            f"View note: {self.view_fidelity_note or '—'}",
        ]


def _catalog_acroform(doc: Any) -> tuple[int | None, str | None]:
    """
    Return (acroform_xref_or_none, inline_dict_body_or_none).

    PyMuPDF often stores a small AcroForm as an inline catalog dict (`-1` sentinel
    via xref=None + inline body).
    """
    try:
        cat = doc.pdf_catalog()
        key = doc.xref_get_key(cat, "AcroForm")
        if not key or key[0] == "null":
            return None, None
        if key[0] == "xref":
            parts = str(key[1]).split()
            return int(parts[0]), None
        if key[0] == "dict":
            body = str(key[1]).strip()
            if body.startswith("<<") and body.endswith(">>"):
                body = body[2:-2].strip()
            return None, body
    except Exception:  # noqa: BLE001
        return None, None
    return None, None


def _catalog_acroform_xref(doc: Any) -> int | None:
    xref, inline = _catalog_acroform(doc)
    if xref is not None:
        return xref
    if inline is not None:
        return -1
    return None


def _read_need_appearances(doc: Any, acro_xref: int | None) -> bool | None:
    if acro_xref is None or acro_xref < 0:
        # Inline AcroForm — parse NeedAppearances from serialized dict if present
        try:
            _, inline = _catalog_acroform(doc)
            if inline and "NeedAppearances" in inline:
                low = inline.lower()
                if "/true" in low:
                    return True
                if "/false" in low:
                    return False
        except Exception:  # noqa: BLE001
            pass
        # Do not call Document.need_appearances() for reads — PyMuPDF's getter also writes False.
        return None
    try:
        key = doc.xref_get_key(acro_xref, "NeedAppearances")
        if not key or key[0] == "null":
            return None
        val = str(key[1]).strip().lower()
        if val in ("true", "/true"):
            return True
        if val in ("false", "/false"):
            return False
    except Exception:  # noqa: BLE001
        pass
    return None


def _xfa_packets_from_bytes(data: bytes) -> list[str]:
    packets: list[str] = []
    low = data.lower()
    for token in (
        b"template",
        b"datasets",
        b"config",
        b"localeset",
        b"xdp:xdp",
        b"connectionset",
    ):
        if token in low:
            packets.append(token.decode("ascii"))
    return packets


def _detect_xfa(doc: Any, acro_xref: int | None) -> tuple[XfaKind, list[str]]:
    """Inspect AcroForm /XFA array or stream; classify static/dynamic/hybrid/unknown."""
    packets: list[str] = []
    has_xfa = False

    def _ingest_xfa_key(xref: int) -> None:
        nonlocal has_xfa, packets
        try:
            key = doc.xref_get_key(xref, "XFA")
            if not key or key[0] == "null":
                return
            has_xfa = True
            raw = str(key[1])
            for token in ("template", "datasets", "config", "localeSet", "xdp:xdp", "connectionSet"):
                if token.lower() in raw.lower() and token not in packets:
                    packets.append(token)
            # Resolve stream contents when /XFA points at a stream xref
            if key[0] == "xref":
                try:
                    sx = int(str(key[1]).split()[0])
                    data = doc.xref_stream(sx) or b""
                    for p in _xfa_packets_from_bytes(data):
                        if p not in packets:
                            packets.append(p)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    if acro_xref is not None and acro_xref >= 0:
        _ingest_xfa_key(acro_xref)
        try:
            txt = doc.xref_object(acro_xref) or ""
            if "/XFA" in txt:
                has_xfa = True
        except Exception:  # noqa: BLE001
            pass
    else:
        # Inline AcroForm — check serialized body
        try:
            _, inline = _catalog_acroform(doc)
            if inline and "/XFA" in inline:
                has_xfa = True
        except Exception:  # noqa: BLE001
            pass

    # Fallback: scan all xrefs for /XFA under objects that also look like AcroForm
    if not has_xfa:
        try:
            for xref in range(1, min(doc.xref_length(), 4000)):
                try:
                    obj = doc.xref_object(xref) or ""
                except Exception:  # noqa: BLE001
                    continue
                if "/XFA" in obj and ("/Fields" in obj or "/AcroForm" in obj):
                    has_xfa = True
                    _ingest_xfa_key(xref)
                    break
        except Exception:  # noqa: BLE001
            pass

    if not has_xfa:
        return XfaKind.NONE, packets

    dynamic_hint = any(p.lower() == "datasets" for p in packets)
    widget_n = 0
    try:
        for i in range(doc.page_count):
            page = doc.load_page(i)
            widget_n += len(list(page.widgets() or []))
    except Exception:  # noqa: BLE001
        pass

    if widget_n > 0:
        return XfaKind.HYBRID, packets
    if dynamic_hint:
        return XfaKind.DYNAMIC, packets
    if packets:
        return XfaKind.STATIC, packets
    return XfaKind.UNKNOWN, packets


def _widget_has_ap(doc: Any, widget: Any) -> bool:
    try:
        xref = int(getattr(widget, "xref", 0) or 0)
        if xref <= 0:
            return False
        key = doc.xref_get_key(xref, "AP")
        return bool(key and key[0] != "null")
    except Exception:  # noqa: BLE001
        return False


def _embedded_fonts(doc: Any) -> tuple[list[str], int]:
    names: list[str] = []
    type0 = 0
    try:
        for xref in range(1, doc.xref_length()):
            try:
                t = doc.xref_get_key(xref, "Type")
                if not t or "Font" not in str(t[1]):
                    continue
                base = doc.xref_get_key(xref, "BaseFont")
                subtype = doc.xref_get_key(xref, "Subtype")
                label = str(base[1]).lstrip("/") if base and base[0] != "null" else f"font@{xref}"
                names.append(label)
                if subtype and "Type0" in str(subtype[1]):
                    type0 += 1
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq, type0


def inspect_pdf_capabilities(doc: Any, *, path: str | Path = "") -> PdfFormCapabilities:
    """Inspect an open PyMuPDF document for form/font capability signals."""
    from core.forms.display import looks_like_internal_field_id, sanitize_field_value

    caps = PdfFormCapabilities(path=str(path or getattr(doc, "name", "") or ""))
    try:
        caps.is_form_pdf = bool(getattr(doc, "is_form_pdf", False))
    except Exception:  # noqa: BLE001
        caps.is_form_pdf = False

    acro_xref = _catalog_acroform_xref(doc)
    caps.acroform = acro_xref is not None or caps.is_form_pdf
    caps.need_appearances = _read_need_appearances(doc, acro_xref)
    caps.xfa, caps.xfa_packet_names = _detect_xfa(doc, acro_xref)

    widget_count = 0
    with_ap = 0
    without_ap = 0
    empty_v = 0
    som_names = 0
    try:
        for i in range(doc.page_count):
            page = doc.load_page(i)
            for w in page.widgets() or []:
                widget_count += 1
                name = str(getattr(w, "field_name", "") or "")
                value = str(getattr(w, "field_value", "") or "")
                if looks_like_internal_field_id(name):
                    som_names += 1
                cleaned = sanitize_field_value(name, value)
                if not cleaned:
                    empty_v += 1
                if _widget_has_ap(doc, w):
                    with_ap += 1
                else:
                    without_ap += 1
    except Exception:  # noqa: BLE001
        pass

    caps.widget_count = widget_count
    caps.widgets_with_ap = with_ap
    caps.widgets_without_ap = without_ap
    caps.empty_value_count = empty_v
    caps.som_like_name_count = som_names
    if widget_count > 0:
        caps.acroform = True

    fonts, type0 = _embedded_fonts(doc)
    caps.embedded_fonts = fonts[:80]
    caps.embedded_font_count = len(fonts)
    caps.type0_font_count = type0

    # Support classification — MuPDF does not fully render dynamic XFA templates.
    if caps.xfa in (XfaKind.DYNAMIC, XfaKind.UNKNOWN) and widget_count == 0:
        caps.interactive_editing = FormSupportLevel.UNSUPPORTED
        caps.view_fidelity_note = (
            "XFA present without AcroForm widgets; interactive editing unsupported. "
            "Page view uses MuPDF's best available appearance (may differ from Acrobat for pure XFA)."
        )
        caps.known_limitations.append("Dynamic/pure XFA interactive editing unsupported")
    elif caps.xfa == XfaKind.HYBRID:
        caps.interactive_editing = FormSupportLevel.PARTIAL
        caps.view_fidelity_note = (
            "Hybrid AcroForm/XFA: view prefers widget /AP and page content; "
            "XFA SOM paths are metadata only. Full XFA template fidelity is not claimed."
        )
        caps.known_limitations.append("XFA template editing unsupported (AcroForm values only)")
    elif caps.xfa == XfaKind.STATIC and widget_count == 0:
        caps.interactive_editing = FormSupportLevel.UNSUPPORTED
        caps.view_fidelity_note = "Static XFA without widgets — viewing best-effort via MuPDF"
        caps.known_limitations.append("Static XFA without AcroForm widgets")
    elif caps.acroform and widget_count > 0:
        caps.interactive_editing = FormSupportLevel.PARTIAL
        caps.view_fidelity_note = (
            "AcroForm: page render uses MuPDF widget appearances; "
            "editor overlays never paint field names as content."
        )
    else:
        caps.interactive_editing = FormSupportLevel.NONE
        caps.view_fidelity_note = "No interactive form dictionary detected"

    if caps.need_appearances:
        caps.known_limitations.append("NeedAppearances=true — some viewers regenerate /AP")

    return caps


def write_capabilities_report(caps: PdfFormCapabilities, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(caps.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
