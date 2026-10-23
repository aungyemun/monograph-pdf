"""Every object a user types text into opens for editing on double-click: a new text box, a sticky
note, a callout and a stamp (form fields: test_field_double_click.py; signatures:
test_signature_edit.py)."""

from __future__ import annotations

import os

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
    create_application(["monograph-pdf-text-entry"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((72, 700), "Body text", fontsize=12)
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _double_click_at(w, x: float, y: float, qtbot):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point

    inner = w._canvas._canvas  # noqa: SLF001
    w._canvas.go_to_page(0)  # noqa: SLF001
    qtbot.wait(20)
    p = QPointF(inner.pdf_to_widget(0, Point(x, y)))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind, button, buttons in ((QEvent.Type.MouseButtonPress, left, left),
                                  (QEvent.Type.MouseButtonRelease, left, none),
                                  (QEvent.Type.MouseButtonDblClick, left, left),
                                  (QEvent.Type.MouseButtonRelease, left, none)):
        QApplication.sendEvent(inner, QMouseEvent(kind, p, inner.mapToGlobal(p), button, buttons,
                                                  Qt.KeyboardModifier.NoModifier))
    qtbot.wait(20)
    return inner


def _select_tool(w):
    from core.editing.edit_model import EditTool

    w.act_select_tool.setChecked(True)
    w._edit.tool = EditTool.SELECT  # noqa: SLF001


def test_new_text_box_opens_for_typing(win, qtbot):
    from PySide6.QtTest import QTest

    from core.editing.geometry import Rect

    w = win
    box = w._edit.create_text_box(0, Rect(100, 100, 200, 40), text="Old")  # noqa: SLF001
    oid = getattr(box, "object_id", box)
    _select_tool(w)
    inner = _double_click_at(w, 150, 120, qtbot)
    editor = inner.text_editor
    assert editor is not None, "double-click must open the text box for typing"
    editor.selectAll()
    QTest.keyClicks(editor, "New words")
    inner.close_text_editor(commit=True)
    assert w._edit.objects[oid].text == "New words"  # noqa: SLF001


@pytest.mark.parametrize("kind", ["note", "callout"])
def test_comment_double_click_asks_for_its_text(win, qtbot, monkeypatch, kind):
    from PySide6.QtWidgets import QInputDialog

    from core.annotations.ops import add_callout, add_text_comment
    from core.editing.geometry import Point, Rect

    w = win
    if kind == "note":
        w._run_annot_command(0, lambda: add_text_comment(w._document, 0, Point(300, 300), "Old note"), "Add Note")  # noqa: SLF001
        x, y = 305, 305
    else:
        w._run_annot_command(0, lambda: add_callout(w._document, 0, Rect(300, 300, 160, 50), "Old callout")[0], "Add Callout")  # noqa: SLF001
        x, y = 380, 325
    w._after_annotation(0, "")  # noqa: SLF001
    _select_tool(w)
    asked = []

    def fake(parent, title, label, current, *a, **k):
        asked.append(current)
        return ("Edited text", True)

    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(fake))
    _double_click_at(w, x, y, qtbot)
    assert asked and asked[0].startswith("Old"), f"double-click did not open the {kind} for editing"
    annot = next(iter(w._document._backend._doc[0].annots()))  # noqa: SLF001
    assert annot.info["content"] == "Edited text"
