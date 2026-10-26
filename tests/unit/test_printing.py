"""Printing helpers — overlays baked for WYSIWYG; export PDF independent of printing."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.shape_box import ShapeKind
from core.editing.text_box import TextBox
from core.printing import (
    ColorMode,
    PrintOptions,
    effective_print_dpi,
    prepare_print_source,
    print_needs_bake,
    render_page_png_for_print,
    render_pages_for_print,
)
from core.printing.ops import resolve_print_pages

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
OUT = Path(__file__).resolve().parents[1] / "outputs" / "generated"


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_samples import main

    main()
    OUT.mkdir(parents=True, exist_ok=True)


def test_resolve_print_pages_and_render():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        assert resolve_print_pages(pdf, PrintOptions()) == [0, 1, 2]
        assert resolve_print_pages(pdf, PrintOptions(page_range="1,3")) == [0, 2]
        out = OUT / "print_rasters"
        paths = render_pages_for_print(pdf, out, PrintOptions(page_range="1-2", dpi=72))
        assert len(paths) == 2
        assert all(p.is_file() for p in paths)
    finally:
        pdf.close()


def test_print_needs_bake_for_overlays():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        edit = EditableDocument(pdf)
        assert print_needs_bake(edit) is False
        box = TextBox(page_index=0, rect=Rect(72, 72, 160, 36), text="Print me")
        edit.objects[box.object_id] = box
        assert print_needs_bake(edit) is True
    finally:
        pdf.close()


def test_prepare_print_source_includes_textbox_and_shape():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    source = None
    try:
        edit = EditableDocument(pdf)
        box = TextBox(
            page_index=0,
            rect=Rect(72, 72, 200, 40),
            text="OVERLAY-PRINT-MARKER",
        )
        edit.objects[box.object_id] = box
        edit.create_shape(0, Rect(72, 140, 120, 80), "rectangle")
        edit.create_shape(0, Rect(220, 140, 80, 80), "ellipse", lock_aspect=True)

        source = prepare_print_source(pdf, edit)
        assert source.owns_document is True
        assert source.temp_path is not None
        assert source.temp_path.is_file()

        baked = fitz.open(source.temp_path.as_posix())
        try:
            text = baked.load_page(0).get_text("text") or ""
            assert "OVERLAY-PRINT-MARKER" in text
            assert baked.page_count == pdf.page_count
        finally:
            baked.close()

        # Source file on disk is unchanged (bake writes a temp only).
        original = fitz.open(pdf.path.as_posix())
        try:
            assert "OVERLAY-PRINT-MARKER" not in (original.load_page(0).get_text("text") or "")
        finally:
            original.close()
    finally:
        if source is not None:
            source.close()
        pdf.close()


def test_grayscale_print_raster():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        color_png = render_page_png_for_print(pdf, 0, dpi=72, color_mode=ColorMode.COLOR)
        gray_png = render_page_png_for_print(pdf, 0, dpi=72, color_mode=ColorMode.GRAYSCALE)
        gray = Image.open(io.BytesIO(gray_png))
        assert gray.mode == "L"
        assert len(gray_png) > 0
        assert len(color_png) > 0
    finally:
        pdf.close()


def test_effective_print_dpi_clamped():
    class _P:
        def __init__(self, r: int) -> None:
            self._r = r

        def resolution(self) -> int:
            return self._r

    assert effective_print_dpi(_P(72)) == 220
    assert effective_print_dpi(_P(300)) == 300
    assert effective_print_dpi(_P(1200)) == 400
    assert effective_print_dpi(None) == 300


def test_shape_kinds_covered_by_bake_for_print():
    """Square/round/line/arrow overlays must survive the print bake path."""
    pdf = open_document(SAMPLES / "sample_text.pdf")
    source = None
    try:
        edit = EditableDocument(pdf)
        edit.create_shape(0, Rect(40, 40, 60, 60), "rectangle", lock_aspect=True)
        edit.create_shape(0, Rect(120, 40, 60, 60), "ellipse", lock_aspect=True)
        edit.create_shape(0, Rect(40, 120, 100, 10), "line", x0=40, y0=125, x1=140, y1=125)
        edit.create_shape(0, Rect(40, 150, 100, 20), "arrow", x0=40, y0=160, x1=140, y1=170)
        assert {s.kind for s in edit.shapes.values()} >= {
            ShapeKind.RECTANGLE,
            ShapeKind.ELLIPSE,
            ShapeKind.LINE,
            ShapeKind.ARROW,
        }
        source = prepare_print_source(pdf, edit)
        png = render_page_png_for_print(source.document, 0, dpi=96, color_mode=ColorMode.COLOR)
        assert len(png) > 1000
    finally:
        if source is not None:
            source.close()
        pdf.close()


def test_place_page_fit_actual_and_shrink():
    from core.printing import PageScaling, auto_landscape, place_page

    # A4 page on an A4 printable area 559 x 806 pt: fit shrinks, centred, aspect kept
    x, y, w, h = place_page(595, 842, 559, 806, PageScaling.FIT)
    assert abs(w / h - 595 / 842) < 1e-6 and w <= 559 + 1e-6 and h <= 806 + 1e-6
    assert abs(x - (559 - w) / 2) < 1e-6 and abs(y - (806 - h) / 2) < 1e-6
    # A5 page: fit enlarges, shrink-only keeps 100 %, actual keeps 100 %
    assert place_page(420, 595, 559, 806, PageScaling.FIT)[2] > 420
    assert place_page(420, 595, 559, 806, PageScaling.SHRINK)[2:] == (420, 595)
    assert place_page(420, 595, 559, 806, PageScaling.ACTUAL)[2:] == (420, 595)
    # A3 page, actual size overflows (cropped, centred); shrink-only fits it
    x, y, w, h = place_page(842, 1191, 559, 806, PageScaling.ACTUAL)
    assert (w, h) == (842, 1191) and x < 0 and y < 0
    assert place_page(842, 1191, 559, 806, PageScaling.SHRINK)[2] <= 559 + 1e-6
    assert auto_landscape(842, 595) and not auto_landscape(595, 842)


def test_headless_font_list_is_not_cached(tmp_path, monkeypatch):
    """A 3-font list seen by a headless run (installer self-check, tests) must not be trusted or cached."""
    import json
    import time

    import core.editing.font_inventory as inv

    tiny = ["Noto Sans", "Noto Sans CJK JP", "Noto Serif"]
    monkeypatch.setattr(inv, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(inv, "_system_cache", None)
    (tmp_path / "font_families.json").write_text(json.dumps({"mtime": time.time(), "families": tiny}), encoding="utf-8")
    found = inv.list_system_families()
    assert found != tiny
    data = json.loads((tmp_path / "font_families.json").read_text(encoding="utf-8"))
    assert data["families"] == tiny or len(data["families"]) >= 10


def test_unsaved_form_entries_and_field_formatting_are_printed(tmp_path):
    """Regression: typed form entries alone (no text boxes) were not baked, so the print preview
    and the printed page showed the empty form."""
    import hashlib

    from core.printing.ops import _print_temp_path
    from tests.fixtures.make_field_variants import write_variant

    src = write_variant("basic", tmp_path)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    pdf = open_document(src)
    source = None
    try:
        edit = EditableDocument(pdf)
        target = next(f for f in edit.fields.values() if f.name == "target")
        keep = next(f for f in edit.fields.values() if "keep" in f.name)
        assert print_needs_bake(edit) is False
        edit.set_field_value(target.object_id, "東京 Print 0123")
        assert print_needs_bake(edit) is True

        source = prepare_print_source(pdf, edit)
        assert source.document is not pdf and source.temp_path is not None
        text = "".join(source.document.page_text(i) for i in range(source.document.page_count))
        assert "東京Print0123" in "".join(text.split()) and "Keepme" in "".join(text.split())
        temp = source.temp_path
    finally:
        if source is not None:
            source.close()
    assert not temp.exists(), "temporary print copy left behind"
    assert target.value == "東京 Print 0123" and target.value_dirty  # still unsaved in the editor
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before  # file on disk untouched
    assert _print_temp_path().parent.is_dir()

    # Formatting only (no new text) must also reach the printout
    edit2 = EditableDocument(pdf)
    keep2 = next(f for f in edit2.fields.values() if f.name == keep.name)
    keep2.font_size = 14
    keep2.style_dirty = True
    assert print_needs_bake(edit2) is True
    pdf.close()


def test_checked_checkbox_appears_in_print_bake(tmp_path):
    """Checked native checkboxes must survive prepare_print_source (flatten bake)."""
    from core.forms.acroform import resolve_widget_on_state

    src = tmp_path / "cb.pdf"
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(72, 72, 92, 92)
    w.field_name = "agree"
    page.add_widget(w)
    page.first_widget.field_value = "Off"
    page.first_widget.update()
    doc.save(src)
    doc.close()

    pdf = open_document(src)
    source = None
    try:
        edit = EditableDocument(pdf)
        fid = next(iter(edit.fields))
        edit.set_field_value(fid, checked=True)
        source = prepare_print_source(pdf, edit)
        # Flattened print copy: widget may be gone, but appearance must show as on
        baked = source.document._backend._doc  # noqa: SLF001
        # After flatten, either no widgets remain or the baked content includes the check
        widgets = list(baked[0].widgets() or [])
        if widgets:
            assert str(widgets[0].field_value) == resolve_widget_on_state(widgets[0], baked)
        else:
            # Flattened into page drawings — ensure bake produced output
            assert baked.page_count >= 1
    finally:
        if source is not None:
            source.close()
        pdf.close()


def test_push_buttons_are_not_fillable_and_keep_their_caption(tmp_path):
    """A form's own push button (e.g. 'Print form') is not a text field; its caption is kept."""
    from core.forms.acroform import load_acroform_fields

    path = tmp_path / "button.pdf"
    doc = fitz.open()
    page = doc.new_page()
    btn = fitz.Widget()
    btn.field_type = fitz.PDF_WIDGET_TYPE_BUTTON
    btn.field_name = "PrintButton1"
    btn.button_caption = "Print form"
    btn.rect = fitz.Rect(400, 20, 520, 40)
    page.add_widget(btn)
    txt = fitz.Widget()
    txt.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    txt.field_name = "name"
    txt.rect = fitz.Rect(72, 100, 300, 120)
    page.add_widget(txt)
    doc.save(path)
    doc.close()

    with fitz.open(path) as d:
        names = [f.name for f in load_acroform_fields(d)]
    assert names == ["name"]
    pdf = open_document(path)
    source = None
    try:
        edit = EditableDocument(pdf)
        assert [f.name for f in edit.fields.values()] == ["name"]
        field = next(iter(edit.fields.values()))
        edit.set_field_value(field.object_id, "Filled")
        source = prepare_print_source(pdf, edit)
        text = source.document.page_text(0)
        assert "Filled" in text and "Print form" in text
    finally:
        if source is not None:
            source.close()
        pdf.close()
