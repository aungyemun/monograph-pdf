"""Page operations can be undone and redone (pages, their overlays and comments come back), and the
page thumbnails have a context menu with the page actions."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-page-undo"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page(width=595 if i != 2 else 842, height=842 if i != 2 else 595)
        page.insert_text((72, 100), f"Page {i + 1}", fontsize=20)
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    assert w.open_path(src)
    yield w, src
    w.close_document(save_session=False)
    w.close()


def _texts(w):
    doc = w._document._backend._doc  # noqa: SLF001
    return [doc[i].get_text().strip() for i in range(doc.page_count)]


def test_delete_reorder_duplicate_undo_redo(win):
    from core.editing.geometry import Rect

    w, src = win
    edit = w._edit  # noqa: SLF001
    edit.create_text_box(3, Rect(72, 200, 150, 30), text="On page four")
    w._left.thumbs.clearSelection()  # noqa: SLF001
    w._left.thumbs.item(1).setSelected(True)  # noqa: SLF001
    w._delete_selected_pages()  # noqa: SLF001
    assert _texts(w) == ["Page 1", "Page 3", "Page 4"]
    assert [o.page_index for o in w._edit.objects.values() if o.text == "On page four"] == [2]  # noqa: SLF001
    w.act_undo.trigger()
    assert _texts(w) == ["Page 1", "Page 2", "Page 3", "Page 4"]
    assert [o.page_index for o in w._edit.objects.values() if o.text == "On page four"] == [3]  # noqa: SLF001
    w.act_redo.trigger()
    assert _texts(w) == ["Page 1", "Page 3", "Page 4"]
    w.act_undo.trigger()
    w._on_thumbs_reordered([3, 0, 1, 2])  # noqa: SLF001
    assert _texts(w)[0] == "Page 4"
    assert [o.page_index for o in w._edit.objects.values() if o.text == "On page four"] == [0]  # noqa: SLF001
    w.act_undo.trigger()
    assert _texts(w) == ["Page 1", "Page 2", "Page 3", "Page 4"]
    # page geometry (the landscape page) survives undo
    doc = w._document._backend._doc  # noqa: SLF001
    assert (doc[2].rect.width, doc[2].rect.height) == (842, 595)
    w.save_document()
    with fitz.open(src) as d:
        assert d.page_count == 4 and "On page four" in d[3].get_text()


def test_undo_history_of_page_operations_is_bounded(win):
    from core.organize import page_snapshot
    from core.organize.page_snapshot import PageStructureCommand

    w, src = win
    for _ in range(page_snapshot.MAX_UNDOABLE + 3):
        w._insert_blank_page()  # noqa: SLF001
    undo = list(w._edit.commands._undo)  # noqa: SLF001
    assert sum(isinstance(c, PageStructureCommand) for c in undo) == page_snapshot.MAX_UNDOABLE


def test_thumbnail_context_menu_offers_the_page_actions(win):
    from PySide6.QtWidgets import QMenu

    w, src = win
    thumbs = w._left.thumbs  # noqa: SLF001
    rect = thumbs.visualItemRect(thumbs.item(2))
    menu = thumbs.build_context_menu(rect.center())
    assert isinstance(menu, QMenu), "no context menu"
    labels = [a.text().replace("&", "") for a in menu.actions() if a.text()]
    for wanted in ("Rotate Clockwise", "Delete Pages", "Duplicate Pages", "Extract Pages…", "Insert Blank Page"):
        assert any(wanted in t for t in labels), (wanted, labels)
    assert thumbs.selected_page_indices() == [2]
