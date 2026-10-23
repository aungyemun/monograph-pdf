"""Regression (0.4.0 crash, access violation): add a text box, type, select the text, then choose a
font from the font list. Opening the list closed the text editor, which rebuilt the Properties panel
and deleted the font box whose list was open — Monograph PDF then crashed. Also: the first click on
the toolbar's font box while typing only flashed the list, and the mouse wheel over a closed font box
changed the font."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-font-list"])
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page()
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1400, 900)
    w.show()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _typing_with_selection(w, qtbot, y: float = 100):
    from core.editing.geometry import Rect

    box = w._edit.create_text_box(0, Rect(100, y, 260, 40), text="")  # noqa: SLF001
    oid = getattr(box, "object_id", box)
    w._edit.select([oid])  # noqa: SLF001
    w._on_edit_changed()  # noqa: SLF001
    qtbot.wait(150)
    inner = w._canvas._canvas  # noqa: SLF001
    inner.open_text_editor(oid)
    qtbot.wait(50)
    QTest.keyClicks(inner.text_editor, "Hello world")
    inner.text_editor.selectAll()
    qtbot.wait(50)
    return oid


def _pick(p, qtbot, family: str) -> None:
    if not p.view().window().isVisible():
        p.showPopup()
    qtbot.wait(150)
    assert p.view().window().isVisible(), "the font list must stay open"
    row = p.findText(family, Qt.MatchFlag.MatchFixedString)
    if row < 0:
        row = 3
    index = p.model().index(row, 0)
    p.view().scrollTo(index)
    qtbot.wait(20)
    QTest.mouseClick(p.view().viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     p.view().visualRect(index).center())
    qtbot.wait(300)


def _panel_picker(w):
    from ui.font_picker import FontPicker

    pickers = [x for x in w._inspector.findChildren(FontPicker) if x.isVisible()]  # noqa: SLF001
    return pickers[-1] if pickers else None


def test_choosing_a_font_in_the_properties_panel_while_typing_does_not_crash(win, qtbot):
    oid = _typing_with_selection(win, qtbot)
    p = _panel_picker(win)
    assert p is not None
    p.showPopup()
    qtbot.wait(300)  # the editor closes and the panel would have been rebuilt here
    assert p.view().window().isVisible(), "the panel was rebuilt under the open list"
    family = p.itemText(5)
    _pick(p, qtbot, family)
    assert win._edit.objects[oid].style.font_family == family  # noqa: SLF001
    qtbot.wait(300)  # the postponed rebuild runs after the list closed
    assert _panel_picker(win) is not None


def test_first_click_on_the_toolbar_font_box_while_typing_keeps_the_list_open(win, qtbot):
    oid = _typing_with_selection(win, qtbot)
    p = win._font_family  # noqa: SLF001
    p.showPopup()
    qtbot.wait(300)  # the editor closes; the context toolbar would have been rebuilt here
    assert p.view().window().isVisible(), "rebuilding the toolbar closed the list after the first click"
    family = p.itemText(7)
    _pick(p, qtbot, family)
    assert win._edit.objects[oid].style.font_family == family  # noqa: SLF001


def test_mouse_wheel_over_a_closed_font_box_does_not_change_the_font(win, qtbot):
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Rect

    box = win._edit.create_text_box(0, Rect(100, 100, 260, 40), text="Hello")  # noqa: SLF001
    oid = getattr(box, "object_id", box)
    win._edit.select([oid])  # noqa: SLF001
    win._on_edit_changed()  # noqa: SLF001
    qtbot.wait(150)
    before = win._edit.objects[oid].style.font_family  # noqa: SLF001
    for p in (win._font_family, _panel_picker(win)):  # noqa: SLF001
        pos = QPointF(p.width() / 2, p.height() / 2)
        for _ in range(5):
            QApplication.sendEvent(p, QWheelEvent(pos, QPointF(p.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                                                  QPoint(0, -120), Qt.MouseButton.NoButton,
                                                  Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                                                  False))
        qtbot.wait(100)
    assert win._edit.objects[oid].style.font_family == before  # noqa: SLF001


def test_panel_rebuild_never_deletes_widgets_immediately(win, qtbot):
    from shiboken6 import isValid

    from core.editing.geometry import Rect

    box = win._edit.create_text_box(0, Rect(100, 100, 260, 40), text="Hello")  # noqa: SLF001
    oid = getattr(box, "object_id", box)
    win._edit.select([oid])  # noqa: SLF001
    win._on_edit_changed()  # noqa: SLF001
    qtbot.wait(150)
    old = _panel_picker(win)
    win._inspector._clear_rows()  # noqa: SLF001
    assert isValid(old), "deleted while it might still be running its own code"
    qtbot.wait(50)
    assert not isValid(old), "removed after the current event"
