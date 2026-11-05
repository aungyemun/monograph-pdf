"""The Select Text tool in the real main window (offscreen): mouse selection, Ctrl+C / Ctrl+A / Esc,
context-menu Copy, permissions, and that selecting never changes the document.

Selection coordinates are checked against MuPDF's own search hits (turned into display space and then
into widget pixels), not against the selection code's own geometry.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-text-selection"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1300, 950)
    win.show()
    msgs: list[str] = []
    win.statusBar().messageChanged.connect(lambda m: msgs.append(m))
    win._test_msgs = msgs  # noqa: SLF001
    yield win
    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pdf(path: Path, pages: list[list[str]], *, rotation: int = 0, fontname: str = "helv", **save) -> Path:
    d = fitz.open()
    for lines in pages:
        page = d.new_page(width=595, height=842)
        for i, t in enumerate(lines):
            page.insert_text((72, 120 + 28 * i), t, fontsize=14, fontname=fontname)
        page.set_rotation(rotation)
    d.save(path, **save)
    d.close()
    return path


def _inner(win):
    return win._canvas._canvas  # noqa: SLF001


def _settle(qtbot, win, ms: int = 60) -> None:
    qtbot.wait(ms)


def _send(widget, kind, pos, *, buttons=None, mods=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    types = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease, "double": QEvent.Type.MouseButtonDblClick}
    left = Qt.MouseButton.LeftButton
    btn = Qt.MouseButton.NoButton if kind == "move" else left
    held = buttons if buttons is not None else (Qt.MouseButton.NoButton if kind == "release" else left)
    mods = mods if mods is not None else Qt.KeyboardModifier.NoModifier
    p = QPointF(pos)
    ev = QMouseEvent(types[kind], p, widget.mapToGlobal(p), btn, held, mods)
    QApplication.sendEvent(widget, ev)


def _word_widget_rect(win, page_index: int, word: str, nth: int = 0):
    """Widget-pixel rectangle of ``word`` from MuPDF's search (independent of the selection code)."""
    from PySide6.QtCore import QRectF

    from core.editing.geometry import Point
    from core.page_space import rect_to_display

    doc = win._document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    r = rect_to_display(page, page.search_for(word)[nth])
    inner = _inner(win)
    p0 = inner.pdf_to_widget_f(page_index, Point(r.x0, r.y0))
    p1 = inner.pdf_to_widget_f(page_index, Point(r.x1, r.y1))
    return QRectF(p0, p1).normalized(), page.rotation


def _ends(rect, rotation: int, letters: int):
    """Press / release points in the outer quarter of the first and last letter, in reading
    direction (a press in a letter's first half is before it, in its second half after it)."""
    inset = 0.25 / letters
    from PySide6.QtCore import QPointF

    cx, cy = rect.center().x(), rect.center().y()
    dx, dy = rect.width() * inset, rect.height() * inset
    if rotation == 0:
        return QPointF(rect.left() + dx, cy), QPointF(rect.right() - dx, cy)
    if rotation == 90:
        return QPointF(cx, rect.top() + dy), QPointF(cx, rect.bottom() - dy)
    if rotation == 180:
        return QPointF(rect.right() - dx, cy), QPointF(rect.left() + dx, cy)
    return QPointF(cx, rect.bottom() - dy), QPointF(cx, rect.top() + dy)


