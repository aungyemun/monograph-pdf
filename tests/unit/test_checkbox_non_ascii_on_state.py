"""Check boxes whose on-state name is not ASCII keep their tick through Save and reopening.

Regression (0.5.0 validation, also in earlier versions): many Japanese forms name the on-state
``/#82#CD#82#A2`` (Shift-JIS "はい"). Saving wrote ``/AS`` correctly but ``/V /Off``; Monograph PDF
and other readers then showed the box unticked after reopening, and form data said "Off".
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend

SJIS_YES = "#82#CD#82#A2"


def _form(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    for i, name in enumerate(("M", "F")):
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.field_name = name
        w.rect = fitz.Rect(72 + 40 * i, 72, 86 + 40 * i, 86)
        page.add_widget(w)
    for w in page.widgets():
        src = doc.xref_object(w.xref)
        # rename the on-state appearance (Yes / On) to the Shift-JIS name used by the real forms
        on = w.on_state()
        doc.update_object(w.xref, src.replace(f"/{on} ", f"/{SJIS_YES} ").replace(f"/{on}>", f"/{SJIS_YES}>"))
    doc.save(path)
    doc.close()


def _value_and_state(path: Path) -> dict[str, tuple[str, str]]:
    out = {}
    with fitz.open(path) as d:
        for w in d[0].widgets():
            obj = d.xref_object(w.xref, compressed=True)
            v = re.search(r"/V\s*/([^/\s>]+)", obj)
            a = re.search(r"/AS\s*/([^/\s>]+)", obj)
            out[w.field_name] = (v.group(1) if v else "", a.group(1) if a else "")
    return out


def test_fixture_has_non_ascii_on_state(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    with fitz.open(src) as d:
        assert {SJIS_YES} == {f"{w.on_state()}" for w in d[0].widgets()}


def test_ticked_box_saves_matching_value_and_reopens_ticked(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    by_name = {f.name: f for f in edit.fields.values()}
    edit.set_field_value(by_name["M"].object_id, checked=True)
    edit.set_field_value(by_name["F"].object_id, checked=False)
    out = tmp_path / "saved.pdf"
    bake_via_backend(edit, out, flatten=False)
    pdf.close()

    raw = _value_and_state(out)
    assert raw["M"] == (SJIS_YES, SJIS_YES)  # value and appearance state name the same on-state
    assert raw["F"][1] == "Off"
    assert raw["F"][0] in ("Off", "")

    pdf2 = open_document(out)
    edit2 = EditableDocument(pdf2)
    checked = {f.name: f.checked for f in edit2.fields.values()}
    pdf2.close()
    assert checked == {"M": True, "F": False}

    # untick again after reopening: saved as Off
    pdf3 = open_document(out)
    edit3 = EditableDocument(pdf3)
    m = next(f for f in edit3.fields.values() if f.name == "M")
    edit3.set_field_value(m.object_id, checked=False)
    out2 = tmp_path / "unticked.pdf"
    bake_via_backend(edit3, out2, flatten=False)
    pdf3.close()
    assert _value_and_state(out2)["M"] == ("Off", "Off")
