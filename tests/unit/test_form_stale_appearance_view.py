"""On-screen view of a PDF form field being changed: its saved (old) appearance is left out of the
page picture, so the old and the new value are never shown on top of each other — and the document
itself is not changed by that."""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

from core.document import open_document
from core.forms.display import stale_appearance_widgets
from core.forms.fields import FieldType, FormField
from core.editing.geometry import Rect


def _form(path: Path, *, flags: int | None = None) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 115), "Label", fontsize=10)  # page content next to the field
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.rect = fitz.Rect(100, 100, 400, 122)
    w.text_fontsize = 12
    w.field_value = "WWWWWWWWWWWWWWWWWWWW"  # old value across the whole box
    page.add_widget(w)
    other = fitz.Widget()
    other.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    other.field_name = "other"
    other.rect = fitz.Rect(100, 200, 400, 222)
    other.field_value = "Other field"
    page.add_widget(other)
    if flags is not None:
        doc.xref_set_key(page.first_widget.xref, "F", str(flags))
    doc.save(path)
    doc.close()
    return path


def _objects(doc: fitz.Document) -> str:
    m = hashlib.sha256()
    for x in range(1, doc.xref_length()):
        m.update(doc.xref_object(x, compressed=True).encode("latin-1", "replace"))
        if doc.xref_is_stream(x):
            m.update(doc.xref_stream_raw(x) or b"")
    return m.hexdigest()


def _dark(samples: bytes) -> int:
    return sum(1 for i in range(0, len(samples), 3) if samples[i] < 128)


def _xref(pdf, name: str) -> int:
    page = pdf._backend._doc[0]  # noqa: SLF001
    return next(w.xref for w in page.widgets() if w.field_name == name)


def test_hidden_widget_left_out_of_the_picture_only(tmp_path):
    pdf = open_document(_form(tmp_path / "f.pdf"))
    try:
        doc = pdf._backend._doc  # noqa: SLF001
        xref = _xref(pdf, "name")
        before = _objects(doc)
        field_clip = (100, 100, 400, 122)
        label_clip = (35, 100, 99, 122)
        other_clip = (100, 200, 400, 222)
        normal = pdf.render_rgb(0, scale=2, clip=field_clip)[0]
        hidden = pdf.render_rgb(0, scale=2, clip=field_clip, hidden_widgets=(xref,))[0]
        assert _dark(normal) > 200  # the old value is drawn normally
        assert _dark(hidden) == 0  # ... and not at all while the field is being changed
        # page content and other fields are still drawn
        assert pdf.render_rgb(0, scale=2, clip=label_clip, hidden_widgets=(xref,))[0] == pdf.render_rgb(0, scale=2, clip=label_clip)[0]
        assert pdf.render_rgb(0, scale=2, clip=other_clip, hidden_widgets=(xref,))[0] == pdf.render_rgb(0, scale=2, clip=other_clip)[0]
        # the document is exactly as before (the flag was only set for the rendering)
        assert _objects(doc) == before
        assert doc.xref_get_key(xref, "F") == ("int", "4")
        assert pdf.render_rgb(0, scale=2, clip=field_clip)[0] == normal
    finally:
        pdf.close()


def test_flags_restored_exactly_and_foreign_xrefs_ignored(tmp_path):
    # no /F at all, and an already hidden widget
    for flags in (None, 2 | 4):
        path = _form(tmp_path / f"f{flags}.pdf", flags=flags)
        if flags is None:
            with fitz.open(path) as d:
                d.xref_set_key(d[0].first_widget.xref, "F", "null")
                d.save(path.with_name("noflag.pdf"))
            path = path.with_name("noflag.pdf")
        pdf = open_document(path)
        try:
            doc = pdf._backend._doc  # noqa: SLF001
            xref = _xref(pdf, "name")
            f_before = doc.xref_get_key(xref, "F")
            before = _objects(doc)
            catalog = doc.pdf_catalog()
            pdf.render_rgb(0, scale=1, hidden_widgets=(xref, catalog, 99999))
            assert doc.xref_get_key(xref, "F") == f_before
            assert _objects(doc) == before
        finally:
            pdf.close()


