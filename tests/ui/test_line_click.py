"""Line / Arrow tool: a click without dragging draws nothing (0.5.1).

0.5.0 created a zero-length line on a single click; Save wrote it into the page, where its round
caps printed as a dot. Real lines — also very short ones drawn zoomed in — are kept.
"""

from __future__ import annotations

import math
import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-line-click"])
    src = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1360, 860)
    w.show()
    assert w.open_path(src)
    qtbot.wait(100)
    yield w, src
    w.close_document(save_session=False)
    w.close()


def _press_release(qtbot, inner, p0, p1):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    if p1 != p0:
        QTest.mouseMove(inner, p1)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
    qtbot.wait(20)


def _page_lines(path):
    with fitz.open(path) as doc:
        return [d for d in doc[0].get_drawings() if any(i[0] == "l" for i in d["items"])]


@pytest.mark.parametrize("tool_name", ["SHAPE_LINE", "SHAPE_ARROW"])
def test_click_without_drag_draws_and_saves_nothing(win, qtbot, tool_name):
    from PySide6.QtCore import QPoint

    from core.editing.edit_model import EditTool
    from core.editing.geometry import Point

    w, src = win
    tool = getattr(EditTool, tool_name)
    inner = w._canvas._canvas  # noqa: SLF001
    w._set_tool(tool)  # noqa: SLF001
    p = inner.pdf_to_widget(0, Point(200, 300))
    _press_release(qtbot, inner, p, p)  # a click
    _press_release(qtbot, inner, p, p + QPoint(1, 1))  # a tremble of the hand: still a click
    assert not w._edit.shapes  # noqa: SLF001
    assert not w._edit.commands.can_undo_now  # noqa: SLF001 — nothing to undo
    assert w._edit.tool == tool  # noqa: SLF001 — the tool stays on for the drag
    # ... and the drag after it draws the line
    _press_release(qtbot, inner, p, p + QPoint(120, 0))
    assert len(w._edit.shapes) == 1  # noqa: SLF001
    w.save_document()
    qtbot.wait(100)
    lines = _page_lines(src)
    assert max(d["rect"].width for d in lines) > 50  # the drawn line (an arrow adds its head)
    assert not [d for d in lines if d["rect"].width < 0.01 and d["rect"].height < 0.01]  # no dot


def test_short_line_drawn_zoomed_in_is_kept(win, qtbot):
    from PySide6.QtCore import QPoint

    from core.editing.edit_model import EditTool
    from core.editing.geometry import Point

    w, src = win
    for _ in range(8):
        w.act_zoom_in.trigger()
    qtbot.wait(50)
    inner = w._canvas._canvas  # noqa: SLF001
    sx, _sy = inner._scale(0)  # noqa: SLF001
    assert sx > 2.5  # zoomed in: a few pixels are well under 3 points
    w._set_tool(EditTool.SHAPE_LINE)  # noqa: SLF001
    p = inner.pdf_to_widget(0, Point(100, 100))
    _press_release(qtbot, inner, p, p + QPoint(6, 0))  # 6 px: a deliberate tiny line
    shapes = list(w._edit.shapes.values())  # noqa: SLF001
    assert len(shapes) == 1
    s = shapes[0]
    length = math.hypot(s.x1 - s.x0, s.y1 - s.y0)
    assert 0.5 < length < 3.0
    w.save_document()
    qtbot.wait(100)
    assert _page_lines(src)  # written into the page
