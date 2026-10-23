"""On-page pop-up of a sticky note: what the note says, who wrote it and when — like a paper note.

Clicking a note opens it next to the note; it stays open (scrolling with the page) until it is closed
with ×, Esc or a click elsewhere. Pointing at a note still shows the quick tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, QVBoxLayout


def _pdf_date(value: str) -> str:
    """'D:20261023213400+09'00'' -> '2026-10-23 21:34' (empty when unreadable)."""
    v = (value or "").strip()
    if v.startswith("D:"):
        v = v[2:]
    if len(v) >= 12 and v[:12].isdigit():
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]} {v[8:10]}:{v[10:12]}"
    if len(v) >= 8 and v[:8].isdigit():
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    return ""


class NotePopup(QFrame):
    editRequested = Signal(int, int)  # page index, xref
    closed = Signal()

    WIDTH = 260

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setObjectName("NotePopup")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(self.WIDTH)
        self.key: tuple[int, int] | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("NotePopupTitle")
        head.addWidget(self.title, 1)
        close = QToolButton()
        close.setText("×")
        close.setToolTip("Close (Esc)")
        close.setAccessibleName("Close note")
        close.setAutoRaise(True)
        close.clicked.connect(self.close_popup)
        head.addWidget(close)
        lay.addLayout(head)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text.setAccessibleName("Note text")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.text)
        scroll.setMaximumHeight(220)
        self._scroll = scroll
        lay.addWidget(scroll)
        row = QHBoxLayout()
        row.addStretch(1)
        edit = QPushButton("Edit…")
        edit.setToolTip("Change the text, icon or colour")
        edit.clicked.connect(lambda: self.key and self.editRequested.emit(*self.key))
        row.addWidget(edit)
        lay.addLayout(row)
        self.hide()

    def show_note(self, page_index: int, xref: int, *, text: str, author: str, date: str, color: QColor,
                  at: QPoint) -> None:
        self.key = (page_index, int(xref))
        head = "Note" + (f" — {author}" if author else "")
        when = _pdf_date(date)
        self.title.setText(f"<b>{head}</b>" + (f"<br><span style='color:#555'>{when}</span>" if when else ""))
        self.text.setText(text or "(no text — click Edit… to add some)")
        bg = QColor(color)
        if not bg.isValid():
            bg = QColor("#fbbf24")
        # a light tint of the note's colour, dark text: readable in the light and the dark theme
        tint = QColor.fromHsvF(bg.hsvHueF() if bg.hsvHueF() >= 0 else 0.12, min(0.35, bg.hsvSaturationF()), 1.0)
        border = bg.darker(150)
        self.setStyleSheet(
            f"QFrame#NotePopup {{ background: {tint.name()}; border: 1px solid {border.name()}; border-radius: 6px; }}"
            "QFrame#NotePopup QLabel { color: #1f2937; background: transparent; }"
            "QFrame#NotePopup QScrollArea, QFrame#NotePopup QScrollArea > QWidget > QWidget { background: transparent; }"
            "QFrame#NotePopup QToolButton { color: #1f2937; font-size: 15px; }"
        )
        text_h = self.text.heightForWidth(self.WIDTH - 30)
        self._scroll.setFixedHeight(max(24, min(220, text_h + 4)))
        self.adjustSize()
        self.move_to(at)
        self.show()
        self.raise_()

    def move_to(self, at: QPoint) -> None:
        """Place the pop-up at *at* (parent coordinates), kept inside the parent."""
        parent = self.parentWidget()
        x, y = at.x(), at.y()
        if parent is not None:
            x = max(0, min(x, parent.width() - self.width()))
            y = max(0, min(y, parent.height() - self.height()))
        self.move(x, y)

    def close_popup(self) -> None:
        if self.isVisible():
            self.hide()
            self.key = None
            self.closed.emit()
