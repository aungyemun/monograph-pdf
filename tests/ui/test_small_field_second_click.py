"""A second click inside a small selected form field starts typing in it.

Regression (audit 2026-11, a real Japanese administrative form): on a text field under about
18 px high on screen (a 24 x 11 pt date / number box at fit width), the catch areas of the top and
bottom resize handles met in the middle of the selected field. The documented second click therefore
began a "resize" that did nothing, typing never started, and the first typed letter was taken as a
tool shortcut (Shift+A = Arrow). The handles still work at the field's edge.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


def _small_field_pdf(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for name, rect in (("small", fitz.Rect(442, 70, 466.5, 81)), ("large", fitz.Rect(72, 200, 400, 240))):
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = name
        w.rect = rect
        w.field_value = ""
        page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-small-field"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1400, 900)
    w.show()
    assert w.open_path(_small_field_pdf(tmp_path / "small.pdf"))
    qtbot.wait(50)
    yield w
    w.close_document(save_session=False)
    w.close()


def _field(w, name):
    return next(f for f in w._edit.fields.values() if f.name == name)  # noqa: SLF001


def _click(qtbot, inner, pos):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    qtbot.wait(20)


@pytest.mark.parametrize(("name", "zoom"), [("small", None), ("small", 0.45), ("large", None)])
def test_second_click_inside_the_field_types(win, qtbot, name, zoom):
    from PySide6.QtTest import QTest

    if zoom is not None:
        win._canvas.set_manual_zoom(zoom)  # noqa: SLF001
        qtbot.wait(150)
    inner = win._canvas._canvas  # noqa: SLF001
    field = _field(win, name)
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    win._canvas.ensureVisible(wr.center().x(), wr.center().y(), 50, 50)  # noqa: SLF001
    qtbot.wait(20)
    if name == "small":
        assert wr.height() < 18, "the regression needs a field this small on screen"
    if zoom is not None:
        assert wr.height() <= 8, "and one at most 8 px high (review 2026-11)"
    _click(qtbot, inner, wr.center())
    assert inner.field_editor is None and win._edit.field_selection == [field.object_id]  # noqa: SLF001
    _click(qtbot, inner, wr.center())
    assert inner.field_editor is not None, "the second click starts typing"
    QTest.keyClicks(inner.field_editor, "A1")
    assert field.value == "A1", "a capital letter is typed, not taken as a tool shortcut"


def test_the_handles_of_a_small_field_still_resize_it_at_its_edge(win, qtbot):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    inner = win._canvas._canvas  # noqa: SLF001
    field = _field(win, "small")
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    _click(qtbot, inner, wr.center())  # select
    before = field.rect.w
    start = QPoint(wr.right() + 1, wr.center().y())  # the right-hand ("e") handle, at the edge
    end = start + QPoint(60, 0)
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(inner, end)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    qtbot.wait(20)
    assert field.rect.w > before + 20, (before, field.rect)
    assert inner.field_editor is None


def test_large_fields_keep_their_full_handle_catch_area(win, qtbot):
    """Review 2026-11: the small-field rule must not shrink the handles of an ordinary field."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    inner = win._canvas._canvas  # noqa: SLF001
    field = _field(win, "large")
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    _click(qtbot, inner, wr.center())  # select
    before = field.rect.w
    start = QPoint(wr.right() - 7, wr.center().y())  # 7 px inside the right edge: still the "e" handle
    end = start + QPoint(60, 0)
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(inner, end)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    qtbot.wait(20)
    assert field.rect.w > before + 20, (before, field.rect)
