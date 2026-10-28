"""Mouse selection on the page: several selected objects move together, a rubber band selects
shapes and pictures too, and a resize handle caught off-centre does not make the edge jump.

Regressions found in the 0.5.0 validation (real mouse events on the canvas):
* pressing on one of several selected objects selected only that one, so the drag moved only it and
  Delete then removed only it;
* the rubber band (drag on empty paper) selected text boxes and fields but not shapes or pictures;
* catching a handle a few pixels off its centre moved the edge to the pointer at the first move.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-selection"])
    src = tmp_path / "page.pdf"
    d = fitz.open()
    d.new_page(width=595, height=842).insert_text((72, 72), "Selection test")
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    assert w.open_path(src)
    qtbot.wait(100)
    yield w
    if w._edit is not None:  # noqa: SLF001
        w._edit.dirty = False  # noqa: SLF001
        w.close_document(save_session=False)
    w.close()


def _send(inner, kind, pos, buttons, mods=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    mods = mods if mods is not None else Qt.KeyboardModifier.NoModifier
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    QApplication.sendEvent(inner, QMouseEvent(kind, QPointF(pos), QPointF(inner.mapToGlobal(pos)), button, buttons, mods))


def _drag(qtbot, inner, a, b, steps=6, mods=None):
    from PySide6.QtCore import QEvent, QPoint, Qt

    _send(inner, QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton, mods)
    for i in range(1, steps + 1):
        p = QPoint(int(a.x() + (b.x() - a.x()) * i / steps), int(a.y() + (b.y() - a.y()) * i / steps))
        _send(inner, QEvent.Type.MouseMove, p, Qt.MouseButton.LeftButton, mods)
    _send(inner, QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton, mods)
    qtbot.wait(30)


def _click(qtbot, inner, p, mods=None):
    _drag(qtbot, inner, p, p, steps=0, mods=mods)


def _objects(win):
    from core.editing.edit_model import EditTool
    from core.editing.geometry import Rect

    e = win._edit  # noqa: SLF001
    tb = e.create_text_box(0, Rect(90, 150, 170, 44), text="Box", auto_match=False)
    e.editing_object_id = None
    rect = e.create_shape(0, Rect(320, 150, 130, 80), "rectangle")
    ell = e.create_shape(0, Rect(90, 290, 130, 80), "ellipse")
    e.clear_selection()
    win._canvas.set_tool(EditTool.SELECT)  # noqa: SLF001
    return e, tb.object_id, rect.object_id, ell.object_id


def _rect(e, oid):
    o = e.objects.get(oid) or e.shapes.get(oid)
    return (o.rect.x, o.rect.y, o.rect.w, o.rect.h)


def test_drag_moves_every_selected_object_and_click_reduces_selection(qtbot, win):
    from PySide6.QtCore import QPoint, Qt

    inner = win._canvas._canvas  # noqa: SLF001
    e, _tb, a, b = _objects(win)
    ca = inner.pdf_rect_to_widget(0, e.shapes[a].rect).center()
    cb = inner.pdf_rect_to_widget(0, e.shapes[b].rect).center()
    _click(qtbot, inner, ca)
    _click(qtbot, inner, cb, Qt.KeyboardModifier.ControlModifier)
    assert set(e.selection) == {a, b}
    ra, rb = _rect(e, a), _rect(e, b)
    _drag(qtbot, inner, ca, ca + QPoint(30, 20))
    assert set(e.selection) == {a, b}
    da = (_rect(e, a)[0] - ra[0], _rect(e, a)[1] - ra[1])
    db = (_rect(e, b)[0] - rb[0], _rect(e, b)[1] - rb[1])
    assert da[0] > 5 and abs(da[0] - db[0]) < 0.05 and abs(da[1] - db[1]) < 0.05, (da, db)
    # a plain click (no movement) on one of them selects just that one
    _click(qtbot, inner, inner.pdf_rect_to_widget(0, e.shapes[a].rect).center())
    assert e.selection == [a]


def test_rubber_band_selects_shapes_too(qtbot, win):
    from core.editing.geometry import Rect

    inner = win._canvas._canvas  # noqa: SLF001
    e, tb, a, b = _objects(win)
    s0 = inner.pdf_rect_to_widget(0, Rect(60, 120, 1, 1)).topLeft()
    s1 = inner.pdf_rect_to_widget(0, Rect(520, 430, 1, 1)).topLeft()
    _drag(qtbot, inner, s0, s1)
    assert set(e.selection) == {tb, a, b}


def test_handle_caught_off_centre_does_not_jump(qtbot, win):
    from PySide6.QtCore import QPoint

    inner = win._canvas._canvas  # noqa: SLF001
    e, _tb, a, _b = _objects(win)
    wr = inner.pdf_rect_to_widget(0, e.shapes[a].rect)
    _click(qtbot, inner, wr.center())
    names = ["nw", "n", "ne", "w", "e", "sw", "s", "se"]
    hx, hy = dict(zip(names, inner._handle_points(wr)))["e"]  # noqa: SLF001
    before = _rect(e, a)
    press = QPoint(int(hx) - 4, int(hy) + 3)  # inside the grab area, 4 px left of the handle
    _drag(qtbot, inner, press, press + QPoint(10, 0), steps=5)
    sx = inner._scale(0)[0]  # noqa: SLF001
    grew = _rect(e, a)[2] - before[2]
    assert abs(grew - 10 / sx) < 1.5 / sx + 0.2, (grew, 10 / sx)  # by the mouse distance, no jump
    assert abs(_rect(e, a)[0] - before[0]) < 0.05  # the left edge stays
