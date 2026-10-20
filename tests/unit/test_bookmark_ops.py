"""Outline editing helpers and the undoable outline command (core.organize.bookmarks)."""

from __future__ import annotations

import fitz
import pytest

from core.document import open_document
from core.organize.bookmarks import (
    SetOutlineCommand,
    clean_title,
    list_bookmarks,
    read_toc,
    subtree_end,
    with_added,
    with_deleted,
    with_moved,
    with_renamed,
    with_target,
)

TOC = [[1, "A", 1], [2, "A.1", 2], [2, "A.2", 3], [1, "B", 4], [1, "C", 5]]


def _pdf(tmp_path, toc=TOC, pages=6):
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"Page {i + 1}")
    d.set_toc(toc)
    path = tmp_path / "outline.pdf"
    d.save(path)
    d.close()
    return path


def test_subtree_end_spans_children():
    assert subtree_end(TOC, 0) == 3
    assert subtree_end(TOC, 1) == 2
    assert subtree_end(TOC, 3) == 4


def test_add_after_entry_goes_after_its_children_at_the_same_level():
    new, at = with_added(TOC, "  New   title ", 5, after=0)
    assert at == 3 and new[3] == [1, "New title", 6]
    new, at = with_added(TOC, "Tail", 0)
    assert at == len(TOC) and new[-1] == [1, "Tail", 1]
    new, at = with_added(TOC, "Child sibling", 2, after=1)
    assert at == 2 and new[2][0] == 2
    assert TOC[0] == [1, "A", 1]  # input not modified


def test_titles_are_cleaned_and_required():
    assert clean_title("a\n b\t c") == "a b c"
    assert len(clean_title("x" * 900)) == 500
    with pytest.raises(ValueError):
        clean_title("   ")


def test_delete_removes_children_too():
    assert [r[1] for r in with_deleted(TOC, 0)] == ["B", "C"]
    assert [r[1] for r in with_deleted(TOC, 2)] == ["A", "A.1", "B", "C"]


def test_move_swaps_sibling_subtrees_and_stops_at_the_ends():
    new, at = with_moved(TOC, 3, -1)
    assert [r[1] for r in new] == ["B", "A", "A.1", "A.2", "C"] and at == 0
    new, at = with_moved(TOC, 0, 1)
    assert [r[1] for r in new] == ["B", "A", "A.1", "A.2", "C"] and at == 1
    new, at = with_moved(TOC, 0, -1)
    assert at == 0 and new == TOC
    new, at = with_moved(TOC, 2, 1)  # last child cannot leave its parent
    assert at == 2 and new == TOC


def test_rename_and_retarget():
    assert with_renamed(TOC, 4, "Z")[4][1] == "Z"
    toc = [[1, "A", 1, {"kind": 1, "page": 0, "to": fitz.Point(10, 20), "zoom": 2.0, "bold": True}]]
    row = with_target(toc, 0, 4)[0]
    assert row[2] == 5 and row[3]["page"] == 4 and row[3]["bold"] is True and row[3]["to"] == fitz.Point(0, 0)
    d = fitz.open()
    for _ in range(5):
        d.new_page()
    d.set_toc(with_target([[1, "A", 1]], 0, 4))
    assert d.get_toc()[0][2] == 5  # a live bookmark, not a dead one
    d.close()


def test_command_changes_outline_and_undo_restores_it(tmp_path):
    doc = open_document(_pdf(tmp_path))

    class Edit:
        pdf = doc
        dirty = False

        def mark_dirty(self):
            self.dirty = True

    edit = Edit()
    calls = []
    before = read_toc(doc)
    cmd = SetOutlineCommand(edit, with_deleted(before, 0), on_changed=lambda: calls.append(1))
    cmd.execute()
    assert [b.title for b in list_bookmarks(doc)] == ["B", "C"]
    assert edit.dirty and calls == [1]
    cmd.undo()
    assert [b.title for b in list_bookmarks(doc)] == ["A", "A.1", "A.2", "B", "C"]
    assert [(r[0], r[1], r[2]) for r in read_toc(doc)] == [(r[0], r[1], r[2]) for r in before]
    cmd.execute()
    out = tmp_path / "saved.pdf"
    doc.save_as(out)
    doc.close()
    reread = fitz.open(out)
    assert [r[1] for r in reread.get_toc()] == ["B", "C"]
    reread.close()


def test_list_bookmarks_marks_pages_outside_the_document(tmp_path):
    doc = open_document(_pdf(tmp_path, toc=[[1, "In", 2], [1, "Nowhere", -1]], pages=3))
    marks = list_bookmarks(doc)
    assert marks[0].page == 1 and marks[1].page == -1
    doc.close()


def test_editing_keeps_web_link_and_styled_bookmarks(tmp_path):
    d = fitz.open()
    for _ in range(3):
        d.new_page()
    d.set_toc([[1, "Page", 2], [1, "Styled", 3, {"kind": 1, "page": 2, "to": fitz.Point(0, 0), "color": (1, 0, 0),
                                                  "bold": True}], [1, "Web", 1]])
    x = d.get_outline_xrefs()[2]
    d.xref_set_key(x, "Dest", "null")
    d.xref_set_key(x, "A", "<</S/URI/URI(https://example.org/doc)>>")
    d.save(tmp_path / "k.pdf")
    d.close()
    doc = open_document(tmp_path / "k.pdf")

    class Edit:
        pdf = doc

        def mark_dirty(self):
            pass

    SetOutlineCommand(Edit(), with_renamed(read_toc(doc), 0, "First")).execute()
    rows = read_toc(doc)
    assert [r[1] for r in rows] == ["First", "Styled", "Web"]
    assert rows[1][3].get("bold") is True and tuple(rows[1][3].get("color")) == (1.0, 0.0, 0.0)
    assert rows[2][3].get("uri") == "https://example.org/doc"
    doc.close()
