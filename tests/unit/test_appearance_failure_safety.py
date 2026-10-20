"""A failure while drawing a form-field appearance must never change the document's pages.

``write_text_appearance`` draws on a temporary page appended to the user's document. The save
path catches its exceptions and keeps saving, so a failure after the page was appended used to
leave an extra page in the written PDF.
"""

from __future__ import annotations

from pathlib import Path

import fitz

import core.forms.appearance as appearance
from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend

MIXED = "Taro 山田 123 東京都"  # needs the custom appearance (CJK + Latin)


def _form(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_name = "name"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 100, 472, 124)
    w.text_font = "Helv"
    w.text_fontsize = 0
    page.add_widget(w)
    page.insert_text((72, 200), "Unrelated page text", fontsize=12)
    doc.save(path)
    doc.close()
    return path


class _Exploding(dict):
    def get(self, *_a, **_k):  # called after the temporary page has been appended
        raise RuntimeError("simulated failure while writing the appearance")


def test_failed_custom_appearance_leaves_no_extra_page(tmp_path, monkeypatch):
    src = _form(tmp_path / "form.pdf")
    monkeypatch.setattr(appearance, "_ROTATION_MATRIX", _Exploding())
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    field = next(iter(edit.fields.values()))
    edit.set_field_value(field.object_id, MIXED)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        assert d.page_count == 1
        assert "Unrelated page text" in d[0].get_text()
        assert next(d[0].widgets()).field_value == MIXED


def test_successful_custom_appearance_keeps_page_count(tmp_path):
    src = _form(tmp_path / "form.pdf")
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    field = next(iter(edit.fields.values()))
    edit.set_field_value(field.object_id, MIXED)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        assert d.page_count == 1
        assert MIXED in d[0].get_text().replace("\n", "")
