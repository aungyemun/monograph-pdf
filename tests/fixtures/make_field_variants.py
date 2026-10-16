"""Fillable text fields built the many ways real PDFs build them (synthetic — no user data).

Every variant has a field called ``target`` (or a path ending in ``target``) for the test to
fill, and most have a ``keep`` field that already holds "Keep me" and must survive a save.
"""

from __future__ import annotations

from pathlib import Path

import fitz

TARGET_RECT = fitz.Rect(150, 200, 400, 240)
KEEP_RECT = fitz.Rect(150, 300, 400, 324)


def _widget(page, name, rect, *, value="", multiline=False, fontsize=0, font="Helv", flags=0):
    w = fitz.Widget()
    w.field_name = name
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = rect
    w.text_font = font
    w.text_fontsize = fontsize
    w.field_flags = flags | (fitz.PDF_TX_FIELD_IS_MULTILINE if multiline else 0)
    if value:
        w.field_value = value
    page.add_widget(w)
    return w


def _labels(page) -> None:
    page.insert_text((60, TARGET_RECT.y0 + 15), "Target:", fontsize=10)
    page.insert_text((60, KEEP_RECT.y0 + 15), "Keep:", fontsize=10)


def _basic(doc, *, multiline=False, **kw):
    page = doc.new_page(width=595, height=842)
    _labels(page)
    _widget(page, "target", TARGET_RECT, multiline=multiline, **kw)
    _widget(page, "keep", KEEP_RECT, value="Keep me")
    return doc


def v_basic(doc):
    return _basic(doc)


def v_multiline(doc):
    return _basic(doc, multiline=True)


def v_fixed_size(doc):
    return _basic(doc, fontsize=9)


def v_tiny(doc):
    page = doc.new_page(width=595, height=842)
    _widget(page, "target", fitz.Rect(150, 200, 260, 209))  # 9 pt high
    _widget(page, "keep", KEEP_RECT, value="Keep me")
    return doc


def v_comb(doc):
    page = doc.new_page(width=595, height=842)
    w = fitz.Widget()
    w.field_name = "target"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = TARGET_RECT
    w.text_font = "Helv"
    w.text_fontsize = 0
    w.text_maxlen = 12
    w.field_flags = fitz.PDF_TX_FIELD_IS_COMB
    page.add_widget(w)
    _widget(page, "keep", KEEP_RECT, value="Keep me")
    return doc


def v_cjk_da(doc):
    _basic(doc)
    for w in doc[0].widgets():
        doc.xref_set_key(w.xref, "DA", fitz.get_pdf_str("/KozMinPr6N-Regular 0 Tf 0 g"))
    return doc


def v_inherited_da(doc):
    """No /DA on the widget — only the AcroForm default (common in older forms)."""
    _basic(doc)
    for w in doc[0].widgets():
        doc.xref_set_key(w.xref, "DA", "null")
    cat = doc.pdf_catalog()
    kind, af = doc.xref_get_key(cat, "AcroForm")
    af_xref = int(af.split()[0]) if kind == "xref" else None
    if af_xref:
        doc.xref_set_key(af_xref, "DA", fitz.get_pdf_str("/Helv 0 Tf 0 g"))
    else:
        doc.xref_set_key(cat, "AcroForm/DA", fitz.get_pdf_str("/Helv 0 Tf 0 g"))
    return doc


def v_no_appearance(doc):
    """Widgets without /AP and NeedAppearances true (viewer must draw them)."""
    _basic(doc)
    for w in doc[0].widgets():
        doc.xref_set_key(w.xref, "AP", "null")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/NeedAppearances", "true")
    return doc


def v_parent_kid(doc):
    """Field dictionary (/T /FT /DA /Q) separate from its widget annotation."""
    _basic(doc)
    page = doc[0]
    w = next(x for x in page.widgets() if x.field_name == "target")
    parent = doc.get_new_xref()
    doc.update_object(
        parent,
        f"<< /FT /Tx /T (target) /DA {fitz.get_pdf_str('/Helv 0 Tf 0 g')} /Q 0 /Kids [{w.xref} 0 R] >>",
    )
    for key in ("T", "FT", "DA", "V", "Q"):
        doc.xref_set_key(w.xref, key, "null")
    doc.xref_set_key(w.xref, "Parent", f"{parent} 0 R")
    cat = doc.pdf_catalog()
    kind, fields = doc.xref_get_key(cat, "AcroForm/Fields")
    items = [t for t in fields.strip("[]").split(" R") if t.strip()]
    refs = [t.strip() + " R" for t in items if not t.strip().startswith(f"{w.xref} ")]
    refs.append(f"{parent} 0 R")
    doc.xref_set_key(cat, "AcroForm/Fields", "[" + " ".join(refs) + "]")
    return doc


