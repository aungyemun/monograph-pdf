"""Regression: form field names / XFA SOM paths must never paint as page content."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument, WorkspaceMode
from core.editing.font_inventory import normalize_family_name, strip_subset_prefix
from core.editing.font_resolver import resolve_font, resolve_font_for_text, text_needs_cjk
from core.editing.geometry import Rect
from core.forms.capabilities import XfaKind, inspect_pdf_capabilities
from core.forms.display import (
    looks_like_internal_field_id,
    sanitize_field_value,
    should_paint_field_overlay,
    visible_field_content,
)
from core.forms.fields import FieldType, FormField
from engines.bake_edits import bake_via_backend

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
OUT_LOGS = Path(__file__).resolve().parents[1] / "outputs" / "logs"
OUT_SHOTS = Path(__file__).resolve().parents[1] / "outputs" / "screenshots"
OUT_GEN = Path(__file__).resolve().parents[1] / "outputs" / "generated"


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_form_samples import main
    from tests.fixtures.make_samples import main as base

    base()
    main()
    OUT_LOGS.mkdir(parents=True, exist_ok=True)
    OUT_SHOTS.mkdir(parents=True, exist_ok=True)
    OUT_GEN.mkdir(parents=True, exist_ok=True)


def test_internal_som_names_detected():
    assert looks_like_internal_field_id("topmostSubform[0].Page1[0].shimei[0]")
    assert looks_like_internal_field_id("topmostSubform[0].Pag...")
    assert not looks_like_internal_field_id("山田太郎")
    assert not looks_like_internal_field_id("A-1001")


def test_sanitize_never_keeps_name_as_value():
    som = "topmostSubform[0].Page1[0].field[0]"
    assert sanitize_field_value(som, som) == ""
    assert sanitize_field_value(som, "") == ""
    assert sanitize_field_value("name", "Alice") == "Alice"


def test_visible_content_empty_for_unnamed_empty_acroform():
    som = "topmostSubform[0].Page1[0].shimei[0]"
    field = FormField(
        page_index=0,
        rect=Rect(0, 0, 100, 20),
        field_type=FieldType.TEXT,
        name=som,
        value="",
        is_acroform=True,
    )
    assert visible_field_content(field) == ""
    assert "topmostSubform" not in visible_field_content(field)
    assert should_paint_field_overlay(field, forms_mode=False) == "none"
    assert should_paint_field_overlay(field, forms_mode=True) == "chrome"
    assert (
        should_paint_field_overlay(field, forms_mode=False, highlight_fillable=True)
        == "highlight"
    )


def test_dirty_value_may_paint_but_never_name():
    som = "topmostSubform[0].Page1[0].shimei[0]"
    field = FormField(
        page_index=0,
        rect=Rect(0, 0, 100, 20),
        field_type=FieldType.TEXT,
        name=som,
        value="佐藤",
        is_acroform=True,
        value_dirty=True,
    )
    assert visible_field_content(field) == "佐藤"
    assert should_paint_field_overlay(field, forms_mode=False) == "content"


def test_hybrid_fixture_capabilities_and_no_name_leak():
    path = SAMPLES / "sample_hybrid_xfa_itinerary.pdf"
    assert path.is_file()
    doc = fitz.open(path)
    try:
        caps = inspect_pdf_capabilities(doc, path=path)
        report = OUT_LOGS / "form_caps_sample_hybrid_xfa_itinerary.json"
        report.write_text(json.dumps(caps.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        assert caps.acroform
        assert caps.widget_count >= 4
        assert caps.som_like_name_count >= 1
        # Fixture promotes AcroForm + attaches stub /XFA → hybrid
        assert caps.xfa == XfaKind.HYBRID
        assert caps.interactive_editing.value == "partial"

        pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        shot = OUT_SHOTS / "sample_hybrid_xfa_itinerary_page0.png"
        pix.save(shot.as_posix())
        assert shot.is_file() and shot.stat().st_size > 1000

        # Native page text must not include SOM paths as content operators
        text = doc.load_page(0).get_text("text")
        # Labels are Japanese; SOM names live in widgets, not page content stream
        assert "topmostSubform" not in text
    finally:
        doc.close()

    pdf = open_document(path)
    try:
        edit = EditableDocument(pdf)
        assert edit.mode != WorkspaceMode.FORMS
        for f in edit.fields.values():
            if f.is_acroform and not f.value_dirty:
                assert should_paint_field_overlay(f, forms_mode=False) == "none"
                vis = visible_field_content(f)
                assert "topmostSubform" not in vis
                assert f.name not in vis or vis == ""
    finally:
        pdf.close()


def test_populated_value_preserved_without_name_fallback():
    path = SAMPLES / "sample_hybrid_xfa_itinerary.pdf"
    pdf = open_document(path)
    try:
        edit = EditableDocument(pdf)
        filled = [f for f in edit.fields.values() if f.value == "A-1001"]
        assert filled
        # Unmodified AcroForm: value kept in model, but canvas trusts /AP (no overlay)
        assert should_paint_field_overlay(filled[0], forms_mode=False) == "none"
        assert "topmostSubform" not in visible_field_content(filled[0])
        # After user edit, overlay may show the new value
        edit.set_field_value(filled[0].object_id, "A-1002")
        assert filled[0].value_dirty
        assert should_paint_field_overlay(filled[0], forms_mode=False) == "content"
        assert visible_field_content(filled[0]) == "A-1002"
    finally:
        pdf.close()


def test_invitation_empty_fields_overlay_none():
    pdf = open_document(SAMPLES / "sample_invitation_form.pdf")
    try:
        edit = EditableDocument(pdf)
        empties = [f for f in edit.fields.values() if f.is_acroform and not f.value and f.field_type == FieldType.TEXT]
        assert empties
        for f in empties:
            assert should_paint_field_overlay(f, forms_mode=False) == "none"
            assert visible_field_content(f) == ""
    finally:
        pdf.close()


def test_save_as_no_modify_preserves_bytes_visually(tmp_path: Path):
    src = tmp_path / "hybrid_src.pdf"
    out = tmp_path / "hybrid_out.pdf"
    original = (SAMPLES / "sample_hybrid_xfa_itinerary.pdf").read_bytes()
    src.write_bytes(original)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    # No edits
    assert not edit.dirty
    bake_via_backend(edit, out)
    pdf.close()
    assert src.read_bytes() == original
    assert out.is_file() and out.stat().st_size > 500
    # Reopen — still no name leak policy
    reopened = open_document(out)
    try:
        edit2 = EditableDocument(reopened)
        for f in edit2.fields.values():
            assert "topmostSubform" not in visible_field_content(f)
    finally:
        reopened.close()


def test_subset_prefix_and_jp_resolver():
    assert strip_subset_prefix("ABCDEE+MS-Mincho") == "MS-Mincho"
    assert normalize_family_name("ABCDEE+MS-Mincho") == "MS Mincho"
    assert text_needs_cjk("Hello 日本語")
    res = resolve_font("ABCDEE+MS-Mincho", "漢字")
    assert res.requested == "ABCDEE+MS-Mincho"
    # Resolved should prefer a real face when available; always a non-empty string
    assert res.resolved
    mixed = resolve_font_for_text("sans-serif", "English + 日本語 + 2026")
    assert mixed.resolved


def test_bake_textbox_does_not_strip_unmodified_acroform(tmp_path: Path):
    """Regression: adding a text box must not destroy AcroForm/XFA on the live doc or output."""
    src = tmp_path / "hybrid.pdf"
    src.write_bytes((SAMPLES / "sample_hybrid_xfa_itinerary.pdf").read_bytes())
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    before_n = len([f for f in edit.fields.values() if f.is_acroform])
    assert before_n >= 4
    # First Save As (no overlays) then edit — mirrors real workflow
    bake_via_backend(edit, tmp_path / "noedit.pdf")
    edit.create_text_box(0, Rect(40, 40, 160, 28), text="overlay-only")
    out = tmp_path / "baked.pdf"
    bake_via_backend(edit, out)
    # Live document must still expose widgets after bake
    live_caps = inspect_pdf_capabilities(pdf._backend._doc, path=src)  # noqa: SLF001
    assert live_caps.widget_count >= before_n
    pdf.close()
    reopened = open_document(out)
    try:
        caps = inspect_pdf_capabilities(reopened._backend._doc, path=out)  # noqa: SLF001
        assert caps.widget_count >= before_n
        assert caps.xfa == XfaKind.HYBRID
    finally:
        reopened.close()


def test_checkbox_state_names_not_used_as_text():
    field = FormField(
        page_index=0,
        rect=Rect(0, 0, 14, 14),
        field_type=FieldType.CHECKBOX,
        name="topmostSubform[0].Page1[0].doi[0]",
        value="",
        checked=False,
        is_acroform=True,
    )
    assert should_paint_field_overlay(field, forms_mode=False) == "none"
    field.value_dirty = True
    assert visible_field_content(field) in ("☐", "☑")
    assert "Yes" not in visible_field_content(field)
    assert "Off" not in visible_field_content(field)
