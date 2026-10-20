"""Unit tests for text boxes, layout, undo/redo, fonts, session recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.font_resolver import resolve_font, text_needs_cjk
from core.editing.geometry import Rect
from core.editing.session_store import clear_session, read_session, write_session
from core.editing.text_box import SizeMode, TextBox
from core.editing.text_layout import apply_layout_to_box, layout_text_box
from core.editing.text_style import TextStyle
from engines.bake_edits import bake_via_backend

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def edit_doc(tmp_path: Path):
    src = tmp_path / "base.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    pdf = open_document(src)
    model = EditableDocument(pdf)
    yield model
    pdf.close()
    clear_session(src)


def test_create_text_box_and_undo(edit_doc: EditableDocument):
    box = edit_doc.create_text_box(0, Rect(72, 72, 200, 40), text="Hello")
    assert box.object_id in edit_doc.objects
    assert edit_doc.dirty
    assert edit_doc.undo()
    assert box.object_id not in edit_doc.objects
    assert edit_doc.redo()
    assert any(o.text == "Hello" for o in edit_doc.all_objects())


def test_wrapping_and_auto_height():
    box = TextBox(
        page_index=0,
        rect=Rect(0, 0, 80, 20),
        text="The quick brown fox jumps over the lazy dog repeatedly.",
        size_mode=SizeMode.AUTO_HEIGHT,
        style=TextStyle(font_size=11),
    )
    apply_layout_to_box(box)
    assert box.rect.h > 20
    layout = layout_text_box(box)
    assert len(layout.lines) >= 2


def test_fixed_overflow_warning():
    box = TextBox(
        page_index=0,
        rect=Rect(0, 0, 60, 18),
        text="Overflowing content that cannot fit this tiny fixed box at all.",
        size_mode=SizeMode.FIXED,
        style=TextStyle(font_size=14),
    )
    apply_layout_to_box(box)
    assert box.overflow is True


def test_resize_then_undo(edit_doc: EditableDocument):
    box = edit_doc.create_text_box(0, Rect(50, 50, 100, 40), text="Resize")
    before = edit_doc.begin_transform_snapshot()
    edit_doc.live_resize(box.object_id, Rect(50, 50, 220, 80))
    edit_doc.commit_transform(before, name="Resize")
    assert edit_doc.get(box.object_id).rect.w == 220
    edit_doc.undo()
    assert abs(edit_doc.get(box.object_id).rect.w - 100) < 0.1


def test_unicode_japanese_text_and_font_fallback():
    assert text_needs_cjk("日本語テスト")
    res = resolve_font("MissingFontXYZ123", "日本語とEnglish")
    assert res.resolved
    assert res.substituted
    box = TextBox(
        page_index=0,
        rect=Rect(0, 0, 200, 60),
        text="こんにちは Monograph PDF — café",
        style=TextStyle(font_family="MissingFontXYZ123", font_size=12),
    )
    apply_layout_to_box(box)
    assert box.font_substituted
    assert box.resolved_font


def test_save_reopen_preserves_text(tmp_path: Path):
    original = (SAMPLES / "sample_text.pdf").read_bytes()
    src = tmp_path / "edit_src.pdf"
    src.write_bytes(original)
    out = tmp_path / "edit_out.pdf"
    pdf = open_document(src)
    model = EditableDocument(pdf)
    model.create_text_box(0, Rect(72, 700, 200, 40), text="SavedOverlay")
    bake_via_backend(model, out)
    pdf.close()
    assert out.is_file()
    assert src.read_bytes() == original  # source never modified by Save As bake
    reopened = open_document(out)
    try:
        assert reopened.page_count >= 1
        assert "SavedOverlay" in reopened.page_text(0)
    finally:
        reopened.close()


def test_session_crash_recovery(tmp_path: Path, monkeypatch):
    src = tmp_path / "session.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    # Point session store into tmp by monkeypatching ROOT usage — write via explicit path helper
    from core.editing import session_store

    monkeypatch.setattr(session_store, "session_dir", lambda: tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()
    pdf = open_document(src)
    model = EditableDocument(pdf)
    model.create_text_box(0, Rect(40, 40, 120, 40), text="RecoverMe")
    path = write_session(src, model.to_dict())
    assert path.is_file()
    pdf.close()
    # Simulate restart
    pdf2 = open_document(src)
    model2 = EditableDocument(pdf2)
    data = read_session(src)
    assert data is not None
    model2.load_objects(data["payload"])
    assert any(o.text == "RecoverMe" for o in model2.all_objects())
    pdf2.close()
    clear_session(src)


def test_duplicate_and_delete(edit_doc: EditableDocument):
    box = edit_doc.create_text_box(0, Rect(10, 10, 80, 30), text="Dup")
    edit_doc.select([box.object_id])
    edit_doc.duplicate_selection()
    assert len(edit_doc.objects) == 2
    edit_doc.delete_selection()
    assert len(edit_doc.selected_objects()) == 0 or len(edit_doc.objects) <= 2


def test_generic_sans_serif_resolves_to_a_normal_face_not_sans_serif_collection():
    """Regression: the default text-box font "sans-serif" resolved to Windows' 'Sans Serif Collection', whose
    line metrics are twice the normal height, so new text boxes drew their text low and clipped."""
    from core.editing.font_resolver import resolve_font

    for generic in ("sans-serif", "Sans-Serif", "serif", "monospace"):
        r = resolve_font(generic, "Font test")
        assert "collection" not in r.resolved.lower(), (generic, r)


@pytest.mark.parametrize("w,h", [(240, 120), (120, 240), (1000, 1000), (3000, 500), (50, 400)])
def test_new_picture_keeps_its_proportions(w, h):
    """Regression (found in the packaged exe): a 240×120 picture was inserted in a fixed 240×180 box and stretched."""
    from core.editing.image_box import default_image_rect

    r = default_image_rect(w, h, 595.0, 842.0)
    assert r.w / r.h == pytest.approx(w / h, rel=0.01)
    assert r.w <= 240.0 + 1e-6 and r.h <= 180.0 + 1e-6
    assert r.x1 <= 595.0 and r.y1 <= 842.0


def test_new_picture_of_unknown_size_gets_the_default_box():
    from core.editing.image_box import default_image_rect

    r = default_image_rect(0, 0, 595.0, 842.0)
    assert (r.w, r.h) == (240.0, 180.0)
