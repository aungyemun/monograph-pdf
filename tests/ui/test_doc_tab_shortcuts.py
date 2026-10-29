"""Ctrl+Tab / Ctrl+Shift+Tab cycle document tabs (0.5.1 regression).

0.5.0 registered both key sequences twice (a QAction and a QShortcut, both application-wide). Qt
treats two active shortcuts with the same sequence as ambiguous and triggers neither, so the keys did
nothing. Earlier tests called _cycle_doc_tab() directly and could not notice. These tests press the
keys through Qt's shortcut system.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
fitz = pytest.importorskip("fitz")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def _pdf(path: Path, pages: int, word: str) -> Path:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 100), f"{word} page {i + 1}", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def _form_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.rect = fitz.Rect(72, 120, 300, 145)
    w.field_value = ""
    page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-tab-shortcuts"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    for sess in list(win._sessions):  # noqa: SLF001
        sess.edit.dirty = False
    win.close_document(save_session=False)
    win.close()


def _names(win) -> list[str]:
    return [s.document.name for s in win._sessions]  # noqa: SLF001


def _active(win) -> str:
    return win._document.name if win._document is not None else ""  # noqa: SLF001


def _press(win, key, mods) -> None:
    target = QApplication.focusWidget() or win
    QTest.keyClick(target, key, mods)
    QApplication.processEvents()


def _ctrl_tab(win) -> None:
    _press(win, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)


def _ctrl_shift_tab(win) -> None:
    _press(win, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)


def _open_three(win, tmp_path) -> None:
    for name, pages in (("Alpha 資料.pdf", 3), ("Beta.pdf", 2), ("Gamma.pdf", 1)):
        assert win.open_path(_pdf(tmp_path / name, pages, name.split(".")[0]))
    win._activate_session(0)  # noqa: SLF001
    QApplication.processEvents()


def _registrations(win) -> dict[str, list[object]]:
    seen: dict[str, list[object]] = defaultdict(list)
    for act in win.findChildren(QAction):
        for seq in act.shortcuts():
            if not seq.isEmpty() and act.shortcutContext() in (Qt.ShortcutContext.ApplicationShortcut,
                                                               Qt.ShortcutContext.WindowShortcut):
                seen[seq.toString(QKeySequence.SequenceFormat.PortableText)].append(act)
    for sc in win.findChildren(QShortcut):
        if not sc.key().isEmpty() and sc.context() in (Qt.ShortcutContext.ApplicationShortcut,
                                                        Qt.ShortcutContext.WindowShortcut):
            seen[sc.key().toString(QKeySequence.SequenceFormat.PortableText)].append(sc)
    return seen


def test_tab_keys_have_exactly_one_registration(window):
    regs = _registrations(window)
    assert len(regs["Ctrl+Tab"]) == 1, regs["Ctrl+Tab"]
    assert len(regs["Ctrl+Shift+Tab"]) == 1, regs["Ctrl+Shift+Tab"]


def test_no_two_window_shortcuts_share_a_key_sequence(window):
    # an ambiguous pair silently disables both shortcuts; catch the whole class, not only Ctrl+Tab
    dupes = {seq: [getattr(o, "text", lambda: type(o).__name__)() for o in objs]
             for seq, objs in _registrations(window).items() if len(set(map(id, objs))) > 1}
    assert not dupes, dupes


def test_ctrl_tab_cycles_forward_and_wraps(window, tmp_path):
    _open_three(window, tmp_path)
    seen = []
    for _ in range(3):
        _ctrl_tab(window)
        seen.append(_active(window))
    assert seen == ["Beta.pdf", "Gamma.pdf", "Alpha 資料.pdf"]
    assert window._doc_tabs.currentIndex() == 0  # noqa: SLF001 — tab bar follows


def test_ctrl_shift_tab_cycles_backward_and_wraps(window, tmp_path):
    _open_three(window, tmp_path)
    seen = []
    for _ in range(3):
        _ctrl_shift_tab(window)
        seen.append(_active(window))
    assert seen == ["Gamma.pdf", "Beta.pdf", "Alpha 資料.pdf"]


def test_tab_keys_with_one_document_do_nothing(window, tmp_path):
    assert window.open_path(_pdf(tmp_path / "Only.pdf", 2, "only"))
    _ctrl_tab(window)
    _ctrl_shift_tab(window)
    assert _names(window) == ["Only.pdf"] and _active(window) == "Only.pdf"


def test_ctrl_tab_while_typing_in_a_text_box_keeps_the_text_in_its_own_document(window, tmp_path):
    from core.editing.geometry import Rect

    _open_three(window, tmp_path)
    box = window._edit.create_text_box(0, Rect(72, 300, 260, 60), text="")  # noqa: SLF001
    inner = window._canvas._canvas  # noqa: SLF001
    assert inner.open_text_editor(box.object_id)
    editor = inner._text_editor  # noqa: SLF001
    editor.setFocus()
    QTest.keyClicks(editor, "typed before Ctrl+Tab")
    QApplication.processEvents()
    _ctrl_tab(window)
    assert _active(window) == "Beta.pdf"
    assert not window._canvas.editor_active()  # noqa: SLF001 — editor closed, not left on the other tab
    assert not window._edit.dirty  # noqa: SLF001 — Beta got no foreign edit
    _ctrl_shift_tab(window)
    assert _active(window) == "Alpha 資料.pdf"
    text = window._edit.objects[box.object_id].text  # noqa: SLF001
    assert text == "typed before Ctrl+Tab"
    assert window._edit.dirty  # noqa: SLF001


def test_ctrl_tab_while_filling_a_form_field_commits_the_value(window, tmp_path):
    form = _form_pdf(tmp_path / "フォーム.pdf")
    assert window.open_path(form)
    assert window.open_path(_pdf(tmp_path / "Other.pdf", 1, "other"))
    window._activate_session(0)  # noqa: SLF001
    field = next(f for f in window._edit.fields.values() if getattr(f, "name", "") == "name")  # noqa: SLF001
    inner = window._canvas._canvas  # noqa: SLF001
    assert inner.open_field_editor(field)
    editor = inner._field_editor  # noqa: SLF001
    editor.setFocus()
    QTest.keyClicks(editor, "Yamada ")
    # Japanese text arrives through the input method as committed text; QTest.keyClicks cannot send
    # CJK characters (PySide6 6.8.1 aborts the process), so insert it the way an IME commit does
    editor.insertPlainText("山田 太郎")
    QApplication.processEvents()
    _ctrl_tab(window)
    assert _active(window) == "Other.pdf"
    _ctrl_tab(window)
    assert _active(window) == "フォーム.pdf"
    assert window._edit.fields[field.object_id].value == "Yamada 山田 太郎"  # noqa: SLF001


def test_other_tab_shortcuts_still_work(window, tmp_path):
    _open_three(window, tmp_path)
    _ctrl_tab(window)  # Beta
    _press(window, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)  # clean tab closes without asking
    assert _names(window) == ["Alpha 資料.pdf", "Gamma.pdf"]
    _press(window, Qt.Key.Key_F4, Qt.KeyboardModifier.ControlModifier)
    assert len(_names(window)) == 1
