"""Undo / Redo of form-field values (text typed into a field, checkboxes, radio groups, Clear).

Before 0.5.1 a field change was not on the document's undo stack: Ctrl+Z only worked while the
field editor was still open, so a wrong entry or click could not be taken back once committed.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend


def _form(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()

    def text(name, rect, value=""):
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = name
        w.rect = fitz.Rect(rect)
        if value:
            w.field_value = value
        page.add_widget(w)

    text("name", (100, 100, 400, 120), "Saved Name")
    text("other", (100, 140, 400, 160), "Other")
    cb = fitz.Widget()
    cb.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    cb.field_name = "agree"
    cb.rect = fitz.Rect(100, 200, 116, 216)
    cb.field_value = True
    page.add_widget(cb)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def edit(tmp_path):
    pdf = open_document(_form(tmp_path / "f.pdf"))
    model = EditableDocument(pdf)
    yield model
    pdf.close()


def _by_name(edit, name):
    return next(f for f in edit.fields.values() if f.name == name)


def test_text_change_can_be_undone_and_redone(edit):
    f = _by_name(edit, "name")
    edit.set_field_value(f.object_id, "Typo Nmae")
    assert edit.commands.can_undo_now
    assert edit.undo()
    f = _by_name(edit, "name")
    assert f.value == "Saved Name"
    assert not f.value_dirty  # back to the saved appearance, nothing to rewrite on Save
    assert edit.redo()
    assert _by_name(edit, "name").value == "Typo Nmae"


def test_checkbox_click_can_be_undone(edit):
    f = _by_name(edit, "agree")
    assert f.checked
    edit.set_field_value(f.object_id, checked=False)
    assert not _by_name(edit, "agree").checked
    assert edit.undo()
    assert _by_name(edit, "agree").checked and not _by_name(edit, "agree").value_dirty


def test_typing_session_is_one_undo_step(edit):
    f = _by_name(edit, "name")
    assert edit.begin_field_edit(f.object_id)
    for text in ("S", "Sa", "Sav", "Saved X"):  # live typing (direct fill)
        edit.set_field_value(f.object_id, text)
    assert not edit.commands.can_undo_now  # nothing recorded while typing
    edit.commit_field_edit(f.object_id)
    assert _by_name(edit, "name").value == "Saved X"
    assert edit.undo()
    assert _by_name(edit, "name").value == "Saved Name"
    assert not edit.commands.can_undo_now  # exactly one step


def test_editor_commit_without_change_records_nothing(edit):
    f = _by_name(edit, "name")
    assert edit.begin_field_edit(f.object_id)
    edit.commit_field_edit(f.object_id)
    assert not edit.commands.can_undo_now


def test_successive_changes_of_one_entry_merge(edit):
    """The inspector writes the value on every keystroke: one Undo step for the whole entry."""
    f = _by_name(edit, "name")
    for text in ("A", "Ab", "Abc"):
        edit.set_field_value(f.object_id, text)
    assert edit.undo()
    assert _by_name(edit, "name").value == "Saved Name"
    assert not edit.commands.can_undo_now


def test_rich_text_commit_and_clear_are_undoable(edit):
    f = _by_name(edit, "name")
    edit.set_field_rich_text(f.object_id, "Rich", [])
    edit.set_field_value(_by_name(edit, "other").object_id, "")  # Clear Field
    assert edit.undo()
    assert _by_name(edit, "other").value == "Other"
    assert edit.undo()
    assert _by_name(edit, "name").value == "Saved Name"


def test_undone_change_is_not_saved(edit, tmp_path):
    f = _by_name(edit, "name")
    edit.set_field_value(f.object_id, "Wrong")
    edit.set_field_value(_by_name(edit, "agree").object_id, checked=False)
    edit.undo()
    edit.undo()
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out, flatten=False)
    with fitz.open(out) as doc:
        values = {w.field_name: w.field_value for w in doc[0].widgets()}
    assert values["name"] == "Saved Name"
    assert values["agree"] not in ("Off", "", False)


def test_radio_group_change_is_one_step(tmp_path):
    """Choosing another radio button unchecks the group's other buttons; Undo restores the group."""
    from core.forms.fields import FieldType

    pdf = open_document(_form(tmp_path / "r.pdf"))
    try:
        edit = EditableDocument(pdf)
        # model-level radio group (two widgets sharing a name)
        a = _by_name(edit, "agree")
        b = _by_name(edit, "other")
        for f in (a, b):
            f.field_type = FieldType.RADIO
            f.name = "grp"
        a.checked, b.checked = True, False
        edit.set_field_value(b.object_id, checked=True)
        assert b.checked and not a.checked
        assert edit.undo()
        fa = edit.fields[a.object_id]
        fb = edit.fields[b.object_id]
        assert fa.checked and not fb.checked
        assert not edit.commands.can_undo_now
    finally:
        pdf.close()
