"""Font box you can type into: matching fonts appear in a list as you type.

Typing ``ti`` lists every installed font containing "ti" (Times New Roman, Tahoma Italic
families, Constantia …), case-insensitive. Nothing is applied while you type; the font is
applied when you pick it from the list, choose it from the drop-down, or press Enter on a
font name that exists. Unknown text is reverted to the current font.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QCompleter, QFontComboBox


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
        self._last = self.currentFont().family()

    # ------------------------------------------------------------------ public
    def set_family(self, family: str) -> None:
        """Show ``family`` without emitting fontPicked."""
        self.blockSignals(True)
        try:
            if family:
                self.setCurrentFont(QFont(family))
                if self.currentText().lower() != family.lower():
                    self.setEditText(family)  # e.g. a PDF font that is not installed
            self._last = self.currentText()
        finally:
            self.blockSignals(False)

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
