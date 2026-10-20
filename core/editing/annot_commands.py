"""Undoable native PDF markup annotations (highlight / underline / strikeout)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

from core.annotations.ops import (
    add_free_highlight,
    add_highlight,
    add_strikeout,
    add_underline,
    delete_annotation_by_nm,
    delete_annotation_by_xref,
    new_annotation_id,
    restore_annotation,
    snapshot_annotation,
)
from core.commands import Command
from core.editing.geometry import Rect

if TYPE_CHECKING:
    from core.document import PdfDocument
    from core.editing.edit_model import EditableDocument

_ADDERS: dict[str, Callable[..., int]] = {
    "highlight": add_highlight,
    "underline": add_underline,
    "strikeout": add_strikeout,
}


class MarkupAnnotCommand(Command):
    """Create a text markup annotation; undo deletes it by xref."""

    def __init__(
        self,
        document: "PdfDocument",
        model: "EditableDocument",
        page_index: int,
        kind: str,
        rects: Sequence[Rect],
        *,
        color: tuple[float, float, float],
    ) -> None:
        if kind not in _ADDERS:
            raise ValueError(f"unsupported markup kind: {kind}")
        self.document = document
        self.model = model
        self.page_index = page_index
        self.kind = kind
        self.rects = [Rect(r.x, r.y, r.w, r.h) for r in rects]
        self.color = color
        self._xref: int | None = None

    @property
    def name(self) -> str:
        return {"highlight": "Highlight", "underline": "Underline", "strikeout": "Strikethrough"}.get(
            self.kind, "Markup"
        )

    def execute(self) -> None:
        adder = _ADDERS[self.kind]
        self._xref = adder(self.document, self.page_index, self.rects, color=self.color)
        self.model.mark_dirty()

    def undo(self) -> None:
        if self._xref is not None:
            delete_annotation_by_xref(self.document, self.page_index, self._xref)
            self._xref = None
        self.model.mark_dirty()


class HighlightStrokeCommand(Command):
    """One pen stroke: text highlight (QuadPoints) and/or free-area ink runs, undone as a single step.

    Every annotation it creates carries a stable /NM identity, so undo/redo (and an Eraser step recorded in
    between) always find the same annotation even though its xref changes when it is recreated."""

    name = "Highlight"

    def __init__(
        self,
        document: "PdfDocument",
        model: "EditableDocument",
        page_index: int,
        rects: Sequence[Rect],
        runs: Sequence[Sequence[tuple[float, float]]],
        *,
        color: tuple[float, float, float],
    ) -> None:
        if not rects and not runs:
            raise ValueError("empty highlight stroke")
        self.document = document
        self.model = model
        self.page_index = page_index
        self.rects = [Rect(r.x, r.y, r.w, r.h) for r in rects]
        self.runs = [list(r) for r in runs]
        self.color = color
        self._ids: list[str] = []
        if self.rects:
            self._ids.append(new_annotation_id())
        if self.runs:
            self._ids.append(new_annotation_id())

    def execute(self) -> None:
        ids = list(self._ids)
        if self.rects:
            add_highlight(self.document, self.page_index, self.rects, color=self.color, nm=ids.pop(0))
        if self.runs:
            add_free_highlight(self.document, self.page_index, self.runs, color=self.color, nm=ids.pop(0))
        self.model.mark_dirty()

    def undo(self) -> None:
        for nm in reversed(self._ids):
            delete_annotation_by_nm(self.document, self.page_index, nm)
        self.model.mark_dirty()


class EraseAnnotCommand(Command):
    """Remove one markup annotation; undo recreates it with the same type, geometry, colour, opacity and identity.

    Only the chosen annotation is touched. The annotation is given an /NM identity first when it has none,
    so a later undo of the command that created it still finds it."""

    name = "Erase highlight"

    def __init__(self, document: "PdfDocument", model: "EditableDocument", page_index: int, xref: int) -> None:
        self.document = document
        self.model = model
        self.page_index = page_index
        self._xref = int(xref)
        self._snap: dict | None = None

    def execute(self) -> None:
        if self._snap is None:
            snap = snapshot_annotation(self.document, self.page_index, self._xref)
            if snap is None:
                raise ValueError("annotation not found")
            if not snap["nm"]:
                snap["nm"] = new_annotation_id()
                self.document._backend._doc.xref_set_key(  # noqa: SLF001
                    self._xref, "NM", fitz_pdf_str(snap["nm"])
                )
            self._snap = snap
        if not delete_annotation_by_nm(self.document, self.page_index, self._snap["nm"]):
            raise ValueError("annotation not found")
        self.model.mark_dirty()

    def undo(self) -> None:
        if self._snap is not None:
            restore_annotation(self.document, self.page_index, self._snap)
        self.model.mark_dirty()


def fitz_pdf_str(text: str) -> str:
    import fitz

    return fitz.get_pdf_str(text)
