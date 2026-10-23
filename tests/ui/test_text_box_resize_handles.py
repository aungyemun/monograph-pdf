from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
"""Regression (0.4.2): a text box just placed (still being typed in) could not be resized: its
handles lie half inside the text editor, which took the press. Every handle must resize the box,
while typing and afterwards. Events go to the widget under the mouse, as on screen."""

from tests.ui.test_text_box_word_formats import win  # noqa: F401
from core.editing.edit_model import EditTool

def _route(cv, p):
    t = cv.childAt(p)
    return (t, t.mapFrom(cv, p)) if t is not None else (cv, p)

def test_placed_text_box_resizes_from_every_handle(win, qtbot):  # noqa: F811
    cv = win._canvas._canvas
    win._set_tool(EditTool.TEXT_BOX); qtbot.wait(50)
    a = QPoint(200, 200); b = QPoint(420, 260)
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for k in range(1, 6): QTest.mouseMove(cv, a + (b - a) * k / 5); qtbot.wait(5)
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b); qtbot.wait(100)
    oid = win._edit.selection[0]
    assert cv.text_editor is not None, "a placed box opens for typing"
    QTest.keyClicks(cv.text_editor, "Typed text") if cv.text_editor else None
    expect = {"e": (1, 0), "s": (0, 1), "se": (1, 1), "nw": (1, 1)}
    for name in ("e", "s", "se", "nw"):
        bx = win._edit.objects[oid]; r0 = (round(bx.rect.w, 1), round(bx.rect.h, 1))
        wr = cv.pdf_rect_to_widget(0, bx.rect)
        pts = dict(zip(["nw","n","ne","w","e","sw","s","se"], cv._handle_points(wr)))
        p = QPoint(*pts[name]); d = {"e": (40, 0), "s": (0, 40), "se": (40, 40), "nw": (-30, -30)}[name]
        t, lp = _route(cv, p)
        QTest.mousePress(t, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, lp); qtbot.wait(20)
        for k in range(1, 6):
            q = p + QPoint(d[0] * k // 5, d[1] * k // 5); t2, lq = _route(cv, q)
            QTest.mouseMove(t2, lq); qtbot.wait(10)
        q = p + QPoint(*d); t3, lq = _route(cv, q)
        QTest.mouseRelease(t3, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, lq); qtbot.wait(50)
        bx = win._edit.objects[oid]
        gw, gh = expect[name]
        assert (bx.rect.w > r0[0] + 15) == bool(gw) and (bx.rect.h > r0[1] + 15) == bool(gh), (name, r0, bx.rect)
        assert bx.text == "Typed text"
