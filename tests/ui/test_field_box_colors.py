"""Forms ▸ Add Field ▸ Text field: its background and border can be changed or removed in the
Properties panel; the choice is undoable and written into the saved PDF field (every reader shows it)."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from tests.ui.test_text_box_word_formats import win  # noqa: E402,F401


def _field(win):
    from core.editing.geometry import Rect

    f = win._edit.create_form_field(0, Rect(100, 100, 200, 24), "text")  # noqa: SLF001
    win._edit.field_selection = [f.object_id]  # noqa: SLF001
    win._on_edit_changed()  # noqa: SLF001
    return f


def test_background_and_border_can_be_removed_and_are_saved(win, qtbot, tmp_path):  # noqa: F811
    from engines.bake_edits import bake_via_backend

    f = _field(win)
    qtbot.waitUntil(lambda: hasattr(win._inspector, "_ffill") and win._inspector._field is f, timeout=3000)  # noqa: SLF001
    panel = win._inspector  # noqa: SLF001
    panel._ffill.setText("#00000000")  # noqa: SLF001 — "None"
    panel._apply_field_box()  # noqa: SLF001
    assert f.fill_color == "#00000000" and f.style_dirty
    panel._fborder.setText("#cc0000")  # noqa: SLF001
    panel._fbw.setValue(2.0)  # noqa: SLF001
    panel._apply_field_box()  # noqa: SLF001
    assert (f.border_color, f.border_width) == ("#cc0000", 2.0)
    f.value = "Hello"
    f.value_dirty = True
    out = tmp_path / "out.pdf"
    bake_via_backend(win._edit, out)  # noqa: SLF001
    with fitz.open(out) as doc:
        w = next(iter(doc[0].widgets()))
        assert w.fill_color in (None, [], ()), w.fill_color
        assert w.border_color and abs(w.border_color[0] - 0.8) < 0.02 and w.border_width == pytest.approx(2.0)
    # undo puts the previous border back
    win._edit.commands.undo()  # noqa: SLF001
    assert f.border_color != "#cc0000" or f.border_width != 2.0


def test_a_new_field_keeps_its_default_look_when_saved(win, tmp_path):  # noqa: F811
    from engines.bake_edits import bake_via_backend

    _field(win)
    out = tmp_path / "out.pdf"
    bake_via_backend(win._edit, out)  # noqa: SLF001
    with fitz.open(out) as doc:
        w = next(iter(doc[0].widgets()))
        assert w.fill_color and min(w.fill_color) > 0.95  # white background
        assert w.border_color and w.border_width >= 0.5
