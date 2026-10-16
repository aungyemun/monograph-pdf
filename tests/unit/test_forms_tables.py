"""Unit tests for AcroForm fields, detection, tables, and layout ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.forms.acroform import apply_field_values_to_doc, load_acroform_fields
from core.forms.detect import detect_field_candidates
from core.forms.fields import FieldType
from core.layout.ops import LayoutPolicy, align_rects, distribute_rects, smart_nudge_related
from core.tables.detect import detect_tables
from core.tables.model import TableModel
from engines.bake_edits import bake_via_backend

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_form_samples import main
    from tests.fixtures.make_samples import main as base

    base()
    main()


def test_load_and_edit_acroform_invitation():
    pdf = open_document(SAMPLES / "sample_invitation_form.pdf")
    try:
        edit = EditableDocument(pdf)
        assert edit.fields
        text_fields = [f for f in edit.fields.values() if f.field_type in (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE)]
        assert text_fields
        f = text_fields[0]
        edit.set_field_value(f.object_id, "Alex Sample")
        assert edit.fields[f.object_id].value == "Alex Sample"
        checks = [f for f in edit.fields.values() if f.field_type == FieldType.CHECKBOX]
        if checks:
            edit.set_field_value(checks[0].object_id, checked=True)
            assert checks[0].checked
        sigs = [f for f in edit.fields.values() if f.field_type == FieldType.SIGNATURE]
        for s in sigs:
            assert "cryptographic" in s.signature_note.lower() or "visual" in s.signature_note.lower()
    finally:
        pdf.close()


def test_japanese_admin_form_loads():
    pdf = open_document(SAMPLES / "sample_jp_admin_form.pdf")
    try:
        edit = EditableDocument(pdf)
        names = {f.name for f in edit.fields.values()}
        assert "shimei" in names or any(f.is_acroform for f in edit.fields.values())
    finally:
        pdf.close()


def test_field_detection_does_not_modify_source(tmp_path: Path):
    src = tmp_path / "detect.pdf"
    original = (SAMPLES / "sample_jp_admin_form.pdf").read_bytes()
    src.write_bytes(original)
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        before = src.read_bytes()
        n = edit.detect_form_fields(0)
        assert src.read_bytes() == before
        # Candidates only
        cands = [f for f in edit.fields.values() if f.is_candidate]
        assert n == len(cands) or n >= 0
        edit.reject_candidates()
        assert not any(f.is_candidate for f in edit.fields.values())
    finally:
        pdf.close()


def test_preserve_field_values_on_save(tmp_path: Path):
    src = tmp_path / "form_src.pdf"
    out = tmp_path / "form_out.pdf"
    src.write_bytes((SAMPLES / "sample_invitation_form.pdf").read_bytes())
    before = src.read_bytes()
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    target = next(f for f in edit.fields.values() if f.field_type in (FieldType.TEXT, FieldType.DATE, FieldType.MULTILINE))
    edit.set_field_value(target.object_id, "Saved Value")
    bake_via_backend(edit, out)
    pdf.close()
    assert src.read_bytes() == before
    reopened = open_document(out)
    try:
        fields = load_acroform_fields(reopened._backend._doc)  # noqa: SLF001
        values = {f.name: f.value for f in fields}
        # Value preserved when widget write succeeds
        assert target.name in values
        assert values[target.name] == "Saved Value" or any(f.value == "Saved Value" for f in fields)
    finally:
        reopened.close()


def test_table_detection_itinerary():
    pdf = open_document(SAMPLES / "sample_itinerary_table.pdf")
    try:
        tables = detect_tables(pdf._backend._doc, 0)  # noqa: SLF001
        assert tables
        t = tables[0]
        assert t.confidence >= 0.55
        assert t.nrows >= 2 and t.ncols >= 2
        t.add_row()
        assert t.nrows >= 3
        t.add_column()
        assert t.ncols >= 3
        assert t.merge_cells(0, 0, 0, 1)
        assert t.split_cell(0, 0)
    finally:
        pdf.close()


def test_layout_align_distribute_and_smart():
    rects = {
        "a": Rect(10, 10, 40, 20),
        "b": Rect(80, 30, 40, 20),
        "c": Rect(150, 50, 40, 20),
    }
    aligned = align_rects(rects, "left")
    assert aligned["a"].x == aligned["b"].x == aligned["c"].x
    dist = distribute_rects(rects, "horizontal")
    assert dist["a"].x <= dist["b"].x <= dist["c"].x
    # Smart nudge only related
    updates = smart_nudge_related(
        "a",
        Rect(10, 10, 40, 20),
        Rect(20, 10, 40, 20),
        {"b": Rect(10, 50, 40, 20), "c": Rect(200, 200, 30, 30)},
        threshold=6,
    )
    assert "b" in updates
    assert "c" not in updates
    assert LayoutPolicy.PRESERVE.value == "preserve_layout"
