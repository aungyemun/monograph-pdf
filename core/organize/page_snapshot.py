"""Undo and redo for page operations (reorder, delete, insert, duplicate, replace, crop, page size).

A page operation changes the document's page tree and moves the editor's overlays between pages. The
command keeps the whole document (as PDF bytes, object numbers unchanged) and the overlay state from
before and after the operation; Undo and Redo put one of them back. Snapshots are held in memory only
and are bounded: very large documents are not snapshotted (the operation then cannot be undone, and
the user is told), and at most ``MAX_UNDOABLE`` page operations stay undoable — older history is
dropped from the Undo list rather than kept without a snapshot.
"""

from __future__ import annotations

from typing import Any, Callable

from core.commands import Command

MAX_SNAPSHOT_BYTES = 200 * 1024 * 1024  # a document larger than this is not kept twice in memory
MAX_UNDOABLE = 8


class PageStructureCommand(Command):
    def __init__(self, name: str, document: Any, edit: Any, before: tuple[bytes, dict], after: tuple[bytes, dict],
                 on_restore: Callable[[], None]) -> None:
        self._name = name
        self.document = document
        self.edit = edit
        self.before = before
        self.after = after
        self.on_restore = on_restore

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> int:
        return len(self.before[0]) + len(self.after[0])

    def _apply(self, state: tuple[bytes, dict]) -> None:
        from engines.mupdf_backend import restore_bytes

        data, model = state
        restore_bytes(self.document._backend, data)  # noqa: SLF001
        self.document.invalidate_pages()
        self.edit.pdf = self.document
        self.edit.load_objects(model)
        self.edit.mark_dirty()
        self.on_restore()

    def execute(self) -> None:  # Redo
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


def capture(document: Any, edit: Any) -> tuple[bytes, dict] | None:
    """(document bytes, overlay state) or None when the document is too large to keep a copy."""
    from engines.mupdf_backend import snapshot_bytes

    data = snapshot_bytes(document._backend)  # noqa: SLF001
    if len(data) > MAX_SNAPSHOT_BYTES:
        return None
    import copy

    return data, copy.deepcopy(edit.to_dict())


def push(stack: Any, command: PageStructureCommand) -> None:
    """Record an already executed page operation, keeping at most MAX_UNDOABLE of them undoable."""
    stack.push_executed(command)
    undo = stack._undo  # noqa: SLF001
    page_ops = [c for c in undo if isinstance(c, PageStructureCommand)]
    while len(page_ops) > MAX_UNDOABLE:
        oldest = page_ops.pop(0)
        while undo and undo[0] is not oldest:
            undo.popleft()
        if undo:
            undo.popleft()
