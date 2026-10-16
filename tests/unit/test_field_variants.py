"""Fillable text fields built in all the common ways: fill, style, save, reopen.

English and Japanese entries, centre / middle / right / bottom, bold and italic, sizes —
for widget-only fields, parent/kid fields, fields shown twice, inherited /DA, missing
appearances, rotated and offset pages, comb, bordered, encrypted and compressed files.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.forms.acroform import load_acroform_fields
from engines.bake_edits import bake_via_backend
from tests.fixtures.make_field_variants import VARIANTS, write_variant

SCENARIOS = {
    "english": {"value": "John Smith, 12 Main St."},
    "english_styled": {"value": "Feb 13–14 Tokyo", "align": "center", "valign": "middle", "bold": True, "italic": True,
                       "font_size": 12},
    "japanese_mixed": {"value": "Feb 13–14 山田 ＡＢ１２"},
    "japanese_styled": {"value": "東京 Feb 13", "align": "right", "valign": "bottom", "bold": True},
}
SHORT = {"tiny", "rotated_widget", "comb"}  # boxes too small for a long entry


def _norm(s: str) -> str:
    return "".join(s.split())


def _fill(path: Path, scenario: str, short: bool) -> tuple[Path, dict]:
    spec = dict(SCENARIOS[scenario])
    value = spec.pop("value")
    if short:
        value = value[:8].strip()
        spec.pop("font_size", None)
    pdf = open_document(path)
    edit = EditableDocument(pdf)
    target = next(f for f in edit.fields.values() if "target" in f.name)
    edit.set_field_value(target.object_id, value)
    for f in [target, *edit.same_field_widgets(target)]:
        for k, v in spec.items():
            setattr(f, k, v)
        if spec:
            f.style_dirty = f.appearance_dirty = True
    out = path.with_name(path.stem + f"_{scenario}_out.pdf")
    bake_via_backend(edit, out)
    pdf.close()
    return out, {"value": value, **spec}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
@pytest.mark.parametrize("variant", list(VARIANTS))
def test_field_variant_saves_entry(tmp_path, variant, scenario):
    mode = "encrypted" if variant in ("basic", "parent_kid", "cjk_da") else "plain"
    src = write_variant(variant, tmp_path, mode)
    out, spec = _fill(src, scenario, variant in SHORT)
    value = spec["value"]
    doc = fitz.open(out)
    if doc.needs_pass:
        assert doc.authenticate("")
    targets = keeps = 0
    for page in doc:
        for w in page.widgets():
            clip = w.rect + (-2, -2, 2, 2)
            shown = _norm(page.get_text("text", clip=clip) if page.rotation == 0 else page.get_text())
            if "target" in w.field_name:
                targets += 1
                assert w.field_value == value  # every copy of the field holds the entry
                want = _norm(value)[:12] if variant == "comb" else _norm(value)
                if variant != "rotated_widget":
                    assert want in shown, (w.field_name, shown)
                if page.rotation == 0 and variant not in SHORT:
                    blocks = [b["bbox"] for b in page.get_text("dict", clip=clip)["blocks"] if b.get("type") == 0]
                    x0, x1 = min(b[0] for b in blocks), max(b[2] for b in blocks)
                    y0, y1 = min(b[1] for b in blocks), max(b[3] for b in blocks)
                    r = w.rect
                    if spec.get("align") == "center":
                        assert abs((x0 + x1) / 2 - (r.x0 + r.x1) / 2) < 3
                    if spec.get("align") == "right":
                        assert r.x1 - x1 < 6
                    if spec.get("valign") == "middle":
                        assert abs((y0 + y1) / 2 - (r.y0 + r.y1) / 2) < 3
                    if spec.get("valign") == "bottom":
                        assert r.y1 - y1 < 6
            if "keep" in w.field_name:
                keeps += 1
                assert w.field_value == "Keep me" and "Keepme" in shown
            if variant == "bordered" and "target" in w.field_name:
                ap = doc.xref_stream(int(doc.xref_get_key(w.xref, "AP/N")[1].split()[0])) or b""
                ap = ap.replace(b"0.800", b".8").replace(b"1.000", b"1").replace(b"0.000", b"0")
                assert b".8 0 0 RG" in ap and b"1 1 .8 rg" in ap  # own border and background kept
    assert targets >= 1 and keeps == 1
    if spec.get("align"):
        for f in load_acroform_fields(doc):
            if "target" in f.name:
                assert f.align == spec["align"] and f.valign == spec["valign"]


@pytest.mark.parametrize("variant", ["basic", "parent_kid", "hierarchical_name", "two_widgets"])
def test_compressed_object_streams(tmp_path, variant):
    src = write_variant(variant, tmp_path, "objstm")
    out, spec = _fill(src, "japanese_styled", False)
    doc = fitz.open(out)
    for page in doc:
        for w in page.widgets():
            if "target" in w.field_name:
                assert w.field_value == spec["value"]
                assert _norm(spec["value"]) in _norm(page.get_text("text", clip=w.rect + (-2, -2, 2, 2)))


def test_long_auto_entry_shrinks_to_fit_like_acrobat(tmp_path):
    src = write_variant("basic", tmp_path)
    doc = fitz.open(src)
    page = doc[0]
    w = next(x for x in page.widgets() if x.field_name == "target")
    w.rect = fitz.Rect(150, 200, 230, 216)  # narrow box
    w.update()
    doc.saveIncr()
    doc.close()
    out, spec = _fill(src, "english", False)
    with fitz.open(out) as d:
        w = next(x for x in d[0].widgets() if x.field_name == "target")
        assert _norm(spec["value"]) in _norm(d[0].get_text("text", clip=w.rect + (-1, -1, 1, 1)))


RICH_RUNS = [
    {"text": "Good ", "family": "Times New Roman", "size": 8},
    {"text": "will", "family": "Arial", "size": 10, "bold": True, "color": "#cc0000"},
    {"text": " 東京", "bold": True, "color": "#0000cc"},
    {"text": " 070-7790"},
]


@pytest.mark.parametrize("variant", [v for v in VARIANTS if v not in SHORT])
def test_mixed_word_formats_in_every_kind_of_field(tmp_path, variant):
    """Words with their own font / size / bold / colour: shown, saved as /RV, reopened."""
    from core.forms.rich_text import RICH_TEXT_FLAG, make_run

    mode = "encrypted" if variant in ("basic", "parent_kid", "cjk_da") else "plain"
    src = write_variant(variant, tmp_path, mode)
    runs = [make_run(r["text"], **{k: v for k, v in r.items() if k != "text"}) for r in RICH_RUNS]
    value = "".join(r["text"] for r in runs)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    target = next(f for f in edit.fields.values() if "target" in f.name)
    assert edit.set_field_rich_text(target.object_id, value, runs)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    doc = fitz.open(out)
    if doc.needs_pass:
        assert doc.authenticate("")
    seen = 0
    for page in doc:
        for w in page.widgets():
            if "target" in w.field_name:
                seen += 1
                assert w.field_value == value
                assert w.field_flags & RICH_TEXT_FLAG
                shown = _norm(page.get_text("text", clip=w.rect + (-2, -2, 2, 2)) if page.rotation == 0 else page.get_text())
                assert _norm(value) in shown
            if "keep" in w.field_name:
                assert w.field_value == "Keep me"
    assert seen >= 1
    for f in load_acroform_fields(doc):
        if "target" in f.name:
            got = [(r["text"], r["family"], r["size"], r["bold"], r["color"]) for r in f.runs]
            assert got[0] == ("Good ", "Times New Roman", 8.0, None, None)
            assert got[1] == ("will", "Arial", 10.0, True, "#cc0000")
            assert got[2][0] == " 東京" and got[2][3] is True and got[2][4] == "#0000cc"


def test_plain_entry_drops_old_word_formats(tmp_path):
    """Replacing a formatted entry with plain text removes /RV and the RichText flag."""
    from core.forms.rich_text import RICH_TEXT_FLAG, make_run

    src = write_variant("basic", tmp_path)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    t = next(f for f in edit.fields.values() if f.name == "target")
    edit.set_field_rich_text(t.object_id, "Good will", [make_run("Good", size=8), make_run(" will")])
    first = tmp_path / "one.pdf"
    bake_via_backend(edit, first)
    pdf.close()
    pdf = open_document(first)
    edit = EditableDocument(pdf)
    t = next(f for f in edit.fields.values() if f.name == "target")
    assert t.runs
    edit.set_field_rich_text(t.object_id, "plain now", [])
    second = tmp_path / "two.pdf"
    bake_via_backend(edit, second)
    pdf.close()
    with fitz.open(second) as d:
        w = next(x for x in d[0].widgets() if x.field_name == "target")
        assert w.field_value == "plain now"
        assert not (w.field_flags & RICH_TEXT_FLAG)
        assert d.xref_get_key(w.xref, "RV")[0] == "null"

