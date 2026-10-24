"""Curated colours and a swatch menu used wherever a colour is chosen (shapes, page design, stamps).

A grid of a few well-matched colours covers most professional documents in one click; "More
colors…" still opens the full picker. The picker is parented to the window, never to a styled
colour button, so it is not tinted by that button's own colour.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGridLayout, QMenu, QToolButton, QWidget, QWidgetAction

# (name, hex): dark, readable on white paper — text, lines, stamps, watermarks
INK_COLORS: list[tuple[str, str]] = [
    ("Black", "#000000"), ("Charcoal", "#333333"), ("Slate", "#475569"), ("Gray", "#6B7280"),
    ("Navy", "#1F3A5F"), ("Blue", "#1D4ED8"), ("Teal", "#0F766E"), ("Green", "#15803D"),
    ("Burgundy", "#8B1E3F"), ("Red", "#B91C1C"), ("Amber", "#B45309"), ("Purple", "#5B21B6"),
]
# light, low-contrast tints that keep black text legible — page backgrounds and shape fills
PAPER_COLORS: list[tuple[str, str]] = [
    ("White", "#FFFFFF"), ("Ivory", "#FFFDF5"), ("Cream", "#FFF8E1"), ("Sand", "#F7F1E3"),
    ("Light gray", "#F3F4F6"), ("Cool gray", "#EEF2F7"), ("Pale blue", "#EAF2FB"), ("Mint", "#EAF7F0"),
    ("Sage", "#EEF3E8"), ("Blush", "#FBEFF1"), ("Lavender", "#F1EEFA"), ("Pale yellow", "#FFFBE6"),
]
NO_COLOR = "#00000000"


def swatch_icon(color: str, size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    c = QColor(color)
    if c.alpha() == 0:  # "none": white with a red slash
        p.fillRect(1, 1, size - 2, size - 2, QColor("#ffffff"))
        p.setPen(QPen(QColor("#dc2626"), 2))
        p.drawLine(3, size - 3, size - 3, 3)
    else:
        p.fillRect(1, 1, size - 2, size - 2, c)
    p.setPen(QPen(QColor("#9aa3af"), 1))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pm)


class SwatchMenu(QMenu):
    """Grid of named swatches, an optional "No color", and "More colors…" (full picker)."""

    def __init__(self, palette: list[tuple[str, str]], on_pick: Callable[[str], None], *, title: str,
                 current: Callable[[], str] | None = None, allow_none: bool = False, parent=None,
                 none_label: str = "No color") -> None:
        super().__init__(parent)
        self._on_pick = on_pick
        self._title = title
        self._current = current
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(8, 8, 8, 4)
        grid.setSpacing(4)
        for i, (name, value) in enumerate(palette):
            b = QToolButton()
            b.setIcon(swatch_icon(value, 22))
            b.setIconSize(QSize(22, 22))
            b.setAutoRaise(True)
            b.setToolTip(f"{name} ({value})")
            b.setAccessibleName(f"{name} {value}")
            b.setObjectName("SwatchButton")
            b.clicked.connect(lambda _c=False, v=value: self._choose(v))
            grid.addWidget(b, i // 6, i % 6)
        act = QWidgetAction(self)
        act.setDefaultWidget(grid_w)
        self.addAction(act)
        if allow_none:
            none = self.addAction(swatch_icon(NO_COLOR), none_label)
            none.triggered.connect(lambda: self._choose(NO_COLOR))
        self.addSeparator()
        more = self.addAction("More colors…")
        more.triggered.connect(self._more)

    def _choose(self, value: str) -> None:
        self.close()
        self._on_pick(value)

    def _more(self) -> None:
        start = QColor(self._current() if self._current else "#000000")
        owner = self.parentWidget().window() if self.parentWidget() is not None else None
        from ui.color_picker import get_color

        c = get_color(start if start.isValid() else QColor("#000000"), owner, self._title)
        if c.isValid():
            self._on_pick(c.name())


def pick_color_dialog(owner: QWidget | None, initial: str, title: str) -> str | None:
    """Full colour picker parented to ``owner``'s window (untinted by any styled button)."""
    from ui.color_picker import get_color

    c = get_color(QColor(initial), owner, title)
    return c.name() if c.isValid() else None
