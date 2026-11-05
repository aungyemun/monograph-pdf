"""Selecting and copying existing page text: the model (core/text_selection.py), without Qt.

Text in every test is written into synthetic PDFs with PyMuPDF; expected strings are the strings
written, never strings read back by the code under test.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.text_selection import (
    PageTextCache,
    TextPosition,
    TextSelection,
    char_class,
    extract_page_text,
    is_cjk,
)

ROOT = Path(__file__).resolve().parents[2]
NOTO = ROOT / "resources" / "fonts" / "NotoSans-Regular.ttf"


def _page(lines: list[tuple[str, dict]], *, rotation: int = 0, width: float = 595, height: float = 842):
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    if NOTO.exists():
        page.insert_font(fontname="noto", fontfile=str(NOTO))
    y = 80
    for text, kw in lines:
        kw = dict(kw)
        pos = kw.pop("pos", (72, y))
        page.insert_text(pos, text, **({"fontsize": 12} | kw))
        y += 30
    page.set_rotation(rotation)
    return doc, doc[0]


def _all(pt) -> str:
    return pt.text(0, len(pt.glyphs))


def test_english_lines_keep_their_text_and_line_breaks():
    _doc, page = _page([("Hello world, this is line one.", {}), ("Second line: 42 apples.", {})])
    pt = extract_page_text(page)
    assert _all(pt) == "Hello world, this is line one.\nSecond line: 42 apples."
    assert len(pt.lines) == 2


@pytest.mark.parametrize("text", [
    "ひらがなのぶんしょうです",  # Hiragana
    "カタカナノテキスト",  # Katakana
    "日本語漢字文書",  # Kanji
    "東京タワーは333メートルです。",  # mixed scripts, digits, Japanese punctuation
])
def test_japanese_is_copied_without_added_spaces(text):
    _doc, page = _page([(text, {"fontname": "japan"})])
    pt = extract_page_text(page)
    assert _all(pt) == text
    assert " " not in _all(pt)


def test_mixed_english_and_japanese_keeps_only_the_spaces_in_the_pdf():
    text = "Monograph PDF で 日本語 と English を混ぜる"
    _doc, page = _page([(text, {"fontname": "japan"})])
    assert _all(extract_page_text(page)) == text


@pytest.mark.skipif(not NOTO.exists(), reason="bundled Noto Sans font missing")
def test_accents_symbols_and_combining_marks():
    precomposed = "Café naïve façade — “quotes” ± € © § ° ¶"  # characters of the bundled font
    combining = "Café naïve"
    _doc, page = _page([(precomposed, {"fontname": "noto"}), (combining, {"fontname": "noto"})])
    pt = extract_page_text(page)
    lines = _all(pt).split("\n")
    assert lines[0] == precomposed
    assert lines[1] == combining
    # the combining acute belongs to its "e": a selection boundary can never split them
    second = pt.lines[1]
    clusters = [g.text for g in pt.glyphs[second.start:second.end]]
    assert "é" in clusters and "ï" in clusters
    assert pt.text(second.start, second.start + 4) == "Café"


def test_different_fonts_on_one_line_are_joined_as_one_line():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Times part", fontname="tiro", fontsize=12)
    x = 72 + fitz.get_text_length("Times part ", fontname="tiro", fontsize=12)
    page.insert_text((x, 100), "Courier part", fontname="cour", fontsize=12)
    assert _all(extract_page_text(page)) == "Times part Courier part"


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotated_pages_give_the_same_text_and_display_space_boxes(rotation):
    doc, page = _page([("alpha beta gamma", {})], rotation=rotation)
    pt = extract_page_text(page)
    assert _all(pt) == "alpha beta gamma"
    # the box of "beta" equals MuPDF's own search hit, turned into display space
    hit = page.search_for("beta")[0] * page.rotation_matrix
    hit.normalize()
    start = _all(pt).index("beta")
    (x0, y0, x1, y1), = pt.rects(start, start + 4)
    sel = fitz.Rect(x0, y0, x1, y1)
    inter = sel & hit
    assert not inter.is_empty and inter.get_area() / (sel | hit).get_area() > 0.6
    assert fitz.Rect(0, 0, page.rect.width, page.rect.height).contains(sel)


def test_position_at_and_word_line_block_ranges():
    _doc, page = _page([("first paragraph line", {}), ("second line here", {}), ("third", {"pos": (72, 300)})])
    pt = extract_page_text(page)
    text = _all(pt)
    i = text.index("paragraph") + 2
    a, b = pt.word_range(i)
    assert pt.text(a, b) == "paragraph"
    a, b = pt.line_range(i)
    assert pt.text(a, b) == "first paragraph line"
    g = pt.glyphs[i]
    # a point in the left half of a glyph is before it, in the right half after it
    assert pt.position_at(g.x0 + 0.2 * (g.x1 - g.x0), g.cy) == i
    assert pt.position_at(g.x1 - 0.2 * (g.x1 - g.x0), g.cy) == i + 1
    a, b = pt.block_range(i)
    assert "first paragraph line" in pt.text(a, b)


def test_japanese_word_selection_takes_a_run_of_one_script():
    text = "東京タワーはとても高い"
    _doc, page = _page([(text, {"fontname": "japan"})])
    pt = extract_page_text(page)
    assert pt.text(*pt.word_range(text.index("タ") + 1)) == "タワー"
    assert pt.text(*pt.word_range(0)) == "東京"
    assert pt.text(*pt.word_range(text.index("と"))) == "はとても"


def test_multi_column_layout_keeps_columns_apart():
    doc = fitz.open()
    page = doc.new_page()
    left = ["Left column one", "Left column two", "Left column three"]
    right = ["Right column one", "Right column two", "Right column three"]
    for i, t in enumerate(left):
        page.insert_text((50, 100 + 14 * i), t, fontsize=11)
    for i, t in enumerate(right):
        page.insert_text((320, 100 + 14 * i), t, fontsize=11)
    pt = extract_page_text(page)
    text = _all(pt)
    for t in left + right:
        assert t in text.split("\n")
    # selecting inside the right column never copies text of the left one
    lines = [ln for ln in pt.lines if pt.text(ln.start, ln.end).startswith("Right")]
    sel = pt.text(lines[0].start, lines[-1].end)
    assert "Left" not in sel and sel == "\n".join(right)


def test_invisible_ocr_layer_is_selectable():
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
    pix.clear_with(200)
    page.insert_image(fitz.Rect(50, 50, 450, 250), pixmap=pix)
    page.insert_text((60, 120), "Recognized scan words", fontsize=14, render_mode=3)  # invisible
    assert _all(extract_page_text(page)) == "Recognized scan words"


def test_text_under_an_annotation_is_still_selectable_and_annotation_text_is_not():
    doc, page = _page([("covered by a highlight", {})])
    page.add_highlight_annot(page.search_for("covered by")[0])
    page.add_text_annot((300, 300), "note body not page text")
    assert _all(extract_page_text(page)) == "covered by a highlight"


def test_image_only_page_has_no_text():
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), False)
    pix.clear_with(10)
    page.insert_image(fitz.Rect(50, 50, 300, 300), pixmap=pix)
    assert extract_page_text(page).empty


def test_selection_across_pages_in_page_order():
    doc = fitz.open()
    for i in range(3):
        doc.new_page().insert_text((72, 80), f"Page {i + 1} text", fontsize=12)
    cache = PageTextCache()
    sel = TextSelection(cache)
    n0 = len(cache.get(doc, 0).glyphs)
    sel.set(TextPosition(2, 6), TextPosition(0, 5))  # dragged backwards, from page 3 to page 1
    assert sel.text(doc) == "1 text\n\nPage 2 text\n\nPage 3"
    assert sel.page_range(doc, 0) == (5, n0)
    assert sel.page_range(doc, 1) == (0, len(cache.get(doc, 1).glyphs))
    assert sel.page_range(doc, 2) == (0, 6)


def test_cache_is_lazy_bounded_and_follows_page_changes():
    doc = fitz.open()
    for i in range(40):
        doc.new_page().insert_text((72, 80), f"page {i}", fontsize=12)
    cache = PageTextCache(max_pages=8)
    assert len(cache) == 0  # nothing extracted until a page is selected on
    for i in range(20):
        cache.get(doc, i)
    assert len(cache) == 8 and cache.extractions == 20
    cache.get(doc, 19)
    assert cache.extractions == 20  # cached
    doc[19].set_rotation(90)
    assert _all(cache.get(doc, 19)) == "page 19" and cache.extractions == 21  # rotation re-extracts
    doc.move_page(0, 19)  # page 0 now sits at index 18: another page object, so read again
    assert _all(cache.get(doc, 18)) == "page 0" and cache.extractions == 22
    cache.invalidate([18])
    cache.get(doc, 18)
    assert cache.extractions == 23


def test_extraction_does_not_change_the_document(tmp_path):
    src = tmp_path / "doc.pdf"
    doc, page = _page([("unchanged text", {})])
    doc.save(src)
    before = src.read_bytes()
    with fitz.open(src) as d:
        xrefs = d.xref_length()
        extract_page_text(d[0])
        assert d.xref_length() == xrefs and not d.is_dirty
        assert list(d[0].annots()) == []
    assert src.read_bytes() == before


def test_char_classes():
    assert char_class("a") == char_class("Z") == char_class("7") == "word"
    assert char_class("あ") == "hiragana" and char_class("ア") == char_class("ー") == "katakana"
    assert char_class("漢") == char_class("々") == "han"
    assert char_class(" ") == "space"
    assert is_cjk("日") and is_cjk("。") and not is_cjk("é")
