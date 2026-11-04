"""Text markup lands on the dragged words at every zoom and page rotation (Phase 1 audit, P0 §4).

A real mouse drag with the Highlight tool across one word, at four zoom levels and four page rotations:
the saved highlight must cover that word (compared with the word's own box in unrotated page space) and
must not spill onto the neighbouring words.
"""

from __future__ import annotations

import os

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
    create_application(["monograph-pdf-markup-geometry"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1300, 950)
    win.show()
    yield win
    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return inter.get_area() / (a | b).get_area()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0, 3.0])
def test_highlight_drag_covers_exactly_the_word(window, qtbot, tmp_path, zoom, rotation):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    src = tmp_path / "words.pdf"
    d = fitz.open()
    page = d.new_page(width=595, height=842)
    page.insert_text((72, 300), "alpha TARGETWORD omega", fontsize=16)
    page.set_rotation(rotation)
    d.save(src)
    d.close()
    with fitz.open(src) as d:
        pg = d[0]
        words = {w[4]: fitz.Rect(w[:4]) for w in pg.get_text("words")}  # unrotated page space
        target = words["TARGETWORD"]
        disp = target * pg.rotation_matrix  # where the word appears on screen (display space)
        disp.normalize()
    assert window.open_path(src)
    window._canvas.set_manual_zoom(zoom)  # noqa: SLF001
    qtbot.wait(150)
    inner = window._canvas._canvas  # noqa: SLF001
    window.act_annot_highlight.trigger()
    horizontal = rotation in (0, 180)
    if horizontal:
        pts = [Point(disp.x0 + 2 + (disp.width - 4) * i / 10, (disp.y0 + disp.y1) / 2) for i in range(11)]
    else:
        pts = [Point((disp.x0 + disp.x1) / 2, disp.y0 + 2 + (disp.height - 4) * i / 10) for i in range(11)]
    if rotation in (180, 270):
        pts.reverse()  # drag in reading direction
    wp = [inner.pdf_to_widget(0, p) for p in pts]
    window._canvas.ensureVisible(wp[5].x(), wp[5].y(), 200, 200)  # noqa: SLF001
    qtbot.wait(30)
    wp = [inner.pdf_to_widget(0, p) for p in pts]
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[0])
    for p in wp[1:]:
        QTest.mouseMove(inner, p)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[-1])
    qtbot.wait(60)
    live_page = window._document._backend._doc[0]  # noqa: SLF001 — keep the page while its annotations are read
    vertices = [list(a.vertices or []) for a in live_page.annots() or [] if a.type[1] == "Highlight"]
    assert vertices, "a highlight was created"
    quads = [fitz.Quad(vertices[0][i:i + 4]).rect for i in range(0, len(vertices[0]), 4)]
    covered = quads[0]
    for q in quads[1:]:
        covered |= q
    assert _iou(covered, target) > 0.6, f"zoom {zoom} rotation {rotation}: highlight {covered} vs word {target}"
    for name in ("alpha", "omega"):
        spill = covered & words[name]
        assert spill.is_empty or spill.get_area() < 0.15 * words[name].get_area(), f"spills onto '{name}'"
