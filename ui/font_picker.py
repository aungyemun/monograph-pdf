"""Font box you can type into: matching fonts appear in a list as you type.

Typing ``ti`` lists every installed font containing "ti" (Times New Roman, Tahoma Italic
families, Constantia …), case-insensitive. Nothing is applied while you type; the font is
applied when you pick it from the list, choose it from the drop-down, or press Enter on a
font name that exists. Unknown text is reverted to the current font.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QCompleter, QFontComboBox, QStyledItemDelegate


class _ActiveFontDelegate(QStyledItemDelegate):
    """Wraps the list's own delegate (which draws each name in its own font) and marks the font in use:
    a tinted row, an accent bar and a check mark — readable in the light and the dark theme."""

    def __init__(self, picker: "FontPicker", inner: QStyledItemDelegate) -> None:
        super().__init__(picker)
        self._picker = picker
        self._inner = inner

    def paint(self, painter: QPainter, option, index) -> None:
        active = index.row() == self._picker.active_row()
        if not active:
            self._inner.paint(painter, option, index)
            return
        from ui.theme import current_palette

        pal = current_palette()
        accent = QColor(pal.accent)
        painter.save()
        tint = QColor(accent)
        tint.setAlpha(60)
        painter.fillRect(option.rect, tint)  # visible until the row is hovered / selected
        painter.restore()
        self._inner.paint(painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = option.rect
        painter.fillRect(r.x(), r.y(), 3, r.height(), accent)  # accent bar, never covered
        pen = QPen(QColor(pal.accent_text), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        cx, cy = r.right() - 14.0, r.center().y()
        painter.drawPolyline(QPolygonF([QPointF(cx - 4.5, cy), QPointF(cx - 1.5, cy + 3.5), QPointF(cx + 4.5, cy - 3.5)]))
        painter.restore()

    def sizeHint(self, option, index):
        return self._inner.sizeHint(option, index)


class FontPicker(QFontComboBox):
    fontPicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(16)
        self.setToolTip("Font — type a few letters to find a font")
        self.setAccessibleName("Font")
        completer = QCompleter(self.model(), self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setMaxVisibleItems(14)
        self.setCompleter(completer)
        completer.activated[str].connect(self._pick)
        self.activated.connect(lambda i: self._pick(self.itemText(i)))
        line = self.lineEdit()
        line.setPlaceholderText("Type to search fonts")
        line.returnPressed.connect(self._commit_typed)
        line.editingFinished.connect(self._commit_typed)
        self._last = self.currentText() or self.currentFont().family()
        self.setItemDelegate(_ActiveFontDelegate(self, self.itemDelegate()))

    # ------------------------------------------------------------------ public
    def active_row(self) -> int:
        """List row of the font in use, or -1 when it is not an installed font (e.g. an embedded-only
        PDF font): nothing unrelated is then shown as selected."""
        return self.findText(self._last or "", Qt.MatchFlag.MatchFixedString) if self._last else -1

    def set_family(self, family: str) -> None:
        """Show ``family`` without emitting fontPicked and without picking a look-alike font."""
        self.blockSignals(True)
        try:
            if family:
                idx = self.findText(family, Qt.MatchFlag.MatchFixedString)  # exact, case-insensitive
                if idx >= 0:
                    self.setCurrentIndex(idx)
                    self._last = self.itemText(idx)
                else:  # a PDF font that is not installed: show its name, select nothing
                    self.setCurrentIndex(-1)
                    self.setEditText(family)
                    self._last = family
        finally:
            self.blockSignals(False)
        view = self.view()
        if view is not None:
            view.viewport().update()

    def showPopup(self) -> None:  # noqa: N802
        """Open with the font in use highlighted and scrolled into view (nothing is applied)."""
        super().showPopup()
        view = self.view()
        row = self.active_row()
        if view is None:
            return
        if row >= 0:
            index = self.model().index(row, 0)
            view.setCurrentIndex(index)
            view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            view.clearSelection()
        view.viewport().update()

    def family(self) -> str:
        return self._last

    # ---------------------------------------------------------------- internals
    def _match(self, text: str) -> int:
        text = text.strip()
        if not text:
            return -1
        exact = self.findText(text, Qt.MatchFlag.MatchFixedString)  # case-insensitive exact
        if exact >= 0:
            return exact
        low = text.lower()
        starts = [i for i in range(self.count()) if self.itemText(i).lower().startswith(low)]
        if len(starts) == 1:
            return starts[0]
        contains = [i for i in range(self.count()) if low in self.itemText(i).lower()]
        return contains[0] if len(contains) == 1 else -1

    def _commit_typed(self) -> None:
        typed = self.lineEdit().text()
        if typed.strip().lower() == (self._last or "").lower():
            return
        idx = self._match(typed)
        if idx >= 0:
            self._pick(self.itemText(idx))
        else:
            self.blockSignals(True)
            self.setEditText(self._last)
            self.blockSignals(False)

    def _pick(self, family: str) -> None:
        if not family:
            return
        idx = self.findText(family, Qt.MatchFlag.MatchFixedString)
        if idx >= 0 and idx != self.currentIndex():
            self.blockSignals(True)
            self.setCurrentIndex(idx)
            self.blockSignals(False)
        if family != self._last:
            self._last = family
            self.fontPicked.emit(family)
