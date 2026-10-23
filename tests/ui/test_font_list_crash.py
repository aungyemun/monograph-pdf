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
    qtbot.waitUntil(lambda: _panel_picker(win) is not None, timeout=3000)
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
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox
    from shiboken6 import isValid

    from core.editing.geometry import Rect
    from ui.font_picker import FontPicker

    box = win._edit.create_text_box(0, Rect(100, 100, 260, 40), text="Hello")  # noqa: SLF001
    oid = getattr(box, "object_id", box)
    win._edit.select([oid])  # noqa: SLF001
    win._on_edit_changed()  # noqa: SLF001
    qtbot.waitUntil(lambda: _panel_picker(win) is not None, timeout=3000)
    picker = _panel_picker(win)
    others = [w for w in win._inspector.findChildren(QAbstractSpinBox) + win._inspector.findChildren(QComboBox)  # noqa: SLF001
              if w.isVisibleTo(win._inspector) and not isinstance(w, FontPicker)  # noqa: SLF001
              and w.parent() is not picker]
    assert others
    old = others[0]
    win._inspector._clear_rows()  # noqa: SLF001
    assert isValid(old), "deleted while it might still be running its own code"
    qtbot.wait(50)
    assert not isValid(old), "removed after the current event"
    # the panel's font box is kept for its whole life (never deleted under an open or scrolling list)
    assert isValid(picker)
    win._on_edit_changed()  # noqa: SLF001
    qtbot.wait(200)
    assert _panel_picker(win) is picker


def test_scrolling_the_open_font_lists_while_the_text_box_changes_does_not_crash(win, qtbot):
    """Regression (0.4.2 crash, access violation in Qt6Widgets): place a text box, type, then scroll the
    font list. Both font boxes: the list is scrolled by wheel and scroll bar while the text box keeps
    changing (each change asks the panel and toolbar to refresh). Nothing may be rebuilt or deleted
    under the open list, no error may be raised, and choosing a font afterwards works."""
    import sys

    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import isValid

    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda t, e, tb: errors.append(f"{t.__name__}: {e}")
    try:
        oid = _typing_with_selection(win, qtbot)
        for p in (_panel_picker(win), win._font_family):  # noqa: SLF001
            assert p is not None
            p.showPopup()
            qtbot.wait(450)
            if not p.view().window().isVisible():
                pytest.skip("the offscreen platform did not open the list")
            view = p.view()
            bar = view.verticalScrollBar()
            for step in range(40):
                vp = view.viewport()
                pos = QPointF(vp.width() / 2, vp.height() / 2)
                QApplication.sendEvent(vp, QWheelEvent(pos, QPointF(vp.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                                                       QPoint(0, -120 if step % 7 else 360), Qt.MouseButton.NoButton,
                                                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
                if step % 5 == 0:
                    bar.setValue((bar.maximum() * step) // 40)
                # the text box keeps changing meanwhile (typing, auto-height): refresh requests
                win._edit.live_set_text(oid, f"Hello world {step}", notify=True)  # noqa: SLF001
                win._on_edit_changed()  # noqa: SLF001
                win._flush_chrome_refresh()  # noqa: SLF001
                qtbot.wait(5)
            assert isValid(p) and p.view().window().isVisible(), "the font box was rebuilt under its open list"
            family = p.itemText(min(9, p.count() - 1))
            _pick(p, qtbot, family)
            assert win._edit.objects[oid].style.font_family == family  # noqa: SLF001
            qtbot.wait(300)
        assert errors == []
    finally:
        sys.excepthook = old_hook


def test_problem_report_window_opens_after_the_failing_handler_one_at_a_time(win, qtbot, monkeypatch):
    """An error inside a paint or mouse handler (e.g. while a list scrolls) must not open the modal
    report window inside that handler: it opens from the main event loop, and a burst of the same
    error opens it once."""
    import ui.error_report_dialog as erd

    shown = []
    monkeypatch.setattr(erd.ErrorReportDialog, "exec", lambda self: shown.append(self) or 0)
    monkeypatch.setattr(win, "_is_headless_ui", lambda: False)
    from core.diagnostics import EventId, crash
    from core.diagnostics import report as reports

    monkeypatch.setattr(crash, "save_pending", lambda rep: shown.append("saved"))
    report = reports.build(EventId.UNHANDLED_EXCEPTION, ValueError("x"), report_type="crash")
    assert win.offer_report(report, "x") is True
    assert win.offer_report(report, "x") is True  # same burst
    assert shown == [], "opened inside the failing handler"
    qtbot.waitUntil(lambda: len(shown) == 1, timeout=2000)
    qtbot.wait(50)
    assert len(shown) == 1
    assert win.offer_report(report, "x") is True  # a later error is shown again
    qtbot.waitUntil(lambda: len(shown) == 2, timeout=2000)
    assert "saved" not in shown, "the window failed to open"
