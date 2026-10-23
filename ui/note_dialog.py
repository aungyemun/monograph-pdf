"""Sticky note dialog: the note's text, its icon and its colour, with a live preview of the icon.

Used for a new note and for editing one (double-click it, or Edit in its pop-up / the Comments panel).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.annotations.note_style import NOTE_COLORS, NOTE_ICONS, _icon_stream, _shade


@lru_cache(maxsize=256)
def note_icon_image(name: str, color: str, size: int = 32) -> QImage:
    """The exact note appearance written into the PDF, drawn by MuPDF (so the preview never lies)."""
    import fitz

    c = QColor(color)
    rgb = (c.redF(), c.greenF(), c.blueF())
    doc = fitz.open()
    page = doc.new_page(width=20, height=20)
    annot = page.add_text_annot(fitz.Point(2, 2), "", icon="Comment")
    annot.update()
    ap = int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    bbox = [float(v) for v in doc.xref_get_key(ap, "BBox")[1].strip("[] ").split()]
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    stream = _icon_stream(name, w, h, fill=rgb, border=_shade(rgb, 0.55), ink=_shade(rgb, 0.45))
    if bbox[0] or bbox[1]:
        stream = f"1 0 0 1 {bbox[0]:.2f} {bbox[1]:.2f} cm\n".encode("ascii") + stream
    doc.update_stream(ap, stream)
    clip = annot.rect
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(size / clip.width, size / clip.height), clip=clip, alpha=True,
                            annots=True)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888).copy()
    doc.close()
    return img


class NoteDialog(QDialog):
    """Text + icon + colour of a sticky note."""

    def __init__(self, parent=None, *, title: str = "Sticky Note", text: str = "", icon: str = "Comment",
                 color: str = "#fbbf24", offer_default: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._icon = icon if icon in {n for n, _ in NOTE_ICONS} else "Comment"
        self._color = QColor(color).name() if QColor(color).isValid() else "#fbbf24"

        from ui.theme import current_palette

        pal = current_palette()
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 12)
        head = QHBoxLayout()
        head.setSpacing(10)
        self._preview = QLabel()
        self._preview.setFixedSize(36, 36)
        self._preview.setAccessibleName("Note icon preview")
        head.addWidget(self._preview)
        heading = QLabel("Note text")
        heading.setObjectName("NoteDialogHeading")
        head.addWidget(heading, 1)
        lay.addLayout(head)
        self.text = QPlainTextEdit(text)
        self.text.setAccessibleName("Comment text")
        self.text.setPlaceholderText("Write your comment…")
        self.text.setMinimumHeight(90)
        self.text.setMaximumHeight(160)
        lay.addWidget(self.text)

        def section(title: str) -> None:
            lab = QLabel(title)
            lab.setObjectName("NoteDialogSection")
            lay.addWidget(lab)

        self.setStyleSheet(
            f"QLabel#NoteDialogHeading {{ font-weight: 600; color: {pal.text}; }}"
            f"QLabel#NoteDialogSection {{ color: {pal.text_subtle}; margin-top: 4px; }}"
            f"QToolButton#NoteIconButton {{ border: 1px solid {pal.border}; border-radius: 6px; background: {pal.surface}; }}"
            f"QToolButton#NoteIconButton:hover {{ background: {pal.hover}; }}"
            f"QToolButton#NoteIconButton:checked {{ border: 2px solid {pal.accent}; background: {pal.accent_soft}; }}"
        )
        self._ring = pal.accent
        section("Icon")
        icons = QWidget()
        grid = QGridLayout(icons)
        grid.setContentsMargins(0, 0, 0, 0)
        self._icon_group = QButtonGroup(self)
        self._icon_buttons: dict[str, QToolButton] = {}
        for i, (name, label) in enumerate(NOTE_ICONS):
            b = QToolButton()
            b.setObjectName("NoteIconButton")
            b.setCheckable(True)
            b.setToolTip(label)
            b.setAccessibleName(f"Icon: {label}")
            b.setIconSize(QSize(24, 24))
            b.setFixedSize(38, 38)
            b.setChecked(name == self._icon)
            b.clicked.connect(lambda _=False, n=name: self._set_icon(n))
            self._icon_group.addButton(b)
            self._icon_buttons[name] = b
            grid.addWidget(b, 0, i)
        grid.setColumnStretch(len(NOTE_ICONS), 1)
        lay.addWidget(icons)

        section("Color")
        colors = QWidget()
        row = QHBoxLayout(colors)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._color_buttons: dict[str, QToolButton] = {}
        for label, hex_ in NOTE_COLORS:
            b = QToolButton()
            b.setToolTip(label)
            b.setAccessibleName(f"Color: {label}")
            b.setFixedSize(24, 24)
            b.setCheckable(True)
            # round swatches; the chosen one gets a ring in the accent colour (visible in both themes)
            b.setStyleSheet(f"QToolButton {{ background: {hex_}; border: 1px solid rgba(0,0,0,60); border-radius: 12px; }}"
                            f"QToolButton:checked {{ border: 3px solid {self._ring}; }}")
            b.clicked.connect(lambda _=False, h=hex_: self._set_color(h))
            row.addWidget(b)
            self._color_buttons[hex_.lower()] = b
        more = QToolButton()
        more.setText("More…")
        more.setToolTip("Any colour")
        more.clicked.connect(self._more_colors)
        row.addWidget(more)
        row.addStretch(1)
        lay.addWidget(colors)

        self.remember = QCheckBox("Use this icon and colour for new notes")
        self.remember.setVisible(offer_default)
        lay.addWidget(self.remember)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save Note")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._refresh()
        self.text.setFocus()
        self.text.selectAll()

    # ---------------------------------------------------------------- state
    def note_text(self) -> str:
        return self.text.toPlainText()

    def icon(self) -> str:
        return self._icon

    def color(self) -> str:
        return self._color

    def color_rgb(self) -> tuple[float, float, float]:
        c = QColor(self._color)
        return (c.redF(), c.greenF(), c.blueF())

    def _set_icon(self, name: str) -> None:
        self._icon = name
        self._refresh()

    def _set_color(self, hex_: str) -> None:
        self._color = QColor(hex_).name()
        self._refresh()

    def _more_colors(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Note color")
        if c.isValid():
            self._set_color(c.name())

    def _refresh(self) -> None:
        for name, b in self._icon_buttons.items():
            b.setIcon(QIcon(QPixmap.fromImage(note_icon_image(name, self._color, 56))))
            b.setChecked(name == self._icon)
        pm = QPixmap.fromImage(note_icon_image(self._icon, self._color, 72))
        pm.setDevicePixelRatio(2.0)
        self._preview.setPixmap(pm)
        for hex_, b in self._color_buttons.items():
            b.setChecked(hex_ == self._color.lower())
