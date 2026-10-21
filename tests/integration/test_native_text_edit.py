"""Editing existing PDF text: Edit -> Save -> Reopen -> Validate (controlled reconstruction).

The original span's glyphs must be removed at Save (text only: drawings and the background stay) and
the edited text written in their place; neighbouring lines are untouched; Undo and an unchanged edit
leave the original exactly as it was.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document import open_document  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from engines.bake_edits import bake_via_backend  # noqa: E402


def _make(path: Path, *, line_gap: float = 40, background: tuple | None = None) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    if background:
        page.draw_rect(fitz.Rect(60, 60, 400, 220), color=None, fill=background)
    page.insert_text((72, 100), "First line stays", fontsize=12)
    page.insert_text((72, 100 + line_gap), "Hello world", fontsize=12, color=(0.8, 0.1, 0.1))
    page.insert_text((72, 100 + 2 * line_gap), "Third line stays", fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _edit(src: Path):
    pdf = open_document(src)
    return pdf, EditableDocument(pdf)


def _span(edit, startswith: str):
    return next(s for s in edit.extract_native_spans(0) if s.text.startswith(startswith))


def _replace(edit, span, new: str):
    box = edit.begin_native_edit(span, span.text)
    edit.live_set_text(box.object_id, new)
    edit.commit_text_edit(box.object_id, span.text, new)
    return box


def _words(path: Path) -> list[tuple[float, float, str]]:
    with fitz.open(path) as d:
        return [(w[0], w[3], w[4]) for w in d[0].get_text("words")]


@pytest.mark.parametrize("line_gap", [40, 13])  # normal and tight (lines' boxes touch) spacing
def test_replace_existing_text_save_and_reopen(tmp_path, line_gap):
    src = _make(tmp_path / "in.pdf", line_gap=line_gap)
    pdf, edit = _edit(src)
    span = _span(edit, "Hello")
    original_x = span.rect.x
    _replace(edit, span, "Goodbye world")
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    words = _words(out)
    text = " ".join(w[2] for w in words)
    assert "Hello" not in text  # the original glyphs are gone, not just covered
    assert "Goodbye world" in text
    assert "First line stays" in text and "Third line stays" in text
    goodbye = next(w for w in words if w[2] == "Goodbye")
    assert abs(goodbye[0] - original_x) < 2.0  # written where the original started
    assert abs(goodbye[1] - (100 + line_gap)) < 4.0  # on the original line
    # the source file is untouched
    assert "Hello world" in fitz.open(src)[0].get_text()


def test_style_of_the_original_is_kept(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    box = _replace(edit, _span(edit, "Hello"), "Changed")
    assert box.style.text_color.lower() == "#cc1a1a"
    assert abs(box.style.font_size - 12) < 0.01
    assert box.style.padding == 0 and box.style.wrap is False
    pdf.close()


def test_drawings_and_background_under_the_text_are_kept(tmp_path):
    src = _make(tmp_path / "in.pdf", background=(0.85, 0.9, 1.0))
    pdf, edit = _edit(src)
    _replace(edit, _span(edit, "Hello"), "Replaced")
    plan = next(iter(edit.native_replacements.values()))
    cover = tuple(int(plan["cover"][i:i + 2], 16) for i in (1, 3, 5))
    assert all(abs(a - b) <= 2 for a, b in zip(cover, (217, 230, 255)))  # the page's background colour
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        fills = [dr for dr in d[0].get_drawings() if dr.get("fill")]
        assert any(abs(dr["rect"].width - 340) < 1 for dr in fills)
        pix = d[0].get_pixmap(clip=fitz.Rect(300, 130, 310, 145), dpi=72)
        assert all(abs(a - b) <= 2 for a, b in zip(pix.pixel(2, 2)[:3], (217, 230, 255)))


def test_undo_restores_the_original(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    _replace(edit, _span(edit, "Hello"), "Goodbye")
    while edit.undo():
        pass
    assert edit.native_replacements == {}
    assert not any(b.replaces_native for b in edit.all_objects())
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    assert "Hello world" in fitz.open(out)[0].get_text()


def test_an_unchanged_edit_is_discarded_without_an_undo_entry(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    span = _span(edit, "Hello")
    box = edit.begin_native_edit(span, span.text)
    edit.commit_text_edit(box.object_id, span.text, span.text)
    assert edit.discard_unchanged_native_edit(box.object_id) is True
    assert edit.native_replacements == {} and box.object_id not in edit.objects
    assert not edit.commands.can_undo_now
    # a changed edit is not discarded
    box = _replace(edit, _span(edit, "Hello"), "Other")
    assert edit.discard_unchanged_native_edit(box.object_id) is False
    pdf.close()


def test_deleting_the_replacement_deletes_the_text(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    box = _replace(edit, _span(edit, "Hello"), "Hello world")
    edit.select([box.object_id])
    edit.delete_selection()
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    text = fitz.open(out)[0].get_text()
    assert "Hello" not in text and "First line stays" in text


def test_japanese_text_can_replace_latin_text(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    _replace(edit, _span(edit, "Hello"), "日本語のテキスト α+β=γ")
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    text = fitz.open(out)[0].get_text()
    assert "日本語のテキスト" in text and "α+β=γ" in text and "Hello" not in text


def test_existing_japanese_cid_text_can_be_edited(tmp_path):
    src = tmp_path / "jp.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "上の行", fontsize=12, fontname="japan")
    page.insert_text((72, 140), "元の文章です", fontsize=12, fontname="japan")
    page.insert_text((72, 180), "下の行", fontsize=12, fontname="japan")
    doc.save(src)
    doc.close()
    pdf, edit = _edit(src)
    _replace(edit, _span(edit, "元の"), "新しい文章です")
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    text = fitz.open(out)[0].get_text()
    assert "元の文章" not in text and "新しい文章です" in text and "上の行" in text and "下の行" in text


def test_plans_without_a_rectangle_from_older_sessions_still_remove_the_original(tmp_path):
    src = _make(tmp_path / "in.pdf")
    pdf, edit = _edit(src)
    box = _replace(edit, _span(edit, "Hello"), "Newer")
    sid = box.native_span_id
    edit._native_replacements[sid] = {"mode": "safe_direct", "span_id": sid, "new_text": "Hello world"}  # noqa: SLF001
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    text = fitz.open(out)[0].get_text()
    assert "Hello" not in text and "Newer" in text
