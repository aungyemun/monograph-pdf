"""Round 7: Highlight toggle, mid-stroke Esc, colour switching, eraser, preservation across edits."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

TEMPLATES = Path(__file__).resolve().parents[1] / "fixtures" / "templates"
PLAYGROUND = TEMPLATES / "pdf" / "highlight_playground.pdf"
if not PLAYGROUND.is_file():  # pragma: no cover
    pytest.skip("template PDFs not generated", allow_module_level=True)

TEXT_Y = 118.0


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-hl7"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 900)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(window, tmp_path, src=PLAYGROUND, name="work.pdf", rotation=0):
    dst = tmp_path / name
    d = fitz.open(src.as_posix())
    if rotation:
        d[0].set_rotation(rotation)
    d.save(dst.as_posix())
    d.close()
    assert window.open_path(dst)
    return dst


def _drag(window, qtbot, page, pts):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    inner = window._canvas._canvas  # noqa: SLF001
    wp = [inner.pdf_to_widget(page, Point(x, y)) for x, y in pts]
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[0])
    for p in wp[1:]:
        QTest.mouseMove(inner, p)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wp[-1])
    qtbot.wait(60)


def _click(window, qtbot, page, x, y):
    _drag(window, qtbot, page, [(x, y)])


def _line(x0, x1, y, n=12):
    return [(x0 + (x1 - x0) * i / n, y) for i in range(n + 1)]


def _annots(window, subtype=None):
    from types import SimpleNamespace

    out = []
    for p in window._document._backend._doc:  # noqa: SLF001
        for a in p.annots() or []:
            if subtype is None or a.type[1] == subtype:
                out.append(
                    SimpleNamespace(
                        type=a.type,
                        xref=a.xref,
                        rect=fitz.Rect(a.rect),
                        opacity=a.opacity,
                        border=a.border,
                        info=a.info,
                        colors=a.colors,
                        vertices=a.vertices,
                    )
                )
    return out


def _esc(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.keyClick(window._canvas._canvas, Qt.Key.Key_Escape)  # noqa: SLF001
    qtbot.wait(30)


def test_highlight_button_toggles_off_without_escape(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    assert window._markup_sticky == "highlight"  # noqa: SLF001
    _drag(window, qtbot, 0, _line(380, 500, 740))
    assert len(_annots(window)) == 1
    window.act_annot_highlight.trigger()  # second click → Select
    assert window._markup_sticky is None  # noqa: SLF001
    assert window.act_select_tool.isChecked()
    assert not window._canvas.region_pick_active  # noqa: SLF001
    assert len(_annots(window)) == 1  # preserved


def test_mid_stroke_escape_cancels_only_unfinished_stroke(window, qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    assert len(_annots(window)) == 1

    inner = window._canvas._canvas  # noqa: SLF001
    a = inner.pdf_to_widget(0, Point(380, 770))
    b = inner.pdf_to_widget(0, Point(450, 770))
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(inner, b)
    assert window._canvas.region_stroke_in_progress  # noqa: SLF001
    _esc(window, qtbot)  # cancel unfinished stroke only
    assert window._canvas.region_pick_active  # still in Highlight  # noqa: SLF001
    assert window._markup_sticky == "highlight"  # noqa: SLF001
    assert len(_annots(window)) == 1
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    qtbot.wait(40)
    assert len(_annots(window)) == 1  # aborted stroke not saved
    _esc(window, qtbot)  # second Esc → Select
    assert window.act_select_tool.isChecked()
    assert not window._canvas.region_pick_active  # noqa: SLF001


def test_color_switch_keeps_prior_colours_and_mode(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    window._set_highlight_color("#ff69b4")  # noqa: SLF001
    qtbot.wait(40)
    assert window._canvas.region_pick_active  # noqa: SLF001
    _drag(window, qtbot, 0, _line(380, 500, 770))
    window._set_highlight_color("#90ee90")  # noqa: SLF001
    qtbot.wait(40)
    _drag(window, qtbot, 0, _line(380, 500, 800))
    cols = [tuple(round(c * 255) for c in a.colors["stroke"]) for a in _annots(window, "Ink")]
    assert cols == [(255, 255, 0), (255, 105, 180), (144, 238, 144)]


def test_eraser_removes_one_annotation_and_stays_active(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    _drag(window, qtbot, 0, _line(380, 500, 770))
    _drag(window, qtbot, 0, _line(380, 500, 800))
    assert len(_annots(window)) == 3
    window.act_annot_eraser.trigger()
    assert window._eraser_active  # noqa: SLF001
    # Click middle stroke
    _click(window, qtbot, 0, 440, 770)
    assert len(_annots(window)) == 2
    assert window._eraser_active and window._canvas.region_pick_active  # noqa: SLF001
    # Remaining two still present at 740 and 800
    ys = sorted((a.rect.y0 + a.rect.y1) / 2 for a in _annots(window))
    assert abs(ys[0] - 740) < 15 and abs(ys[1] - 800) < 15


def test_eraser_undo_redo_independent(window, qtbot, tmp_path):
    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    window._set_highlight_color("#ff69b4")  # noqa: SLF001
    qtbot.wait(30)
    _drag(window, qtbot, 0, _line(380, 500, 770))
    window._set_highlight_color("#90ee90")  # noqa: SLF001
    qtbot.wait(30)
    _drag(window, qtbot, 0, _line(380, 500, 800))
    window.act_annot_eraser.trigger()
    _click(window, qtbot, 0, 440, 770)
    assert len(_annots(window)) == 2
    assert window._edit.undo()  # noqa: SLF001
    assert len(_annots(window)) == 3
    mid = [a for a in _annots(window, "Ink") if abs((a.rect.y0 + a.rect.y1) / 2 - 770) < 15][0]
    assert tuple(round(c * 255) for c in mid.colors["stroke"]) == (255, 105, 180)
    assert window._edit.redo()  # noqa: SLF001
    assert len(_annots(window)) == 2


def test_highlights_survive_text_box_shape_and_save(window, qtbot, tmp_path):
    from core.editing.edit_model import EditTool
    from core.editing.geometry import Rect

    dst = _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(75, 280, TEXT_Y - 4))
    _drag(window, qtbot, 0, _line(380, 500, 740))
    n = len(_annots(window))
    assert n >= 2
    window.act_text_tool.trigger()
    assert not window._canvas.region_pick_active  # noqa: SLF001
    window._edit.create_text_box(0, Rect(100, 200, 160, 40), text="Over highlight")  # noqa: SLF001
    window._set_tool(EditTool.SHAPE_RECT)
    window._edit.create_shape(0, Rect(350, 700, 120, 60), "rectangle")  # noqa: SLF001
    assert len(_annots(window)) == n  # native annots untouched
    window.act_select_tool.trigger()
    window.save_document()
    d = fitz.open(dst.as_posix())
    try:
        assert len(list(d[0].annots() or [])) == n
        assert any(a.type[1] == "Highlight" for a in d[0].annots())
        assert any(a.type[1] == "Ink" for a in d[0].annots())
    finally:
        d.close()
    window.close_document(save_session=False)
    assert window.open_path(dst)
    assert len(_annots(window)) == n


def test_highlights_survive_form_field_overlay(window, qtbot, tmp_path):
    """Native highlights remain when a form field is created and filled (same page)."""
    from core.editing.geometry import Rect

    _open(window, tmp_path)
    window.act_annot_highlight.trigger()
    _drag(window, qtbot, 0, _line(380, 500, 740))
    n = len(_annots(window))
    assert n == 1
    window.act_select_tool.trigger()
    field = window._edit.create_form_field(0, Rect(80, 160, 180, 28), "text")  # noqa: SLF001
    window._edit.set_field_value(field.object_id, "Round7 fill")  # noqa: SLF001
    assert len(_annots(window)) == n
    assert window._edit.fields[field.object_id].value == "Round7 fill"  # noqa: SLF001


@pytest.mark.parametrize("rotation", [0, 90, 270])
def test_eraser_hit_test_on_rotated_page(window, qtbot, tmp_path, rotation):
    _open(window, tmp_path, rotation=rotation)
    import fitz as _f

    pg = window._document._backend._doc[0]  # noqa: SLF001
    p_a = _f.Point(380, 745) * pg.rotation_matrix
    p_b = _f.Point(500, 745) * pg.rotation_matrix
    window.act_annot_highlight.trigger()
    _drag(
        window,
        qtbot,
        0,
        [(p_a.x + (p_b.x - p_a.x) * i / 10, p_a.y + (p_b.y - p_a.y) * i / 10) for i in range(11)],
    )
    assert len(_annots(window, "Ink")) == 1
    window.act_annot_eraser.trigger()
    mid = _f.Point(440, 745) * pg.rotation_matrix
    _click(window, qtbot, 0, mid.x, mid.y)
    assert not _annots(window)


def test_core_erase_command_roundtrip(tmp_path):
    from core.annotations import annotations_at
    from core.document import open_document
    from core.editing.annot_commands import EraseAnnotCommand, HighlightStrokeCommand
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Point, Rect

    src = tmp_path / "e.pdf"
    d = fitz.open()
    d.new_page(width=400, height=400)
    d.save(src.as_posix())
    d.close()
    doc = open_document(src)
    edit = EditableDocument(doc)
    cmd = HighlightStrokeCommand(
        doc, edit, 0, [Rect(40, 40, 80, 12)], [[(200, 200), (300, 200)]], color=(1, 1, 0)
    )
    edit.commands.execute(cmd)
    assert len(list(doc._backend._doc[0].annots() or [])) == 2  # noqa: SLF001
    hits = annotations_at(doc, 0, Point(250, 200))
    assert hits and hits[-1]["kind"] == "Ink"
    erase = EraseAnnotCommand(doc, edit, 0, hits[-1]["xref"])
    edit.commands.execute(erase)
    assert len(list(doc._backend._doc[0].annots() or [])) == 1  # noqa: SLF001
    edit.commands.undo()
    assert len(list(doc._backend._doc[0].annots() or [])) == 2  # noqa: SLF001
    doc.close()
