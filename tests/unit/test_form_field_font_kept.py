"""A text field keeps the font its form defines when it is filled and saved.

Regression (0.5.0 validation): a field whose /DA names a font from the form's own resources
(``/TimesNewRoman`` in ``/AcroForm /DR``) got ``/Helv`` on every Save, so readers that redraw fields
(Acrobat, Edge) showed the entry in Helvetica. Japanese fonts were already kept.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend


def _form(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    for i, name in enumerate(("Year", "Name")):
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = name
        w.rect = fitz.Rect(72, 72 + 40 * i, 300, 96 + 40 * i)
        w.text_font = "TiRo"
        w.text_fontsize = 0  # auto size, as in the real form
        page.add_widget(w)
    cat = doc.pdf_catalog()
    times = doc.get_new_xref()
    doc.update_object(times, "<</Type/Font/Subtype/Type1/BaseFont/Times-Roman/Encoding/WinAnsiEncoding>>")
    helv = doc.get_new_xref()
    doc.update_object(helv, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>")
    doc.xref_set_key(cat, "AcroForm/DR", f"<</Font<</Helv {helv} 0 R/TimesNewRoman {times} 0 R>>>>")
    assert doc.xref_get_key(cat, "AcroForm/DR/Font")[0] in ("dict", "xref")
    for w in page.widgets():
        doc.xref_set_key(w.xref, "DA", fitz.get_pdf_str("/TimesNewRoman 0 Tf 0 g"))
    doc.save(path)
    doc.close()


def _da(path: Path) -> dict[str, str]:
    with fitz.open(path) as d:
        return {w.field_name: d.xref_get_key(w.xref, "DA")[1] for w in d[0].widgets()}


def test_form_font_kept_after_fill_and_save(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    assert all("/TimesNewRoman" in v for v in _da(src).values())
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    year = next(f for f in edit.fields.values() if f.name == "Year")
    edit.set_field_value(year.object_id, "2026")
    out = tmp_path / "saved.pdf"
    bake_via_backend(edit, out, flatten=False)
    pdf.close()
    da = _da(out)
    assert "/TimesNewRoman" in da["Year"], da
    assert " 0 Tf" in da["Year"], da  # auto size stays auto size
    assert "/TimesNewRoman" in da["Name"], da  # untouched field untouched
    with fitz.open(out) as d:
        assert next(w for w in d[0].widgets() if w.field_name == "Year").field_value == "2026"


def test_font_chosen_in_monograph_pdf_is_not_overridden(tmp_path: Path):
    src = tmp_path / "form.pdf"
    _form(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    year = next(f for f in edit.fields.values() if f.name == "Year")
    year.font_family = "Courier New"
    year.style_dirty = True
    edit.set_field_value(year.object_id, "2026")
    out = tmp_path / "saved.pdf"
    bake_via_backend(edit, out, flatten=False)
    pdf.close()
    assert "/TimesNewRoman" not in _da(out)["Year"]
