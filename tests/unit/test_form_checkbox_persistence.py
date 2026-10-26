"""Checkbox / radio persistence: on-state must be a real PDF name, not Widget.on_state method."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.forms.acroform import (
    apply_field_values_to_doc,
    load_acroform_fields,
    resolve_widget_on_state,
)
from core.forms.fields import FieldType
from engines.bake_edits import bake_via_backend


def _checkbox_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(72, 72, 92, 92)
    w.field_name = "agree"
    page.add_widget(w)
    live = page.first_widget
    live.field_value = "Off"
    live.update()
    doc.save(path)
    doc.close()


def test_resolve_on_state_calls_method_not_attribute():
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(50, 50, 70, 70)
    w.field_name = "cb"
    page.add_widget(w)
    live = page.first_widget
    assert resolve_widget_on_state(live, doc) == "Yes"
    doc.close()


def test_checkbox_survives_save_and_reopen(tmp_path: Path):
    src = tmp_path / "check.pdf"
    _checkbox_pdf(src)

    pdf = open_document(src)
    edit = EditableDocument(pdf)
    assert len(edit.fields) == 1
    fid = next(iter(edit.fields))
    assert edit.fields[fid].checked is False

    edit.set_field_value(fid, checked=True)
    dest = tmp_path / "checked.pdf"
    bake_via_backend(edit, dest, flatten=False)
    pdf.close()

    with fitz.open(dest) as out:
        w = out[0].first_widget
        assert w is not None
        on = resolve_widget_on_state(w, out)
        assert w.field_value == on
        assert str(w.field_value).lower() not in ("off", "")
        xref = int(w.xref)
        kind, as_val = out.xref_get_key(xref, "AS")
        assert kind == "name"
        assert as_val.lstrip("/") == on.lstrip("/")

    # Reopen via EditableDocument — checkmark still editable and on
    pdf2 = open_document(dest)
    edit2 = EditableDocument(pdf2)
    assert next(iter(edit2.fields.values())).checked is True
    pdf2.close()


def test_checkbox_uncheck_writes_off(tmp_path: Path):
    src = tmp_path / "check.pdf"
    _checkbox_pdf(src)

    pdf = open_document(src)
    edit = EditableDocument(pdf)
    fid = next(iter(edit.fields))
    edit.set_field_value(fid, checked=True)
    bake_via_backend(edit, tmp_path / "on.pdf", flatten=False)
    pdf.close()

    pdf2 = open_document(tmp_path / "on.pdf")
    edit2 = EditableDocument(pdf2)
    fid2 = next(iter(edit2.fields))
    assert edit2.fields[fid2].checked is True
    edit2.set_field_value(fid2, checked=False)
    bake_via_backend(edit2, tmp_path / "off.pdf", flatten=False)
    pdf2.close()

    with fitz.open(tmp_path / "off.pdf") as out:
        w = out[0].first_widget
        assert str(w.field_value).lower() in ("off", "")


def test_apply_never_assigns_bound_method(tmp_path: Path):
    """Regression: getattr(w, 'on_state') is a method; assigning it to field_value broke saves."""
    src = tmp_path / "check.pdf"
    _checkbox_pdf(src)
    doc = fitz.open(src)
    fields = load_acroform_fields(doc)
    assert fields
    fields[0].checked = True
    fields[0].value_dirty = True
    apply_field_values_to_doc(doc, fields)
    w = doc[0].first_widget
    assert not callable(w.field_value)
    assert str(w.field_value) == resolve_widget_on_state(w, doc)
    doc.close()


def test_radio_group_mutual_exclusion(tmp_path: Path):
    """Model-level mutual exclusion for radio widgets that share a field name."""
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(src)
    doc.close()

    pdf = open_document(src)
    edit = EditableDocument(pdf)
    from core.forms.fields import FormField
    from core.editing.geometry import Rect

    a = FormField(
        page_index=0, rect=Rect(72, 72, 20, 20), field_type=FieldType.RADIO, name="choice", is_acroform=True
    )
    b = FormField(
        page_index=0, rect=Rect(72, 100, 20, 20), field_type=FieldType.RADIO, name="choice", is_acroform=True
    )
    edit.fields[a.object_id] = a
    edit.fields[b.object_id] = b
    edit.set_field_value(a.object_id, checked=True)
    assert a.checked and not b.checked
    edit.set_field_value(b.object_id, checked=True)
    assert b.checked and not a.checked
    pdf.close()