def _drag(win, qtbot, a, b, steps: int = 6):
    from PySide6.QtCore import QPointF

    inner = _inner(win)
    _send(inner, "press", a)
    for k in range(1, steps + 1):
        t = k / steps
        _send(inner, "move", QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    _send(inner, "release", b)
    _settle(qtbot, win, 20)


def _iou(a, b) -> float:
    inter = a.intersected(b)
    if inter.isEmpty():
        return 0.0
    ua = a.united(b)
    return (inter.width() * inter.height()) / (ua.width() * ua.height())


def _open_select_text(win, qtbot, path: Path, zoom: float | None = None):
    assert win.open_path(path)
    _settle(qtbot, win, 80)
    if zoom is not None:
        win._canvas.set_manual_zoom(zoom)  # noqa: SLF001
        _settle(qtbot, win, 80)
    win.act_text_select_tool.trigger()
    _settle(qtbot, win, 10)


# -- the tool -----------------------------------------------------------------------------------

def test_tool_is_separate_from_object_selection(window, qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from core.editing.edit_model import EditTool

    src = _pdf(tmp_path / "a.pdf", [["alpha beta gamma"]])
    _open_select_text(window, qtbot, src)
    inner = _inner(window)
    assert window._edit.tool == EditTool.TEXT_SELECT  # noqa: SLF001
    assert inner.cursor().shape() == Qt.CursorShape.IBeamCursor
    assert window.act_text_select_tool.isChecked() and not window.act_select_tool.isChecked()
    window.act_select_tool.trigger()
    assert window._edit.tool == EditTool.SELECT and inner.cursor().shape() == Qt.CursorShape.ArrowCursor  # noqa: SLF001
    assert not inner.text_select.has_selection


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0])
def test_drag_selects_exactly_the_word_at_every_zoom_and_rotation(window, qtbot, tmp_path, zoom, rotation):
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / f"w{rotation}.pdf", [["alpha TARGETWORD omega"]], rotation=rotation)
    _open_select_text(window, qtbot, src, zoom=zoom)
    word, rot = _word_widget_rect(window, 0, "TARGETWORD")
    a, b = _ends(word, rot, len("TARGETWORD"))
    _drag(window, qtbot, a, b)
    inner = _inner(window)
    assert inner.text_select.selected_text() == "TARGETWORD"
    # the painted selection lies on the rendered word
    rects = inner.text_select.selected_page_rects(0)
    assert len(rects) == 1
    from core.editing.geometry import Point

    x0, y0, x1, y1 = rects[0]
    shown = QRectF(inner.pdf_to_widget_f(0, Point(x0, y0)), inner.pdf_to_widget_f(0, Point(x1, y1))).normalized()
    assert _iou(shown, word) > 0.6, (shown, word)
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == "TARGETWORD"


def test_partial_word_and_lines_and_paragraphs(window, qtbot, tmp_path):
    src = _pdf(tmp_path / "p.pdf", [["first line of text", "second line of text", "third line"]])
    _open_select_text(window, qtbot, src, zoom=1.5)
    inner = _inner(window)
    # partial word: from inside "first" to inside "line"
    r1, _ = _word_widget_rect(window, 0, "first")
    r2, _ = _word_widget_rect(window, 0, "line", 0)
    from PySide6.QtCore import QPointF

    a = QPointF(r1.left() + r1.width() * 0.45, r1.center().y())  # after "fi" / "fir"
    b = QPointF(r2.left() + r2.width() * 0.55, r2.center().y())
    _drag(window, qtbot, a, b)
    got = inner.text_select.selected_text()
    assert got.startswith(("rst", "st")) and got.endswith(("li", "lin")) and "\n" not in got
    # multiple lines: from "first" to the end of "second line of text"
    r3, _ = _word_widget_rect(window, 0, "text", 1)
    _drag(window, qtbot, QPointF(r1.left() + 1, r1.center().y()), QPointF(r3.right() - 1, r3.center().y()))
    assert inner.text_select.selected_text() == "first line of text\nsecond line of text"


def test_double_click_word_and_triple_click_paragraph(window, qtbot, tmp_path):
    src = tmp_path / "d.pdf"
    d = fitz.open()
    page = d.new_page()
    # one paragraph of three wrapped lines, and a second paragraph further down
    page.insert_textbox(fitz.Rect(72, 100, 300, 200), "one two three four five six seven eight nine ten",
                        fontsize=14)
    page.insert_text((72, 400), "another paragraph", fontsize=14)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src, zoom=1.5)
    inner = _inner(window)
    r, _ = _word_widget_rect(window, 0, "two")
    c = r.center()
    _send(inner, "press", c)
    _send(inner, "release", c)
    _send(inner, "double", c)
    _send(inner, "release", c)
    assert inner.text_select.selected_text() == "two"
    _send(inner, "press", c)  # third click in quick succession
    _send(inner, "release", c)
    para = inner.text_select.selected_text()
    assert para.replace("\n", " ") == "one two three four five six seven eight nine ten"
    assert para.count("\n") >= 1 and "another" not in para


