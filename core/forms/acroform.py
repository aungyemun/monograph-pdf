"""Read / apply AcroForm widgets via PyMuPDF. Signature fields stay visual-only."""

from __future__ import annotations

from typing import Any

import fitz

from core.editing.geometry import Rect
from core.page_space import rect_to_display, rect_to_page
from core.forms.display import sanitize_field_value
from core.forms.fields import FieldType, FormField

# PyMuPDF widget type constants
_TYPE_MAP = {
    getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7): FieldType.TEXT,
    getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", 2): FieldType.CHECKBOX,
    getattr(fitz, "PDF_WIDGET_TYPE_RADIOBUTTON", 5): FieldType.RADIO,
    getattr(fitz, "PDF_WIDGET_TYPE_COMBOBOX", 3): FieldType.DROPDOWN,
    getattr(fitz, "PDF_WIDGET_TYPE_LISTBOX", 4): FieldType.DROPDOWN,
    getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 6): FieldType.SIGNATURE,
}


def _widget_has_ap(doc: fitz.Document, widget: Any) -> bool:
    try:
        xref = int(getattr(widget, "xref", 0) or 0)
        if xref <= 0:
            return False
        key = doc.xref_get_key(xref, "AP")
        return bool(key and key[0] != "null")
    except Exception:  # noqa: BLE001
        return False


def _set_button_value(doc: fitz.Document, xref: int, state: str, *, radio: bool = False) -> None:
    """Write the check box / radio value ``/V`` with exactly the name used for ``/AS``.

    PyMuPDF compares the value it is given with its own decoded on-state, so an on-state that is not
    plain ASCII (``/#82#CD#82#A2`` — Shift-JIS "はい" in many Japanese forms) was written as
    ``/V /Off`` although ``/AS`` showed the tick: Monograph PDF and other readers then read the box as
    not ticked after reopening. The value belongs to the field dictionary: the widget itself, or its
    parent when the widget is one kid of a field. A radio group's value is only set by the chosen kid.
    """
    target = xref
    if doc.xref_get_key(xref, "T")[0] == "null":
        parent = doc.xref_get_key(xref, "Parent")
        if parent[0] == "xref":
            target = int(parent[1].split()[0])
    if radio and state == "Off" and target != xref:
        return  # an unchosen radio kid must not clear the group's value
    doc.xref_set_key(target, "V", f"/{state}")


def resolve_widget_on_state(widget: Any, doc: fitz.Document | None = None) -> str:
    """The on-state name for a checkbox/radio widget (``Yes``, ``On``, or a custom export value).

    PyMuPDF exposes ``Widget.on_state`` as a *method* — never assign the unbound attribute to
    ``field_value`` (that writes a bound-method repr and checkmarks vanish after Save).
    """
    on = getattr(widget, "on_state", None)
    if callable(on):
        try:
            val = on()
            if val not in (None, ""):
                return str(val)
        except Exception:  # noqa: BLE001
            pass
    elif on not in (None, ""):
        return str(on)
    try:
        states = widget.button_states()
        if isinstance(states, dict):
            for key in ("normal", "down"):
                names = states.get(key) or []
                if not isinstance(names, (list, tuple)):
                    continue
                for name in names:
                    s = str(name)
                    if s and s.lower() != "off":
                        return s
    except Exception:  # noqa: BLE001
        pass
    if doc is not None:
        try:
            xref = int(getattr(widget, "xref", 0) or 0)
            if xref > 0:
                kind, ap = doc.xref_get_key(xref, "AP/N")
                if kind == "dict" and ap:
                    # Serialized appearance dict keys look like ``/Yes /Off`` etc.
                    for token in str(ap).replace("<<", " ").replace(">>", " ").split():
                        if token.startswith("/") and token[1:].lower() != "off":
                            return token[1:]
        except Exception:  # noqa: BLE001
            pass
    return "Yes"


