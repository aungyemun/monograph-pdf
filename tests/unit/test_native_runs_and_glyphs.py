"""Edit Text works on whole runs of text, and the glyph check asks the font file itself.

Regressions found in the 0.5.0 validation:
* Text placed word by word (also text saved by Monograph PDF, whose spaces come from its built-in
  font) was editable only one word at a time; a longer word was drawn over the next one.
* ``glyph_coverage_missing`` used PySide6's one-character ``inFont(str)``, which answers wrongly for
  non-ASCII characters (Arial "had" ゴ, MS Gothic "lacked" Ｍ), so fonts were substituted for no reason.
"""

from __future__ import annotations

import os

import pytest

from core.editing.native_text import _merge_word_spans


def _span(text, x0, x1, font="ArialMT", size=12.0, color=0, flags=0, y0=100.0):
    return {"text": text, "bbox": (x0, y0, x1, y0 + size * 1.1), "font": font, "size": size, "color": color,
            "flags": flags}


def test_words_and_foreign_spaces_form_one_run():
    line = {"dir": (1.0, 0.0), "spans": [
        _span("Arial", 44.0, 68.0), _span(" ", 68.0, 71.1, font="Droid Sans Fallback Regular"),
        _span("12", 71.1, 84.5), _span(" ", 84.5, 87.6, font="Droid Sans Fallback Regular"),
        _span("red", 87.6, 105.0)]}
    runs = _merge_word_spans(line)
    assert [r["text"] for r in runs] == ["Arial 12 red"]
    assert runs[0]["bbox"][0] == 44.0 and runs[0]["bbox"][2] == 105.0


def test_other_style_or_far_apart_stays_separate():
    line = {"dir": (1.0, 0.0), "spans": [
        _span("Name:", 40, 72), _span("Bold", 75, 100, font="Arial-BoldMT", flags=16),
        _span("next", 103, 125), _span("column", 300, 340)]}
    assert [r["text"] for r in _merge_word_spans(line)] == ["Name:", "Bold", "next", "column"]


def test_touching_glyph_runs_join_without_a_space():
    line = {"dir": (1.0, 0.0), "spans": [_span("日本", 40, 64), _span("語", 64.2, 76)]}
    assert [r["text"] for r in _merge_word_spans(line)] == ["日本語"]


def test_vertical_lines_are_left_alone():
    line = {"dir": (0.0, 1.0), "spans": [_span("縦", 40, 52), _span("書き", 40, 52, y0=114)]}
    assert len(_merge_word_spans(line)) == 2


def test_glyph_check_uses_the_font_itself(qtbot):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QFontDatabase

    if "Arial" not in QFontDatabase.families():
        pytest.skip("Arial is not available to Qt here (offscreen without a font folder)")
    from core.editing.font_inventory import glyph_coverage_missing

    assert glyph_coverage_missing("Arial", "aé€") == []  # a, é, €
    assert glyph_coverage_missing("Arial", "aゴ") == ["ゴ"]  # Arial has no Japanese


def test_glyph_check_does_not_crash_without_fonts(qtbot):
    """Offscreen without a font folder Qt has no fonts; QRawFont.fromFont would crash the process."""
    from core.editing.font_inventory import glyph_coverage_missing

    assert isinstance(glyph_coverage_missing("Arial", "aゴ"), list)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
