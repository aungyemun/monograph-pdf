"""Rotating pages in the real window: layout, zoom, coordinates, undo/redo, signed documents."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from core.editing.geometry import Point  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-rotation"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


@pytest.fixture
def doc_window(window, tmp_path):
    src = tmp_path / "tall.pdf"
    d = fitz.open()
    p = d.new_page(width=300, height=500)
    p.insert_text((40, 80), "Anchor", fontsize=24)
    d.save(src.as_posix())
    d.close()
    assert window.open_path(src)
    return window


def _layout_aspect(win) -> float:
    r = win._canvas._canvas._layouts[0]  # noqa: SLF001
    return r.width() / r.height()


def test_layout_follows_page_orientation_through_all_turns(doc_window):
    w = doc_window
    portrait = 300 / 500
    assert _layout_aspect(w) == pytest.approx(portrait, rel=0.01)
    for step in range(1, 5):
        w._rotate_selected(90)  # noqa: SLF001
        expected = portrait if step % 2 == 0 else 1 / portrait
        assert _layout_aspect(w) == pytest.approx(expected, rel=0.01), f"after {90 * step}°"
    assert w._document.page(0).rotation == 0  # noqa: SLF001


def test_coordinates_roundtrip_after_rotation_and_zoom(doc_window):
    from PySide6.QtCore import QPoint

    w = doc_window
    c = w._canvas._canvas  # noqa: SLF001
    w._rotate_selected(-90)  # noqa: SLF001
    for zoom in (0.75, 1.0, 1.5):
        c.set_manual_zoom(zoom, w.size())
        info = w._document.page(0)  # noqa: SLF001
        assert (info.display_width_pt, info.display_height_pt) == (500, 300)
        for pt in (Point(10, 10), Point(250, 150), Point(480, 290)):
            wp = c.pdf_to_widget(0, pt)
            assert wp is not None
            back = c.widget_to_pdf(QPoint(int(round(wp.x())), int(round(wp.y()))))
            assert back is not None
            assert back[0] == 0
            assert abs(back[1].x - pt.x) < 1.5 and abs(back[1].y - pt.y) < 1.5


def test_rotate_is_undoable_and_marks_modified(doc_window):
    w = doc_window
    w._rotate_selected(90)  # noqa: SLF001
    assert w._document.page(0).rotation == 90  # noqa: SLF001
    assert w._edit.dirty  # noqa: SLF001
    w._undo()  # noqa: SLF001
    assert w._document.page(0).rotation == 0  # noqa: SLF001
    assert _layout_aspect(w) == pytest.approx(300 / 500, rel=0.01)
    w._redo()  # noqa: SLF001
    assert w._document.page(0).rotation == 90  # noqa: SLF001
    assert _layout_aspect(w) == pytest.approx(500 / 300, rel=0.01)


def test_rotating_a_signed_document_asks_first(doc_window, monkeypatch):
    w = doc_window
    asked = []
    monkeypatch.setattr(w, "_warn_signatures_if_needed", lambda: asked.append(1) or False)
    w._rotate_selected(90)  # noqa: SLF001
    assert asked, "signature warning not consulted"
    assert w._document.page(0).rotation == 0  # declined → untouched  # noqa: SLF001


def test_undo_and_redo_buttons_follow_the_rotation(doc_window):
    w = doc_window
    assert not w.act_undo.isEnabled()
    w._rotate_selected(90)  # noqa: SLF001
    assert w.act_undo.isEnabled() and not w.act_redo.isEnabled()
    w._undo()  # noqa: SLF001
    assert not w.act_undo.isEnabled() and w.act_redo.isEnabled()
    w._redo()  # noqa: SLF001
    assert w.act_undo.isEnabled() and not w.act_redo.isEnabled()