def clear_need_appearances(doc: fitz.Document) -> None:
    """Force ``/NeedAppearances`` false after we write real appearance streams.

    Relying on NeedAppearances alone breaks Chrome/Edge (they often ignore it). Callers must
    still generate valid ``/AP`` streams via ``Widget.update()`` / custom appearance writers.
    """
    try:
        if getattr(doc, "is_form_pdf", False):
            doc.need_appearances(False)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Also clear via catalog xref when present (covers edge cases where the setter no-ops).
        cat = doc.pdf_catalog()
        kind, acro = doc.xref_get_key(cat, "AcroForm")
        if kind == "xref":
            ax = int(str(acro).split()[0])
            doc.xref_set_key(ax, "NeedAppearances", "false")
        elif kind == "dict":
            # Inline AcroForm — rewrite if NeedAppearances is present
            if "NeedAppearances" in str(acro):
                doc.xref_set_key(cat, "AcroForm/NeedAppearances", "false")
    except Exception:  # noqa: BLE001
        pass


def _widget_is_checked(widget: Any, raw_value: str) -> bool:
    """Whether a checkbox/radio widget is currently on, using its real on-state name."""
    value = str(raw_value or "").strip()
    if not value or value.lower() in ("off", "no", "false", "0"):
        return False
    on_state = resolve_widget_on_state(widget)
    if value == on_state or value.lstrip("/") == on_state.lstrip("/"):
        return True
    if _pdf_name_bytes(value) == _pdf_name_bytes(on_state):
        return True  # same name, one escaped (#82#CD…) and one decoded (non-ASCII on-state names)
    return value.lower() in ("yes", "on", "true", "1")


def _pdf_name_bytes(name: str) -> bytes:
    """The raw bytes of a PDF name as PyMuPDF hands it out: ``#xx``-escaped, or decoded as UTF-8 with
    surrogate escapes for bytes that are not UTF-8 (``/V`` of a Shift-JIS on-state)."""
    s = str(name or "").lstrip("/")
    try:
        raw = s.encode("utf-8", "surrogateescape")
    except UnicodeError:
        return s.encode("utf-8", "replace")
    out = bytearray()
    i = 0
    while i < len(raw):
        if raw[i] == 0x23 and i + 2 < len(raw) and all(c in b"0123456789abcdefABCDEF" for c in raw[i + 1:i + 3]):
            out.append(int(raw[i + 1:i + 3], 16))
            i += 3
        else:
            out.append(raw[i])
            i += 1
    return bytes(out)


# PDF font resource names in a field's /DA → (family shown in the UI, bold, italic)
_DA_FONTS = {
    "helv": ("Helvetica", False, False), "hebo": ("Helvetica", True, False),
    "heit": ("Helvetica", False, True), "heob": ("Helvetica", False, True), "hebi": ("Helvetica", True, True),
    "tiro": ("Times New Roman", False, False), "tibo": ("Times New Roman", True, False),
    "tiit": ("Times New Roman", False, True), "tibi": ("Times New Roman", True, True),
    "cour": ("Courier New", False, False), "cobo": ("Courier New", True, False),
    "coit": ("Courier New", False, True), "coob": ("Courier New", False, True), "cobi": ("Courier New", True, True),
}


def _font_from_da(name: str) -> tuple[str, bool, bool]:
    """Best-effort UI font for a field's /DA font name (e.g. Helv, TiBo, MS-Mincho, KozMinPr6N)."""
    key = (name or "").strip().lstrip("/").lower()
    if key in _DA_FONTS:
        return _DA_FONTS[key]
    bold = any(k in key for k in ("bold", "-bd", "heavy", "black", "w6", "w7", "w8", "w9"))
    italic = any(k in key for k in ("italic", "oblique"))
    if any(k in key for k in ("mincho", "minch", "kozmin", "heiseimin", "ms-pmincho", "yumin")):
        return "MS Mincho", bold, italic
    if any(k in key for k in ("gothic", "goth", "kozgo", "heiseikakugo", "meiryo", "yugoth", "msgo")):
        return "MS Gothic", bold, italic
    if any(k in key for k in ("times", "serif", "roman", "georgia")) and "sans" not in key:
        return "Times New Roman", bold, italic
    if any(k in key for k in ("courier", "mono", "consola")):
        return "Courier New", bold, italic
    if any(k in key for k in ("arial", "helvetica", "verdana", "tahoma", "segoe", "calibri")):
        return ("Arial" if "arial" in key else "Helvetica"), bold, italic
    return "Helvetica", bold, italic


_NONE = "#00000000"  # fully transparent: the PDF field has no border / no background


