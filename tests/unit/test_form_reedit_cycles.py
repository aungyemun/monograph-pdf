"""Existing PDF form fields: OPEN -> EDIT -> SAVE -> REOPEN, five times (synthetic fixture only).

Guards the saved document of the "old text stays visible / new text overlaps" report: after every
cycle each edited field holds and shows only its latest value, keeps one widget and one appearance,
stays an editable form field, and nothing else in the file changes (page content, untouched fields).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend

READONLY = 1  # /Ff bit 1


def _text_field(page, name, rect, *, font="Helv", size=10.0, multiline=False, value=""):
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = name
    w.rect = fitz.Rect(rect)
    w.text_font = font
    w.text_fontsize = size
    if multiline:
        w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
    if value:
        w.field_value = value
    page.add_widget(w)


def _form(path: Path) -> Path:
    """Two pages; fields with different fonts / sizes, single and multi-line, empty and pre-filled,
    plus printed labels next to (not inside) the fields."""
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((40, 95), "Name", fontsize=9)
    p1.insert_text((40, 135), "Address", fontsize=9)
    p1.insert_text((40, 245), "Country", fontsize=9)
    _text_field(p1, "name", (120, 80, 420, 100), font="Helv", size=11, value="Previously Saved Name")
    _text_field(p1, "address", (120, 120, 520, 200), font="TiRo", size=9, multiline=True,
                value="1 Old Street\nOld Town")
    _text_field(p1, "country", (120, 230, 320, 250), font="Cour", size=0)  # auto size, empty
    _text_field(p1, "untouched", (120, 270, 320, 290), font="Helv", size=10, value="Keep Me")
    p2 = doc.new_page()
    p2.insert_text((40, 95), "Notes", fontsize=9)
    _text_field(p2, "notes", (120, 80, 520, 160), font="Helv", size=10, multiline=True)
    _text_field(p2, "city_ja", (120, 180, 420, 200), font="Helv", size=10)
    doc.save(path)
    doc.close()
    return path


# Per cycle: values for the edited fields (long, non-ASCII and Japanese included).
CYCLES = [
    {"name": "Aung Ye", "address": "22 New Road\nYangon", "country": "Myanmar", "notes": "short",
     "city_ja": "東京都"},
    {"name": "A considerably longer name that fills most of the box", "address": "x", "country": "Japan",
     "notes": "Line one\nLine two\nLine three", "city_ja": "千代田区 Chiyoda"},
    {"name": "Zoë Ñandú-Øresund", "address": "Straße 5\nMünchen", "country": "Deutschland",
     "notes": "", "city_ja": "大阪"},
    {"name": "B", "address": "Long address text " * 6, "country": "", "notes": "ünïcödé", "city_ja": "札幌市"},
    {"name": "Final Name", "address": "Final Address\nLine 2", "country": "Thailand",
     "notes": "final notes", "city_ja": "京都 Kyoto"},
]


def _widgets(doc):
    out = {}
    for page in doc:
        for w in page.widgets():
            out.setdefault(w.field_name, []).append((page.number, w))
    return out


def _ap(doc, xref) -> bytes:
    kind, ref = doc.xref_get_key(xref, "AP/N")
    assert kind == "xref", f"normal appearance must be one stream, got {kind}"
    return doc.xref_stream(int(ref.split()[0])) or b""


def _page_content_hash(doc) -> list[str]:
    return [hashlib.sha256(b"".join(doc.xref_stream(x) or b"" for x in p.get_contents())).hexdigest() for p in doc]


def _edit_and_save(src: Path, dest: Path, values: dict[str, str]) -> None:
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        by_name = {f.name: fid for fid, f in edit.fields.items()}
        for name, value in values.items():
            edit.set_field_value(by_name[name], value=value)
        bake_via_backend(edit, dest, flatten=False)
    finally:
        pdf.close()


@pytest.fixture()
def cycles(tmp_path):
    src = _form(tmp_path / "form.pdf")
    paths = [src]
    for i, values in enumerate(CYCLES, 1):
        dest = tmp_path / f"cycle{i}.pdf"
        _edit_and_save(paths[-1], dest, values)
        paths.append(dest)
    return paths


def test_every_cycle_holds_and_shows_only_the_latest_value(cycles):
    for i, values in enumerate(CYCLES, 1):
        with fitz.open(cycles[i]) as doc:
            widgets = _widgets(doc)
            for name, value in values.items():
                assert len(widgets[name]) == 1, f"cycle {i}: {name} has duplicate widgets"
                pno, w = widgets[name][0]
                assert w.field_value == value, f"cycle {i}: {name} /V"
                ap = _ap(doc, w.xref)
                assert ap.count(b"BT") <= max(1, value.count("\n") + 1) * 8  # one text block, no pile-up
                # What a viewer shows inside the field = the field's appearance only
                shown = " ".join(doc[pno].get_textbox(w.rect).split())
                expected = " ".join(value.split())
                if "\n" not in value and len(value) < 40:  # unwrapped single line: exact
                    assert shown == expected, f"cycle {i}: {name} shows {shown!r}"
                else:  # wrapped / long text: every shown word belongs to the current value
                    assert set(shown.split()) <= set(expected.split()), f"cycle {i}: {name} shows old text"


def test_no_accumulation_and_rest_of_file_unchanged(cycles):
    with fitz.open(cycles[0]) as original:
        content0 = _page_content_hash(original)
        w0 = _widgets(original)
        untouched_ap = _ap(original, w0["untouched"][0][1].xref)
        n_widgets = sum(len(v) for v in w0.values())
    sizes, xrefs = [], []
    for path in cycles[1:]:
        with fitz.open(path) as doc:
            assert doc.page_count == 2
            assert _page_content_hash(doc) == content0, "page content must not change (no text drawn on the page)"
            widgets = _widgets(doc)
            assert sum(len(v) for v in widgets.values()) == n_widgets
            keep = widgets["untouched"][0][1]
            assert keep.field_value == "Keep Me"
            assert _ap(doc, keep.xref) == untouched_ap, "an untouched field's appearance must be left alone"
            for page in doc:
                annots = doc.xref_get_key(page.xref, "Annots")[1]
                assert annots.count(" 0 R") == len(list(page.widgets())), "no extra annotations"
            xrefs.append(doc.xref_length())
        sizes.append(path.stat().st_size)
    # Five rounds of saving leave no more objects or bytes than filling the form once with the
    # same final values: nothing piles up (old appearances, fonts, widgets).
    once = cycles[0].with_name("once_for_size.pdf")
    _edit_and_save(cycles[0], once, CYCLES[-1])
    with fitz.open(once) as doc:
        once_xrefs = doc.xref_length()
    assert xrefs[-1] <= once_xrefs, (xrefs, once_xrefs)
    assert sizes[-1] <= once.stat().st_size * 1.02, (sizes, once.stat().st_size)


def test_fields_stay_editable_form_fields(cycles):
    final = cycles[-1]
    with fitz.open(final) as doc:
        assert doc.is_form_pdf
        for page in doc:
            for w in page.widgets():
                assert w.field_type == fitz.PDF_WIDGET_TYPE_TEXT
                assert not (int(w.field_flags or 0) & READONLY), f"{w.field_name} became read-only"
        kind, value = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/NeedAppearances")
        assert kind == "null" or value == "false"
    # ... and can be edited once more, with the new value replacing the old one
    again = final.with_name("again.pdf")
    _edit_and_save(final, again, {"name": "Edited Again"})
    with fitz.open(again) as doc:
        (pno, w), = _widgets(doc)["name"]
        assert w.field_value == "Edited Again"
        assert " ".join(doc[pno].get_textbox(w.rect).split()) == "Edited Again"


def test_after_five_cycles_page_looks_like_a_single_fill(cycles, tmp_path):
    """The re-edited form renders exactly like the original form filled once with the final values:
    nothing of the earlier values is left anywhere on the pages."""
    once = tmp_path / "once.pdf"
    _edit_and_save(cycles[0], once, CYCLES[-1])
    with fitz.open(cycles[-1]) as a, fitz.open(once) as b:
        for pa, pb in zip(a, b):
            ia = pa.get_pixmap(dpi=96, alpha=False).samples
            ib = pb.get_pixmap(dpi=96, alpha=False).samples
            assert ia == ib, f"page {pa.number + 1} differs from a single fill"


@pytest.mark.parametrize("multiline", [False, True])
def test_clearing_a_saved_field_saves_it_empty(tmp_path, multiline):
    """Emptying a field that already holds a saved value removes the value and its text — before,
    PyMuPDF kept the old /V and the old appearance, so the "cleared" text came back after Save."""
    src = tmp_path / "filled.pdf"
    doc = fitz.open()
    page = doc.new_page()
    _text_field(page, "f", (100, 100, 400, 160 if multiline else 120), multiline=multiline,
                value="Old saved\ntext" if multiline else "Old saved text")
    doc.save(src)
    doc.close()
    out = tmp_path / "cleared.pdf"
    _edit_and_save(src, out, {"f": ""})
    with fitz.open(out) as d:
        w = d[0].first_widget
        assert w.field_value == ""
        assert d.xref_get_key(w.xref, "V") == ("string", "")
        assert d[0].get_textbox(w.rect).strip() == ""
        ap = _ap(d, w.xref)
        assert b"Tj" not in ap and b"TJ" not in ap
    # and it can be filled again afterwards
    again = tmp_path / "refilled.pdf"
    _edit_and_save(out, again, {"f": "New"})
    with fitz.open(again) as d:
        w = d[0].first_widget
        assert w.field_value == "New" and d[0].get_textbox(w.rect).strip() == "New"