def test_shift_click_and_shift_arrows_extend(window, qtbot, tmp_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    src = _pdf(tmp_path / "s.pdf", [["alpha beta gamma"]])
    _open_select_text(window, qtbot, src, zoom=1.5)
    inner = _inner(window)
    ra, _ = _word_widget_rect(window, 0, "alpha")
    rb, _ = _word_widget_rect(window, 0, "beta")
    _send(inner, "press", QPointF(ra.left() + 1, ra.center().y()))
    _send(inner, "release", QPointF(ra.left() + 1, ra.center().y()))
    shift = Qt.KeyboardModifier.ShiftModifier
    _send(inner, "press", QPointF(rb.right() - 1, rb.center().y()), mods=shift)
    _send(inner, "release", QPointF(rb.right() - 1, rb.center().y()), mods=shift)
    assert inner.text_select.selected_text() == "alpha beta"
    QTest.keyClick(inner, Qt.Key.Key_Right, shift)
    QTest.keyClick(inner, Qt.Key.Key_Right, shift)
    assert inner.text_select.selected_text() == "alpha beta g"
    QTest.keyClick(inner, Qt.Key.Key_Left, shift)
    assert inner.text_select.selected_text() == "alpha beta "
    QTest.keyClick(inner, Qt.Key.Key_Escape)
    assert not inner.text_select.has_selection


def test_select_all_copies_the_page_and_esc_clears(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "all.pdf", [["page one alpha", "page one beta"], ["page two"]])
    _open_select_text(window, qtbot, src)
    window._select_all()  # noqa: SLF001 — Ctrl+A in the Select Text tool
    window._copy()  # noqa: SLF001 — Ctrl+C
    assert QApplication.clipboard().text() == "page one alpha\npage one beta"
    inner = _inner(window)
    assert inner.text_select.key(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Escape, 0)
    assert not inner.text_select.has_selection


def test_keyboard_shortcuts_reach_the_actions(window, qtbot, tmp_path):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "k.pdf", [["shortcut text here"]])
    _open_select_text(window, qtbot, src)
    assert window.act_copy.shortcut() == QKeySequence(QKeySequence.StandardKey.Copy)
    assert QKeySequence("Ctrl+A") in window.act_select_all.shortcuts() or \
        window.act_select_all.shortcut() == QKeySequence("Ctrl+A")
    window.act_select_all.trigger()
    window.act_copy.trigger()
    assert QApplication.clipboard().text() == "shortcut text here"


def test_selection_across_two_pages(window, qtbot, tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "mp.pdf", [["end of page one", "last line one"], ["first line two", "more two"]])
    _open_select_text(window, qtbot, src, zoom=0.5)
    r1, _ = _word_widget_rect(window, 0, "last")
    r2, _ = _word_widget_rect(window, 1, "first")
    _drag(window, qtbot, QPointF(r1.left() - 0.5, r1.center().y()), QPointF(r2.right() + 0.5, r2.center().y()), steps=12)
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == "last line one\n\nfirst"


def test_context_menu_copy(window, qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "cm.pdf", [["context menu words"]])
    _open_select_text(window, qtbot, src, zoom=1.5)
    inner = _inner(window)
    r, _ = _word_widget_rect(window, 0, "menu")
    _drag(window, qtbot, QPointF(r.left() + 1, r.center().y()), QPointF(r.right() - 1, r.center().y()))
    seen = {}

    def fake_exec(menu, *a, **k):
        acts = {a.text(): a for a in menu.actions()}
        seen["enabled"] = acts["Copy"].isEnabled()
        return acts["Copy"]

    monkeypatch.setattr(type(inner), "exec_context_menu", staticmethod(fake_exec))
    QApplication.clipboard().setText("before")
    QApplication.sendEvent(inner, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, r.center().toPoint(),
                                                    inner.mapToGlobal(r.center().toPoint())))
    assert seen["enabled"] and QApplication.clipboard().text() == "menu"