def _pdf_color_hex(color: Any) -> str:
    """MuPDF colour tuple (gray / RGB / CMYK, 0-1) → '#rrggbb'; no colour → transparent."""
    try:
        c = [float(v) for v in (color or ())]
    except (TypeError, ValueError):
        return _NONE
    if len(c) == 1:
        c = c * 3
    elif len(c) == 4:
        k = c[3]
        c = [(1 - c[0]) * (1 - k), (1 - c[1]) * (1 - k), (1 - c[2]) * (1 - k)]
    if len(c) != 3:
        return _NONE
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in c)


def _widget_to_field(page_index: int, widget: Any, doc: fitz.Document | None = None) -> FormField:
    ftype = _TYPE_MAP.get(int(getattr(widget, "field_type", -1)), FieldType.TEXT)
    rect = widget.rect
    if doc is not None:  # MuPDF reports widgets in unrotated page space; the editor uses display space
        rect = rect_to_display(doc.load_page(page_index), rect)
    name = str(getattr(widget, "field_name", "") or "")
    raw_value = str(getattr(widget, "field_value", "") or "")
    # /TU tooltip — metadata only
    alternate = ""
    try:
        alternate = str(getattr(widget, "field_label", "") or getattr(widget, "label", "") or "")
    except Exception:  # noqa: BLE001
        alternate = ""
    flags = int(getattr(widget, "field_flags", 0) or 0)
    multiline = bool(flags & getattr(fitz, "PDF_TX_FIELD_IS_MULTILINE", 1 << 12))
    if ftype == FieldType.TEXT and multiline:
        ftype = FieldType.MULTILINE
    # Heuristic date-style: name/label contains date keywords
    low = name.lower()
    if ftype in (FieldType.TEXT, FieldType.MULTILINE) and any(
        k in low for k in ("date", "日付", "年月日", "dob", "born")
    ):
        ftype = FieldType.DATE

    options: list[str] = []
    try:
        choice = getattr(widget, "choice_values", None)
        if choice:
            options = [str(x) for x in choice]
    except Exception:  # noqa: BLE001
        pass

    checked = False
    if ftype in (FieldType.CHECKBOX, FieldType.RADIO):
        checked = _widget_is_checked(widget, raw_value)
        value = ""
    else:
        value = sanitize_field_value(name, raw_value)

    # MuPDF uses 0 for Auto font size — preserve it (do not coerce to a fixed size).
    font_size = 0.0
    try:
        raw_fs = getattr(widget, "text_fontsize", None)
        if raw_fs is None:
            font_size = 0.0
        else:
            font_size = float(raw_fs)
    except Exception:  # noqa: BLE001
        font_size = 0.0

    has_ap = _widget_has_ap(doc, widget) if doc is not None else False
    # Use the field's own border and background; most forms have neither (the page draws the lines).
    border_color = _pdf_color_hex(getattr(widget, "border_color", None))
    try:
        border_width = float(getattr(widget, "border_width", 0) or 0)
    except (TypeError, ValueError):
        border_width = 0.0
    if border_color == _NONE:
        border_width = 0.0
    fill_color = _pdf_color_hex(getattr(widget, "fill_color", None))
    family, bold, italic = _font_from_da(str(getattr(widget, "text_font", "") or ""))

    model = FormField(
        page_index=page_index,
        rect=Rect(float(rect.x0), float(rect.y0), float(rect.width), float(rect.height)),
        field_type=ftype,
        name=name,
        value=value,
        original_value=value,
        options=options,
        checked=checked,
        multiline=multiline or ftype == FieldType.MULTILINE,
        font_size=font_size,
        font_family=family,
        bold=bold,
        italic=italic,
        fill_color=fill_color,
        border_color=border_color,
        align=_read_align(doc, int(getattr(widget, "xref", 0) or 0)),
        valign=_read_valign(doc, int(getattr(widget, "xref", 0) or 0)),
        border_width=border_width,
        is_acroform=True,
        xref=int(getattr(widget, "xref", 0) or 0) or None,
        has_appearance=has_ap,
        alternate_name=alternate,
        value_dirty=False,
        appearance_dirty=False,
        readonly=bool(getattr(widget, "field_flags", 0) & getattr(fitz, "PDF_FIELD_IS_READ_ONLY", 1)),
    )
    if doc is not None and model.xref and ftype in (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE):
        model.runs = _read_rich_runs(doc, model.xref, model)
    return model


