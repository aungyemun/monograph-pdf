"""Hybrid AcroForm/XFA forms (Adobe LiveCycle Designer, e.g. Japanese government forms): Adobe Acrobat
shows the XFA copy of the fields, every other viewer the AcroForm copy. Values filled in Monograph PDF
used to be saved only in the AcroForm copy, so Acrobat showed an empty form. Saving must now put the
values into the XFA data as well, or remove the XFA copy when that is not safely possible."""

from __future__ import annotations

import re
from pathlib import Path

import fitz
import pytest

PREFIX = "topmostSubform[0].Page1[0]."

TEMPLATE = """<template xmlns="http://www.xfa.org/schema/xfa-template/2.8/"
><subform layout="tb" name="topmostSubform"
><pageSet><pageArea name="Page1" id="Page1"/></pageSet
><subform h="842pt" name="Page1" w="595pt"
><bind match="none"/>
<field name="fill_1" w="100pt" h="20pt"><ui><textEdit/></ui></field>
<field name="fill_2" w="100pt" h="20pt"><ui><textEdit multiLine="1"/></ui></field>
<field name="check_1" w="10pt" h="10pt"><ui><checkButton/></ui>
<items><integer>1</integer><integer>0</integer></items></field>
</subform></subform></template>"""

DATASETS = """<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/"
><xfa:data><topmostSubform><fill_1></fill_1><fill_2></fill_2><check_1>0</check_1></topmostSubform
></xfa:data></xfa:datasets>"""

FORM = '<form checksum="abc=" xmlns="http://www.xfa.org/schema/xfa-form/2.8/"/>'


def _stream(doc: fitz.Document, data: str) -> int:
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, data.encode("utf-8"))
    return xref


def make_hybrid(path: Path, *, extra_acroform_field: bool = False) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 60), "Fictional stay schedule (hybrid AcroForm/XFA test form)", fontsize=10)
    names = [("fill_1", fitz.PDF_WIDGET_TYPE_TEXT), ("fill_2", fitz.PDF_WIDGET_TYPE_TEXT),
             ("check_1", fitz.PDF_WIDGET_TYPE_CHECKBOX)]
    if extra_acroform_field:
        names.append(("not_in_template", fitz.PDF_WIDGET_TYPE_TEXT))
    for i, (name, kind) in enumerate(names):
        w = fitz.Widget()
        w.field_type = kind
        w.field_name = PREFIX + name + "[0]"
        w.rect = fitz.Rect(72, 100 + 40 * i, 272 if kind == fitz.PDF_WIDGET_TYPE_TEXT else 86,
                           124 + 40 * i if kind == fitz.PDF_WIDGET_TYPE_TEXT else 114 + 40 * i)
        if kind == fitz.PDF_WIDGET_TYPE_CHECKBOX:
            w.on_state = "1"
        page.add_widget(w)
    packets = [("xdp:xdp", '<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/">'), ("template", TEMPLATE),
               ("datasets", DATASETS), ("form", FORM), ("</xdp:xdp>", "</xdp:xdp>")]
    arr = "[" + "".join(f"{fitz.get_pdf_str(n)}{_stream(doc, s)} 0 R" for n, s in packets) + "]"
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/XFA", arr)  # inline AcroForm dictionary
    doc.save(path)
    doc.close()
    return path


def _xfa(path: Path) -> tuple[str | None, dict[str, str]]:
    with fitz.open(path) as doc:
        kind, val = doc.xref_get_key(doc.pdf_catalog(), "AcroForm")
        acro, key = (int(val.split()[0]), "XFA") if kind == "xref" else (doc.pdf_catalog(), "AcroForm/XFA")
        kind, arr = doc.xref_get_key(acro, key)
        if kind == "null":
            return None, {}
        packets = {m.group(1): doc.xref_stream(int(m.group(2))).decode("utf-8")
                   for m in re.finditer(r"\((.*?)\)\s*(\d+)\s+0\s+R", arr)}
        return arr, packets


def _values(path: Path) -> dict[str, str]:
    with fitz.open(path) as doc:
        return {w.field_name.split(".")[-1]: w.field_value for w in doc[0].widgets()}


def _edit(path: Path):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument

    document = open_document(path)
    return document, EditableDocument(document)


