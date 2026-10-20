"""Text typing/paste undo and highlight color / pen-stroke markup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-text-undo"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


@pytest.fixture
def doc_window(window, tmp_path):
    src = tmp_path / "work.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    assert window.open_path(src)
    return window


def test_typing_then_ctrl_z_restores_text_in_editor(doc_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Rect

    w = doc_window
    box = w._edit.create_text_box(0, Rect(72, 72, 200, 40), text="Hello")  # noqa: SLF001
    oid = box.object_id
    inner = w._canvas._canvas  # noqa: SLF001
    assert inner.open_text_editor(oid)
    editor = inner._text_editor
    assert editor is not None
    editor.setFocus()
    qtbot.wait(20)
    editor.insertPlainText(" world")
    assert w._edit.objects[oid].text == "Hello world"  # noqa: SLF001
    assert editor.document().isUndoAvailable()
    QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(20)
    assert w._edit.objects[oid].text == "Hello"  # noqa: SLF001


def test_paste_then_undo_in_editor(doc_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from core.editing.geometry import Rect

    w = doc_window
    box = w._edit.create_text_box(0, Rect(80, 80, 220, 40), text="Base")  # noqa: SLF001
    oid = box.object_id
    inner = w._canvas._canvas  # noqa: SLF001
    assert inner.open_text_editor(oid)
    editor = inner._text_editor
    assert editor is not None
    editor.setFocus()
    QGuiApplication.clipboard().setText(" pasted")
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(20)
    assert "pasted" in w._edit.objects[oid].text  # noqa: SLF001
    QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(20)
    assert w._edit.objects[oid].text == "Base"  # noqa: SLF001


def test_close_editor_then_document_undo_restores_session(doc_window, qtbot):
    from core.editing.geometry import Rect

    w = doc_window
    box = w._edit.create_text_box(0, Rect(90, 90, 200, 36), text="Start")  # noqa: SLF001
    oid = box.object_id
    # create_text_box already on undo stack; clear interaction by closing editor commit
    inner = w._canvas._canvas  # noqa: SLF001
    assert inner.open_text_editor(oid)
    editor = inner._text_editor
    editor.insertPlainText(" X")
    inner.close_text_editor(commit=True)
    assert w._edit.objects[oid].text == "Start X"  # noqa: SLF001
    assert w._edit.undo()  # noqa: SLF001
    assert w._edit.objects[oid].text == "Start"  # noqa: SLF001


def test_highlight_color_pref_and_pen_stroke(doc_window, qtbot):
    from core.annotations import list_annotations
    from core.editing.geometry import Point

    w = doc_window
    w._prefs.highlight_color = "#90ee90"  # noqa: SLF001
    w._refresh_highlight_color_button()  # noqa: SLF001
    assert w._highlight_color_button is not None  # noqa: SLF001

    hits = w._document.search("alpha-bravo-charlie")  # noqa: SLF001
    assert hits
    page, r = hits[0]
    # Simulate pen stroke across the hit
    stroke = [
        Point(r.x0 - 2, (r.y0 + r.y1) / 2),
        Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2),
        Point(r.x1 + 2, (r.y0 + r.y1) / 2),
    ]
    w._canvas._canvas._last_region_stroke = stroke  # noqa: SLF001
    w.act_annot_highlight.trigger()
    # Drive apply via the same path as a finished stroke pick
    from core.editing.geometry import Rect

    area = Rect(r.x0 - 4, r.y0 - 2, r.width + 8, r.height + 4)
    # Call the markup tool's apply by finishing a stroke pick manually
    w._canvas.cancel_region_pick(announce=False)
    applied = {"ok": False}

    def on_done(p, rect):
        from core.annotations import text_rects_along_stroke
        from core.editing.annot_commands import MarkupAnnotCommand

        page_pts = [w._to_page_point(p, pt.x, pt.y) for pt in stroke]  # noqa: SLF001
        lines = text_rects_along_stroke(w._document, p, page_pts)  # noqa: SLF001
        assert lines
        color = w._markup_color_rgb("highlight")  # noqa: SLF001
        assert color[1] > color[0]  # green-ish #90ee90
        w._edit.commands.execute(  # noqa: SLF001
            MarkupAnnotCommand(w._document, w._edit, p, "highlight", lines, color=color)  # noqa: SLF001
        )
        applied["ok"] = True
        w._after_annotation(p, "Highlight added")  # noqa: SLF001

    on_done(page, area)
    assert applied["ok"]
    annots = [a for a in list_annotations(w._document) if a.kind.lower() == "highlight"]  # noqa: SLF001
    assert annots
    assert w._edit.commands.can_undo_now  # noqa: SLF001
    before = len(annots)
    assert w._edit.undo()  # noqa: SLF001
    after = [a for a in list_annotations(w._document) if a.kind.lower() == "highlight"]  # noqa: SLF001
    assert len(after) == before - 1


def test_highlight_tool_creates_undoable_annot_via_ui(doc_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.annotations import list_annotations
    from core.editing.geometry import Point

    w = doc_window
    hits = w._document.search("alpha-bravo-charlie")  # noqa: SLF001
    assert hits
    page, r = hits[0]
    w._set_highlight_color("#ffa500")  # noqa: SLF001
    w.act_annot_highlight.trigger()
    assert w._canvas.region_pick_active
    inner = w._canvas._canvas  # noqa: SLF001
    p0 = inner.pdf_to_widget(page, Point(r.x0, (r.y0 + r.y1) / 2))
    p1 = inner.pdf_to_widget(page, Point(r.x1, (r.y0 + r.y1) / 2))
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    # intermediate points for a pen stroke
    mid = inner.pdf_to_widget(page, Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
    QTest.mouseMove(inner, mid)
    QTest.mouseMove(inner, p1)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
    qtbot.wait(40)
    annots = [a for a in list_annotations(w._document) if a.kind.lower() == "highlight"]  # noqa: SLF001
    assert annots, "pen highlight not created"
    assert w._edit.dirty  # noqa: SLF001
    assert w._edit.undo()  # noqa: SLF001
    left = [a for a in list_annotations(w._document) if a.kind.lower() == "highlight"]  # noqa: SLF001
    assert len(left) < len(annots)


def test_stroke_selects_only_touched_characters_on_one_line(doc_window):
    from core.annotations import text_rects_along_stroke
    from core.editing.geometry import Point

    w = doc_window
    page, r = w._document.search("alpha-bravo-charlie")[0]  # noqa: SLF001
    ym = (r.y0 + r.y1) / 2
    full = text_rects_along_stroke(w._document, page, [Point(r.x0 - 1, ym), Point(r.x1 + 1, ym)])  # noqa: SLF001
    half = text_rects_along_stroke(w._document, page, [Point(r.x0 - 1, ym), Point((r.x0 + r.x1) / 2, ym)])  # noqa: SLF001
    assert len(full) == 1 and len(half) == 1
    assert half[0].x1 < full[0].x1 - 5  # partial stroke → partial highlight
    # a stroke well above the line (in the margin of the line above) selects nothing on this line
    above = text_rects_along_stroke(w._document, page, [Point(r.x0, r.y0 - 12), Point(r.x1, r.y0 - 12)])  # noqa: SLF001
    assert all(abs(a.y - full[0].y) > 3 for a in above)


def test_pen_preview_uses_selected_color(doc_window):
    w = doc_window
    w._prefs.highlight_color = "#87cefa"  # noqa: SLF001
    w.act_annot_highlight.trigger()
    c = w._canvas._canvas  # noqa: SLF001
    assert c.region_pick_active
    assert c._region_stroke_color.name() == "#87cefa"  # noqa: SLF001