def load_acroform_fields(doc: fitz.Document) -> list[FormField]:
    fields: list[FormField] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        try:
            widgets = page.widgets() or []
        except Exception:  # noqa: BLE001
            widgets = []
        for w in widgets:
            if int(getattr(w, "field_type", -1)) not in _TYPE_MAP:
                # Push buttons (e.g. a form's own "Print form" button) and unknown widgets hold no
                # value: they stay as drawn on the page and are never offered for typing.
                continue
            try:
                fields.append(_widget_to_field(i, w, doc))
            except Exception:  # noqa: BLE001
                continue
    return fields


def apply_field_values_to_doc(doc: fitz.Document, fields: list[FormField]) -> None:
    """
    Write dirty field values/geometry back to AcroForm widgets. Does not flatten.

    Unmodified widgets are left untouched — calling Widget.update() on every field
    (especially hybrid XFA) can strip /XFA packets and destroy appearances.
    """
    by_xref = {f.xref: f for f in fields if f.is_acroform and f.xref}
    by_name: dict[str, FormField] = {f.name: f for f in fields if f.is_acroform and f.name}
    # Our own appearances are written after MuPDF has updated every widget: writing one adds and
    # removes a scratch page, which invalidates the other widget objects of the page being walked
    # (their values were then saved empty).
    custom: list[tuple[int, int, FormField]] = []

    for i in range(doc.page_count):
        page = doc.load_page(i)
        try:
            widgets = list(page.widgets() or [])
        except Exception:  # noqa: BLE001
            continue
        for w in widgets:
            xref = int(getattr(w, "xref", 0) or 0)
            name = str(getattr(w, "field_name", "") or "")
            model = by_xref.get(xref) or by_name.get(name)
            if model is None or model.is_candidate:
                continue
            dirty = bool(
                getattr(model, "value_dirty", False) or getattr(model, "appearance_dirty", False)
            )
            if not dirty:
                continue
            try:
                w.rect = rect_to_page(page, fitz.Rect(model.rect.x, model.rect.y, model.rect.x1, model.rect.y1))
                if model.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
                    on_state = resolve_widget_on_state(w, doc)
                    w.field_value = on_state if model.checked else "Off"
                elif model.field_type == FieldType.SIGNATURE:
                    # Never invent cryptographic signature data — leave visual widget only.
                    pass
                else:
                    w.field_value = model.value
                try:
                    w.text_fontsize = model.font_size
                except Exception:  # noqa: BLE001
                    pass
                orig_da = doc.xref_get_key(xref, "DA") if xref else ("null", "null")
                if getattr(model, "style_dirty", False):
                    _apply_text_style(doc, w, model)
                w.update()
                if model.field_type in (FieldType.CHECKBOX, FieldType.RADIO) and xref:
                    # Ensure /AS matches /V — some viewers (Chrome) ignore /V without a matching appearance state.
                    try:
                        as_name = resolve_widget_on_state(w, doc) if model.checked else "Off"
                        doc.xref_set_key(xref, "AS", f"/{as_name}")
                        _set_button_value(doc, xref, as_name, radio=model.field_type == FieldType.RADIO)
                    except Exception:  # noqa: BLE001
                        pass
                _restore_cjk_da(doc, xref, orig_da, model)
                if model.field_type in (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE):
                    from core.forms.appearance import needs_custom_appearance, write_text_appearance

                    if needs_custom_appearance(model) and xref:
                        custom.append((i, xref, model))
                if xref and model.field_type not in (FieldType.CHECKBOX, FieldType.RADIO, FieldType.SIGNATURE):
                    _store_valign(doc, xref, model)
                    _store_rich_value(doc, xref, model)
            except Exception:  # noqa: BLE001
                continue

    from core.forms.appearance import write_text_appearance

    for page_index, xref, model in custom:
        try:
            widget = doc.load_page(page_index).load_widget(xref)
            if widget is not None:
                write_text_appearance(doc, widget, model)
        except Exception:  # noqa: BLE001 — keep MuPDF's appearance rather than fail the save
            pass

    clear_need_appearances(doc)


