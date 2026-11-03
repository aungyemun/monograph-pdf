"""Comments panel, stamp library, squiggly markup and movable visual signatures through the real
window: place with the mouse, list, edit, delete, undo, save and reopen."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

from tests.ui.note_answers import answer_note_text

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-comments"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Line one to be marked with a squiggle", fontsize=14)
    page.add_text_annot((400, 400), "Imported note").update()  # a comment from another PDF app
    doc.new_page()
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1360, 860)
    w.show()
    assert w.open_path(src)
    yield w, src
    w.close_document(save_session=False)
    w.close()


def _drag(qtbot, w, page, x0, y0, x1, y1):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    inner = w._canvas._canvas  # noqa: SLF001
    p0 = inner.pdf_to_widget(page, Point(x0, y0))
    p1 = inner.pdf_to_widget(page, Point(x1, y1))
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    QTest.mouseMove(inner, p1)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
    qtbot.wait(20)


def _panel_kinds(w):
    w._left.comments.refresh()  # noqa: SLF001
    return [(c.page_index, c.kind) for c in w._left.comments.comments()]  # noqa: SLF001


def test_comments_panel_lists_imported_and_new_comments_and_deletes_with_undo(win, qtbot, monkeypatch):
    w, src = win
    w.act_show_comments.trigger()
    assert w._left.currentWidget() is w._left.comments  # noqa: SLF001
    assert _panel_kinds(w) == [(0, "Text")]  # the imported note
    answer_note_text(monkeypatch, "My note")
    w.act_annot_comment.trigger()
    _drag(qtbot, w, 0, 150, 300, 150, 300)
    assert sorted(_panel_kinds(w)) == [(0, "Text"), (0, "Text")]
    panel = w._left.comments  # noqa: SLF001
    mine = next(c for c in panel.comments() if c.rect[0] < 300)
    assert panel.select(mine.page_index, mine.xref)
    # edit the text from the panel (undoable)
    answer_note_text(monkeypatch, "Edited note")
    panel.editTextRequested.emit(mine)
    from core.annotations import list_annotations

    assert "Edited note" in [a.content for a in list_annotations(w._document)]  # noqa: SLF001
    w.act_undo.trigger()
    assert "My note" in [a.content for a in list_annotations(w._document)]  # noqa: SLF001
    panel.deleteRequested.emit(mine)
    assert _panel_kinds(w) == [(0, "Text")]
    w.act_undo.trigger()
    assert len(_panel_kinds(w)) == 2
    w.save_document()
    with fitz.open(src) as d:
        assert sorted((a.info or {}).get("content") for a in d[0].annots() if a.type[1] == "Text") == ["Imported note", "My note"]


def test_squiggly_underline_through_the_menu(win, qtbot):
    from core.annotations import list_annotations

    w, src = win
    hits = w._document.search("squiggle")  # noqa: SLF001
    page, r = hits[0]
    w.act_annot_squiggly.trigger()
    _drag(qtbot, w, page, r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2)
    assert [a.kind for a in list_annotations(w._document) if a.kind == "Squiggly"] == ["Squiggly"]  # noqa: SLF001
    w.act_undo.trigger()
    assert not [a for a in list_annotations(w._document) if a.kind == "Squiggly"]  # noqa: SLF001


def test_stamp_library_place_undo_and_save(win, qtbot, monkeypatch):
    from ui import stamp_dialog

    w, src = win

    class Auto(stamp_dialog.StampLibraryDialog):
        def exec(self):  # noqa: A003
            row = next(i for i in range(self.list.count()) if self.list.item(i).text() == "For Review")
            self.list.setCurrentRow(row)
            self.date.setChecked(True)
            self.opacity.setValue(80)
            return self.DialogCode.Accepted

    monkeypatch.setattr(stamp_dialog, "StampLibraryDialog", Auto)
    w.act_annot_stamp.trigger()
    _drag(qtbot, w, 0, 100, 500, 300, 560)
    assert (0, "Stamp") in _panel_kinds(w)
    w.act_undo.trigger()
    assert (0, "Stamp") not in _panel_kinds(w)
    w.act_redo.trigger()
    w.save_document()
    with fitz.open(src) as d:
        page = d[0]
        stamps = [a for a in page.annots() if a.type[1] == "Stamp"]
        assert len(stamps) == 1 and stamps[0].info["content"] == "FOR REVIEW"
        assert abs(stamps[0].opacity - 0.8) < 0.01
        assert abs(stamps[0].rect.width - 200) < 2 and abs(stamps[0].rect.height - 60) < 2


def test_visual_signature_is_a_movable_picture_until_saved(win, qtbot, monkeypatch):
    from ui import app_dialogs

    w, src = win

    class Pad(app_dialogs.SignaturePadDialog):
        def exec(self):  # noqa: A003
            return self.DialogCode.Accepted

        def strokes(self):
            return [[(0, 0), (40, 20), (80, 0), (120, 25)]]

    monkeypatch.setattr(app_dialogs, "SignaturePadDialog", Pad)
    w.act_sig_drawn.trigger()
    _drag(qtbot, w, 0, 100, 600, 300, 660)
    edit = w._edit  # noqa: SLF001
    (sig,) = [i for i in edit.images.values() if i.role == "signature"]
    assert 98.5 <= sig.rect.x and sig.rect.x1 <= 301.5 and Path(sig.source_path).is_file()
    # move it (undoable), then save: the page gets the picture where it was moved to
    edit.select([sig.object_id])
    before = edit.begin_transform_snapshot()
    edit.live_translate([sig.object_id], 50, -100)
    edit.commit_transform(before)
    w.act_undo.trigger()
    assert 98.5 <= sig.rect.x
    w.act_redo.trigger()
    w.save_document()
    with fitz.open(src) as d:
        infos = d[0].get_image_info()
        assert len(infos) == 1
        x0, y0, x1, y1 = infos[0]["bbox"]
        assert y0 >= 490 and y1 <= 570 and x0 >= 140
    assert not w._edit.images  # noqa: SLF001 — saved into the page


def test_select_tool_moves_and_deletes_a_comment_on_the_page(win, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.annotations import list_annotations

    w, src = win
    w.act_select_tool.trigger()
    (note,) = [a for a in list_annotations(w._document) if a.kind == "Text"]  # noqa: SLF001
    x0, y0, x1, y1 = note.rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    _drag(qtbot, w, 0, cx, cy, cx + 60, cy + 40)
    (moved,) = [a for a in list_annotations(w._document) if a.kind == "Text"]  # noqa: SLF001
    assert abs(moved.rect[0] - (x0 + 60)) < 2 and abs(moved.rect[1] - (y0 + 40)) < 2
    assert w._canvas.selected_annotation()[:2] == (0, moved.xref)  # noqa: SLF001
    w.act_undo.trigger()
    (back,) = [a for a in list_annotations(w._document) if a.kind == "Text"]  # noqa: SLF001
    assert abs(back.rect[0] - x0) < 1
    # click it, press Delete; Undo brings it back
    _drag(qtbot, w, 0, cx, cy, cx, cy)
    QTest.keyClick(w._canvas._canvas, Qt.Key.Key_Delete)  # noqa: SLF001
    assert not [a for a in list_annotations(w._document) if a.kind == "Text"]  # noqa: SLF001
    w.act_undo.trigger()
    assert [a for a in list_annotations(w._document) if a.kind == "Text"]  # noqa: SLF001
