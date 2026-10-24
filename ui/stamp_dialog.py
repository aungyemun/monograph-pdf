"""Stamp library dialog: preset stamps, the user's own text and picture stamps, and their options.

Every stamp is previewed with the same drawing that goes into the PDF (core/annotations/stamps.py).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QToolButton,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.annotations import stamp_library as lib
from core.annotations.stamps import CORNERS, FONTS, FRAMES, PRESETS, StampSpec, draw_appearance

ROLE = Qt.ItemDataRole.UserRole
PREVIEW = QSize(150, 52)
PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"


def render_preview(spec: StampSpec, size: QSize = PREVIEW) -> QPixmap:
    """The stamp as it will appear in the PDF, rendered with MuPDF."""
    w, h = 180.0, 60.0
    if spec.image_path:
        try:
            from PIL import Image

            with Image.open(spec.image_path) as im:
                iw, ih = im.size
            w, h = 120.0 * iw / max(ih, 1), 120.0
            if w > 240:
                w, h = 240.0, 240.0 * ih / max(iw, 1)
        except Exception:  # noqa: BLE001
            pass
    try:
        scratch = draw_appearance(StampSpec(**{**spec.__dict__, "rotation": 0.0}), w, h)
        try:
            pix = scratch[0].get_pixmap(dpi=96 * 2, alpha=True)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888).copy()
        finally:
            scratch.close()
        pm = QPixmap.fromImage(img).scaled(size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(2)
        return pm
    except Exception:  # noqa: BLE001
        return QPixmap()


class StampLibraryDialog(QDialog):
    def __init__(self, parent=None, *, start_dir: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Stamps")
        self.setMinimumSize(520, 460)
        self._start_dir = start_dir
        self._custom_color = QColor("#1d4ed8")
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Choose a stamp, then drag a box on the page (or click to place it)."))
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(PREVIEW)
        self.list.setGridSize(QSize(PREVIEW.width() + 18, PREVIEW.height() + 30))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setAccessibleName("Stamp library")
        self.list.currentItemChanged.connect(lambda *_a: self._sync())
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        root.addWidget(self.list, 1)

        mine = QHBoxLayout()
        self.new_text = QLineEdit()
        self.new_text.setPlaceholderText("Custom stamp text, e.g. CHECKED BY QA")
        self.new_text.setMaxLength(60)
        self.color_btn = QPushButton("Colour…")
        self.color_btn.clicked.connect(self._pick_color)
        add_text = QPushButton("Add Text Stamp")
        add_text.clicked.connect(self._add_text)
        mine.addWidget(self.new_text, 1)
        mine.addWidget(self.color_btn)
        mine.addWidget(add_text)
        root.addLayout(mine)
        pics = QHBoxLayout()
        self.remove_white = QCheckBox("Make a white background transparent")
        self.remove_white.setChecked(True)
        add_pic = QPushButton("Add Picture Stamp…")
        add_pic.clicked.connect(self._add_picture)
        self.style_btn = QPushButton("Customize Look…")
        self.style_btn.setToolTip("Change the font, colours, frame, corners and line thickness of this stamp")
        self.style_btn.clicked.connect(self._customize)
        self._look: dict = {}
        self.remove_btn = QPushButton("Remove from Library")
        self.remove_btn.clicked.connect(self._remove)
        pics.addWidget(add_pic)
        pics.addWidget(self.style_btn)
        pics.addWidget(self.remove_btn)
        pics.addStretch(1)
        root.addLayout(pics)
        root.addWidget(self.remove_white)  # own row: the label is never cut off

        form = QFormLayout()
        self.date = QCheckBox("Add today's date")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Optional name shown under the label")
        self.name.setMaxLength(60)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setValue(100)
        self.rotation = QSpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setSuffix(" °")
        form.addRow("", self.date)
        form.addRow("Name:", self.name)
        form.addRow("Opacity:", self.opacity)
        form.addRow("Rotation:", self.rotation)
        root.addLayout(form)
        note = QLabel("Stamps are PDF stamp annotations: other PDF readers show them, and they can be "
                      "changed or deleted later in the Comments panel.")
        note.setWordWrap(True)
        note.setObjectName("ContextHint")
        root.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Place")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self._populate()

    # --- library ---------------------------------------------------------------------------------

    def _add_item(self, label: str, spec: StampSpec, entry: lib.LibraryEntry | None) -> QListWidgetItem:
        item = QListWidgetItem(QIcon(render_preview(spec)), label)
        item.setData(ROLE, (spec, entry))
        item.setToolTip(label)
        self.list.addItem(item)
        return item

    def _populate(self, select_last: bool = False) -> None:
        self.list.clear()
        for p in PRESETS:
            self._add_item(p.label.title(), StampSpec(text=p.label, color=p.color), None)
        for e in lib.load_entries():
            if e.kind == "text":
                self._add_item(e.text, StampSpec(text=e.text, color=e.color), e)
            else:
                self._add_item("Picture", StampSpec(text="Picture stamp", image_path=str(lib.picture_path(e))), e)
        self.list.setCurrentRow(self.list.count() - 1 if select_last else 0)

    def _pick_color(self) -> None:
        from ui.color_picker import get_color

        c = get_color(self._custom_color, self, "Stamp color")
        if c.isValid():
            self._custom_color = c

    def _add_text(self) -> None:
        text = " ".join(self.new_text.text().split())
        if not text:
            return
        entries = lib.load_entries()
        entries.append(lib.LibraryEntry(kind="text", text=text, color=self._custom_color.name()))
        lib.save_entries(entries)
        self.new_text.clear()
        self._populate(select_last=True)

    def _add_picture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Picture Stamp", self._start_dir, PICTURE_FILTER)
        if not path:
            return
        try:
            stored = lib.import_picture(Path(path), remove_white=self.remove_white.isChecked())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Picture Stamp", f"The picture could not be read: {type(exc).__name__}")
            return
        entries = lib.load_entries()
        entries.append(lib.LibraryEntry(kind="picture", picture=stored.name))
        lib.save_entries(entries)
        self._populate(select_last=True)

    def _remove(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        _spec, entry = item.data(ROLE)
        if entry is None:
            return
        lib.save_entries([e for e in lib.load_entries() if e != entry])
        self._populate()

    def _sync(self) -> None:
        item = self.list.currentItem()
        entry = item.data(ROLE)[1] if item is not None else None
        self.remove_btn.setEnabled(entry is not None)
        is_picture = bool(item is not None and item.data(ROLE)[0].image_path)
        self.style_btn.setEnabled(item is not None and not is_picture)
        self.date.setEnabled(not is_picture)
        self.name.setEnabled(not is_picture)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(item is not None)

    # --- result ----------------------------------------------------------------------------------

    def spec(self) -> StampSpec:
        item = self.list.currentItem()
        base: StampSpec = item.data(ROLE)[0] if item is not None else StampSpec()
        parts = []
        if not base.image_path:
            if self.date.isChecked():
                parts.append(_dt.date.today().isoformat())
            if self.name.text().strip():
                parts.append(self.name.text().strip())
        spec = StampSpec(text=base.text, color=base.color, image_path=base.image_path,
                         subtitle=" · ".join(parts), opacity=self.opacity.value() / 100.0,
                         rotation=float(self.rotation.value()))
        if not spec.image_path and self._look:
            spec = StampSpec(**{**spec.__dict__, **self._look})
        return spec

    def _customize(self) -> None:
        item = self.list.currentItem()
        if item is None or item.data(ROLE)[0].image_path:
            return
        dlg = StampStyleDialog(self, self.spec(), title="Customize Stamp", ok_text="Use This Look")
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        result = dlg.spec()
        self._look = {k: getattr(result, k) for k in LOOK_KEYS + ("text", "color")}
        self.opacity.setValue(int(round(result.opacity * 100)))
        self.rotation.setValue(int(round(result.rotation)))

    def default_size(self) -> tuple[float, float]:
        spec = self.spec()
        if spec.image_path:
            try:
                from PIL import Image

                with Image.open(spec.image_path) as im:
                    iw, ih = im.size
                h = 60.0
                return (min(240.0, h * iw / max(ih, 1)), h)
            except Exception:  # noqa: BLE001
                return (120.0, 60.0)
        return (max(110.0, min(260.0, 13.0 * len(spec.text) + 40.0)), 52.0 if spec.subtitle else 42.0)


LOOK_KEYS = ("font", "bold", "text_color", "border_color", "fill_color", "frame", "corners", "line_scale")
FONT_LABELS = {"Helvetica": "Sans serif (Helvetica)", "Times": "Serif (Times)", "Courier": "Typewriter (Courier)"}
FRAME_LABELS = {"double": "Double line", "single": "Single line", "none": "No border"}
CORNER_LABELS = {"rounded": "Rounded", "square": "Square", "pill": "Round ends (pill)"}
THICKNESS = (("Thin", 0.6), ("Normal", 1.0), ("Thick", 1.6), ("Extra thick", 2.4))


class _ColorChoice(QToolButton):
    """A colour button with the swatch menu; ``none_label`` adds a choice that stores ""."""

    def __init__(self, title: str, value: str, *, palette: str = "ink", none_label: str = "",
                 on_change=None, parent=None) -> None:
        super().__init__(parent)
        from ui.color_swatches import INK_COLORS, PAPER_COLORS, SwatchMenu

        self._title, self._none_label, self._on_change = title, none_label, on_change
        self._value = value
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setAccessibleName(title)
        self.setMenu(SwatchMenu(PAPER_COLORS if palette == "paper" else INK_COLORS, self._picked, title=title,
                                current=lambda: self._value or "#000000", allow_none=bool(none_label),
                                none_label=none_label or "No color", parent=self))
        self._refresh()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value
        self._refresh()

    def _picked(self, value: str) -> None:
        from ui.color_swatches import NO_COLOR

        self._value = "" if value == NO_COLOR else QColor(value).name()
        self._refresh()
        if self._on_change:
            self._on_change()

    def _refresh(self) -> None:
        from ui.color_swatches import NO_COLOR, swatch_icon

        self.setIcon(swatch_icon(self._value or NO_COLOR))
        self.setText(self._value.upper() if self._value else self._none_label)


class StampStyleDialog(QDialog):
    """Edit a text stamp: wording, theme, font, colours, frame, corners, line thickness, opacity and
    rotation, with a large live preview drawn exactly as it goes into the PDF."""

    def __init__(self, parent, spec: StampSpec, *, title: str = "Edit Stamp", ok_text: str = "Update Stamp") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._base = spec
        root = QVBoxLayout(self)
        root.setSpacing(10)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(130)
        self.preview.setObjectName("StampPreview")
        self.preview.setStyleSheet("QLabel#StampPreview { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; }")
        self.preview.setAccessibleName("Stamp preview")
        root.addWidget(self.preview)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        row = 0

        def add(label: str, widget, col: int = 0) -> None:
            nonlocal row
            grid.addWidget(QLabel(label), row, col)
            grid.addWidget(widget, row, col + 1)

        self.theme = QComboBox()
        self.theme.addItem("Keep current look", None)
        for p in PRESETS:
            self.theme.addItem(p.label.title(), p)
        self.theme.setToolTip("Switch to another standard stamp (wording and colour)")
        add("Stamp type:", self.theme)
        row += 1
        self.text = QLineEdit(spec.text)
        self.text.setMaxLength(60)
        add("Text:", self.text)
        row += 1
        self.subtitle = QLineEdit(spec.subtitle)
        self.subtitle.setMaxLength(80)
        self.subtitle.setPlaceholderText("Optional second line, e.g. a date or a name")
        add("Second line:", self.subtitle)
        row += 1
        self.font = QComboBox()
        for key in FONTS:
            self.font.addItem(FONT_LABELS[key], key)
        self.font.setCurrentIndex(max(0, self.font.findData(spec.font)))
        self.bold = QCheckBox("Bold")
        self.bold.setChecked(bool(spec.bold))
        font_row = QHBoxLayout()
        font_row.addWidget(self.font, 1)
        font_row.addWidget(self.bold)
        grid.addWidget(QLabel("Font:"), row, 0)
        grid.addLayout(font_row, row, 1)
        row += 1
        self.color = _ColorChoice("Stamp Colour", spec.color, on_change=self._sync)
        add("Stamp colour:", self.color)
        row += 1
        self.text_color = _ColorChoice("Text Colour", spec.text_color, none_label="Same as stamp", on_change=self._sync)
        add("Text colour:", self.text_color)
        row += 1
        self.border_color = _ColorChoice("Border Colour", spec.border_color, none_label="Same as stamp", on_change=self._sync)
        add("Border colour:", self.border_color)
        row += 1
        self.fill_color = _ColorChoice("Fill Colour", spec.fill_color, palette="paper", none_label="No fill",
                                       on_change=self._sync)
        add("Fill:", self.fill_color)
        row += 1
        self.frame = QComboBox()
        for key in FRAMES:
            self.frame.addItem(FRAME_LABELS[key], key)
        self.frame.setCurrentIndex(max(0, self.frame.findData(spec.frame)))
        add("Border:", self.frame)
        row += 1
        self.corners = QComboBox()
        for key in CORNERS:
            self.corners.addItem(CORNER_LABELS[key], key)
        self.corners.setCurrentIndex(max(0, self.corners.findData(spec.corners)))
        add("Corners:", self.corners)
        row += 1
        self.thickness = QComboBox()
        for label, value in THICKNESS:
            self.thickness.addItem(label, value)
        nearest = min(range(len(THICKNESS)), key=lambda i: abs(THICKNESS[i][1] - float(spec.line_scale or 1.0)))
        self.thickness.setCurrentIndex(nearest)
        add("Line thickness:", self.thickness)
        row += 1
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setValue(int(round(spec.opacity * 100)))
        add("Opacity:", self.opacity)
        row += 1
        self.rotation = QSpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setSuffix(" °")
        self.rotation.setValue(int(round(spec.rotation)))
        add("Rotation:", self.rotation)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.theme.currentIndexChanged.connect(self._apply_theme)
        for w in (self.text, self.subtitle):
            w.textChanged.connect(lambda *_: self._sync())
        for w in (self.font, self.frame, self.corners, self.thickness):
            w.currentIndexChanged.connect(lambda *_: self._sync())
        self.bold.toggled.connect(lambda *_: self._sync())
        self._sync()

    def _apply_theme(self) -> None:
        preset = self.theme.currentData()
        if preset is None:
            return
        self.text.setText(preset.label)
        self.color.set_value(preset.color)
        self.text_color.set_value("")
        self.border_color.set_value("")
        self._sync()

    def spec(self) -> StampSpec:
        return StampSpec(**{**self._base.__dict__,
                            "text": " ".join(self.text.text().split()) or self._base.text,
                            "subtitle": self.subtitle.text().strip(),
                            "color": self.color.value() or self._base.color,
                            "text_color": self.text_color.value(),
                            "border_color": self.border_color.value(),
                            "fill_color": self.fill_color.value(),
                            "font": self.font.currentData(),
                            "bold": self.bold.isChecked(),
                            "frame": self.frame.currentData(),
                            "corners": self.corners.currentData(),
                            "line_scale": float(self.thickness.currentData()),
                            "opacity": self.opacity.value() / 100.0,
                            "rotation": float(self.rotation.value())})

    def _sync(self) -> None:
        spec = self.spec()
        self.preview.setPixmap(render_preview(spec, QSize(360, 110)))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.text.text().strip()))
