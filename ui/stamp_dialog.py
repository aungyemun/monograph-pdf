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
    QColorDialog,
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
from core.annotations.stamps import PRESETS, StampSpec, draw_appearance

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
        self.remove_btn = QPushButton("Remove from Library")
        self.remove_btn.clicked.connect(self._remove)
        pics.addWidget(self.remove_white, 1)
        pics.addWidget(add_pic)
        pics.addWidget(self.remove_btn)
        root.addLayout(pics)

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
        c = QColorDialog.getColor(self._custom_color, self, "Stamp Colour")
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
        return StampSpec(text=base.text, color=base.color, image_path=base.image_path,
                         subtitle=" · ".join(parts), opacity=self.opacity.value() / 100.0,
                         rotation=float(self.rotation.value()))

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
