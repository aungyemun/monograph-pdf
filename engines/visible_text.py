"""The text a page shows while replacements of existing text are not saved yet (0.6.0 RC2, F-15).

Replacing existing text (double-click with **Select**) does not change the PDF until Save: the canvas
covers the original characters (``plan["rect"]``) and draws the replacement text box over them, and
Save removes the original glyphs (``engines/bake_edits.remove_native_spans``) and draws the box
(``_bake_text_box``). Select Text must copy what is shown, so this module gives the selection cache
(``core.text_selection.PageTextCache.overlay``):

* the areas whose original characters are hidden — the same removal rectangles Save uses
  (``core.editing.native_text.removal_rect``), so the hidden characters are the ones Save removes;
* the replacement text with character boxes, made by drawing each replacement box exactly as Save
  draws it, on a **separate scratch PDF in memory** of the displayed page's size, and reading that
  scratch page back. The open document is never written, flattened or saved for this.

Only replacements of existing text are included. Text boxes the user *added* stay objects of the
Select tool (their text is copied with Select ▸ Copy) and become page text when the document is saved.
"""

from __future__ import annotations

from typing import Any, Callable

import fitz

from core.text_selection import PageText, _extract


class _ScratchTargets:
    """``engines.bake_edits._OverlayTargets`` stand-in: every page is an upright scratch page of the
    displayed page's size in a throw-away document, so display coordinates need no conversion."""

    def __init__(self, width: float, height: float) -> None:
        self.doc = fitz.open()
        self._page = self.doc.new_page(width=width, height=height)

    def page(self, index: int) -> fitz.Page:  # noqa: ARG002 — one page per scratch document
        return self._page

    def close(self) -> None:
        self.doc.close()


def _box_key(box: Any) -> tuple:
    r = box.rect
    style = getattr(box, "style", None)
    try:
        style_d = repr(sorted(style.to_dict().items())) if style is not None else ""
    except Exception:  # noqa: BLE001
        style_d = repr(style)
    return (str(box.object_id), str(box.text), (float(r.x), float(r.y), float(r.w), float(r.h)), style_d,
            repr(getattr(box, "runs", None)), str(getattr(getattr(box, "align", None), "value", "")),
            str(getattr(getattr(box, "valign", None), "value", "")))


class ReplacementOverlay:
    """Supplies unsaved replacements of existing text to the Select Text cache."""

    def __init__(self, get_edit: Callable[[], Any]) -> None:
        self._get_edit = get_edit

    def _parts(self, page_index: int):
        edit = self._get_edit()
        if edit is None:
            return None, [], []
        plans = getattr(edit, "native_replacements", None) or {}
        prefix = f"p{page_index}-"
        mine = sorted((str(sid), plan) for sid, plan in plans.items() if str(sid).startswith(prefix))
        boxes = [b for b in edit.objects_on_page(page_index) if getattr(b, "replaces_native", False)]
        return edit, mine, boxes

    def signature(self, doc: fitz.Document, page_index: int):  # noqa: ARG002
        _, plans, boxes = self._parts(page_index)
        if not plans and not boxes:
            return None
        return (tuple((sid, tuple(plan.get("rect") or ())) for sid, plan in plans),
                tuple(sorted(_box_key(b) for b in boxes)))

    def contribution(self, doc: fitz.Document, page_index: int):
        from core.editing.native_text import removal_rect

        _, plans, boxes = self._parts(page_index)
        removals = []
        for _sid, plan in plans:
            rect_t = plan.get("rect")
            if rect_t:
                x, y, w, h = removal_rect(tuple(rect_t))
                removals.append((x, y, x + w, y + h))
        extra: list[PageText] = []
        if boxes:
            page = doc.load_page(page_index)
            extra = [_replacement_text(box, page.rect.width, page.rect.height, page_index) for box in boxes]
            extra = [t for t in extra if not t.empty]
        return removals, extra


def _replacement_text(box: Any, width: float, height: float, page_index: int) -> PageText:
    """The characters of one replacement box as Save would draw them (display coordinates)."""
    from core.editing import system_fonts
    from engines.bake_edits import _bake_text_box

    if not str(getattr(box, "text", "") or "").strip():
        return PageText(page_index=page_index)
    pending = system_fonts.take_notes()  # font notices belong to Save, not to selecting
    targets = _ScratchTargets(width, height)
    try:
        _bake_text_box(targets, box)
        return _extract(targets.page(page_index), page_index)
    finally:
        targets.close()
        system_fonts.take_notes()
        for family, why in pending.items():
            system_fonts.note_fallback(family, why)