def _field_dict_xref(doc: fitz.Document, xref: int) -> int:
    """The field dictionary holding /V (the widget itself, or its parent for kid widgets)."""
    try:
        if doc.xref_get_key(xref, "T")[0] != "null":
            return xref
        kind, parent = doc.xref_get_key(xref, "Parent")
        if kind == "xref":
            return int(parent.split()[0])
    except Exception:  # noqa: BLE001
        pass
    return xref


def _read_rich_runs(doc: fitz.Document, xref: int, model: FormField) -> list[dict]:
    """Mixed formatting saved in /RV (by Monograph PDF, PDF Editor or Acrobat), when it matches the value."""
    from core.forms.rich_text import runs_for_value

    try:
        fx = _field_dict_xref(doc, xref)
        kind, val = doc.xref_get_key(fx, "RV")
        if kind == "xref":  # a stream (allowed by the spec)
            rv = (doc.xref_stream(int(val.split()[0])) or b"").decode("utf-8", "replace")
        elif kind == "string":
            rv = val  # PyMuPDF returns PDF strings decoded
        else:
            return []
        return runs_for_value(rv, model.value, model)
    except Exception:  # noqa: BLE001
        return []


def _store_rich_value(doc: fitz.Document, xref: int, model: FormField) -> None:
    """/RV + RichText flag when the entry has mixed formatting; removed again when it no longer does."""
    from core.forms.rich_text import RICH_TEXT_FLAG, default_style, to_xhtml

    def set_flag(on: bool) -> None:
        # /Ff is inheritable: the field dictionary gets it, and so does a widget that has its own
        # /Ff (the nearest value wins, so a kid widget's 0 would otherwise hide the flag)
        for x in dict.fromkeys((fx, xref)):
            kind, ff = doc.xref_get_key(x, "Ff")
            if x != fx and kind == "null":
                continue
            flags = int(ff) if kind == "int" else 0
            doc.xref_set_key(x, "Ff", str(flags | RICH_TEXT_FLAG if on else flags & ~RICH_TEXT_FLAG))

    try:
        fx = _field_dict_xref(doc, xref)
        if model.runs:
            doc.xref_set_key(fx, "RV", fitz.get_pdf_str(to_xhtml(model)))
            doc.xref_set_key(fx, "DS", fitz.get_pdf_str(default_style(model)))
            set_flag(True)
        elif doc.xref_get_key(fx, "RV")[0] != "null" and (model.value_dirty or model.style_dirty):
            doc.xref_set_key(fx, "RV", "null")
            doc.xref_set_key(fx, "DS", "null")
            set_flag(False)
    except Exception:  # noqa: BLE001
        pass


# Key names kept from PDF Editor (<= 0.1.5) so documents saved by it and by Monograph PDF read the same
_VALIGN_KEY = "PDFEditorVAlign"  # private key: vertical position of the text inside the box


_ALIGN_KEY = "PDFEditorAlign"  # private key: justify (PDF /Q only knows left / centre / right)


def _store_valign(doc: fitz.Document, xref: int, model: FormField) -> None:
    v = str(getattr(model, "valign", "") or "")
    try:
        doc.xref_set_key(xref, _VALIGN_KEY, f"/{v}" if v in ("top", "middle", "bottom") else "null")
        justify = str(getattr(model, "align", "") or "") == "justify"
        doc.xref_set_key(xref, _ALIGN_KEY, "/justify" if justify else "null")
    except Exception:  # noqa: BLE001
        pass


def _read_align(doc: fitz.Document | None, xref: int) -> str:
    """/Q quadding on the widget (or its parent field): 0 left, 1 centre, 2 right."""
    if doc is None or not xref:
        return "left"
    try:
        kind, val = doc.xref_get_key(xref, _ALIGN_KEY)
        if kind == "name" and val.lstrip("/") == "justify":
            return "justify"  # other readers see /Q 0 (left)
        kind, val = doc.xref_get_key(xref, "Q")
        if kind == "null":
            kind, val = doc.xref_get_key(xref, "Parent/Q")
        return {"1": "center", "2": "right"}.get(val.strip(), "left") if kind == "int" else "left"
    except Exception:  # noqa: BLE001
        return "left"


