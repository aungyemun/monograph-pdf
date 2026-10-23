"""A field just added in Forms mode can be filled by double-clicking it (every field kind), and a
double-click on a field never starts editing the page text printed underneath it."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-field-dblclick"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    src = tmp_path / "page.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((80, 214), "If you are a foreign resident in Japan, you can apply", fontsize=12)  # under the field
    doc.save(str(src))
    doc.close()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _double_click(w, field, qtbot):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point

    inner = w._canvas._canvas  # noqa: SLF001
    p = QPointF(inner.pdf_to_widget(field.page_index, Point(field.rect.cx, field.rect.cy)))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind, button, buttons in (
        (QEvent.Type.MouseButtonPress, left, left),
        (QEvent.Type.MouseButtonRelease, left, none),
        (QEvent.Type.MouseButtonDblClick, left, left),
        (QEvent.Type.MouseButtonRelease, left, none),
    ):
        QApplication.sendEvent(inner, QMouseEvent(kind, p, inner.mapToGlobal(p), button, buttons,
                                                  Qt.KeyboardModifier.NoModifier))
    qtbot.wait(20)
    return inner


def _new_field(w, kind):
    from core.editing.edit_model import EditTool, WorkspaceMode
    from core.editing.geometry import Rect

    w._set_mode(WorkspaceMode.FORMS)  # noqa: SLF001
    field = w._edit.create_form_field(0, Rect(70, 195, 300, 40 if kind == "multiline" else 26), kind)  # noqa: SLF001
    w._edit.tool = EditTool.FORM_SELECT  # noqa: SLF001  as after Forms ▸ Add Field
    return field


@pytest.mark.parametrize("kind", ["text", "multiline", "date"])
def test_double_click_types_into_a_new_text_field(win, qtbot, kind):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    field = _new_field(win, kind)
    inner = _double_click(win, field, qtbot)
    ed = inner.field_editor
    assert ed is not None, "double-click must open the field for typing"
    QTest.keyClicks(ed, "Hello")
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    qtbot.wait(10)
    assert field.value == "Hello"
    assert not win._edit.native_replacements  # noqa: SLF001  the printed text underneath was not touched


def test_double_click_in_select_mode_keeps_typing(win, qtbot):
    from PySide6.QtTest import QTest

    from core.editing.edit_model import EditTool, WorkspaceMode

    field = _new_field(win, "text")
    win._set_mode(WorkspaceMode.EDIT)  # noqa: SLF001
    win._edit.tool = EditTool.SELECT  # noqa: SLF001
    inner = _double_click(win, field, qtbot)
    assert inner.field_editor is not None
    QTest.keyClicks(inner.field_editor, "abc")
    inner.close_field_editor(commit=True)
    assert field.value == "abc" and not win._edit.native_replacements  # noqa: SLF001


def test_double_click_checkbox_ticks_once(win, qtbot):
    field = _new_field(win, "checkbox")
    assert not field.checked
    _double_click(win, field, qtbot)
    assert field.checked  # the first click ticked it; the double-click does not untick it again


def test_double_click_dropdown_offers_its_choices(win, qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMenu

    field = _new_field(win, "dropdown")
    offered = []

    def choose_second() -> None:
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(20, choose_second)
            return
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        offered.extend(a.text() for a in menu.actions())
        menu.setActiveAction(menu.actions()[1])
        QTest.keyClick(menu, Qt.Key.Key_Return)  # as a user picks the second choice

    QTimer.singleShot(20, choose_second)
    _double_click(win, field, qtbot)
    assert offered == field.options and field.value == field.options[1]


def test_double_click_signature_field_explains_instead_of_editing(win, qtbot):
    field = _new_field(win, "signature")
    inner = _double_click(win, field, qtbot)
    assert inner.field_editor is None and not win._edit.native_replacements  # noqa: SLF001
