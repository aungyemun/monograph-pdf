"""Japanese text in a chosen Japanese font is shown (and laid out) in that font.

Regression (0.5.0 validation, also in earlier versions): for text with Japanese characters the
resolver put its Japanese fallback list (Yu Gothic UI, Yu Mincho …) before the chosen font, so a text
box set to MS Gothic, MS Mincho or Meiryo was drawn on screen and measured in Yu Gothic UI while Save
embedded MS Gothic — different glyph widths, line breaks and box height. Edit Text on saved text took
the PostScript name (MS-Gothic, YuGothic-Regular, TimesNewRomanPSMT) and came out in a substitute.

The Windows font database is not available on Qt's offscreen platform, so the installed fonts are
simulated at the resolver's boundary (``_match`` and the glyph check).
"""

from __future__ import annotations

import pytest

from core.editing import font_resolver as fr

INSTALLED = {"ms gothic": "MS Gothic", "ms mincho": "MS Mincho", "meiryo": "Meiryo", "yu gothic": "Yu Gothic",
             "yu gothic ui": "Yu Gothic UI", "yu mincho": "Yu Mincho", "arial": "Arial",
             "times new roman": "Times New Roman"}
LATIN_ONLY = {"Arial", "Times New Roman"}


@pytest.fixture
def installed(monkeypatch):
    def match(name, _available):
        key = (name or "").lower()
        if key in INSTALLED:
            return INSTALLED[key]
        compact = fr._compact(fr.normalize_family_name(name))  # noqa: SLF001
        return next((v for v in INSTALLED.values() if fr._compact(v) == compact), None)  # noqa: SLF001

    def missing(family, text):
        if family in LATIN_ONLY:
            return [c for c in text if ord(c) > 0x2E80]
        return []

    monkeypatch.setattr(fr, "_match", match)
    monkeypatch.setattr(fr, "glyph_coverage_missing", missing)
    monkeypatch.setattr(fr, "_available_families", lambda: {k for k in INSTALLED})
    monkeypatch.setattr(fr, "_register_bundled_with_qt", lambda: None)
    monkeypatch.setattr(fr, "_bundled_family_map", lambda: {})


@pytest.mark.parametrize("family", ["MS Gothic", "MS Mincho", "Meiryo", "Yu Gothic"])
def test_chosen_japanese_font_is_used_for_japanese_text(installed, family):
    res = fr.resolve_font(family, "日本語テキスト 123")
    assert res.resolved == family
    assert not res.substituted


def test_latin_font_with_japanese_text_still_falls_back(installed):
    res = fr.resolve_font("Arial", "日本語")
    assert res.resolved == "Yu Gothic UI"  # Arial has no Japanese characters
    assert res.substituted


@pytest.mark.parametrize(("ps_name", "text", "family"), [
    ("MS-Gothic", "改訂", "MS Gothic"),
    ("YuGothic-Regular", "改訂", "Yu Gothic"),
    ("MS-Mincho", "見出し", "MS Mincho"),
    ("TimesNewRomanPSMT", "Edited", "Times New Roman"),
    ("ArialMT", "Edited", "Arial"),
])
def test_postscript_names_resolve_to_the_installed_family(installed, ps_name, text, family):
    res = fr.resolve_font(ps_name, text)
    assert res.resolved == family
    assert not res.substituted


def test_edit_text_replacement_uses_installed_family(installed):
    from core.editing.geometry import Rect
    from core.editing.native_text import NativeSpan, span_to_textbox

    span = NativeSpan(span_id="p0-s1", page_index=0, text="明朝体", rect=Rect(10, 10, 60, 18),
                      font="ABCDEE+MS-Mincho", size=18.0, safe_direct=True)
    assert span_to_textbox(span).style.font_family == "MS Mincho"


def test_compact_names():
    c = fr._compact  # noqa: SLF001
    assert c("TimesNewRomanPSMT") == c("Times New Roman") == "timesnewroman"
    assert c("Arial MT") == c("Arial") == "arial"
    assert c("Yu Gothic") == c("YuGothic")
    assert c("MS") == "ms"  # short names are not cut
