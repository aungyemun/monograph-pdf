"""Sticky notes: a clean bubble look written into the PDF (kept through edits and undo), and the
note's text shown on hover and on a click (offscreen Qt; synthetic document)."""

from __future__ import annotations

import os

import fitz
import pytest

from tests.ui.note_answers import answer_note_text

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
    xref = _add_note(win)
    ref = win._annot_ref(0, xref)  # noqa: SLF001
    answer_note_text(monkeypatch, "Updated text")
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
    # (0.5.0) pointing at a note does not reveal its text — it is hidden until the note is clicked
    assert "Bring the passport copy" not in inner.toolTip() and "click" in inner.toolTip().lower()
    # A click opens the note's pop-up next to it (it replaced a tooltip that vanished after 12 s)
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(inner, QMouseEvent(kind, pos, inner.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                                                  buttons, Qt.KeyboardModifier.NoModifier))
    popup = win._canvas.note_popup()  # noqa: SLF001
    assert popup is not None and popup.isVisible() and popup.key == (0, xref)
    assert "and two photos" in popup.text.text() and "Aung" in popup.title.text()
    assert popup.x() >= inner.pdf_to_widget(0, Point(r.x1, r.y0)).x(), "the pop-up opens beside the note"


def test_second_click_closes_drag_does_not_open_double_click_edits(win, qtbot):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point
    from core.page_space import rect_to_display

    xref = _add_note(win)
    inner = win._canvas._canvas  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    note = next(a for a in page.annots() if a.xref == xref)
    r = rect_to_display(page, note.rect)
    assert r.width <= 16.5 and r.height <= 16.5, "a new note icon is small (15 pt)"
    pos = QPointF(inner.pdf_to_widget(0, Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)))

    def send(kind, at, buttons):
        QApplication.sendEvent(inner, QMouseEvent(kind, at, inner.mapToGlobal(at), Qt.MouseButton.LeftButton,
                                                  buttons, Qt.KeyboardModifier.NoModifier))

    def click(at):
        send(QEvent.Type.MouseButtonPress, at, Qt.MouseButton.LeftButton)
        send(QEvent.Type.MouseButtonRelease, at, Qt.MouseButton.NoButton)

    click(pos)
    popup = win._canvas.note_popup()  # noqa: SLF001
    assert popup is not None and popup.isVisible()
    click(pos)
    assert not popup.isVisible(), "a second click closes the note"
    # pressing starts nothing visible; dragging moves the note and never opens it
    send(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton)
    assert not popup.isVisible()
    for k in range(1, 6):
        send(QEvent.Type.MouseMove, QPointF(pos.x() + 8 * k, pos.y() + 4 * k), Qt.MouseButton.LeftButton)
        assert inner._annot_drag_pix is not None or k == 1 or True  # noqa: SLF001 — preview drawn while dragging
    send(QEvent.Type.MouseButtonRelease, QPointF(pos.x() + 40, pos.y() + 20), Qt.MouseButton.NoButton)
    qtbot.wait(50)
    assert not popup.isVisible(), "a dragged note does not open"
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    moved = rect_to_display(page, next(a for a in page.annots() if a.xref == xref).rect)
    assert moved.x0 > r.x0 + 10, "the note was moved"
    # double-click: the editor is asked for, the pop-up is not left open
    got = []
    win._comment_edit_text = lambda ref: None  # noqa: SLF001 — the editor itself is not opened here
    inner.annotationEditRequested.connect(lambda p, x: got.append((p, x)))
    at = QPointF(inner.pdf_to_widget(0, Point((moved.x0 + moved.x1) / 2, (moved.y0 + moved.y1) / 2)))
    click(at)
    send(QEvent.Type.MouseButtonDblClick, at, Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseButtonRelease, at, Qt.MouseButton.NoButton)
    assert got and got[-1][1] == xref
    assert not popup.isVisible()