def _fill(edit, leaf: str, value: str | None = None, *, checked: bool | None = None) -> None:
    field = next(f for f in edit.fields.values() if f.name.endswith(leaf + "[0]"))
    if value is not None:
        field.value = value
    if checked is not None:
        field.checked = checked
    field.value_dirty = True


@pytest.fixture
def hybrid(tmp_path) -> Path:
    return make_hybrid(tmp_path / "hybrid.pdf")


def test_filled_values_reach_the_xfa_data(hybrid, tmp_path):
    from core.forms import xfa_sync
    from engines.bake_edits import bake_via_backend

    xfa_sync.take_notes()
    document, edit = _edit(hybrid)
    try:
        _fill(edit, "fill_1", "ヤンゴン発、関西空港着 <&> \"x\"")
        _fill(edit, "fill_2", "東浦町へ移動。\n二行目")
        _fill(edit, "check_1", checked=True)
        out = tmp_path / "filled.pdf"
        bake_via_backend(edit, out)
    finally:
        document.close()
    arr, packets = _xfa(out)
    assert arr is not None, "the XFA copy must be kept when it can be updated"
    data = packets["datasets"]
    # compare parsed values: how quotes are escaped differs between Python versions (both are valid XML)
    from xml.dom import minidom

    root = minidom.parseString(data.encode("utf-8"))
    text = {n.tagName: "".join(c.data for c in n.childNodes if c.nodeType == c.TEXT_NODE)
            for n in root.getElementsByTagName("topmostSubform")[0].childNodes if n.nodeType == n.ELEMENT_NODE}
    assert text["fill_1"] == "ヤンゴン発、関西空港着 <&> \"x\""
    assert text["fill_2"] == "東浦町へ移動。\n二行目"
    assert text["check_1"] == "1"
    assert "&lt;&amp;&gt;" in data  # markup characters are escaped
    assert "form" not in packets, "the cached form state would make Acrobat ignore the new data"
    assert {"xdp:xdp", "template", "datasets", "</xdp:xdp>"} <= set(packets)
    values = _values(out)
    assert values["fill_1[0]"].startswith("ヤンゴン発") and values["fill_2[0]"].startswith("東浦町")
    assert xfa_sync.take_notes() == [], "a successful update needs no message"


def test_unchanged_form_keeps_its_xfa_exactly(hybrid, tmp_path):
    from engines.bake_edits import bake_via_backend

    before = _xfa(hybrid)[1]
    document, edit = _edit(hybrid)
    try:
        out = tmp_path / "untouched.pdf"
        bake_via_backend(edit, out)
    finally:
        document.close()
    assert _xfa(out)[1] == before


def test_field_missing_from_the_template_removes_the_xfa_copy(tmp_path):
    from core.forms import xfa_sync
    from engines.bake_edits import bake_via_backend

    src = make_hybrid(tmp_path / "mismatch.pdf", extra_acroform_field=True)
    xfa_sync.take_notes()
    document, edit = _edit(src)
    try:
        _fill(edit, "not_in_template", "value Acrobat must show")
        out = tmp_path / "out.pdf"
        bake_via_backend(edit, out)
    finally:
        document.close()
    assert _xfa(out)[0] is None, "Acrobat would show an empty XFA field instead of the value"
    assert _values(out)["not_in_template[0]"] == "value Acrobat must show"
    notes = xfa_sync.take_notes()
    assert len(notes) == 1 and "XFA" in notes[0] and "original file is unchanged" in notes[0]
    assert _xfa(src)[0] is not None, "the source file is never changed"


def test_flattening_removes_the_xfa_copy(hybrid, tmp_path):
    from core.forms import xfa_sync
    from engines.bake_edits import bake_via_backend

    document, edit = _edit(hybrid)
    try:
        _fill(edit, "fill_1", "flattened")
        out = tmp_path / "flat.pdf"
        bake_via_backend(edit, out, flatten=True)
    finally:
        document.close()
    assert _xfa(out)[0] is None
    xfa_sync.take_notes()


def test_pdf_without_xfa_is_not_affected(tmp_path):
    from core.forms import xfa_sync

    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "plain"
    w.rect = fitz.Rect(72, 72, 200, 92)
    page.add_widget(w)
    assert not xfa_sync.has_xfa(doc)
    result = xfa_sync.sync_xfa(doc, [], flattened=True)
    assert result.action == "none" and xfa_sync.take_notes() == []
