"""Words selected in a text box keep their selection while the font box (or size box, colour) is used,
and only those words change: a run with its own font / size / bold / italic / colour, shown on screen,
undone and redone with the text, kept in the session and written into the saved PDF."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from PySide6.QtTest import QTest  # noqa: E402


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-word-formats"])
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page()
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1400, 900)
    w.show()
    w.activateWindow()
    w.raise_()
    assert w.open_path(src)
    qtbot.wait(50)
    yield w
    w.close_document(save_session=False)
    w.close()


def _typed_with_world_selected(w, qtbot, family="Noto Sans"):
    from core.editing.geometry import Rect

    box = w._edit.create_text_box(0, Rect(100, 100, 300, 40), text="")  # noqa: SLF001
    w._edit.change_style(box.object_id, font_family=family)  # noqa: SLF001
    w._edit.select([box.object_id])  # noqa: SLF001
    w._on_edit_changed()  # noqa: SLF001
    qtbot.wait(100)
    inner = w._canvas._canvas  # noqa: SLF001
    inner.open_text_editor(box.object_id)
    ed = inner.text_editor
    ed.setFocus()
    QTest.keyClicks(ed, "Hello world")
    cur = ed.textCursor()
    cur.setPosition(6)
    cur.setPosition(11, cur.MoveMode.KeepAnchor)
    ed.setTextCursor(cur)
    qtbot.wait(50)
    return box.object_id, inner


def _own(box, key):
    from core.forms.rich_text import char_styles

    keys = ("family", "size", "bold", "italic", "color")
    return [st[keys.index(key)] for st in char_styles(box.runs, box.text)]


def test_font_for_selected_words_only_and_selection_kept(win, qtbot):
    oid, inner = _typed_with_world_selected(win, qtbot)
    from PySide6.QtWidgets import QApplication

    picker = win._font_family  # noqa: SLF001
    picker.lineEdit().setFocus()  # clicking the font box takes the focus
    qtbot.wait(100)
    focus_moved = QApplication.focusWidget() is picker.lineEdit()
    assert inner.text_editor is not None, "using the font box closed the text box"
    assert inner.text_editor.textCursor().selectedText() == "world", "the selection was lost"
    win._apply_font_family("Noto Serif")  # noqa: SLF001
    box = win._edit.objects[oid]  # noqa: SLF001
    assert box.style.font_family == "Noto Sans", "the whole box changed"
    fams = _own(box, "family")
    assert fams[:6] == [None] * 6 and fams[6:] == ["Noto Serif"] * 5
    assert inner.text_editor.textCursor().selectedText() == "world"
    _ = focus_moved  # (offscreen: no focus change at all; on Windows it really moves to the font box)
    # size and colour of the same words; bold too
    win._canvas._canvas.format_field_selection(size=20.0)  # noqa: SLF001
    win._canvas._canvas.format_field_selection(color="#cc0000")  # noqa: SLF001
    win._canvas._canvas.format_field_selection(bold=True)  # noqa: SLF001
    box = win._edit.objects[oid]  # noqa: SLF001
    assert _own(box, "size")[6:] == [20.0] * 5 and _own(box, "color")[6:] == ["#cc0000"] * 5
    assert _own(box, "bold")[:6] == [None] * 6


def test_word_formats_undo_redo_and_survive_saving(win, qtbot, tmp_path):
    from engines.bake_edits import bake_via_backend

    oid, inner = _typed_with_world_selected(win, qtbot)
    win._apply_font_family("Noto Serif")  # noqa: SLF001
    inner.close_text_editor(commit=True)
    box = win._edit.objects[oid]  # noqa: SLF001
    assert box.text == "Hello world" and box.runs
    runs = [dict(r) for r in box.runs]
    win._edit.commands.undo()  # noqa: SLF001 — the whole typing session, formats included
    assert win._edit.objects[oid].runs == [] and win._edit.objects[oid].text == ""  # noqa: SLF001
    win._edit.commands.redo()  # noqa: SLF001
    assert win._edit.objects[oid].runs == runs  # noqa: SLF001
    # session file round trip
    from core.editing.text_box import TextBox

    again = TextBox.from_dict(win._edit.objects[oid].to_dict())  # noqa: SLF001
    assert again.runs == runs
    assert TextBox.from_dict({**again.to_dict(), "runs": "garbage"}).runs == []
    # saved PDF: "world" in the serif font, "Hello" in the sans font
    out = tmp_path / "out.pdf"
    bake_via_backend(win._edit, out)  # noqa: SLF001
    with fitz.open(out) as doc:
        spans = [s for b in doc[0].get_text("dict")["blocks"] for line in b.get("lines", []) for s in line["spans"]]
    fonts = {s["text"].strip(): s["font"] for s in spans if s["text"].strip()}
    hello = next(f for t, f in fonts.items() if "Hello" in t)
    world = next(f for t, f in fonts.items() if "world" in t)
    assert "serif" in world.lower() and "serif" not in hello.lower().replace("sans", ""), fonts


def test_whole_box_font_reaches_words_with_their_own_font(win, qtbot):
    oid, inner = _typed_with_world_selected(win, qtbot)
    win._apply_font_family("Noto Serif")  # noqa: SLF001
    inner.close_text_editor(commit=True)
    win._edit.select([oid])  # noqa: SLF001
    win._restyle_boxes(font_family="Noto Sans")  # noqa: SLF001 — nothing selected inside: the whole box
    box = win._edit.objects[oid]  # noqa: SLF001
    assert box.style.font_family == "Noto Sans" and set(_own(box, "family")) == {None}
    win._edit.commands.undo()  # noqa: SLF001
    assert _own(win._edit.objects[oid], "family")[6:] == ["Noto Serif"] * 5  # noqa: SLF001


def test_leaving_for_another_panel_still_finishes_typing(win, qtbot):
    from PySide6.QtWidgets import QApplication

    oid, inner = _typed_with_world_selected(win, qtbot)
    target = win._search_edit  # noqa: SLF001 — not a formatting control
    target.setFocus()
    qtbot.wait(50)
    if QApplication.focusWidget() is not target:
        pytest.skip("this platform gives no keyboard focus to an inactive window")
    qtbot.waitUntil(lambda: inner.text_editor is None, timeout=2000)
    assert win._edit.objects[oid].text == "Hello world"  # noqa: SLF001


def test_selection_stays_visible_without_focus(win, qtbot):
    from PySide6.QtGui import QPalette

    _oid, inner = _typed_with_world_selected(win, qtbot)
    pal = inner.text_editor.palette()
    active = pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
    inactive = pal.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight)
    assert inactive == active and inactive.alpha() == 255


def test_all_text_selected_changes_the_box_itself(win, qtbot):
    oid, inner = _typed_with_world_selected(win, qtbot)
    inner.text_editor.selectAll()
    win._apply_font_family("Noto Serif")  # noqa: SLF001
    box = win._edit.objects[oid]  # noqa: SLF001
    assert box.style.font_family == "Noto Serif" and box.runs == []
    assert inner.text_editor is not None and inner.text_editor.textCursor().selectedText() == "Hello world"
