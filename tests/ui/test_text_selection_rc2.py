"""Select Text in the real window follows visual reading order (F-14) and selects unsaved replacements
of existing text as shown (F-15) — 0.6.0 RC2. Offscreen; synthetic PDFs; positions come from MuPDF's
own search (independent of the selection code)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from tests.ui.test_text_selection_ui import (  # noqa: E402,F401  (window is a fixture)
    _drag,
    _inner,
    _iou,
    _open_select_text,
    _settle,
    _word_widget_rect,
    window,
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _clip() -> str:
    from PySide6.QtWidgets import QApplication

    return QApplication.clipboard().text()


def _lines_pdf(path: Path, stored: tuple[int, ...], texts=("Line 1", "Line 2", "Line 3"), *, font="helv") -> Path:
    d = fitz.open()
    p = d.new_page()
    for i in stored:
        p.insert_text((72, 120 + 28 * i), texts[i], fontsize=14, fontname=font)
    d.save(path)
    d.close()
    return path


def _from_start_to_end(win, qtbot, first: str, last: str, *, page_a=0, page_b=0, upward=False):
    from PySide6.QtCore import QPointF

    ra, _ = _word_widget_rect(win, page_a, first)
    rb, _ = _word_widget_rect(win, page_b, last)
    a = QPointF(ra.left() + 0.5, ra.center().y())
    b = QPointF(rb.right() - 0.5, rb.center().y())
    if upward:
        a, b = b, a
    _drag(win, qtbot, a, b, steps=10)
    return _inner(win).text_select.selected_text()


def _replace(win, old_prefix: str, new_text: str, page: int = 0):
    edit = win._edit  # noqa: SLF001
    span = next(s for s in edit.extract_native_spans(page) if s.text.startswith(old_prefix))
    box = edit.begin_native_edit(span, span.text)
    edit.live_set_text(box.object_id, new_text)
    edit.commit_text_edit(box.object_id, span.text, new_text)
    return span, box


# -- F-14 cases A, B, C -----------------------------------------------------------------------------

@pytest.mark.parametrize("stored", [(0, 1, 2), (1, 0, 2), (2, 1, 0)], ids=["A-same", "B-2-1-3", "C-reversed"])
def test_cases_a_b_c_copy_and_drag_follow_the_screen(window, qtbot, tmp_path, stored):
    src = _lines_pdf(tmp_path / "abc.pdf", stored)
    before = _sha(src)
    _open_select_text(window, qtbot, src, zoom=1.5)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Line 1\nLine 2\nLine 3"
    assert _from_start_to_end(window, qtbot, "Line 1", "Line 2") == "Line 1\nLine 2"
    assert _from_start_to_end(window, qtbot, "Line 1", "Line 3") == "Line 1\nLine 2\nLine 3"
    assert _from_start_to_end(window, qtbot, "Line 2", "Line 3", upward=True) == "Line 2\nLine 3"
    assert not window._edit.dirty and _sha(src) == before  # noqa: SLF001


def test_highlight_lies_on_the_selected_lines(window, qtbot, tmp_path):
    from PySide6.QtCore import QRectF

    from core.editing.geometry import Point

    src = _lines_pdf(tmp_path / "hl.pdf", (2, 1, 0))
    _open_select_text(window, qtbot, src, zoom=1.5)
    assert _from_start_to_end(window, qtbot, "Line 1", "Line 2") == "Line 1\nLine 2"
    inner = _inner(window)
    rects = inner.text_select.selected_page_rects(0)
    assert len(rects) == 2
    for (x0, y0, x1, y1), word in zip(rects, ("Line 1", "Line 2")):
        shown = QRectF(inner.pdf_to_widget_f(0, Point(x0, y0)), inner.pdf_to_widget_f(0, Point(x1, y1))).normalized()
        assert _iou(shown, _word_widget_rect(window, 0, word)[0]) > 0.6


def test_case_g_two_columns_do_not_jump(window, qtbot, tmp_path):
    src = tmp_path / "cols.pdf"
    d = fitz.open()
    p = d.new_page()
    for i in range(5):  # stored row by row, right column first
        p.insert_text((310, 100 + 14 * i), f"right column sentence {i + 1} of text", fontsize=9)
        p.insert_text((72, 100 + 14 * i), f"left column sentence {i + 1} of text", fontsize=9)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src, zoom=1.0)
    got = _from_start_to_end(window, qtbot, "left column sentence 1", "left column sentence 3 of text")
    assert got == "\n".join(f"left column sentence {i} of text" for i in (1, 2, 3))
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    rows = _clip().split("\n")
    assert rows == [f"left column sentence {i} of text" for i in range(1, 6)] + \
        [f"right column sentence {i} of text" for i in range(1, 6)]


def test_case_h_japanese_reordered_lines_without_spaces(window, qtbot, tmp_path):
    texts = ("日本語の一行目です", "カタカナの二行目", "三行目 English 混在")
    src = _lines_pdf(tmp_path / "jp.pdf", (2, 0, 1), texts, font="japan")
    _open_select_text(window, qtbot, src, zoom=1.5)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "\n".join(texts)
    assert _from_start_to_end(window, qtbot, texts[0], texts[1]) == texts[0] + "\n" + texts[1]


def test_reordered_lines_on_a_turned_page(window, qtbot, tmp_path):
    src = tmp_path / "rot.pdf"
    d = fitz.open()
    p = d.new_page()
    for i in (2, 0, 1):
        p.insert_text((72, 120 + 28 * i), f"Line {i + 1}", fontsize=14)
    p.set_rotation(90)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Line 1\nLine 2\nLine 3"


def test_multipage_selection_keeps_page_order_and_reading_order(window, qtbot, tmp_path):
    src = tmp_path / "mp.pdf"
    d = fitz.open()
    for texts in (("p1 top", "p1 bottom"), ("p2 top", "p2 bottom")):
        p = d.new_page()
        p.insert_text((72, 300), texts[1], fontsize=14)  # bottom line stored first
        p.insert_text((72, 120), texts[0], fontsize=14)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src, zoom=0.5)
    got = _from_start_to_end(window, qtbot, "p1 bottom", "p2 top", page_a=0, page_b=1)
    assert got == "p1 bottom\n\np2 top"


# -- case D: edited, saved, reopened ------------------------------------------------------------------

def test_case_d_replaced_saved_and_reopened(window, qtbot, tmp_path):
    src = _lines_pdf(tmp_path / "d.pdf", (0, 1, 2))
    _open_select_text(window, qtbot, src)
    _replace(window, "Line 1", "Edited 1")
    window.save_document()
    _settle(qtbot, window, 100)
    with fitz.open(src) as doc:  # the saved file stores the new line last
        assert doc[0].get_text().split("\n")[:3] == ["Line 2", "Line 3", "Edited 1"]
    window.close_document(save_session=False)
    _open_select_text(window, qtbot, src, zoom=1.5)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Edited 1\nLine 2\nLine 3"
    assert _from_start_to_end(window, qtbot, "Edited 1", "Line 2") == "Edited 1\nLine 2"


# -- F-15 cases E, F and related ------------------------------------------------------------------------

def test_case_e_unsaved_replacement_is_selected_as_shown(window, qtbot, tmp_path):
    src = _lines_pdf(tmp_path / "e.pdf", (0, 1, 2), ("Hello world", "Keep me", "Last line"))
    before = _sha(src)
    _open_select_text(window, qtbot, src, zoom=1.5)
    _replace(window, "Hello", "Goodbye world")
    _settle(qtbot, window, 40)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Goodbye world\nKeep me\nLast line"
    # a drag over the replacement selects the replacement, never the hidden original
    from PySide6.QtCore import QPointF

    from core.editing.geometry import Point

    inner = _inner(window)
    pt = inner.text_select.cache.get(window._document._backend._doc, 0)  # noqa: SLF001
    first = pt.lines[0]
    a = inner.pdf_to_widget_f(0, Point(first.x0 + 0.3, (first.y0 + first.y1) / 2))
    b = inner.pdf_to_widget_f(0, Point(first.x1 - 0.3, (first.y0 + first.y1) / 2))
    _drag(window, qtbot, QPointF(a), QPointF(b))
    assert inner.text_select.selected_text() == "Goodbye world"
    assert "Hello" not in _clip()
    # nothing was written: the PDF and its in-memory page still hold the original text
    assert _sha(src) == before
    assert "Hello world" in window._document._backend._doc[0].get_text()  # noqa: SLF001
    window._edit.dirty = False  # noqa: SLF001


def test_case_f_undo_and_redo_change_what_is_copied(window, qtbot, tmp_path):
    src = _lines_pdf(tmp_path / "f.pdf", (0, 1), ("Hello world", "Keep me"))
    _open_select_text(window, qtbot, src)
    _replace(window, "Hello", "Goodbye world")
    edit = window._edit  # noqa: SLF001
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    assert _inner(window).text_select.selected_text() == "Goodbye world\nKeep me"
    undone = 0
    while edit.native_replacements and edit.undo():
        undone += 1
    assert undone >= 1 and not edit.native_replacements
    _settle(qtbot, window, 30)
    assert not _inner(window).text_select.has_selection  # the old selection is dropped, not shifted
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Hello world\nKeep me"
    for _ in range(undone):
        assert edit.redo()
    _settle(qtbot, window, 30)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Goodbye world\nKeep me"
    edit.dirty = False


def test_save_as_keeps_the_replacement_selectable(window, qtbot, tmp_path, monkeypatch):
    src = _lines_pdf(tmp_path / "sa.pdf", (0, 1), ("Hello world", "Keep me"))
    before = _sha(src)
    _open_select_text(window, qtbot, src)
    _replace(window, "Hello", "Goodbye world")
    out = tmp_path / "saved_as.pdf"
    from ui import main_window as mw

    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "PDF (*.pdf)")))
    window.save_as_dialog()
    _settle(qtbot, window, 150)
    assert out.exists() and _sha(src) == before
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Goodbye world\nKeep me"


def test_replacement_does_not_leak_into_another_document(window, qtbot, tmp_path):
    a = _lines_pdf(tmp_path / "a.pdf", (0, 1), ("Hello world", "Keep me"))
    b = _lines_pdf(tmp_path / "b.pdf", (0, 1), ("Hello world", "Other doc"))
    _open_select_text(window, qtbot, a)
    _replace(window, "Hello", "Goodbye world")
    assert window.open_path(b)
    _settle(qtbot, window, 80)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Hello world\nOther doc"
    window._doc_tabs.setCurrentIndex(0)  # noqa: SLF001
    _settle(qtbot, window, 80)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Goodbye world\nKeep me"
    window._edit.dirty = False  # noqa: SLF001


@pytest.mark.parametrize("zoom", [0.5, 2.0])
def test_zoom_does_not_change_the_copied_replacement(window, qtbot, tmp_path, zoom):
    src = _lines_pdf(tmp_path / "z.pdf", (0, 1), ("Hello world", "Keep me"))
    _open_select_text(window, qtbot, src)
    _replace(window, "Hello", "Goodbye world")
    window._canvas.set_manual_zoom(zoom)  # noqa: SLF001
    _settle(qtbot, window, 80)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Goodbye world\nKeep me"
    window._edit.dirty = False  # noqa: SLF001


def test_replacement_on_a_turned_page(window, qtbot, tmp_path):
    src = tmp_path / "turned.pdf"
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 120), "Hello world", fontsize=14)
    p.insert_text((72, 150), "Keep me", fontsize=14)
    p.set_rotation(90)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src)
    _replace(window, "Hello", "Goodbye world")
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    text = _inner(window).text_select.selected_text()
    assert "Goodbye world" in text and "Keep me" in text and "Hello" not in text
    window._edit.dirty = False  # noqa: SLF001


def test_further_typing_updates_the_selectable_text(window, qtbot, tmp_path):
    src = _lines_pdf(tmp_path / "t.pdf", (0, 1), ("Hello world", "Keep me"))
    _open_select_text(window, qtbot, src)
    span, box = _replace(window, "Hello", "Goodbye world")
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    assert _inner(window).text_select.selected_text().startswith("Goodbye world")
    edit = window._edit  # noqa: SLF001
    edit.live_set_text(box.object_id, "Farewell world")
    edit.commit_text_edit(box.object_id, "Goodbye world", "Farewell world")
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert _clip() == "Farewell world\nKeep me"
    edit.dirty = False


def test_selecting_an_unedited_page_reads_the_pdf_only_once(window, qtbot, tmp_path):
    src = _lines_pdf(tmp_path / "once.pdf", (2, 1, 0))
    _open_select_text(window, qtbot, src)
    cache = _inner(window).text_select.cache
    n = cache.extractions
    for _ in range(5):
        window._select_all()  # noqa: SLF001
        _inner(window).text_select.selected_text()
    assert cache.extractions - n <= 1
