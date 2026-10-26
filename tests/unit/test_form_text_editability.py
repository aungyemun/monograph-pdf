"""Ordinary Save must keep AcroForm text fields editable (no silent flatten)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend


def _text_form(path: Path, *, japanese: bool = False) -> None:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 72, 300, 96)
    w.field_name = "fullname"
    w.text_fontsize = 11
    w.field_value = ""
    page.add_widget(w)
    if japanese:
        w2 = fitz.Widget()
        w2.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w2.rect = fitz.Rect(72, 120, 300, 144)
        w2.field_name = "氏名"
        w2.text_fontsize = 11
        page.add_widget(w2)
    doc.save(path)
    doc.close()


def test_text_field_remains_widget_after_save(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _text_form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    fid = next(f.object_id for f in edit.fields.values() if f.name == "fullname")
    edit.set_field_value(fid, "Alice Smith")
    dest = tmp_path / "filled.pdf"
    bake_via_backend(edit, dest, flatten=False)
    pdf.close()

    with fitz.open(dest) as out:
        widgets = list(out[0].widgets() or [])
        assert len(widgets) == 1
        assert widgets[0].field_value == "Alice Smith"
        # Still a widget — not baked into page content only
        assert widgets[0].field_type == fitz.PDF_WIDGET_TYPE_TEXT

    pdf2 = open_document(dest)
    edit2 = EditableDocument(pdf2)
    field = next(iter(edit2.fields.values()))
    assert field.value == "Alice Smith"
    edit2.set_field_value(field.object_id, "Bob Jones")
    bake_via_backend(edit2, tmp_path / "edited.pdf", flatten=False)
    pdf2.close()

    with fitz.open(tmp_path / "edited.pdf") as out:
        assert out[0].first_widget.field_value == "Bob Jones"


def test_japanese_text_field_value_roundtrip(tmp_path: Path):
    src = tmp_path / "jp.pdf"
    _text_form(src, japanese=True)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    by_name = {f.name: f for f in edit.fields.values()}
    edit.set_field_value(by_name["氏名"].object_id, "山田太郎")
    edit.set_field_value(by_name["fullname"].object_id, "Taro Yamada")
    dest = tmp_path / "jp_filled.pdf"
    bake_via_backend(edit, dest, flatten=False)
    pdf.close()

    pdf2 = open_document(dest)
    edit2 = EditableDocument(pdf2)
    values = {f.name: f.value for f in edit2.fields.values()}
    assert values.get("氏名") == "山田太郎"
    assert values.get("fullname") == "Taro Yamada"
    pdf2.close()


def test_ordinary_save_does_not_set_need_appearances_true(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _text_form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    fid = next(iter(edit.fields))
    edit.set_field_value(fid, "Hello")
    dest = tmp_path / "out.pdf"
    bake_via_backend(edit, dest, flatten=False)
    pdf.close()
    with fitz.open(dest) as out:
        if out.is_form_pdf:
            # Getter mutates — read via xref when possible
            cat = out.pdf_catalog()
            kind, acro = out.xref_get_key(cat, "AcroForm")
            if kind == "xref":
                ax = int(str(acro).split()[0])
                na = out.xref_get_key(ax, "NeedAppearances")
                if na[0] != "null":
                    assert str(na[1]).lower() in ("false", "/false")
