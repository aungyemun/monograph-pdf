"""A placed typed signature can be changed after placing (double-click): name, style and ink, in
place, as one undoable step; any other picture can be replaced the same way (offscreen Qt)."""

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
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "ud"))
    create_application(["monograph-pdf-sig-edit"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page(width=595, height=842)
    d.save(src)
    d.close()
    assert w.open_path(src)
    yield w
    if w._edit is not None:  # noqa: SLF001
        w._edit.dirty = False  # noqa: SLF001
    w.close_document(save_session=False)
    w.close()


def _place_typed(w, text="Aung Ye Mun"):
    from core.annotations.stamp_library import png_bytes_to_library
    from core.editing.geometry import Rect
    from core.signatures.ops import signature_box
    from ui.security_dialogs import TypedSignatureDialog

    dlg = TypedSignatureDialog(w)
    dlg.name.setText(text)
    box = signature_box(0, Rect(100, 600, 240, 70), png_bytes_to_library(dlg.signature_png()))
    box.signature = dlg.spec()
    w._edit.add_image(box)  # noqa: SLF001
    return box


def test_typed_signature_keeps_how_it_was_made(win):
    box = _place_typed(win)
    assert box.signature["kind"] == "typed" and box.signature["text"] == "Aung Ye Mun"
    again = type(box).from_dict(box.to_dict())  # session recovery keeps it too
    assert again.signature == box.signature


def test_double_click_changes_name_and_ink_in_place_with_undo(win, qtbot, monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point
    from ui.security_dialogs import TypedSignatureDialog

    box = _place_typed(win)
    before_path, before_rect = box.source_path, box.rect
    opened = {}

    def fake_exec(dlg):
        opened["text"] = dlg.name.text()
        opened["title"] = dlg.windowTitle()
        dlg.name.setText("A. Y. Mun")
        dlg.ink.setCurrentIndex(dlg.ink.findData("#14532d"))
        return dlg.DialogCode.Accepted

    monkeypatch.setattr(TypedSignatureDialog, "exec", fake_exec)
    inner = win._canvas._canvas  # noqa: SLF001
    p = QPointF(inner.pdf_to_widget(0, Point(box.rect.cx, box.rect.cy)))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind, button, buttons in ((QEvent.Type.MouseButtonPress, left, left), (QEvent.Type.MouseButtonRelease, left, none),
                                  (QEvent.Type.MouseButtonDblClick, left, left), (QEvent.Type.MouseButtonRelease, left, none)):
        QApplication.sendEvent(inner, QMouseEvent(kind, p, inner.mapToGlobal(p), button, buttons, Qt.KeyboardModifier.NoModifier))
    qtbot.wait(20)
    live = win._edit.images[box.object_id]  # noqa: SLF001
    assert opened == {"text": "Aung Ye Mun", "title": "Edit Signature"}  # opened on the placed signature
    assert live.signature["text"] == "A. Y. Mun" and live.signature["color"] == "#14532d"
    assert live.source_path != before_path
    assert abs(live.rect.cx - before_rect.cx) < 0.01 and abs(live.rect.h - before_rect.h) < 0.01  # same place
    win._undo()  # noqa: SLF001
    live = win._edit.images[box.object_id]  # noqa: SLF001
    assert live.source_path == before_path and live.signature["text"] == "Aung Ye Mun"
