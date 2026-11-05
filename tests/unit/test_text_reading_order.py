"""Select Text reads page text in visual reading order, not in the order the PDF stores it
(0.6.0 RC2, F-14). Synthetic pages; expected texts are written out by hand."""

from __future__ import annotations

import fitz
import pytest

from core.text_selection import extract_page_text, extract_page_text_stored, visual_order


def _page(lines, *, rotation: int = 0, width: float = 595, height: float = 842, **kw):
    """``lines``: (x, y, text, size[, font]) in the order they are written into the content stream."""
    d = fitz.open()
    p = d.new_page(width=width, height=height)
    for item in lines:
        x, y, t, size = item[:4]
        font = item[4] if len(item) > 4 else "helv"
        p.insert_text((x, y), t, fontsize=size, fontname=font, **kw)
    p.set_rotation(rotation)
    return d, p


def _all(pt) -> str:
    return pt.text(0, len(pt.glyphs))


THREE = [(72, 120, "Line 1", 14), (72, 148, "Line 2", 14), (72, 176, "Line 3", 14)]


@pytest.mark.parametrize("stored", [(0, 1, 2), (1, 0, 2), (2, 1, 0), (0, 2, 1), (2, 0, 1), (1, 2, 0)])
def test_three_lines_in_any_stored_order_read_top_to_bottom(stored):
    d, p = _page([THREE[i] for i in stored])
    assert _all(extract_page_text(p)) == "Line 1\nLine 2\nLine 3"
    d.close()


def test_stored_order_is_still_available_and_differs():
    d, p = _page([THREE[i] for i in (2, 1, 0)])
    assert _all(extract_page_text_stored(p)) == "Line 3\nLine 2\nLine 1"
    d.close()


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_turned_pages_read_in_the_turned_direction(rotation):
    d, p = _page([THREE[i] for i in (2, 0, 1)], rotation=rotation)
    assert _all(extract_page_text(p)) == "Line 1\nLine 2\nLine 3"
    d.close()


def test_wrapped_paragraph_and_two_paragraphs():
    d = fitz.open()
    p = d.new_page()
    # second paragraph written first
    p.insert_textbox(fitz.Rect(72, 300, 300, 400), "second paragraph has words", fontsize=12)
    p.insert_textbox(fitz.Rect(72, 100, 300, 200), "one two three four five six seven eight nine ten eleven", fontsize=12)
    text = _all(extract_page_text(p))
    first, second = text.split("\nsecond")
    assert first.replace("\n", " ") == "one two three four five six seven eight nine ten eleven"
    assert "second" + second == "second paragraph has words"
    d.close()


def _two_columns(interleaved: bool):
    lines = [(72, 60, "Journal of Synthetic Layouts, volume 1, a header across both columns", 10)]
    left = [(72, 100 + 14 * i, f"left column sentence number {i + 1} goes here", 9) for i in range(6)]
    right = [(310, 100 + 14 * i, f"right column sentence number {i + 1} goes here", 9) for i in range(6)]
    body = [x for pair in zip(right, left) for x in pair] if interleaved else right + left
    lines += body
    lines.append((290, 810, "12", 9))  # page number footer
    return lines


@pytest.mark.parametrize("interleaved", [False, True])
def test_two_columns_are_read_column_by_column_between_header_and_footer(interleaved):
    d, p = _page(_two_columns(interleaved))
    rows = _all(extract_page_text(p)).split("\n")
    assert rows[0].startswith("Journal of Synthetic Layouts")
    assert rows[1:7] == [f"left column sentence number {i + 1} goes here" for i in range(6)]
    assert rows[7:13] == [f"right column sentence number {i + 1} goes here" for i in range(6)]
    assert rows[13:] == ["12"]
    d.close()


def test_column_of_uneven_length_does_not_interleave():
    left = [(72, 100 + 14 * i, f"left column sentence number {i + 1} goes here", 9) for i in range(8)]
    right = [(310, 100 + 14 * i, f"right column sentence number {i + 1} goes here", 9) for i in range(3)]
    d, p = _page(right + left)
    rows = _all(extract_page_text(p)).split("\n")
    assert rows[:8] == [f"left column sentence number {i + 1} goes here" for i in range(8)]
    assert rows[8:] == [f"right column sentence number {i + 1} goes here" for i in range(3)]
    d.close()


