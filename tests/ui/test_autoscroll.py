"""Scroll button: middle-click / hold auto-scrolling and View ▸ Automatic Scrolling."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QCursor, QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-autoscroll"])
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    for i in range(8):
        d.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=24)
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    assert w.open_path(src)
    qtbot.waitUntil(lambda: len(w._canvas._canvas._cache) > 0, timeout=3000)  # noqa: SLF001
    yield w
    w._canvas.autoscroll.stop()  # noqa: SLF001
    w.close_document(save_session=False)
    w.close()


def _middle(widget, kind, pos: QPoint):
    glob = widget.mapToGlobal(pos)
    buttons = Qt.MouseButton.MiddleButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, QPointF(pos), QPointF(glob), Qt.MouseButton.MiddleButton, buttons,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def test_speed_curve():
    from ui.autoscroll import DEAD_ZONE, _speed

    assert _speed(0) == 0 and _speed(DEAD_ZONE) == 0 and _speed(-DEAD_ZONE) == 0
    assert _speed(60) > _speed(30) > 0
    assert _speed(-60) == -_speed(60)


def test_middle_click_shows_marker_and_scrolls_towards_pointer(win, qtbot, monkeypatch):
    outer = win._canvas  # noqa: SLF001
    sc = outer.autoscroll
    vp = outer.viewport()
    start = QPoint(vp.width() // 2, vp.height() // 2)
    _middle(outer._canvas, QEvent.Type.MouseButtonPress, outer._canvas.mapFrom(vp, start))  # noqa: SLF001
    assert sc.active and sc.mode == "hold"
    assert sc.marker().isVisible()
    assert sc.marker().geometry().center().y() - start.y() in (-1, 0, 1)
    _middle(vp, QEvent.Type.MouseButtonRelease, start)  # quick release without moving: "click" mode
    assert sc.mode == "click"
    # pointer 150 px below the marker: the view scrolls down
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: vp.mapToGlobal(start + QPoint(0, 150))))
    vb = outer.verticalScrollBar()
    before = vb.value()
    qtbot.waitUntil(lambda: vb.value() > before + 100, timeout=3000)
    # pointer above: scrolls back up
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: vp.mapToGlobal(start - QPoint(0, 150))))
    top = vb.value()
    qtbot.waitUntil(lambda: vb.value() < top - 50, timeout=3000)
    # inside the dead zone: nothing moves
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: vp.mapToGlobal(start + QPoint(0, 3))))
    qtbot.wait(60)
    still = vb.value()
    qtbot.wait(120)
    assert vb.value() == still
    # Esc stops it, the marker disappears and the cursor is restored
    QApplication.sendEvent(vp, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not sc.active
    assert not sc.marker().isVisible()
    assert QApplication.overrideCursor() is None


def test_hold_and_drag_stops_on_release(win, qtbot, monkeypatch):
    outer = win._canvas  # noqa: SLF001
    sc = outer.autoscroll
    vp = outer.viewport()
    start = QPoint(300, 300)
    _middle(vp, QEvent.Type.MouseButtonPress, start)
    assert sc.mode == "hold"
    qtbot.wait(400)  # held longer than a click
    _middle(vp, QEvent.Type.MouseButtonRelease, start + QPoint(0, 40))
    assert not sc.active


def test_a_click_while_scrolling_stops_and_is_not_passed_to_the_page(win, qtbot):
    outer = win._canvas  # noqa: SLF001
    sc = outer.autoscroll
    vp = outer.viewport()
    _middle(vp, QEvent.Type.MouseButtonPress, QPoint(200, 200))
    _middle(vp, QEvent.Type.MouseButtonRelease, QPoint(200, 200))
    assert sc.mode == "click"
    seen = []
    inner = outer._canvas  # noqa: SLF001
    orig = inner.mousePressEvent
    inner.mousePressEvent = lambda e: (seen.append(e.button()), orig(e))
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(50, 50), QPointF(inner.mapToGlobal(QPoint(50, 50))),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(inner, ev)
    assert not sc.active
    assert seen == []


def test_automatic_scrolling_menu_action(win, qtbot):
    outer = win._canvas  # noqa: SLF001
    sc = outer.autoscroll
    assert win.act_autoscroll.shortcut().toString() == "Ctrl+Shift+L"
    win.act_autoscroll.trigger()
    assert sc.mode == "read" and win.act_autoscroll.isChecked()
    assert not sc.marker().isVisible()
    vb = outer.verticalScrollBar()
    before = vb.value()
    slow = sc.read_speed
    QApplication.sendEvent(outer.viewport(), QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
    assert sc.read_speed > slow
    qtbot.waitUntil(lambda: vb.value() > before + 5, timeout=3000)
    for _ in range(12):  # ↑ past the slowest speed reverses
        sc.change_reading_speed(False)
    assert sc.read_speed < 0
    win.act_autoscroll.trigger()
    assert not sc.active and not win.act_autoscroll.isChecked()


def test_automatic_scrolling_stops_at_the_end(win, qtbot):
    outer = win._canvas  # noqa: SLF001
    sc = outer.autoscroll
    vb = outer.verticalScrollBar()
    vb.setValue(vb.maximum() - 3)
    win.act_autoscroll.trigger()
    qtbot.waitUntil(lambda: not sc.active, timeout=3000)
    assert not win.act_autoscroll.isChecked()