def test_japanese_selection_and_copy(window, qtbot, tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    line = "東京タワーはとても高いです。English 123"
    src = _pdf(tmp_path / "jp.pdf", [[line, "ひらがな カタカナ 漢字"]], fontname="japan")
    _open_select_text(window, qtbot, src, zoom=1.5)
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == line + "\nひらがな カタカナ 漢字"
    r, _ = _word_widget_rect(window, 0, "タワー")
    inner = _inner(window)
    _send(inner, "double", r.center())
    _send(inner, "release", r.center())
    assert inner.text_select.selected_text() == "タワー"
    _drag(window, qtbot, QPointF(r.left() + 1, r.center().y()), QPointF(r.right() - 1, r.center().y()))
    assert inner.text_select.selected_text() == "タワー"


def test_selecting_and_copying_never_changes_the_document(window, qtbot, tmp_path):
    src = _pdf(tmp_path / "safe.pdf", [["do not change me", "second line"], ["page two"]])
    before = _sha(src)
    with fitz.open(src) as d:
        xrefs = d.xref_length()
    _open_select_text(window, qtbot, src)
    for _ in range(3):
        window._select_all()  # noqa: SLF001
        window._copy()  # noqa: SLF001
    from PySide6.QtCore import QPointF

    r, _ = _word_widget_rect(window, 0, "change")
    _drag(window, qtbot, QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
    window._copy()  # noqa: SLF001
    assert not window._edit.dirty  # noqa: SLF001
    assert "*" not in window.windowTitle()
    live = window._document._backend._doc  # noqa: SLF001
    assert live.xref_length() == xrefs
    assert not any(list(p.annots()) for p in live)
    asked = []
    window._ask_save_changes = lambda *a, **k: asked.append(1)  # noqa: SLF001 — must not be needed
    window.close_document(save_session=False)
    assert _sha(src) == before


def test_copy_respects_the_copy_permission(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    perms = int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY)  # copying not allowed
    src = _pdf(tmp_path / "noc.pdf", [["secret selectable text"]],
               encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-pw", user_pw="", permissions=perms)
    _open_select_text(window, qtbot, src)
    window._select_all()  # noqa: SLF001
    QApplication.clipboard().setText("unchanged")
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == "unchanged"
    assert any("not allowed" in m for m in window._test_msgs)  # noqa: SLF001


def test_encrypted_document_that_allows_copying(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "enc.pdf", [["encrypted but copyable"]],
               encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    assert window.open_path(src, password="u")
    _settle(qtbot, window, 60)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == "encrypted but copyable"


def test_marked_but_unapplied_redaction_is_copied_with_a_warning(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "red.pdf", [["public SECRET-ALPHA public"]])
    _open_select_text(window, qtbot, src)
    from core.redaction import mark_text

    mark_text(window._document, 0, "SECRET-ALPHA")  # noqa: SLF001
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert "SECRET-ALPHA" in QApplication.clipboard().text()
    assert any("marked for redaction" in m for m in window._test_msgs)  # noqa: SLF001


def test_image_only_page_explains_there_is_no_text(window, qtbot, tmp_path):
    src = tmp_path / "img.pdf"
    d = fitz.open()
    page = d.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
    pix.clear_with(30)
    page.insert_image(fitz.Rect(50, 50, 400, 400), pixmap=pix)
    d.save(src)
    d.close()
    _open_select_text(window, qtbot, src)
    from PySide6.QtCore import QPointF

    from core.editing.geometry import Point

    p = _inner(window).pdf_to_widget_f(0, Point(200, 200))
    _drag(window, qtbot, p, QPointF(p.x() + 40, p.y() + 10))
    assert not _inner(window).text_select.has_selection
    assert any("no selectable text" in m for m in window._test_msgs)  # noqa: SLF001
    window._select_all()  # noqa: SLF001
    assert any("has no selectable text" in m for m in window._test_msgs)  # noqa: SLF001
    assert not window._edit.dirty  # noqa: SLF001 — and no OCR was started


def test_object_clipboard_still_works_and_text_boxes_reach_the_system_clipboard(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Rect

    src = _pdf(tmp_path / "obj.pdf", [["page text"]])
    assert window.open_path(src)
    edit = window._edit  # noqa: SLF001
    box = edit.create_text_box(0, Rect(100, 300, 200, 30), text="box words", auto_match=False)
    edit.select([box.object_id])
    window._copy()  # noqa: SLF001 — Select tool: object copy
    assert QApplication.clipboard().text() == "box words"
    n = len(edit.objects)
    window._paste()  # noqa: SLF001
    assert len(edit.objects) == n + 1
    # switching to Select Text and back does not lose the object clipboard
    window.act_text_select_tool.trigger()
    window.act_select_tool.trigger()
    window._paste()  # noqa: SLF001
    assert len(edit.objects) == n + 2


def test_form_field_editor_keeps_its_own_copy(window, qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    src = tmp_path / "form.pdf"
    d = fitz.open()
    page = d.new_page()
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 90, 300, 112), "field text"
    page.add_widget(w)
    d.save(src)
    d.close()
    assert window.open_path(src)
    _settle(qtbot, window, 60)
    inner = _inner(window)
    field = next(f for f in window._edit.fields.values() if f.name == "name")  # noqa: SLF001
    assert inner.open_field_editor(field)
    ed = inner.field_editor
    ed.setFocus()
    ed.selectAll()
    QApplication.clipboard().setText("before")
    QTest.keySequence(ed, "Ctrl+C")
    assert QApplication.clipboard().text() == "field text"
    assert not window._edit.dirty  # noqa: SLF001


def test_cache_follows_page_rotation_and_invalidation(window, qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    src = _pdf(tmp_path / "rot.pdf", [["rotate me later"], ["other page"]])
    _open_select_text(window, qtbot, src)
    window._select_all()  # noqa: SLF001
    assert _inner(window).text_select.has_selection
    assert window._rotate_pages([0], 90)  # noqa: SLF001
    _settle(qtbot, window, 60)
    window.act_text_select_tool.trigger()
    window._select_all()  # noqa: SLF001
    window._copy()  # noqa: SLF001
    assert QApplication.clipboard().text() == "rotate me later"
    rects = _inner(window).text_select.selected_page_rects(0)
    page = window._document._backend._doc.load_page(0)  # noqa: SLF001
    x0, y0, x1, y1 = rects[0]
    assert (y1 - y0) > (x1 - x0)  # the line now runs downwards on the turned page
    assert x1 <= page.rect.width + 1 and y1 <= page.rect.height + 1


def test_dragging_past_the_bottom_of_the_view_scrolls_and_extends(window, qtbot, tmp_path):
    from PySide6.QtCore import QPointF

    pages = [[f"page {p + 1} line {i + 1}" for i in range(20)] for p in range(4)]
    src = _pdf(tmp_path / "long.pdf", pages)
    _open_select_text(window, qtbot, src, zoom=1.5)
    inner = _inner(window)
    bar = window._canvas.verticalScrollBar()  # noqa: SLF001
    start = bar.value()
    r, _ = _word_widget_rect(window, 0, "page 1 line 1")
    _send(inner, "press", QPointF(r.left() - 0.5, r.center().y()))
    vp = window._canvas.viewport()  # noqa: SLF001
    bottom = inner.mapFromGlobal(vp.mapToGlobal(vp.rect().bottomLeft())) + __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(int(r.left()) + 5, -5)
    bottom.setX(int(r.center().x()))
    _send(inner, "move", QPointF(bottom))
    qtbot.waitUntil(lambda: bar.value() > start + 200, timeout=5000)
    _send(inner, "release", QPointF(bottom))
    text = inner.text_select.selected_text()
    assert text.startswith("page 1 line 1\npage 1 line 2") and len(text.splitlines()) > 5
    assert not window._edit.dirty  # noqa: SLF001


def test_selection_geometry_at_200_percent_display_scaling(tmp_path):
    """A separate process with Qt's display scale factor 2 (like 200 % Windows scaling)."""
    import subprocess
    import sys
    import textwrap

    script = tmp_path / "scaled.py"
    script.write_text(textwrap.dedent(f"""
        import faulthandler, os, sys
        faulthandler.dump_traceback_later(60, exit=True)  # a hang prints where it is and ends the process
        sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})
        os.environ["QT_SCALE_FACTOR"] = "2"
        for n in ("RUNTIME_DIR", "UPDATES_DIR", "DIAGNOSTICS_DIR", "USER_DATA_DIR"):
            os.environ["MONOGRAPH_PDF_" + n] = {str(tmp_path)!r} + "/" + n.lower()
        os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"
        import fitz
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from core.editing.geometry import Point
        from core.page_space import rect_to_display
        from ui.main_window import MainWindow, create_application
        src = {str(tmp_path / "s.pdf")!r}
        d = fitz.open(); d.new_page().insert_text((72, 200), "left SCALEDWORD right", fontsize=14); d.save(src); d.close()
        app = create_application(["scaled"]); w = MainWindow(); w.resize(1200, 900); w.show(); app.processEvents()
        assert w.open_path(src); app.processEvents()
        w.act_text_select_tool.trigger()
        inner = w._canvas._canvas
        page = w._document._backend._doc.load_page(0)
        r = rect_to_display(page, page.search_for("SCALEDWORD")[0])
        a = inner.pdf_to_widget_f(0, Point(r.x0 + 1, (r.y0 + r.y1) / 2))
        b = inner.pdf_to_widget_f(0, Point(r.x1 - 1, (r.y0 + r.y1) / 2))
        def send(t, p, held):
            ev = QMouseEvent(t, QPointF(p), inner.mapToGlobal(QPointF(p)), Qt.MouseButton.LeftButton, held, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(inner, ev)
        send(QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton)
        send(QEvent.Type.MouseMove, b, Qt.MouseButton.LeftButton)
        send(QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)
        print("DPR", inner.devicePixelRatioF(), flush=True)
        print("TEXT", inner.text_select.selected_text(), flush=True)
        os._exit(0)
    """), encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", MONOGRAPH_PDF_HEADLESS="1")
    log = tmp_path / "scaled.log"
    # output into a file, not a pipe: a pipe kept open by anything the child started could block reading
    with open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen([sys.executable, str(script)], stdout=fh, stderr=subprocess.STDOUT, env=env)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:  # never hang the whole test run
            proc.kill()
            proc.wait(timeout=10)
            pytest.fail("the scaled window did not finish: " + log.read_text(encoding="utf-8", errors="replace"))
    text = log.read_text(encoding="utf-8", errors="replace")
    assert "TEXT SCALEDWORD" in text, text
    assert "DPR 2.0" in text, text
