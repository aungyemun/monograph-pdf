"""The Select Text tool of the page canvas (0.6.0): selecting existing page text with the mouse.

The canvas forwards mouse, key and paint events here while ``EditTool.TEXT_SELECT`` is active. The
selection is a temporary overlay painted over the pages; it is never written into the PDF and does
not touch the editing model, so selecting never marks the document as modified.

Behaviour (documented in the User Guide):

* drag — select from the press point to the pointer, character by character, across lines and pages
  (the view scrolls while the pointer is held above or below it);
* double-click — a word (Japanese: a run of Kanji, Hiragana or Katakana);
* triple-click — the paragraph (MuPDF text block);
* text is ordered as it is read on screen (``core.text_selection.visual_order``), and replacements of
  existing text that are not saved yet are selected as shown (``engines/visible_text.py``);
* Shift+click — extend the selection to the click; Shift+Left / Shift+Right — by one character;
* Esc — clear the selection; Ctrl+A — all text of the current page; Ctrl+C / right-click ▸ Copy —
  copy (the window checks the PDF's copy permission).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QScrollArea

from core.text_selection import PageTextCache, TextPosition, TextSelection

_SELECTION_FILL = QColor(0, 120, 215, 80)  # translucent system-like blue, readable in both themes
_EDGE = 28  # pointer this close to the top / bottom of the view while dragging scrolls it


class TextSelectController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.cache = PageTextCache()
        # unsaved replacements of existing text are selected as shown, not as stored (F-15)
        from engines.visible_text import ReplacementOverlay

        self.cache.overlay = ReplacementOverlay(lambda: getattr(self.canvas, "_edit", None))
        self.selection = TextSelection(self.cache)
        self._dragging = False
        self._drag_unit: tuple[int, int, int] | None = None  # (page, start, end) of a double/triple-click
        self._last_press = 0.0
        self._last_double: tuple[float, QPoint] | None = None
        self._last_pos: QPoint | None = None
        self._scroll_timer = QTimer(canvas)
        self._scroll_timer.setInterval(40)
        self._scroll_timer.timeout.connect(self._auto_scroll)

    # -- document ------------------------------------------------------------------------------

    def _doc(self):
        document = getattr(self.canvas, "_document", None)
        if document is None or getattr(document, "is_closed", False):
            return None
        try:
            return document._backend._doc  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None

    def reset(self) -> None:
        """A new or closed document: forget every page and the selection."""
        self.cache.invalidate()
        self.selection.clear()
        self._dragging = False
        self._scroll_timer.stop()

    def invalidate(self, pages=None) -> None:
        """The content of ``pages`` (all when ``None``) changed: read them again; a selection on
        them is dropped (its positions may no longer exist)."""
        self.cache.invalidate(pages)
        if pages is None:
            self.selection.clear()
            return
        sel_pages = set(self.selection.pages())
        if sel_pages & {int(p) for p in pages}:
            self.selection.clear()

    # -- state -----------------------------------------------------------------------------------

    @property
    def has_selection(self) -> bool:
        return not self.selection.empty

    def selected_text(self) -> str:
        doc = self._doc()
        return self.selection.text(doc) if doc is not None else ""

    def selected_page_rects(self, page_index: int) -> list[tuple[float, float, float, float]]:
        doc = self._doc()
        if doc is None:
            return []
        rng = self.selection.page_range(doc, page_index)
        if rng is None:
            return []
        return self.cache.get(doc, page_index).rects(*rng)

    def selection_touches(self, rects_by_page: dict[int, list]) -> bool:
        """True when the selected text overlaps any of the display-space rectangles given per page
        (redaction marks)."""
        doc = self._doc()
        if doc is None:
            return False
        for p in self.selection.pages():
            rects = rects_by_page.get(p)
            rng = self.selection.page_range(doc, p)
            if rects and rng and self.cache.get(doc, p).overlaps(*rng, rects):
                return True
        return False

    def clear(self) -> None:
        if not self.selection.empty or self.selection.anchor is not None:
            self.selection.clear()
            self.canvas.update()

    def select_page(self, page_index: int) -> int:
        """Select all text of one page; returns the number of characters selected (0: none)."""
        doc = self._doc()
        if doc is None or not (0 <= page_index < doc.page_count):
            return 0
        pt = self.cache.get(doc, page_index)
        if pt.empty:
            self.selection.clear()
        else:
            self.selection.set(TextPosition(page_index, 0), TextPosition(page_index, len(pt.glyphs)))
        self.canvas.update()
        return len(pt.glyphs)

    def page_has_text(self, page_index: int) -> bool:
        doc = self._doc()
        return doc is not None and not self.cache.get(doc, page_index).empty

    # -- mouse -------------------------------------------------------------------------------

    def _position(self, pos: QPoint, *, clamp_page: int | None = None) -> TextPosition | None:
        doc = self._doc()
        mapped = self.canvas.widget_to_pdf(pos)
        if doc is None or mapped is None:
            return None
        page_index, pt = mapped
        if clamp_page is not None and page_index < 0:
            page_index = clamp_page
        if not (0 <= page_index < doc.page_count):
            return None
        text = self.cache.get(doc, page_index)
        p = text.position_at(pt.x, pt.y)
        return None if p is None else TextPosition(page_index, p)

    def press(self, pos: QPoint, modifiers) -> None:
        now = time.monotonic()
        interval = QApplication.doubleClickInterval() / 1000.0
        triple = (
            self._last_double is not None
            and now - self._last_double[0] <= interval
            and (pos - self._last_double[1]).manhattanLength() <= QApplication.startDragDistance() * 2
        )
        self._last_press = now
        self._last_pos = pos
        if triple:
            self._last_double = None
            self._select_unit(pos, "block")
            return
        target = self._position(pos)
        if modifiers & Qt.KeyboardModifier.ShiftModifier and self.selection.anchor is not None and target is not None:
            self.selection.focus = target
            self._dragging = True
            self._drag_unit = None
            self.canvas.update()
            return
        self._drag_unit = None
        if target is None:
            self.clear()
            self._announce_no_text(pos)
            return
        self.selection.set(target, target)
        self._dragging = True
        self.canvas.update()

    def double_click(self, pos: QPoint) -> None:
        self._last_double = (time.monotonic(), QPoint(pos))
        self._select_unit(pos, "word")

    def _select_unit(self, pos: QPoint, unit: str) -> None:
        doc = self._doc()
        mapped = self.canvas.widget_to_pdf(pos)
        if doc is None or mapped is None:
            return
        page_index, pt = mapped
        if not (0 <= page_index < doc.page_count):
            return
        text = self.cache.get(doc, page_index)
        g = text.glyph_at(pt.x, pt.y, slack=3.0)
        if g is None:
            p = text.position_at(pt.x, pt.y)
            if p is None:
                self._announce_no_text(pos)
                return
            g = min(p, len(text.glyphs) - 1)
        a, b = text.word_range(g) if unit == "word" else text.block_range(g)
        self.selection.set(TextPosition(page_index, a), TextPosition(page_index, b))
        self._drag_unit = (page_index, a, b)
        self._dragging = True
        self.canvas.update()

    def move(self, pos: QPoint, buttons) -> None:
        if not (buttons & Qt.MouseButton.LeftButton) or not self._dragging:
            return
        self._last_pos = pos
        self._extend_to(pos)
        self._update_auto_scroll(pos)

    def _extend_to(self, pos: QPoint) -> None:
        target = self._position(pos)
        if target is None:
            return
        if self._drag_unit is not None:
            # dragging after a double- / triple-click extends by whole words / paragraphs
            page, a, b = self._drag_unit
            lo, hi = TextPosition(page, a), TextPosition(page, b)
            if target < lo:
                self.selection.set(hi, target)
            else:
                self.selection.set(lo, max(target, hi, key=lambda t: (t.page, t.pos)))
        else:
            self.selection.focus = target
        self.canvas.update()

    def release(self) -> None:
        self._dragging = False
        self._scroll_timer.stop()

    # -- auto scroll -----------------------------------------------------------------------------

    def _scroll_area(self) -> QScrollArea | None:
        w = self.canvas.parentWidget()
        while w is not None and not isinstance(w, QScrollArea):
            w = w.parentWidget()
        return w

    def _update_auto_scroll(self, pos: QPoint) -> None:
        area = self._scroll_area()
        if area is None:
            return
        vp = area.viewport().mapFromGlobal(self.canvas.mapToGlobal(pos))
        h = area.viewport().height()
        if vp.y() < _EDGE or vp.y() > h - _EDGE:
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_timer.stop()

    def _auto_scroll(self) -> None:
        area = self._scroll_area()
        if area is None or not self._dragging or self._last_pos is None:
            self._scroll_timer.stop()
            return
        vp = area.viewport().mapFromGlobal(self.canvas.mapToGlobal(self._last_pos))
        h = area.viewport().height()
        bar = area.verticalScrollBar()
        if vp.y() < _EDGE:
            step = -max(8, (_EDGE - vp.y()) * 2)
        elif vp.y() > h - _EDGE:
            step = max(8, (vp.y() - (h - _EDGE)) * 2)
        else:
            self._scroll_timer.stop()
            return
        before = bar.value()
        bar.setValue(before + step)
        moved = bar.value() - before
        if moved == 0:
            return
        self._last_pos = QPoint(self._last_pos.x(), self._last_pos.y() + moved)
        self._extend_to(self._last_pos)

    # -- keyboard ----------------------------------------------------------------------------------

    def key(self, key: int, modifiers) -> bool:
        """Handle a key in the Select Text tool; True when it was used."""
        if key == Qt.Key.Key_Escape:
            if not self.selection.empty:
                self.clear()
                self.canvas.requestStatus.emit("Text selection cleared")
                return True
            return False
        if modifiers & Qt.KeyboardModifier.ShiftModifier and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            doc = self._doc()
            if doc is None or self.selection.focus is None:
                return False
            f = self.selection.focus
            n = len(self.cache.get(doc, f.page).glyphs)
            if key == Qt.Key.Key_Right:
                if f.pos < n:
                    f = TextPosition(f.page, f.pos + 1)
                elif f.page + 1 < doc.page_count:
                    f = TextPosition(f.page + 1, 0)
            else:
                if f.pos > 0:
                    f = TextPosition(f.page, f.pos - 1)
                elif f.page > 0:
                    f = TextPosition(f.page - 1, len(self.cache.get(doc, f.page - 1).glyphs))
            self.selection.focus = f
            self.canvas.update()
            return True
        return False

    # -- painting ----------------------------------------------------------------------------------

    def paint_page(self, painter: QPainter, page_index: int) -> None:
        if self.selection.empty:
            return
        rects = self.selected_page_rects(page_index)
        if not rects:
            return
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_SELECTION_FILL)
        for x0, y0, x1, y1 in rects:
            p0 = self.canvas.pdf_to_widget_f(page_index, _Pt(x0, y0))
            p1 = self.canvas.pdf_to_widget_f(page_index, _Pt(x1, y1))
            if p0 is None or p1 is None:
                continue
            painter.drawRect(QRectF(p0, p1).normalized())
        painter.restore()

    # -- messages ------------------------------------------------------------------------------

    def _announce_no_text(self, pos: QPoint) -> None:
        doc = self._doc()
        mapped = self.canvas.widget_to_pdf(pos)
        if doc is None or mapped is None or not (0 <= mapped[0] < doc.page_count):
            return
        if self.cache.get(doc, mapped[0]).empty:
            self.canvas.requestStatus.emit(
                "This page has no selectable text (it may be a scanned picture). "
                "OCR ▸ Make Searchable PDF… adds a text layer; nothing is recognized automatically.")


class _Pt:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y
