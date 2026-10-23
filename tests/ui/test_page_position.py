"""Pages can be inserted and moved to an exact position: before/after page N, beginning or end."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from ui.page_position_dialog import AFTER, BEFORE, END, START, insert_index, move_order  # noqa: E402


def test_insert_index_for_every_choice():
    assert insert_index(BEFORE, 3, 5) == 2
    assert insert_index(AFTER, 3, 5) == 3
    assert insert_index(START, 3, 5) == 0
    assert insert_index(END, 3, 5) == 5
    assert insert_index(AFTER, 99, 5) == 5 and insert_index(BEFORE, 0, 5) == 0  # clamped


def test_move_order_keeps_selected_pages_together_and_in_order():
    assert move_order(5, [0], 3) == [1, 2, 0, 3, 4]  # page 1 to between pages 3 and 4
    assert move_order(5, [3, 4], 0) == [3, 4, 0, 1, 2]  # to the beginning
    assert move_order(5, [1, 3], 5) == [0, 2, 4, 1, 3]  # to the end
    assert move_order(5, [2], 2) == [0, 1, 2, 3, 4]  # already there
    for n in range(1, 7):
        for t in range(n + 1):
            order = move_order(n, [0, n - 1], t)
            assert sorted(order) == list(range(n))


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-page-position"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    for i in range(4):
        doc.new_page(width=595, height=842).insert_text((72, 100), f"Page {i + 1}", fontsize=20)
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _texts(w):
    doc = w._document._backend._doc  # noqa: SLF001
    return [doc[i].get_text().strip() for i in range(doc.page_count)]


def test_insert_several_blank_pages_before_a_page_and_undo(win):
    w = win
    w._insert_blank_page(at=insert_index(BEFORE, 2, 4), count=2)  # noqa: SLF001
    assert _texts(w) == ["Page 1", "", "", "Page 2", "Page 3", "Page 4"]
    w.act_undo.trigger()
    assert _texts(w) == ["Page 1", "Page 2", "Page 3", "Page 4"]
    w._insert_blank_page(at=insert_index(START, 1, 4))  # noqa: SLF001
    assert _texts(w)[0] == ""


def test_move_selected_pages_to_an_exact_position_with_their_objects(win):
    from core.editing.geometry import Rect

    w = win
    w._edit.create_text_box(0, Rect(72, 200, 150, 30), text="On page one")  # noqa: SLF001
    thumbs = w._left.thumbs  # noqa: SLF001
    thumbs.clearSelection()
    thumbs.item(0).setSelected(True)
    w._move_selected_pages(insert_index(AFTER, 3, 4))  # noqa: SLF001
    assert _texts(w) == ["Page 2", "Page 3", "Page 1", "Page 4"]
    assert [o.page_index for o in w._edit.objects.values() if getattr(o, "text", "") == "On page one"] == [2]  # noqa: SLF001
    w.act_undo.trigger()
    assert _texts(w) == ["Page 1", "Page 2", "Page 3", "Page 4"]


def test_page_position_dialog_reports_the_choice(qtbot):
    from ui.page_position_dialog import PagePositionDialog

    dlg = PagePositionDialog(None, title="Insert Blank Pages", intro="Where?", page_count=4, page=1,
                             ok_text="Insert", count_label="Number of blank pages:")
    qtbot.addWidget(dlg)
    assert dlg.where() == AFTER and dlg.page_spin.value() == 2 and dlg.insert_index() == 2
    dlg.radio_before.setChecked(True)
    assert dlg.insert_index() == 1 and "between page 1 and page 2" in dlg.summary.text()
    dlg.radio_end.setChecked(True)
    assert dlg.insert_index() == 4 and not dlg.page_spin.isEnabled()
    dlg.count_spin.setValue(3)
    assert dlg.count() == 3
