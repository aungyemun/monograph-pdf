"""Form fields: mixed Japanese / Latin / full-width entries, bold & italic, case changes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from engines.bake_edits import bake_via_backend

MIXED = "Taro 山田 123-4567 ＡＢＣ１２３ ｶﾀｶﾅ 東京都"


def _form(path: Path, font: str = "Helv") -> Path:
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_name = "name"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 100, 472, 124)
    w.text_font = "Helv"
    w.text_fontsize = 0
    page.add_widget(w)
    doc.save(path)
    doc.close()
    if font != "Helv":  # simulate a Japanese form whose /DA names a CJK font
        doc = fitz.open(path)
        x = next(doc[0].widgets()).xref
        doc.xref_set_key(x, "DA", fitz.get_pdf_str(f"/{font} 0 Tf 0 g"))
        doc.saveIncr()
        doc.close()
    return path


def _fill_and_save(path: Path, value: str, **style) -> fitz.Widget:
    pdf = open_document(path)
    edit = EditableDocument(pdf)
    field = next(iter(edit.fields.values()))
    edit.set_field_value(field.object_id, value)
    for k, v in style.items():
        setattr(field, k, v)
    if style:
        field.style_dirty = True
        field.appearance_dirty = True
    out = path.with_name("out.pdf")
    bake_via_backend(edit, out)
    pdf.close()
    return out


def _ap_fonts(doc: fitz.Document, widget) -> str:
    ap = int(doc.xref_get_key(widget.xref, "AP/N")[1].split()[0])
    return doc.xref_object(ap) + str(doc.xref_get_key(ap, "Resources"))


def test_mixed_japanese_latin_fullwidth_saved_and_searchable(tmp_path):
    out = _fill_and_save(_form(tmp_path / "f.pdf"), MIXED)
    with fitz.open(out) as d:
        w = next(d[0].widgets())
        assert w.field_value == MIXED
        assert MIXED in d[0].get_text().replace("\n", "")  # drawn with the right glyphs, not "······"
        assert "\u00b7" not in d[0].get_text()
        # Embedded CJK subset is small
        assert out.stat().st_size < 200_000


def test_japanese_form_keeps_its_own_font_in_da(tmp_path):
    out = _fill_and_save(_form(tmp_path / "f.pdf", font="KozMinPr6N-Regular"), "山田 Taro 123")
    with fitz.open(out) as d:
        w = next(d[0].widgets())
        assert d.xref_get_key(w.xref, "DA")[1].startswith("/KozMinPr6N-Regular")
        assert "山田 Taro 123" in d[0].get_text()


def test_bold_italic_latin_uses_font_variants(tmp_path):
    out = _fill_and_save(_form(tmp_path / "f.pdf"), "Hello 世界", bold=True, italic=True, font_family="Times New Roman")
    with fitz.open(out) as d:
        fonts = _ap_fonts(d, next(d[0].widgets()))
        text = d[0].get_text("dict")
        names = {s["font"] for b in text["blocks"] for l in b.get("lines", []) for s in l["spans"]}
        # Latin part in a bold-italic serif (MuPDF's built-in Times is Nimbus Roman)
        assert any("BoldItalic" in n and ("Times" in n or "Roman" in n) for n in names), names
        assert "Hello 世界" in d[0].get_text()
        assert "Font" in fonts


def test_plain_latin_values_keep_mupdf_appearance(tmp_path):
    out = _fill_and_save(_form(tmp_path / "f.pdf"), "Plain text 123")
    with fitz.open(out) as d:
        assert "Helv" in _ap_fonts(d, next(d[0].widgets()))


def test_recent_list_drops_test_and_selfcheck_entries(tmp_path, monkeypatch):
    import tempfile

    from core.recent_files import RecentFiles

    real = Path(tempfile.mkdtemp(prefix="recent-user-")) / "keep.pdf"  # outside pytest's temp tree
    real.write_bytes(b"%PDF-1.4")
    store = tmp_path / "recent.json"
    store.write_text(json.dumps([
        str(real),
        "C:\\Users\\a\\AppData\\Local\\Temp\\pdfeditor-smoke-x1\\smoke.pdf",
        "C:\\Users\\a\\AppData\\Local\\Temp\\pytest-of-a\\pytest-3\\t0\\edit_perf.pdf",
    ]))
    rf = RecentFiles(store)
    assert rf.list() == [real]
    assert len(json.loads(store.read_text())) == 1


def test_user_data_dir_override_is_honoured(tmp_path, monkeypatch):
    from core.user_prefs import user_data_dir

    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "ud"))
    assert user_data_dir() == tmp_path / "ud"


def test_opening_office_module_does_not_load_all_converters():
    import subprocess
    import sys

    code = "import sys, core.convert.office_bridge; print('docx' in sys.modules or 'pptx' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


def _three_field_form(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    for name, rect, multi in (
        ("jp", fitz.Rect(72, 100, 472, 124), False),
        ("plain", fitz.Rect(72, 140, 472, 164), False),
        ("notes", fitz.Rect(72, 180, 472, 260), True),
    ):
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = rect
        w.text_fontsize = 0
        if multi:
            w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
        page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


def test_other_fields_keep_values_next_to_a_japanese_field(tmp_path):
    """Writing our own appearance for one field must not empty the other fields on the page."""
    from core.forms.acroform import apply_field_values_to_doc, load_acroform_fields

    doc = fitz.open(_three_field_form(tmp_path / "f.pdf"))
    fields = load_acroform_fields(doc)
    values = {"jp": "Feb 13–14 山田", "plain": "plain text", "notes": "Feb 13-14 hello"}
    for f in fields:
        f.value = values[f.name]
        f.value_dirty = True
    apply_field_values_to_doc(doc, fields)
    saved = fitz.open("pdf", doc.tobytes())
    for w in saved[0].widgets():
        assert saved[0].get_text("text", clip=w.rect).strip() == values[w.field_name]


def test_vertical_middle_and_centre_are_saved_and_reloaded(tmp_path):
    from core.forms.acroform import apply_field_values_to_doc, load_acroform_fields

    doc = fitz.open(_three_field_form(tmp_path / "f.pdf"))
    fields = load_acroform_fields(doc)
    notes = next(f for f in fields if f.name == "notes")
    assert notes.valign == ""  # natural: wrapped text starts at the top
    notes.value, notes.value_dirty = "Feb 13–14", True
    notes.align, notes.valign, notes.font_size, notes.style_dirty = "center", "middle", 13, True
    apply_field_values_to_doc(doc, fields)
    saved = fitz.open("pdf", doc.tobytes())
    w = next(x for x in saved[0].widgets() if x.field_name == "notes")
    x0, y0, x1, y1 = saved[0].get_text("dict", clip=w.rect)["blocks"][0]["bbox"]
    assert abs((x0 + x1) / 2 - (w.rect.x0 + w.rect.x1) / 2) < 3
    assert abs((y0 + y1) / 2 - (w.rect.y0 + w.rect.y1) / 2) < 3
    again = next(f for f in load_acroform_fields(saved) if f.name == "notes")
    assert again.valign == "middle" and again.align == "center"


@pytest.mark.parametrize(
    "value",
    [
        "Depart Yangon via Singapore. Arrive at Kansai International Airport on Feb 14 and travel to "
        "the inviter's residence in Higashiura, Aichi.",
        "シンガポール経由でヤンゴンを出発し、2月14日に関西国際空港に到着後、愛知県東浦町の招へい人宅へ移動します。",
    ],
)
def test_justified_field_lines_reach_both_edges(tmp_path, value):
    """Justify (not in PDF's /Q): wrapped lines fill the width, the last line stays left, the
    choice survives reopening and other readers get /Q 0 (left)."""
    from core.forms.acroform import apply_field_values_to_doc, load_acroform_fields

    doc = fitz.open(_three_field_form(tmp_path / "f.pdf"))
    fields = load_acroform_fields(doc)
    notes = next(f for f in fields if f.name == "notes")
    notes.value, notes.value_dirty = value, True
    notes.align, notes.font_size, notes.style_dirty = "justify", 10, True
    apply_field_values_to_doc(doc, fields)
    saved = fitz.open("pdf", doc.tobytes())
    w = next(x for x in saved[0].widgets() if x.field_name == "notes")
    assert saved.xref_get_key(w.xref, "Q") == ("int", "0")
    lines = [
        ln["bbox"]
        for b in saved[0].get_text("dict", clip=w.rect)["blocks"]
        for ln in b.get("lines", [])
    ]
    lines.sort(key=lambda bb: bb[1])
    assert len(lines) >= 2
    for x0, _y0, x1, _y1 in lines[:-1]:
        assert x0 - w.rect.x0 < 5 and w.rect.x1 - x1 < 5  # full lines touch both edges
    assert w.rect.x1 - lines[-1][2] > 10  # last line is not stretched
    again = next(f for f in load_acroform_fields(saved) if f.name == "notes")
    assert again.align == "justify"



def test_overflowing_multiline_entry_prints_whole_lines_only_and_is_flagged(tmp_path):
    """A fixed-size entry longer than its box: only lines that fit are drawn (no half-cut glyphs
    under the last line), and entry_overflows() reports the hidden text for the on-screen marker."""
    import fitz

    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.forms.appearance import entry_overflows
    from engines.bake_edits import bake_via_backend

    src = tmp_path / "cell.pdf"
    doc = fitz.open()
    page = doc.new_page()
    wdg = fitz.Widget()
    wdg.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    wdg.field_name = "cell"
    wdg.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
    wdg.rect = fitz.Rect(100, 100, 219, 128)  # 119 x 28 pt, like a table cell
    wdg.text_fontsize = 10
    page.add_widget(wdg)
    doc.save(src)
    doc.close()

    pdf = open_document(src)
    edit = EditableDocument(pdf)
    field = next(iter(edit.fields.values()))
    long_text = "ヤンゴン発、シンガポール経由。2月14日関西国際空港着後、東浦町の招へい人宅へ移動。"
    assert not entry_overflows(field, "2月13日")
    assert entry_overflows(field, long_text)
    edit.set_field_value(field.object_id, long_text)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        w = d[0].widgets().__next__()
        assert w.field_value == long_text  # the whole entry is kept in the field
        blocks = [b for b in d[0].get_text("dict")["blocks"] if b.get("type") == 0]
        lines = [ln for b in blocks for ln in b["lines"]]
        assert lines and max(ln["bbox"][3] for ln in lines) <= 128 + 0.5  # nothing drawn below the box
        assert len(lines) == 2
