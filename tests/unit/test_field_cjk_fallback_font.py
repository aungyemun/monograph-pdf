"""Japanese text in a word given a Latin-only font is drawn in the field's own font.

Before 0.5.1 RC 3, Japanese pasted with the source program's "Segoe UI" was drawn in MuPDF's
built-in gothic (Droid Sans Fallback), which looked bold beside the form's Mincho text.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from core.editing import system_fonts
from core.forms import appearance
from core.forms.rich_text import make_run

JP = "東浦町へ戻り、招へい人宅に滞在。"


def _mincho() -> fitz.Font | None:
    """MS Mincho on Windows; an installed Japanese serif font as a stand-in elsewhere."""
    font = system_fonts.load("MS Mincho", False, False)
    if font is not None:
        return font
    for path in ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",):
        if Path(path).is_file():
            idx = system_fonts.collection_index(path, "Noto Serif CJK JP", False, False)
            if idx is not None:
                return system_fonts._load_face(path, idx)  # noqa: SLF001 - registers it as an installed font
    return None


@pytest.fixture
def mincho(monkeypatch):
    font = _mincho()
    if font is None:
        pytest.skip("no installed Japanese Mincho font on this computer")
    real = system_fonts.load

    def load(family, bold=False, italic=False):
        if family == "MS Mincho" and not bold and not italic:
            return font
        if family == "MS Mincho":
            return None
        return real(family, bold, italic)

    monkeypatch.setattr(system_fonts, "load", load)
    return font


def _field(runs):
    return SimpleNamespace(
        value="".join(r["text"] for r in runs), runs=runs, font_family="MS Mincho", font_size=7.0,
        bold=False, italic=False, text_color="#000000",
    )


def _fonts(runs, family="MS Mincho"):
    field = _field(runs)
    field.font_family = family
    layout = appearance._Layout(field, multiline=True)  # noqa: SLF001
    layout.set_base(7.0)
    return layout, [f for f, _s, _l in layout.items]


def test_japanese_in_latin_word_font_uses_field_font(mincho):
    plain, plain_fonts = _fonts([make_run(JP)])
    assert sum(f is mincho for f in plain_fonts) > len(JP) // 2  # the field's own text is Mincho
    layout, fonts = _fonts([make_run(JP, family="Segoe UI"), make_run(" 0570")])
    # every Japanese character looks exactly as it would in the field's own font
    assert [f.name for f in fonts[: len(JP)]] == [f.name for f in plain_fonts]
    assert any(f is mincho for f in fonts[: len(JP)])
    assert not any(f is layout.cjk for f, p in zip(fonts, plain_fonts) if p is mincho)


def test_latin_field_font_keeps_builtin_cjk_fallback(mincho):
    # the field's own font has no Japanese either: the built-in CJK font, as before
    layout, fonts = _fonts([make_run(JP, family="Segoe UI")], family="Helvetica")
    assert all(f is layout.cjk for f in fonts)
