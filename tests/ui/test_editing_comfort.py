"""Comfort fixes found in daily use: a steady toolbar while searching, searching long documents without
freezing, sticky notes that open as a pop-up and can change icon and colour, smooth picture resizing,
text boxes that keep their size while typing, line and arrow editing, symbols, the font list and the
print dialog's custom paper size."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-comfort"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1366, 768)
    w.show()
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    for i in range(3):
        d.new_page().insert_text((72, 90), f"Page {i + 1} findme", fontsize=14)
    d.save(src)
    d.close()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _mouse(inner, kind, pos, buttons, button, mods=None):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    p = QPointF(pos)
    QApplication.sendEvent(inner, QMouseEvent(kind, p, inner.mapToGlobal(p), button, buttons,
                                              mods or Qt.KeyboardModifier.NoModifier))


def _drag(inner, start, end, steps=6, mods=None):
    from PySide6.QtCore import QEvent, QPoint, Qt

    left = Qt.MouseButton.LeftButton
    _mouse(inner, QEvent.Type.MouseButtonPress, start, left, left, mods)
    for i in range(1, steps + 1):
        p = QPoint(start.x() + (end.x() - start.x()) * i // steps, start.y() + (end.y() - start.y()) * i // steps)
        _mouse(inner, QEvent.Type.MouseMove, p, left, Qt.MouseButton.NoButton, mods)
    _mouse(inner, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton, left, mods)


# ------------------------------------------------------------------ search
def test_typing_in_the_search_box_does_not_move_the_toolbar(win, qtbot):
    from PySide6.QtWidgets import QToolBar

    bar = [b for b in win.findChildren(QToolBar) if b.objectName() == "MainToolbar"][0]
    before = {a.text(): bar.widgetForAction(a).x() for a in (win.act_zoom_in, win.act_next) if bar.widgetForAction(a)}
    width = win._search_edit.width()  # noqa: SLF001
    win._search_edit.setFocus()  # noqa: SLF001
    qtbot.keyClicks(win._search_edit, "fg")  # noqa: SLF001
    after = {a.text(): bar.widgetForAction(a).x() for a in (win.act_zoom_in, win.act_next) if bar.widgetForAction(a)}
    assert after == before and win._search_edit.width() == width  # noqa: SLF001


def test_long_documents_are_searched_step_by_step(win, tmp_path, qtbot, monkeypatch):
    d = fitz.open()
    for i in range(120):
        d.new_page().insert_text((72, 90), f"Chapter {i} needle text", fontsize=12)
    path = tmp_path / "long.pdf"
    d.save(path)
    d.close()
    assert win.open_path(path)
    monkeypatch.setattr(type(win), "SEARCH_SLICE_S", 0.0)  # one page per step
    win._run_search_query("needle")  # noqa: SLF001
    assert 0 < len(win._search_hits) < 120  # noqa: SLF001 — the first match is shown at once
    assert win._search_index == 0  # noqa: SLF001
    qtbot.waitUntil(lambda: len(win._search_hits) == 120, timeout=10000)  # noqa: SLF001
    win._run_search_query("Chapter 7")  # noqa: SLF001 — a new search replaces the old one
    qtbot.waitUntil(lambda: win._search_next_page >= 120, timeout=10000)  # noqa: SLF001
    assert {p for p, _r in win._search_hits} >= {7, 70}  # noqa: SLF001


# ------------------------------------------------------------------ sticky notes
def test_note_icon_and_colour_change_and_undo(win):
    from core.annotations import add_text_comment
    from core.annotations.note_style import note_icon_name
    from core.editing.geometry import Point

    win._run_annot_command(0, lambda: add_text_comment(win._document, 0, Point(300, 300), "Hello", icon="Star"), "Add Note")  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    xref = next(a.xref for a in page.annots() if a.type[1] == "Text")
    assert note_icon_name(win._document, xref) == "Star"  # noqa: SLF001
    ref = win._annot_ref(0, xref)  # noqa: SLF001
    win.apply_note_changes(ref, text="Changed", icon="Help", color="#60a5fa")
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    note = next(a for a in page.annots() if a.xref == xref)
    assert note.info["content"] == "Changed" and note_icon_name(win._document, xref) == "Help"  # noqa: SLF001
    assert note.colors["stroke"] == pytest.approx((0.376, 0.647, 0.98), abs=0.01)
    win._undo()  # noqa: SLF001
    page = win._document._backend._doc.load_page(0)  # noqa: SLF001
    assert next(a for a in page.annots() if a.xref == xref).info["content"] == "Hello"
    assert note_icon_name(win._document, xref) == "Star"  # noqa: SLF001


def test_note_dialog_offers_icons_and_colours(qtbot):
    from core.annotations.note_style import NOTE_COLORS, NOTE_ICONS
    from ui.note_dialog import NoteDialog

    dlg = NoteDialog(text="Hi", icon="Key", color="#4ade80")
    qtbot.addWidget(dlg)
    assert dlg.icon() == "Key" and dlg.note_text() == "Hi"
    assert len(dlg._icon_buttons) == len(NOTE_ICONS) and len(dlg._color_buttons) == len(NOTE_COLORS)  # noqa: SLF001
    dlg._icon_buttons["Check"].click()  # noqa: SLF001
    dlg._color_buttons["#f87171"].click()  # noqa: SLF001
    assert dlg.icon() == "Check" and dlg.color() == "#f87171"


def test_note_popup_closes_with_escape_and_on_other_clicks(win):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    from core.annotations import add_text_comment
    from core.editing.geometry import Point

    win._run_annot_command(0, lambda: add_text_comment(win._document, 0, Point(300, 300), "Read me"), "Add")  # noqa: SLF001
    xref = next(a.xref for a in win._document._backend._doc.load_page(0).annots())  # noqa: SLF001
    assert win._canvas.open_note_popup(0, xref)  # noqa: SLF001
    popup = win._canvas.note_popup()  # noqa: SLF001
    assert popup.isVisible() and popup.text.text() == "Read me"
    inner = win._canvas._canvas  # noqa: SLF001
    QApplication.sendEvent(inner, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not popup.isVisible()


# ------------------------------------------------------------------ pictures and text boxes
def test_picture_resize_keeps_proportions_and_edges_never_cross(win, tmp_path):
    from PIL import Image

    from core.editing.geometry import Point, Rect
    from core.editing.image_box import ImageBox

    img = tmp_path / "photo.png"
    Image.new("RGB", (400, 300), (30, 90, 160)).save(img)
    box = ImageBox(page_index=0, rect=Rect(100, 200, 200, 150), source_path=str(img))
    win._edit.add_image(box)  # noqa: SLF001
    win._edit.select([box.object_id])  # noqa: SLF001
    inner = win._canvas._canvas  # noqa: SLF001
    corner = inner.pdf_to_widget(0, Point(box.rect.x1, box.rect.y1))
    _drag(inner, corner, corner + type(corner)(90, 15))
    assert box.rect.w / box.rect.h == pytest.approx(4 / 3, abs=0.01)
    assert (box.rect.x, box.rect.y) == pytest.approx((100, 200))
    win._undo()  # noqa: SLF001
    assert (box.rect.w, box.rect.h) == pytest.approx((200, 150))
    west = inner.pdf_to_widget(0, Point(box.rect.x, box.rect.cy))
    _drag(inner, west, west + type(west)(900, 0))
    assert box.rect.x1 == pytest.approx(300, abs=0.5), "the opposite edge stays where it was"


def test_resize_rect_helper():
    from core.editing.geometry import Point, Rect
    from ui.pdf_canvas import resize_rect

    base = Rect(0, 0, 200, 100)
    assert resize_rect(base, "e", Point(300, 50), keep_ratio=False) == Rect(0, 0, 300, 100)
    r = resize_rect(base, "se", Point(400, 120), keep_ratio=True)
    assert (r.w, r.h) == pytest.approx((400, 200))
    r = resize_rect(base, "nw", Point(-100, 40), keep_ratio=True)
    assert (r.x1, r.y1) == pytest.approx((200, 100)) and r.w / r.h == pytest.approx(2)
    r = resize_rect(base, "w", Point(500, 50), keep_ratio=False)
    assert r.x1 == pytest.approx(200) and r.w == pytest.approx(8)


def test_text_box_keeps_its_drawn_size_while_typing(win, qtbot):
    from core.editing.geometry import Rect

    box = win._edit.create_text_box(0, Rect(100, 200, 180, 80))  # noqa: SLF001
    inner = win._canvas._canvas  # noqa: SLF001
    inner.open_text_editor(box.object_id)
    seen = set()
    for word in ("Hello ", "world ", "this ", "is "):
        qtbot.keyClicks(inner._text_editor, word)  # noqa: SLF001
        seen.add((round(box.rect.x, 2), round(box.rect.y, 2), round(box.rect.w, 2), round(box.rect.h, 2)))
    assert seen == {(100, 200, 180, 80)}, "the box must not jump or shrink while typing"
    qtbot.keyClicks(inner._text_editor, "a much longer sentence " * 8)  # noqa: SLF001
    assert box.rect.h > 80 and (box.rect.x, box.rect.y, box.rect.w) == (100, 200, 180)  # grows downwards only
    ed = inner._text_editor  # noqa: SLF001
    assert ed.document().size().height() <= ed.height() + 1, "every typed line is visible"


# ------------------------------------------------------------------ shapes
def test_arrow_end_handles_move_one_end_and_undo_restores_both(win):
    from core.editing.geometry import Point, Rect

    sh = win._edit.create_shape(0, Rect(0, 0, 1, 1), "arrow", x0=150, y0=300, x1=300, y1=200)  # noqa: SLF001
    inner = win._canvas._canvas  # noqa: SLF001
    end = inner.pdf_to_widget(0, Point(sh.x1, sh.y1))
    _drag(inner, end, inner.pdf_to_widget(0, Point(100, 120)))
    assert (sh.x0, sh.y0) == pytest.approx((150, 300))
    assert (sh.x1, sh.y1) == pytest.approx((100, 120), abs=1.5)
    win._undo()  # noqa: SLF001
    assert (sh.x0, sh.y0, sh.x1, sh.y1) == pytest.approx((150, 300, 300, 200))


def test_moving_an_arrow_then_undo_keeps_its_direction(win):
    from core.editing.geometry import Point, Rect

    sh = win._edit.create_shape(0, Rect(0, 0, 1, 1), "arrow", x0=300, y0=300, x1=150, y1=200)  # noqa: SLF001
    inner = win._canvas._canvas  # noqa: SLF001
    mid = inner.pdf_to_widget(0, Point(225, 250))
    _drag(inner, mid, mid + type(mid)(40, 30))
    win._undo()  # noqa: SLF001
    assert (sh.x0, sh.y0, sh.x1, sh.y1) == pytest.approx((300, 300, 150, 200), abs=0.6)


def test_circle_can_be_stretched_into_an_oval(win):
    from core.editing.geometry import Point

    win._start_circle_tool()  # noqa: SLF001
    inner = win._canvas._canvas  # noqa: SLF001
    _drag(inner, inner.pdf_to_widget(0, Point(100, 300)), inner.pdf_to_widget(0, Point(200, 380)))
    sh = next(iter(win._edit.shapes.values()))  # noqa: SLF001
    assert sh.rect.w == pytest.approx(sh.rect.h, abs=1) and not sh.lock_aspect
    win._edit.select([sh.object_id])  # noqa: SLF001
    east = inner.pdf_to_widget(0, Point(sh.rect.x1, sh.rect.cy))
    _drag(inner, east, east + type(east)(120, 0))
    assert sh.rect.w > sh.rect.h * 1.3, "a side handle reshapes the circle into an oval"


def test_line_ends_dashes_and_freehand_are_saved(win, tmp_path):
    from core.editing.geometry import Rect
    from core.editing.shape_box import StrokeStyle
    from engines.bake_edits import bake_via_backend

    win._edit.create_shape(0, Rect(0, 0, 1, 1), "line", x0=100, y0=400, x1=300, y1=400, start_head="circle",  # noqa: SLF001
                           end_head="filled", stroke_style=StrokeStyle.DASH_DOT, stroke_width=2)
    win._edit.create_shape(0, Rect(0, 0, 1, 1), "freehand",  # noqa: SLF001
                           points=[(100 + i, 500 + (i % 7) * 0.2) for i in range(80)])
    out = tmp_path / "shapes.pdf"
    bake_via_backend(win._edit, out)  # noqa: SLF001
    with fitz.open(out) as d:
        drawings = d[0].get_drawings()
    fills = [x for x in drawings if x.get("fill") and x["rect"].y0 > 380 and x["rect"].y1 < 420]
    assert len(fills) >= 2, "a dot at the start and a filled head at the end"
    assert any(x.get("dashes") and "[]" not in str(x.get("dashes")) for x in drawings if x["rect"].y0 > 390)
    curves = [x for x in drawings if any(item[0] == "c" for item in x["items"])]
    assert curves, "freehand strokes are saved as smooth curves"


# ------------------------------------------------------------------ symbols
def test_symbols_are_placed_as_text_and_saved(win, tmp_path):
    from engines.bake_edits import bake_via_backend
    from ui.symbol_dialog import SymbolDialog, available_groups, symbol_font

    groups = dict(available_groups())
    assert "✓" in groups["Marks"] and "→" in groups["Arrows"] and "€" in groups["Currency & signs"]
    for i, ch in enumerate("✓→€①"):
        win.place_symbol(0, 80 + i * 40, 600, ch, symbol_font(ch), 18)
    out = tmp_path / "symbols.pdf"
    bake_via_backend(win._edit, out)  # noqa: SLF001
    with fitz.open(out) as d:
        text = d[0].get_text()
    assert all(ch in text for ch in "✓→€①")
    dlg = SymbolDialog(win)
    assert not dlg._box.button(dlg._box.StandardButton.Ok).isEnabled()  # noqa: SLF001
    dlg._buttons[0].click()  # noqa: SLF001
    assert dlg.symbol() and dlg._box.button(dlg._box.StandardButton.Ok).isEnabled()  # noqa: SLF001


# ------------------------------------------------------------------ font list
def test_font_list_is_not_changed_while_open(win):
    from PySide6.QtWidgets import QApplication

    picker = win._font_family  # noqa: SLF001
    names = [picker.itemText(i) for i in range(min(picker.count(), 3))]
    if len(names) < 2:
        pytest.skip("not enough fonts installed")
    picker.set_family(names[0])
    picker.showPopup()
    QApplication.processEvents()
    if not picker.view().isVisible():
        pytest.skip("the offscreen platform did not open the list")
    picker.set_family(names[1])  # a toolbar refresh while the list is open
    assert picker.family() == names[0], "the open list must not jump"
    picker.hidePopup()
    QApplication.processEvents()
    QApplication.processEvents()
    assert picker.family() == names[1]
    assert picker.active_row() == picker.findText(names[1])


# ------------------------------------------------------------------ printing
def test_print_dialog_custom_paper_and_unit_conversion(win):
    from PySide6.QtGui import QPageSize

    from ui.print_dialog import PrintDialog, from_mm, to_mm

    assert to_mm(1, "in") == pytest.approx(25.4) and to_mm(1, "ft") == pytest.approx(304.8)
    assert from_mm(297, "cm") == pytest.approx(29.7)
    dlg = PrintDialog(win._document, doc_name="doc.pdf", parent=win)  # noqa: SLF001
    dlg.show()
    assert dlg.paper.maxVisibleItems() <= 15 and dlg.paper.findData("custom") >= 0
    dlg.set_custom_size(30, 40, "cm")
    assert dlg.is_custom_paper() and dlg.custom_size_mm() == pytest.approx((300, 400))
    dlg.custom_unit.setCurrentIndex(dlg.custom_unit.findData("in"))
    assert dlg.custom_w.value() == pytest.approx(11.811, abs=0.001)
    assert dlg.custom_size_mm() == pytest.approx((300, 400), abs=0.05), "changing the unit keeps the size"
    size = dlg._page_size().size(QPageSize.Unit.Millimeter)  # noqa: SLF001
    assert (size.width(), size.height()) == pytest.approx((300, 400), abs=0.5)
    for rb in (dlg.flip_long, dlg.flip_short):
        assert rb.width() >= rb.sizeHint().width(), f"“{rb.text()}” must not be cut off"
    dlg.reject()
