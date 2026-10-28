"""A multi-line field with Auto font size shows all of a long entry in the saved PDF.

Regression (0.5.0 validation, also in earlier versions): for plain text MuPDF's own appearance was
used, which keeps the size from the field height and cuts the last lines off at the bottom. Acrobat
shrinks the text until it fits; Monograph PDF's appearance writer does the same.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend

LONG = "This is a deliberately long entry to see whether the saved field shows all of it 0123456789"


def _form(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "plan"
    w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
    w.rect = fitz.Rect(72, 72, 300, 104)  # two lines' height at the usual auto size
    w.text_fontsize = 0
    page.add_widget(w)
    doc.save(path)
    doc.close()


def _shown_words(path: Path) -> tuple[str, list[str]]:
    with fitz.open(path) as d:
        rect = d[0].first_widget.rect
        mem = fitz.open("pdf", d.tobytes())
    mem.bake()
    words = mem[0].get_text("words", clip=rect + (-1, -1, 1, 1))
    mem.close()
    inside = [w[4] for w in words if rect.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))]
    outside = [w[4] for w in words if w[0] < rect.x0 - 1 or w[2] > rect.x1 + 1 or w[3] > rect.y1 + 2]
    return " ".join(inside), outside


def test_long_entry_in_auto_size_multiline_field_is_complete(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    field = next(iter(edit.fields.values()))
    edit.set_field_value(field.object_id, LONG)
    out = tmp_path / "saved.pdf"
    bake_via_backend(edit, out, flatten=False)
    pdf.close()
    shown, outside = _shown_words(out)
    assert "".join(shown.split()) == "".join(LONG.split()), shown
    assert not outside, outside
    with fitz.open(out) as d:
        w = d[0].first_widget
        assert w.field_value == LONG
        assert " 0 Tf" in d.xref_get_key(w.xref, "DA")[1]  # the field stays Auto in the PDF


def test_short_entry_keeps_a_normal_size(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    edit.set_field_value(next(iter(edit.fields.values())).object_id, "Short")
    out = tmp_path / "saved.pdf"
    bake_via_backend(edit, out, flatten=False)
    pdf.close()
    with fitz.open(out) as d:
        mem = fitz.open("pdf", d.tobytes())
    mem.bake()
    sizes = [s["size"] for b in mem[0].get_text("dict")["blocks"] for line in b.get("lines", [])
             for s in line["spans"] if s["text"].strip() == "Short"]
    mem.close()
    assert sizes and 8.0 <= sizes[0] <= 12.5, sizes