def test_table_cells_are_read_row_by_row():
    cells = [(72 + c * 120, 100 + r * 16, f"r{r}c{c}", 10) for r in range(3) for c in range(3)]
    d, p = _page(cells[::-1])
    assert _all(extract_page_text(p)) == "r0c0 r0c1 r0c2\nr1c0 r1c1 r1c2\nr2c0 r2c1 r2c2"
    d.close()


def test_labels_and_values_are_read_row_by_row():
    d, p = _page([(200, 116, "thirty years old and counting", 10), (72, 100, "Name:", 10),
                  (72, 116, "Age:", 10), (200, 100, "John Smith from somewhere far", 10)])
    assert _all(extract_page_text(p)) == "Name: John Smith from somewhere far\nAge: thirty years old and counting"
    d.close()


def test_mixed_font_sizes_and_indented_lines():
    d, p = _page([(90, 160, "an indented first line of the paragraph", 10), (72, 100, "Big Title", 24),
                  (72, 174, "and the rest of the paragraph", 10), (72, 130, "A subtitle line", 14)])
    assert _all(extract_page_text(p)) == ("Big Title\nA subtitle line\nan indented first line of the paragraph\n"
                                          "and the rest of the paragraph")
    d.close()


def test_pieces_of_one_line_written_out_of_order_are_joined_left_to_right():
    d, p = _page([(140, 100, "second part", 12, "cour"), (72, 100, "First", 12, "tiro")])
    assert _all(extract_page_text(p)) == "First second part"
    d.close()


def test_overlapping_text_keeps_both_copies_in_stored_order():
    d, p = _page([(72, 100, "same place", 12), (72, 100, "same place", 12), (72, 130, "below", 12)])
    assert _all(extract_page_text(p)).split("\n")[-1] == "below"
    assert _all(extract_page_text(p)).count("same place") == 2
    d.close()


def test_japanese_lines_are_ordered_without_added_spaces():
    d, p = _page([(72, 150, "カタカナの二行目です", 14, "japan"), (72, 120, "日本語の一行目です", 14, "japan"),
                  (72, 180, "三行目 mixed English 混在", 14, "japan")])
    assert _all(extract_page_text(p)) == "日本語の一行目です\nカタカナの二行目です\n三行目 mixed English 混在"
    d.close()


def test_invisible_ocr_text_layer_is_ordered_too():
    d, p = _page([THREE[i] for i in (1, 2, 0)], render_mode=3)
    assert _all(extract_page_text(p)) == "Line 1\nLine 2\nLine 3"
    d.close()


def test_embedded_font_text_is_ordered():
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname="emb", fontbuffer=fitz.Font("tiro").buffer)
    for x, y, t, s in [THREE[i] for i in (2, 1, 0)]:
        p.insert_text((x, y), t, fontsize=s, fontname="emb")
    assert _all(extract_page_text(p)) == "Line 1\nLine 2\nLine 3"
    d.close()


def test_lines_in_different_directions_keep_stored_order():
    """Documented fallback: no guess for pages mixing writing directions."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 300), "bottom horizontal", fontsize=12)
    p.insert_text((300, 100), "turned", fontsize=12, rotate=90)
    p.insert_text((72, 100), "top horizontal", fontsize=12)
    stored = extract_page_text_stored(p)
    assert _all(extract_page_text(p)) == _all(stored)
    d.close()


def test_reordering_keeps_every_character_and_positions_consistent():
    d, p = _page(_two_columns(True))
    stored, shown = extract_page_text_stored(p), extract_page_text(p)
    assert sorted(g.text for g in stored.glyphs) == sorted(g.text for g in shown.glyphs)
    for i, ln in enumerate(shown.lines):
        assert all(shown.glyphs[k].line == i for k in range(ln.start, ln.end))
    assert visual_order(shown).glyphs == shown.glyphs  # idempotent
    d.close()


def test_paragraph_range_uses_neighbouring_lines_of_the_block():
    d = fitz.open()
    p = d.new_page()
    p.insert_textbox(fitz.Rect(72, 300, 300, 400), "lower paragraph words", fontsize=12)
    p.insert_textbox(fitz.Rect(72, 100, 200, 200), "upper paragraph that wraps onto lines", fontsize=12)
    pt = extract_page_text(p)
    a, b = pt.block_range(0)
    assert pt.text(a, b).replace("\n", " ") == "upper paragraph that wraps onto lines"
    d.close()