def v_hierarchical_name(doc):
    """XFA-style names: topmostSubform[0].Page1[0].target[0] (hybrid forms)."""
    page = doc.new_page(width=595, height=842)
    _labels(page)
    _widget(page, "topmostSubform[0].Page1[0].target[0]", TARGET_RECT)
    _widget(page, "topmostSubform[0].Page1[0].keep[0]", KEEP_RECT, value="Keep me")
    return doc


def v_rotated_page(doc):
    _basic(doc)
    doc[0].set_rotation(90)
    return doc


def v_rotated_widget(doc):
    """/MK /R 90 — the widget's text runs bottom-to-top (rare but legal)."""
    _basic(doc)
    w = next(x for x in doc[0].widgets() if x.field_name == "target")
    doc.xref_set_key(w.xref, "MK/R", "90")
    return doc


def v_cropbox_offset(doc):
    _basic(doc)
    doc[0].set_cropbox(fitz.Rect(40, 40, 555, 802))
    return doc


def v_mediabox_offset(doc):
    """MediaBox not starting at 0,0 (scanned / imposed forms)."""
    _basic(doc)
    page = doc[0]
    doc.xref_set_key(page.xref, "MediaBox", "[50 60 645 902]")
    return doc


def v_bordered(doc):
    """Field with its own border and background colour — both must stay."""
    page = doc.new_page(width=595, height=842)
    _labels(page)
    w = fitz.Widget()
    w.field_name = "target"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = TARGET_RECT
    w.text_font = "Helv"
    w.text_fontsize = 0
    w.border_color = (0.8, 0, 0)
    w.border_width = 1.5
    w.fill_color = (1, 1, 0.8)
    page.add_widget(w)
    _widget(page, "keep", KEEP_RECT, value="Keep me")
    return doc


def v_two_widgets(doc):
    """One field shown in two places (same name on page 1 and page 2)."""
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        _labels(page)
        _widget(page, "target", TARGET_RECT)
    _widget(doc[0], "keep", KEEP_RECT, value="Keep me")
    return doc


def v_third_page(doc):
    for _ in range(3):
        doc.new_page(width=595, height=842)
    _widget(doc[2], "target", TARGET_RECT)
    _widget(doc[2], "keep", KEEP_RECT, value="Keep me")
    return doc


def v_letter_landscape(doc):
    page = doc.new_page(width=792, height=612)
    page.insert_text((300, 325), "Target:", fontsize=10)
    page.insert_text((300, 418), "Keep:", fontsize=10)
    _widget(page, "target", fitz.Rect(400, 300, 700, 340))
    _widget(page, "keep", fitz.Rect(400, 400, 700, 424), value="Keep me")
    return doc


VARIANTS = {
    "basic": v_basic,
    "multiline": v_multiline,
    "fixed_size": v_fixed_size,
    "tiny": v_tiny,
    "comb": v_comb,
    "cjk_da": v_cjk_da,
    "inherited_da": v_inherited_da,
    "no_appearance": v_no_appearance,
    "parent_kid": v_parent_kid,
    "hierarchical_name": v_hierarchical_name,
    "rotated_page": v_rotated_page,
    "rotated_widget": v_rotated_widget,
    "cropbox_offset": v_cropbox_offset,
    "mediabox_offset": v_mediabox_offset,
    "bordered": v_bordered,
    "two_widgets": v_two_widgets,
    "third_page": v_third_page,
    "letter_landscape": v_letter_landscape,
}

# Saved differently: compressed object streams, and permissions-only encryption (no open password)
SAVE_MODES = {
    "plain": {},
    "objstm": {"garbage": 3, "deflate": True, "use_objstms": 1},
    "encrypted": {
        "encryption": fitz.PDF_ENCRYPT_AES_256,
        "owner_pw": "owner-secret",
        "user_pw": "",
        "permissions": fitz.PDF_PERM_PRINT | fitz.PDF_PERM_FORM | fitz.PDF_PERM_ACCESSIBILITY,
    },
}


def write_variant(name: str, folder: Path, save_mode: str = "plain") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    VARIANTS[name](doc)
    path = folder / f"field_{name}_{save_mode}.pdf"
    doc.save(path, **SAVE_MODES[save_mode])
    doc.close()
    return path
