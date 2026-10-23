"""Choose exactly where pages go: before or after a given page, at the beginning or at the end.

Used by Insert Blank Pages…, Insert Pages from PDF… and Move Pages…. Page numbers shown to the user
are 1-based; :meth:`PagePositionDialog.insert_index` returns the 0-based index at which new pages
are inserted (0 … page_count).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

BEFORE, AFTER, START, END = "before", "after", "start", "end"


def insert_index(where: str, page_number: int, page_count: int) -> int:
    """0-based insertion index for ``where`` relative to the 1-based ``page_number``."""
    page_number = max(1, min(int(page_number), max(1, page_count)))
    if where == START:
        return 0
    if where == END:
        return page_count
    if where == BEFORE:
        return page_number - 1
    return page_number  # AFTER


def move_order(page_count: int, pages: list[int], target: int) -> list[int]:
    """New page order (list of old indices) after moving ``pages`` (0-based, kept in their order)
    so that they start at insertion index ``target`` (counted in the original document)."""
    moving = sorted({p for p in pages if 0 <= p < page_count})
    rest = [i for i in range(page_count) if i not in moving]
    at = sum(1 for i in range(min(target, page_count)) if i not in moving)
    return rest[:at] + moving + rest[at:]


class PagePositionDialog(QDialog):
    """``count_label`` adds a "how many pages" box (blank pages)."""

    def __init__(self, parent=None, *, title: str, intro: str, page_count: int, page: int,
                 ok_text: str, count_label: str | None = None, default: str = AFTER) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._count = max(1, page_count)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel(intro)
        head.setWordWrap(True)
        lay.addWidget(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.group = QButtonGroup(self)
        self.radio_before = QRadioButton("Before page")
        self.radio_after = QRadioButton("After page")
        self.radio_start = QRadioButton("At the beginning of the document")
        self.radio_end = QRadioButton("At the end of the document")
        for i, (key, radio) in enumerate(((BEFORE, self.radio_before), (AFTER, self.radio_after),
                                          (START, self.radio_start), (END, self.radio_end))):
            radio.setProperty("where", key)
            self.group.addButton(radio, i)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, self._count)
        self.page_spin.setValue(max(1, min(page + 1, self._count)))
        self.page_spin.setSuffix(f"  of {self._count}")
        self.page_spin.setAccessibleName("Page number")
        grid.addWidget(self.radio_before, 0, 0)
        grid.addWidget(self.radio_after, 1, 0)
        grid.addWidget(self.page_spin, 0, 1, 2, 1)
        grid.addWidget(self.radio_start, 2, 0, 1, 2)
        grid.addWidget(self.radio_end, 3, 0, 1, 2)
        lay.addLayout(grid)

        self.count_spin: QSpinBox | None = None
        if count_label:
            row = QGridLayout()
            row.addWidget(QLabel(count_label), 0, 0)
            self.count_spin = QSpinBox()
            self.count_spin.setRange(1, 500)
            self.count_spin.setValue(1)
            self.count_spin.setAccessibleName(count_label.rstrip(":"))
            row.addWidget(self.count_spin, 0, 1)
            row.setColumnStretch(2, 1)
            lay.addLayout(row)

        self.summary = QLabel()
        self.summary.setObjectName("DialogHint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        {BEFORE: self.radio_before, START: self.radio_start, END: self.radio_end}.get(default, self.radio_after).setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self._sync())
        self.page_spin.valueChanged.connect(lambda *_: self._sync())
        if self.count_spin is not None:
            self.count_spin.valueChanged.connect(lambda *_: self._sync())
        self._sync()

    def where(self) -> str:
        button = self.group.checkedButton()
        return button.property("where") if button is not None else AFTER

    def insert_index(self) -> int:
        return insert_index(self.where(), self.page_spin.value(), self._count)

    def count(self) -> int:
        return self.count_spin.value() if self.count_spin is not None else 1

    def _sync(self) -> None:
        relative = self.where() in (BEFORE, AFTER)
        self.page_spin.setEnabled(relative)
        at = self.insert_index()
        first = at + 1
        if at == 0:
            text = "They will become page 1."
        elif at >= self._count:
            text = f"They will follow the last page (page {self._count})."
        else:
            text = f"They will go between page {at} and page {at + 1}, starting as page {first}."
        self.summary.setText(text)
