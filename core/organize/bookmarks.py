"""Bookmark (outline) editing: add, rename, delete, move — undoable.

The outline is read and written with PyMuPDF's ``get_toc(simple=False)`` / ``set_toc`` so each
entry keeps its destination details (zoom, position, colour, bold/italic). Entries are addressed by
their index in that flat list; an entry's *subtree* is the entry plus the following entries with a
deeper level. Commands take the document from the edit model (``edit.pdf``) when they run, so they
stay valid after Save reloads the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.commands import Command

MAX_TITLE = 500


@dataclass(frozen=True)
class Bookmark:
    index: int
    level: int
    title: str
    page: int  # 0-based; -1 when the entry points nowhere in this document


def _doc(document: Any):
    return document._backend._doc  # noqa: SLF001


def read_toc(document: Any) -> list[list]:
    try:
        return [list(row) for row in (_doc(document).get_toc(simple=False) or [])]
    except Exception:  # noqa: BLE001 - a damaged outline reads as empty
        return []


def list_bookmarks(document: Any) -> list[Bookmark]:
    n = document.page_count
    out = []
    for i, row in enumerate(read_toc(document)):
        page = int(row[2]) - 1 if len(row) > 2 else -1
        out.append(Bookmark(i, int(row[0]), str(row[1] or "Untitled"), page if 0 <= page < n else -1))
    return out


def clean_title(title: str) -> str:
    text = " ".join(str(title or "").split())
    if not text:
        raise ValueError("A bookmark needs a title.")
    return text[:MAX_TITLE]


def subtree_end(toc: list[list], index: int) -> int:
    """Index just past the entry ``index`` and its children."""
    level = int(toc[index][0])
    j = index + 1
    while j < len(toc) and int(toc[j][0]) > level:
        j += 1
    return j


def with_added(toc: list[list], title: str, page: int, *, after: int | None = None) -> tuple[list[list], int]:
    """New outline with a bookmark to ``page`` (0-based). It goes after entry ``after`` (and that
    entry's children) at the same level, or at the end at the top level. Returns (toc, new index)."""
    title = clean_title(title)
    new = [list(r) for r in toc]
    if after is None or not (0 <= after < len(new)):
        new.append([1, title, page + 1])
        return new, len(new) - 1
    level = int(new[after][0])
    at = subtree_end(new, after)
    new.insert(at, [level, title, page + 1])
    return new, at


def with_renamed(toc: list[list], index: int, title: str) -> list[list]:
    new = [list(r) for r in toc]
    new[index][1] = clean_title(title)
    return new


def with_deleted(toc: list[list], index: int) -> list[list]:
    """Remove the entry and its children (a child cannot be left without its parent)."""
    end = subtree_end(toc, index)
    return [list(r) for k, r in enumerate(toc) if not index <= k < end]


def with_target(toc: list[list], index: int, page: int) -> list[list]:
    """Point the entry at the top of ``page`` (0-based); colour / bold / italic are kept."""
    import fitz

    new = [list(r) for r in toc]
    row = new[index]
    style = {}
    if len(row) > 3 and isinstance(row[3], dict):
        style = {k: v for k, v in row[3].items() if k in ("color", "bold", "italic", "collapse")}
    new[index] = [row[0], row[1], page + 1, {"kind": fitz.LINK_GOTO, "page": page, "to": fitz.Point(0, 0), **style}]
    return new


def with_moved(toc: list[list], index: int, step: int) -> tuple[list[list], int]:
    """Swap the entry's subtree with the previous / next sibling subtree. Returns (toc, new index)."""
    level = int(toc[index][0])
    end = subtree_end(toc, index)
    block = toc[index:end]
    if step < 0:
        j = index - 1
        while j >= 0 and int(toc[j][0]) > level:
            j -= 1
        if j < 0 or int(toc[j][0]) != level:
            return [list(r) for r in toc], index
        new = toc[:j] + block + toc[j:index] + toc[end:]
        return [list(r) for r in new], j
    if end >= len(toc) or int(toc[end][0]) != level:
        return [list(r) for r in toc], index
    other_end = subtree_end(toc, end)
    new = toc[:index] + toc[end:other_end] + block + toc[other_end:]
    return [list(r) for r in new], index + (other_end - end)


def _set_toc(document: Any, toc: list[list]) -> None:
    doc = _doc(document)
    doc.set_toc(toc, collapse=1)


class SetOutlineCommand(Command):
    """Replace the outline; undo restores the previous one exactly."""

    def __init__(self, edit: Any, new_toc: list[list], *, label: str = "Edit bookmarks",
                 on_changed: Callable[[], None] | None = None) -> None:
        self._edit = edit
        self._old = read_toc(edit.pdf)
        self._new = [list(r) for r in new_toc]
        self._label = label
        self._on_changed = on_changed

    @property
    def name(self) -> str:
        return self._label

    def _apply(self, toc: list[list]) -> None:
        _set_toc(self._edit.pdf, toc)
        self._edit.mark_dirty()
        if self._on_changed is not None:
            self._on_changed()

    def execute(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)
