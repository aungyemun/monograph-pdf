"""Sticky notes: a clean bubble look written into the PDF (kept through edits and undo), and the
note's text shown on hover and on a click (offscreen Qt; synthetic document)."""

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
    create_application(["monograph-pdf-notes"])
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


def _ap_bytes(w, xref):
    doc = w._document._backend._doc  # noqa: SLF001
    kind, value = doc.xref_get_key(xref, "AP/N")
    assert kind == "xref"
    return doc.xref_stream(int(value.split()[0]))


def _add_note(w, text="Bring the passport copy\nand two photos"):
    from core.annotations import add_text_comment
    from core.editing.geometry import Point

    xref = add_text_comment(w._document, 0, Point(300, 300), text, color=(1.0, 0.851, 0.4), author="Aung")  # noqa: SLF001
    w._after_annotation(0, "note")  # noqa: SLF001
    return xref


def test_new_note_has_the_clean_bubble_look(win):
    xref = _add_note(win)
    ap = _ap_bytes(win, xref)
    assert b" c\n" in ap and b"B\n" in ap  # rounded (curves), filled + bordered bubble
    assert b"0 g\n" not in ap  # not MuPDF's black square icon
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    note = next(a for a in page.annots() if a.xref == xref)
    assert note.type[1] == "Text" and note.info["content"].startswith("Bring") and note.info["title"] == "Aung"


def test_editing_and_recolouring_keep_the_look_and_undo_restores(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    xref = _add_note(win)
    ref = win._annot_ref(0, xref)  # noqa: SLF001
    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(lambda *a, **k: ("Updated text", True)))
    win._comment_edit_text(ref)  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    assert next(a for a in page.annots() if a.xref == xref).info["content"] == "Updated text"
    assert b"B\n" in _ap_bytes(win, xref)
    win._undo()  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    assert next(a for a in page.annots() if a.xref == xref).info["content"].startswith("Bring")
    assert b"B\n" in _ap_bytes(win, xref)


def test_hover_and_click_show_the_note_text(win, qtbot, monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.page_space import rect_to_display

    xref = _add_note(win)
    inner = win._canvas._canvas  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    note = next(a for a in page.annots() if a.xref == xref)
    r = rect_to_display(page, note.rect)
    from core.editing.geometry import Point

    pos = QPointF(inner.pdf_to_widget(0, Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)))
    QApplication.sendEvent(inner, QMouseEvent(QEvent.Type.MouseMove, pos, inner.mapToGlobal(pos),
                                              Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                              Qt.KeyboardModifier.NoModifier))
    assert "Bring the passport copy" in inner.toolTip() and "Aung" in inner.toolTip()
    # A click opens the note's pop-up next to it (it replaced a tooltip that vanished after 12 s)
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(inner, QMouseEvent(kind, pos, inner.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                                                  buttons, Qt.KeyboardModifier.NoModifier))
    popup = win._canvas.note_popup()  # noqa: SLF001
    assert popup is not None and popup.isVisible() and popup.key == (0, xref)
    assert "and two photos" in popup.text.text() and "Aung" in popup.title.text()
    assert popup.x() >= inner.pdf_to_widget(0, Point(r.x1, r.y0)).x(), "the pop-up opens beside the note"
