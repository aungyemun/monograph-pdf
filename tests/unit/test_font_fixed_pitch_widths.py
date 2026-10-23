"""Saved text keeps each character's own width, also for "fixed pitch" Japanese fonts.

MS Mincho / MS Gothic declare themselves fixed pitch although full-width characters are twice as
wide as half-width ones. MuPDF then wrote one width for all glyphs (/W [0 65535 500]), so saved
Japanese text was spaced at half width and the characters overlapped (0.4.1 RC1, form fields set to
MS Mincho). Regression tests with a synthetic font and, on Windows, the real fonts."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import fitz
import pytest

pytest.importorskip("fontTools")

from core.editing import system_fonts as sf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "resources" / "fonts"


def _origins(page) -> list[float]:
    return [c[2][0] for span in page.get_texttrace() for c in span["chars"]]


def _write(font: fitz.Font, text: str, size: float = 10) -> fitz.Page:
    doc = fitz.open()
    page = doc.new_page(width=400, height=60)
    tw = fitz.TextWriter(page.rect)
    tw.append((10, 30), text, font=font, fontsize=size)
    tw.write_text(page)
    doc.subset_fonts()
    return fitz.open("pdf", doc.tobytes(garbage=3, deflate=True))[0]


@pytest.fixture
def falsely_fixed_font(tmp_path) -> Path:
    """The bundled Noto Sans with the fixed-pitch flag set although its widths differ."""
    from fontTools.ttLib import TTFont

    tt = TTFont(str(FONTS / "NotoSans-Regular.ttf"))
    tt["post"].isFixedPitch = 1
    path = tmp_path / "FakeMono.ttf"
    tt.save(str(path))
    return path


def test_flag_is_cleared_only_when_widths_really_differ(falsely_fixed_font):
    from fontTools.ttLib import TTFont

    tt = TTFont(str(falsely_fixed_font))
    assert sf._clear_false_fixed_pitch(tt) is True and tt["post"].isFixedPitch == 0  # noqa: SLF001
    assert sf._clear_false_fixed_pitch(tt) is False  # noqa: SLF001
    mono = TTFont(str(falsely_fixed_font))
    for name in mono["hmtx"].metrics:
        mono["hmtx"].metrics[name] = (600, 0)
    assert sf._clear_false_fixed_pitch(mono) is False and mono["post"].isFixedPitch == 1  # noqa: SLF001


def test_single_font_file_with_a_false_fixed_pitch_flag_keeps_its_widths(falsely_fixed_font):
    sf._load.cache_clear()  # noqa: SLF001
    font = sf._load(str(falsely_fixed_font))  # noqa: SLF001
    page = _write(font, "iWiW")
    xs = _origins(page)
    steps = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    assert steps[0] != steps[1], steps  # "i" and "W" keep different widths
    assert abs(steps[0] - font.text_length("i", fontsize=10)) < 0.05


def test_collection_face_with_a_false_fixed_pitch_flag_keeps_its_widths(tmp_path):
    from fontTools.ttLib import TTCollection, TTFont

    face = TTFont(str(FONTS / "NotoSans-Regular.ttf"))
    face["post"].isFixedPitch = 1
    coll = TTCollection()
    coll.fonts = [face]
    path = tmp_path / "fake.ttc"
    coll.save(str(path))
    sf._FACE_CACHE.clear()  # noqa: SLF001
    font = sf._load_face(str(path), 0)  # noqa: SLF001
    xs = _origins(_write(font, "iWiW"))
    steps = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    assert steps[0] != steps[1], steps


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows fonts")
@pytest.mark.parametrize("family", ["MS Mincho", "MS Gothic"])
def test_japanese_fixed_pitch_fonts_save_with_full_width_spacing(family):
    font = sf.load(family)
    if font is None:
        pytest.skip(f"{family} is not installed")
    xs = _origins(_write(font, "東浦町 070"))
    steps = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    assert steps[:2] == [10.0, 10.0], steps  # full-width kanji: 1 em
    assert steps[2] == 10.0 and steps[3] == 5.0 and steps[4] == 5.0, steps  # then half-width space / digits


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows fonts")
def test_form_field_in_ms_mincho_keeps_full_width_spacing_after_save():
    from core.forms import appearance

    if sf.load("MS Mincho") is None:
        pytest.skip("MS Mincho is not installed")
    text = "東浦町・大府市散策買物"
    field = types.SimpleNamespace(value=text, font_family="MS Mincho", font_size=10, bold=False, italic=False, runs=[],
                                  align="left", valign="top", multiline=False, character_spacing=0.0,
                                  rect=fitz.Rect(0, 0, 220, 20), border_width=0, border_color="")
    doc = fitz.open()
    page = doc.new_page(width=240, height=40)
    appearance.draw_text(page, fitz.Rect(5, 5, 235, 25), field, pad=2, multiline=False)
    doc.subset_fonts()
    back = fitz.open("pdf", doc.tobytes(garbage=3, deflate=True))[0]
    xs = _origins(back)
    assert len(xs) == len(text)
    assert all(round(b - a, 2) == 10.0 for a, b in zip(xs, xs[1:])), xs  # no overlapping characters
