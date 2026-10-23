"""On-page pop-up of a sticky note: what the note says, who wrote it and when — like a paper note.

A note's text stays hidden until the note is clicked: one click opens this card beside the note
(a second click, ×, Esc or a click elsewhere closes it), a double-click on the note or the pencil
button opens the editor. The card follows the page while it scrolls and zooms.

Design: a clean card in the interface's colours (light or dark theme) with a strip of the note's
own colour on the left, the author and date in a muted line, and the text in a readable size.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


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

    WIDTH = 280
    TEXT_MAX_H = 240

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setObjectName("NotePopup")
        self.setFixedWidth(self.WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.key: tuple[int, int] | None = None
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._strip = QWidget()
        self._strip.setObjectName("NotePopupStrip")
        self._strip.setFixedWidth(5)
        outer.addWidget(self._strip)
        body = QWidget()
        body.setObjectName("NotePopupBody")
        outer.addWidget(body, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 8, 6, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(2)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("NotePopupTitle")
        self.meta = QLabel()
        self.meta.setObjectName("NotePopupMeta")
        titles.addWidget(self.title)
        titles.addWidget(self.meta)
        head.addLayout(titles, 1)
        from ui.toolbar_icons import make_icon

        self._edit_btn = QToolButton()
        self._edit_btn.setObjectName("NotePopupButton")
        self._edit_btn.setIcon(make_icon("edit_text"))
        self._edit_btn.setIconSize(QSize(16, 16))
        self._edit_btn.setAutoRaise(True)
        self._edit_btn.setToolTip("Edit the note (or double-click the note)")
        self._edit_btn.setAccessibleName("Edit note")
        self._edit_btn.clicked.connect(lambda: self.key and self.editRequested.emit(*self.key))
        head.addWidget(self._edit_btn, 0, Qt.AlignmentFlag.AlignTop)
        close = QToolButton()
        close.setObjectName("NotePopupButton")
        close.setIcon(make_icon("close"))
        close.setIconSize(QSize(14, 14))
        close.setAutoRaise(True)
        close.setToolTip("Close (Esc)")
        close.setAccessibleName("Close note")
        close.clicked.connect(self.close_popup)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        self.text = QLabel()
        self.text.setObjectName("NotePopupText")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text.setAccessibleName("Note text")
        scroll = QScrollArea()
        scroll.setObjectName("NotePopupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.text)
        self._scroll = scroll
        lay.addWidget(scroll)
        self.hide()

    def _apply_style(self, color: QColor) -> None:
        from ui.theme import current_palette

        pal = current_palette()
        dark = QColor(pal.surface).lightness() < 128
        card = QColor(pal.surface) if dark else QColor("#ffffff")
        accent = QColor(color) if QColor(color).isValid() else QColor("#fbbf24")
        self.setStyleSheet(
            f"QFrame#NotePopup {{ background: {card.name()}; border: 1px solid {pal.border_strong};"
            " border-radius: 8px; }"
            f"QWidget#NotePopupStrip {{ background: {accent.name()}; border-top-left-radius: 8px;"
            " border-bottom-left-radius: 8px; }"
            "QWidget#NotePopupBody { background: transparent; }"
            f"QLabel#NotePopupTitle {{ color: {pal.text}; font-weight: 600; background: transparent; }}"
            f"QLabel#NotePopupMeta {{ color: {pal.text_subtle}; background: transparent; }}"
            f"QLabel#NotePopupText {{ color: {pal.text}; background: transparent; padding-right: 6px; }}"
            "QScrollArea#NotePopupScroll, QScrollArea#NotePopupScroll > QWidget > QWidget { background: transparent; }"
            "QToolButton#NotePopupButton { border: none; border-radius: 4px; padding: 3px; background: transparent; }"
            f"QToolButton#NotePopupButton:hover {{ background: {pal.hover}; }}"
        )
        f = self.meta.font()
        f.setPointSizeF(max(7.5, self.font().pointSizeF() - 1.0))
        self.meta.setFont(f)

    def show_note(self, page_index: int, xref: int, *, text: str, author: str, date: str, color: QColor,
                  at: QPoint) -> None:
        self.key = (page_index, int(xref))
        self.title.setText(author or "Note")
        when = _pdf_date(date)
        meta = " · ".join(part for part in ("Note" if author else "", when) if part)
        self.meta.setText(meta)
        self.meta.setVisible(bool(meta))
        self.text.setText(text or "(empty note — use the pencil to add text)")
        self._apply_style(color)
        text_h = self.text.heightForWidth(self.WIDTH - 40)
        self._scroll.setFixedHeight(max(22, min(self.TEXT_MAX_H, text_h + 4)))
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