def _field(**kw) -> FormField:
    f = FormField(page_index=0, rect=Rect(0, 0, 10, 10), field_type=kw.pop("field_type", FieldType.TEXT))
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def test_only_changed_existing_text_fields_are_left_out():
    fields = [
        _field(object_id="a", xref=11, is_acroform=True, value_dirty=True),  # changed text: yes
        _field(object_id="b", xref=12, is_acroform=True),  # unchanged: no
        _field(object_id="c", xref=13, is_acroform=True, appearance_dirty=True, field_type=FieldType.MULTILINE),
        _field(object_id="d", xref=14, is_acroform=True, value_dirty=True, field_type=FieldType.CHECKBOX),
        _field(object_id="e", xref=0, is_acroform=False, value_dirty=True),  # placed by the user: no widget
        _field(object_id="f", xref=16, is_acroform=True, value_dirty=True, is_candidate=True),
        _field(object_id="g", xref=17, is_acroform=True, value_dirty=True, field_type=FieldType.DROPDOWN),
    ]
    assert stale_appearance_widgets(fields) == (11, 13, 17)
    assert stale_appearance_widgets([]) == ()


def _checkbox_form(path: Path, checked: bool) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.field_name = "agree"
    w.rect = fitz.Rect(100, 100, 130, 130)
    w.field_value = checked
    page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


def test_checkbox_shown_in_its_new_state_with_its_own_appearance(tmp_path):
    """A changed checkbox is drawn with the form's own on / off appearance, exactly as it will look
    after Save — the document itself is unchanged by that."""
    on_pdf = open_document(_checkbox_form(tmp_path / "on.pdf", True))
    off_pdf = open_document(_checkbox_form(tmp_path / "off.pdf", False))
    try:
        clip = (95, 95, 135, 135)
        saved_on = on_pdf.render_rgb(0, scale=3, clip=clip)[0]
        saved_off = off_pdf.render_rgb(0, scale=3, clip=clip)[0]
        assert saved_on != saved_off
        doc = on_pdf._backend._doc  # noqa: SLF001
        xref = doc[0].first_widget.xref
        assert on_pdf.button_state_previewable(xref)
        before = _objects(doc)
        as_before = doc.xref_get_key(xref, "AS")
        # unchecked in the window, not saved yet: looks like a saved unchecked box
        assert on_pdf.render_rgb(0, scale=3, clip=clip, widget_states={xref: False})[0] == saved_off
        assert on_pdf.render_rgb(0, scale=3, clip=clip, widget_states={xref: True})[0] == saved_on
        assert doc.xref_get_key(xref, "AS") == as_before
        assert _objects(doc) == before
        # xrefs that are not widgets of the page are ignored
        on_pdf.render_rgb(0, scale=1, widget_states={doc.pdf_catalog(): False, 99999: True})
        assert _objects(doc) == before
    finally:
        on_pdf.close()
        off_pdf.close()


def test_only_changed_existing_buttons_get_a_pending_state():
    from core.forms.display import pending_button_states

    fields = [
        _field(xref=21, is_acroform=True, value_dirty=True, field_type=FieldType.CHECKBOX, checked=True),
        _field(xref=22, is_acroform=True, value_dirty=True, field_type=FieldType.RADIO, checked=False),
        _field(xref=23, is_acroform=True, field_type=FieldType.CHECKBOX, checked=True),  # unchanged
        _field(xref=0, is_acroform=False, value_dirty=True, field_type=FieldType.CHECKBOX),  # user-placed
        _field(xref=25, is_acroform=True, value_dirty=True, field_type=FieldType.TEXT),
    ]
    assert pending_button_states(fields) == {21: True, 22: False}