"""Insert ▸ Symbol…: check marks, stars, arrows, maths and currency signs, circled numbers, Japanese marks.

Only symbols the fonts bundled with Monograph PDF can draw are offered (Noto Sans, Noto Sans CJK JP),
so a symbol looks the same on every PC and in the saved PDF. A chosen symbol is placed as a text
box: move it, resize it, recolour it like any text.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SYMBOL_GROUPS: list[tuple[str, str]] = [
    ("Marks", "✓★☆●○◎■□▲△▼▽◆◇♥♦♣♠※•†‡§¶"),
    ("Arrows", "→←↑↓↔↕⇒⇐⇔"),
    ("Maths", "±×÷≈≠≤≥∞√∑∏∫°µπΩαβγδ‰"),
    ("Currency & signs", "€£¥¢©®™…"),
    ("Numbers", "①②③④⑤⑥⑦⑧⑨⑩"),
    ("Japanese", "〒〇〆々㊤㊥㊦㊧㊨☎⚠✂☀☁☂☃♪♫"),
]


@lru_cache(maxsize=1)
def _bundled_cmaps() -> list[tuple[str, frozenset]]:
    """(family, code points) of the bundled fonts, Latin font first."""
    from fontTools.ttLib import TTFont

    from core.editing.font_inventory import bundled_fonts_dir

    out = []
    for family, name in (("Noto Sans", "NotoSans-Regular.ttf"), ("Noto Sans CJK JP", "NotoSansCJKjp-Regular.otf")):
        try:
            out.append((family, frozenset(TTFont(str(bundled_fonts_dir() / name), lazy=True).getBestCmap())))
        except Exception:  # noqa: BLE001 — a missing font: its symbols are not offered
            continue
    return out


def symbol_font(ch: str) -> str | None:
    """The bundled font that draws *ch*, or None when none does."""
    for family, cmap in _bundled_cmaps():
        if ord(ch) in cmap:
            return family
    return None


def available_groups() -> list[tuple[str, str]]:
    return [(name, "".join(c for c in chars if symbol_font(c))) for name, chars in SYMBOL_GROUPS
            if any(symbol_font(c) for c in chars)]


class SymbolDialog(QDialog):
    def __init__(self, parent=None, *, size: int = 18) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Symbol")
        self.setMinimumWidth(460)
        self._symbol = ""
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        self._buttons: list[QToolButton] = []
        for name, chars in available_groups():
            page = QWidget()
            grid = QGridLayout(page)
            grid.setSpacing(4)
            for i, ch in enumerate(chars):
                b = QToolButton()
                b.setText(ch)
                b.setCheckable(True)
                b.setAutoExclusive(True)
                b.setFixedSize(40, 40)
                f = QFont(symbol_font(ch) or "")
                f.setPixelSize(20)
                b.setFont(f)
                b.setToolTip(f"U+{ord(ch):04X}")
                b.setAccessibleName(f"Symbol {ch}")
                b.clicked.connect(lambda _=False, c=ch: self._choose(c))
                b.setProperty("symbol", ch)
                self._buttons.append(b)
                grid.addWidget(b, i // 10, i % 10)
            grid.setRowStretch(grid.rowCount(), 1)
            tabs.addTab(page, name)
        lay.addWidget(tabs)
        row = QHBoxLayout()
        row.addWidget(QLabel("Size:"))
        self.size = QSpinBox()
        self.size.setRange(6, 200)
        self.size.setSuffix(" pt")
        self.size.setValue(size)
        row.addWidget(self.size)
        self.preview = QLabel("")
        self.preview.setMinimumWidth(60)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.preview, 1)
        lay.addLayout(row)
        hint = QLabel("Click a symbol, then OK, then click on the page where it should go. It is placed as a "
                      "text box: drag it, resize it or change its colour like other text.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        lay.addWidget(hint)
        self._box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._box.accepted.connect(self.accept)
        self._box.rejected.connect(self.reject)
        self._box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        lay.addWidget(self._box)
        for b in self._buttons:
            b.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.MouseButtonDblClick and obj in self._buttons:
            self._choose(obj.property("symbol"))
            self.accept()  # double-click: choose and close
            return True
        return super().eventFilter(obj, event)

    def _choose(self, ch: str) -> None:
        self._symbol = ch
        f = QFont(symbol_font(ch) or "")
        f.setPixelSize(32)
        self.preview.setFont(f)
        self.preview.setText(ch)
        self._box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def symbol(self) -> str:
        return self._symbol

    def font_family(self) -> str:
        return symbol_font(self._symbol) or "Noto Sans"