def _read_valign(doc: fitz.Document | None, xref: int) -> str:
    if doc is None or not xref:
        return ""
    try:
        kind, val = doc.xref_get_key(xref, _VALIGN_KEY)
    except Exception:  # noqa: BLE001
        return ""
    v = val.lstrip("/") if kind == "name" else ""
    return v if v in ("top", "middle", "bottom") else ""


def _restore_cjk_da(doc: fitz.Document, xref: int, orig_da: tuple[str, str], model: FormField) -> None:
    """MuPDF rewrites /DA with Helvetica on update; a Japanese form keeps its own font there so
    readers that redraw fields (Acrobat, Edge) still use a font that has the characters."""
    from core.forms.appearance import is_cjk_family

    if not xref or orig_da[0] != "string":
        return
    import re as _re

    da = orig_da[1]
    if not is_cjk_family(model.font_family):
        # Any other font the form itself defines (e.g. /TimesNewRoman in /AcroForm /DR) is kept too,
        # unless the font was changed in Monograph PDF: it used to become /Helv on every Save.
        m = _re.search(r"/([^\s/]+)\s+[\d.]+\s+Tf", da)
        if getattr(model, "style_dirty", False) or m is None or not _form_defines_font(doc, m.group(1)):
            return
    size = float(model.font_size or 0)
    da = _re.sub(r"(/\S+)\s+[\d.]+\s+Tf", lambda m: f"{m.group(1)} {size:g} Tf", da, count=1)
    try:
        doc.xref_set_key(xref, "DA", fitz.get_pdf_str(da))
    except Exception:  # noqa: BLE001
        pass


def _form_defines_font(doc: fitz.Document, name: str) -> bool:
    """True when ``/AcroForm /DR /Font`` has a font resource called ``name``."""
    try:
        kind, fonts = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/DR/Font")
        if kind == "xref":
            fonts = doc.xref_object(int(fonts.split()[0]), compressed=True)
        elif kind != "dict":
            return False
        import re as _re

        return _re.search(r"/" + _re.escape(name) + r"(?=[\s/<>\[\]()]|$)", fonts) is not None
    except Exception:  # noqa: BLE001
        return False


def pdf_base_font(family: str) -> str:
    """Map a UI font family to a PDF base-14 font usable in a form field's /DA."""
    f = (family or "").lower()
    if any(k in f for k in ("courier", "mono", "consolas", "cascadia")):
        return "Cour"
    if any(k in f for k in ("times", "serif", "roman", "georgia", "garamond", "cambria", "mincho", "book")) and "sans" not in f:
        return "TiRo"
    return "Helv"


def _hex_rgb(value: str | None):
    """'#rrggbb' / '#aarrggbb' → (r, g, b) 0–1; None for no colour (empty or fully transparent)."""
    v = str(value or "").strip().lstrip("#")
    try:
        if len(v) == 8:
            if int(v[0:2], 16) == 0:
                return None
            v = v[2:]
        if len(v) != 6:
            return None
        return (int(v[0:2], 16) / 255, int(v[2:4], 16) / 255, int(v[4:6], 16) / 255)
    except ValueError:
        return None


def apply_box_colors(w, model: FormField) -> None:
    """The field's background and border (none = transparent / no frame) on the widget (/MK)."""
    fill = _hex_rgb(getattr(model, "fill_color", None))
    border = _hex_rgb(getattr(model, "border_color", None))
    width = float(getattr(model, "border_width", 0) or 0)
    try:
        w.fill_color = fill  # None: no background
        w.border_color = border if width > 0 else None
        w.border_width = width if border is not None else 0
    except Exception:  # noqa: BLE001 — colours are cosmetic; the value is still saved
        pass


def _apply_text_style(doc: fitz.Document, w, model: FormField) -> None:
    """Font family, colour, alignment (/Q) and multi-line flag from the inspector."""
    from core.forms.appearance import is_cjk_family

    if not is_cjk_family(model.font_family):  # keep a Japanese form's own font in /DA
        try:
            w.text_font = pdf_base_font(model.font_family)
        except Exception:  # noqa: BLE001
            pass
    try:
        c = (model.text_color or "#000000").lstrip("#")[-6:]
        w.text_color = (int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255)
    except Exception:  # noqa: BLE001
        pass
    apply_box_colors(w, model)
    if model.field_type not in (FieldType.CHECKBOX, FieldType.RADIO, FieldType.SIGNATURE):
        flag = int(getattr(fitz, "PDF_TX_FIELD_IS_MULTILINE", 1 << 12))
        flags = int(getattr(w, "field_flags", 0) or 0)
        w.field_flags = (flags | flag) if model.multiline else (flags & ~flag)
        q = {"left": 0, "center": 1, "right": 2}.get(str(model.align or "left"), 0)
        try:
            if w.xref:
                doc.xref_set_key(w.xref, "Q", str(q))
        except Exception:  # noqa: BLE001
            pass


