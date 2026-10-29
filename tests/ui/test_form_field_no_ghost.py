"""Changing an already filled PDF form field must not show the old value under the new one.

Before 0.5.1 the page picture still contained the field's saved appearance (the old text) while the
window drew the new value over it — both were visible, overlapping, until the next Save.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

OLD = "WWWWWWWWWWWWWWWWWWWWWWWW"  # covers the whole box, so leftovers show in its right part


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-no-ghost"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1360, 860)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _filled_form(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.rect = fitz.Rect(100, 100, 400, 124)
    w.text_fontsize = 14
    w.field_value = OLD
    page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


def _dark_in_right_part(win) -> int:
    """Black text pixels in the right 55 % of the field (the new short value never reaches it)."""
    from PySide6.QtGui import QColor

    inner = win._canvas.widget()  # noqa: SLF001
    field = next(iter(win._edit.fields.values()))  # noqa: SLF001
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    img = inner.grab().toImage()
    n = 0
    for x in range(wr.left() + int(wr.width() * 0.45), wr.right() - 6, 2):
        for y in range(wr.top() + 5, wr.bottom() - 4, 2):
            c = QColor(img.pixel(x, y))
            if c.red() < 90 and c.green() < 90 and c.blue() < 90:
                n += 1
    return n


def test_new_value_is_not_drawn_over_the_old_one(window, qtbot, tmp_path):
    import fitz

    w = window
    path = _filled_form(tmp_path / "form.pdf")
    assert w.open_path(path)
    inner = w._canvas.widget()  # noqa: SLF001
    qtbot.waitUntil(lambda: _dark_in_right_part(w) > 20, timeout=5000)  # the saved value is shown

    field = next(iter(w._edit.fields.values()))  # noqa: SLF001
    assert inner.open_field_editor(field)
    inner.field_editor.setPlainText("I")
    inner.close_field_editor(commit=True)
    assert field.value == "I" and field.value_dirty

    # Only the new value: no trace of the old text anywhere in the box
    qtbot.waitUntil(lambda: _dark_in_right_part(w) == 0, timeout=5000)

    # Typing the saved value back in shows it once again (the field is still being changed)
    assert inner.open_field_editor(field)
    inner.field_editor.setPlainText(OLD)
    inner.close_field_editor(commit=True)
    qtbot.waitUntil(lambda: _dark_in_right_part(w) > 20, timeout=5000)
    assert inner.open_field_editor(field)
    inner.field_editor.setPlainText("I")
    inner.close_field_editor(commit=True)
    qtbot.waitUntil(lambda: _dark_in_right_part(w) == 0, timeout=5000)

    # Saved: the file holds and shows only the new value, and so does the window
    w.save_document()
    qtbot.wait(300)
    with fitz.open(path) as doc:
        widget = doc[0].first_widget
        assert widget.field_value == "I"
        assert doc[0].get_textbox(widget.rect).strip() == "I"
    qtbot.waitUntil(lambda: _dark_in_right_part(w) == 0, timeout=5000)


def _checkbox_form(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.field_name = "agree"
    w.rect = fitz.Rect(100, 100, 140, 140)
    w.field_value = True
    page.add_widget(w)
    doc.save(path)
    doc.close()
    return path


def _dark_inside(win) -> int:
    from PySide6.QtGui import QColor

    inner = win._canvas.widget()  # noqa: SLF001
    field = next(iter(win._edit.fields.values()))  # noqa: SLF001
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    img = inner.grab().toImage()
    n = 0
    for x in range(wr.left() + 4, wr.right() - 4):
        for y in range(wr.top() + 4, wr.bottom() - 4):
            c = QColor(img.pixel(x, y))
            if c.red() < 90 and c.green() < 90 and c.blue() < 90:
                n += 1
    return n


def test_unticked_checkbox_shows_neither_old_tick_nor_glyph_and_undo_restores(window, qtbot, tmp_path):
    w = window
    assert w.open_path(_checkbox_form(tmp_path / "cb.pdf"))
    qtbot.waitUntil(lambda: _dark_inside(w) > 30, timeout=5000)  # the saved tick
    ticked = _dark_inside(w)
    fid = next(iter(w._edit.fields))  # noqa: SLF001
    w._edit.set_field_value(fid, checked=False)  # noqa: SLF001
    qtbot.waitUntil(lambda: _dark_inside(w) == 0, timeout=5000)  # no old tick, no "☐" glyph
    w._undo()  # noqa: SLF001 — Edit ▸ Undo
    assert next(iter(w._edit.fields.values())).checked  # noqa: SLF001
    qtbot.waitUntil(lambda: abs(_dark_inside(w) - ticked) <= 2, timeout=5000)  # the form's own tick again