def flatten_form_fields(doc: fitz.Document, *, comments: bool = True) -> None:
    """Bake widget appearances into page content and remove form fields. ``comments=False``
    leaves comments and markup as annotations (printing draws them, or leaves them out)."""
    try:
        doc.bake(annots=comments, widgets=True)  # PyMuPDF >= 1.23 style when available
        return
    except Exception:  # noqa: BLE001
        pass
    # Fallback: draw values as text and delete widgets
    for i in range(doc.page_count):
        page = doc.load_page(i)
        try:
            widgets = list(page.widgets() or [])
        except Exception:  # noqa: BLE001
            widgets = []
        for w in widgets:
            try:
                val = str(getattr(w, "field_value", "") or "")
                rect = w.rect
                ftype = int(getattr(w, "field_type", -1))
                if ftype == getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", 2):
                    if val and val.lower() not in ("off", ""):
                        page.insert_text((rect.x0 + 2, rect.y1 - 2), "X", fontsize=10)
                elif ftype == getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 6):
                    page.draw_rect(rect, color=(0.4, 0.4, 0.4), width=0.5)
                    page.insert_text((rect.x0 + 2, rect.y0 + 12), "[Signature]", fontsize=8, color=(0.4, 0.4, 0.4))
                elif val:
                    page.insert_textbox(rect, val, fontsize=max(8, float(getattr(w, "text_fontsize", 10) or 10)))
                page.delete_widget(w)
            except Exception:  # noqa: BLE001
                continue


def create_widget_on_page(
    doc: fitz.Document,
    field: FormField,
) -> FormField:
    """Create a new AcroForm widget for a user-placed field."""
    page = doc.load_page(field.page_index)
    type_map = {
        FieldType.TEXT: getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7),
        FieldType.MULTILINE: getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7),
        FieldType.DATE: getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7),
        FieldType.CHECKBOX: getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", 2),
        FieldType.RADIO: getattr(fitz, "PDF_WIDGET_TYPE_RADIOBUTTON", 5),
        FieldType.DROPDOWN: getattr(fitz, "PDF_WIDGET_TYPE_COMBOBOX", 3),
        FieldType.SIGNATURE: getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 6),
    }
    w = fitz.Widget()
    w.field_type = type_map.get(field.field_type, getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7))
    w.field_name = field.name or f"field_{field.object_id[:8]}"
    w.rect = rect_to_page(page, fitz.Rect(field.rect.x, field.rect.y, field.rect.x1, field.rect.y1))
    if field.field_type not in (FieldType.CHECKBOX, FieldType.RADIO):
        w.field_value = field.value
    w.text_fontsize = field.font_size
    if field.field_type == FieldType.MULTILINE:
        w.field_flags = getattr(fitz, "PDF_TX_FIELD_IS_MULTILINE", 1 << 12)
    if field.field_type == FieldType.DROPDOWN and field.options:
        w.choice_values = field.options
    apply_box_colors(w, field)  # background / border chosen for the new field (none = transparent)
    page.add_widget(w)
    if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
        try:
            live = page.load_widget(int(w.xref)) or w
            on_state = resolve_widget_on_state(live, doc)
            live.field_value = on_state if field.checked else "Off"
            live.update()
            doc.xref_set_key(int(live.xref), "AS", f"/{on_state if field.checked else 'Off'}")
        except Exception:  # noqa: BLE001
            pass
    if page.rotation:
        try:  # /MK /R: the entry reads upright on a turned page
            doc.xref_set_key(int(w.xref), "MK/R", str(int(page.rotation)))
            w.update()
        except Exception:  # noqa: BLE001
            pass
    field.is_acroform = True
    field.is_candidate = False
    try:
        field.xref = int(w.xref)
    except Exception:  # noqa: BLE001
        pass
    return field
