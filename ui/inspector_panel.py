"""Contextual right inspector — selection-aware properties; live updates without Apply."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.document import PdfDocument
from core.editing.edit_model import EditableDocument
from core.editing.font_cache import cached_font_families, recently_used_fonts, remember_font
from core.editing.text_box import SizeMode, TextAlign, TextBox, VAlign, WritingMode
from core.page_info import PageInfo


def _path_name(value: str) -> str:
    if not value:
        return "—"
    return Path(value).name


def _swatch_icon(color: str) -> QIcon:
    """Rounded colour chip with checkerboard for transparent colours."""
    c = QColor(color or "#000000")
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if c.alpha() < 255:
        for i in range(0, size, 8):
            for j in range(0, size, 8):
                p.fillRect(i, j, 8, 8, QColor("#d1d5db") if (i + j) // 8 % 2 else QColor("#ffffff"))
    p.setPen(QPen(QColor(0, 0, 0, 60), 2))
    p.setBrush(c)
    p.drawRoundedRect(2, 2, size - 4, size - 4, 6, 6)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def _color_label(color: str) -> str:
    c = QColor(color or "#000000")
    if c.alpha() == 0:
        return "None"
    name = c.name(QColor.NameFormat.HexRgb).upper()
    return name if c.alpha() == 255 else f"{name}  {round(c.alpha() / 2.55)}%"


def set_swatch(btn: QToolButton, color: str) -> None:
    btn.setIcon(_swatch_icon(color))
    btn.setText(_color_label(color))
    btn.setToolTip(f"Choose a color ({_color_label(color)})")


def _color_btn(initial: str, on_pick, *, compact: bool = False) -> QToolButton:
    """Colour swatch button; ``compact`` shows only the chip (the colour name is in the tooltip)."""
    btn = QToolButton()
    btn.setObjectName("ColorSwatch")
    btn.setIconSize(QSize(16, 16))
    btn.setAutoRaise(False)
    btn.setToolButtonStyle(
        Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    )
    set_swatch(btn, initial)
    btn.clicked.connect(lambda: on_pick(btn))
    return btn


def _color_row(edit: QLineEdit, btn: QToolButton) -> QWidget:
    """Swatch button only; ``edit`` stays as the (hidden) value holder."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(btn)
    row.addWidget(edit)
    edit.hide()
    row.addStretch(1)
    wrap = QWidget()
    wrap.setLayout(row)
    return wrap


def _row(*widgets, stretch_last: bool = False) -> QWidget:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    for i, w in enumerate(widgets):
        lay.addWidget(w, 1 if (stretch_last and i == len(widgets) - 1) else 0)
    if not stretch_last:
        lay.addStretch(1)
    box = QWidget()
    box.setLayout(lay)
    return box


def _percent_spin(fraction: float, minimum: int = 5) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, 100)
    spin.setSuffix(" %")
    spin.setSingleStep(5)
    spin.setValue(int(round(float(fraction) * 100)))
    return spin


def _angle_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-180, 180)
    spin.setDecimals(0)
    spin.setSingleStep(15)
    spin.setSuffix("°")
    spin.setWrapping(True)
    spin.setValue(float(value))
    return spin


def _toggle(label: str, tip: str, checked: bool, font_attr: str) -> QToolButton:
    btn = QToolButton()
    btn.setObjectName("FormatToggle")
    btn.setText(label)
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setToolTip(tip)
    btn.setAccessibleName(tip)
    btn.setFixedSize(30, 28)
    f = btn.font()
    getattr(f, font_attr)(True)
    btn.setFont(f)
    return btn


class _ElidedLabel(QLabel):
    """Single-line label that elides long unbroken text (e.g. field names) instead of overflowing."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = text
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self._refresh()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = max(20, self.width() - 2)
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, width))


class _CommitTextEdit(QPlainTextEdit):
    """Multi-line value box that commits on focus-out (like QLineEdit.editingFinished)."""

    committed = Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.committed.emit()


class InspectorPanel(QScrollArea):
    styleEdited = Signal()
    pageSizeRequested = Signal()
    hideRequested = Signal()  # the panel's own × button

    def show_context(self, *args, **kwargs) -> None:  # noqa: D401 — wrapper adds compaction
        self._show_context_impl(*args, **kwargs)
        self._compact_fields()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("InspectorPanel")
        self.setWidgetResizable(True)
        self.setMinimumWidth(250)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Properties panel")
        self._root = QWidget()
        self._root.setObjectName("InspectorRoot")
        self._layout = QVBoxLayout(self._root)
        self._layout.setContentsMargins(14, 4, 6, 14)
        # Close button in the panel's corner: hide the panel (F8 / View ▸ Properties Panel brings it back)
        from PySide6.QtWidgets import QHBoxLayout, QToolButton

        from ui.toolbar_icons import make_icon

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._hide_btn = QToolButton()
        self._hide_btn.setObjectName("PanelCloseButton")
        self._hide_btn.setIcon(make_icon("close"))
        self._hide_btn.setIconSize(QSize(16, 16))
        self._hide_btn.setAutoRaise(True)
        self._hide_btn.setToolTip("Hide the Properties panel (F8 shows it again)")
        self._hide_btn.setAccessibleName("Hide Properties panel")
        self._hide_btn.clicked.connect(self.hideRequested.emit)
        header.addWidget(self._hide_btn)
        self._layout.addLayout(header)
        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._form.setHorizontalSpacing(10)
        self._form.setVerticalSpacing(6)
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self._layout.addLayout(self._form)
        self._layout.addStretch(1)
        self.setWidget(self._root)
        self._edit: EditableDocument | None = None
        self._box: TextBox | None = None
        self._field = None
        self._shape = None
        self._image = None
        self._context_key: str | None = None
        self._updating = False
        self.clear()

    def clear(self) -> None:
        self._box = None
        self._field = None
        self._shape = None
        self._image = None
        self._context_key = None
        while self._form.rowCount():
            self._form.removeRow(0)
        empty = QLabel("No document open")
        empty.setObjectName("ContextHint")
        self._form.addRow(empty)

    def show_document(
        self,
        document: PdfDocument,
        page: PageInfo | None = None,
        edit: EditableDocument | None = None,
        selected: TextBox | None = None,
    ) -> None:
        self.show_context(document, page, edit, text_box=selected)

    def _show_context_impl(
        self,
        document: PdfDocument,
        page: PageInfo | None = None,
        edit: EditableDocument | None = None,
        *,
        text_box: TextBox | None = None,
        image=None,
        field=None,
        table=None,
        shape=None,
        force: bool = False,
    ) -> None:
        """Show only properties relevant to the current selection."""
        self._edit = edit
        key = None
        if text_box is not None:
            key = f"text:{text_box.object_id}"
        elif shape is not None:
            key = f"shape:{shape.object_id}"
        elif image is not None:
            key = f"image:{image.object_id}"
        elif field is not None:
            key = f"field:{field.object_id}"
        elif table is not None:
            key = f"table:{getattr(table, 'object_id', id(table))}"
        else:
            key = f"doc:{document.name}:{getattr(page, 'index', -1)}"

        # Avoid full rebuild (and focus steal) when same context
        if not force and key == self._context_key and text_box is None and field is None:
            # Still allow geometry-only refresh for shapes/images via force
            if shape is not None and hasattr(self, "_geom_x"):
                self._sync_geometry_fields(shape.rect)
                return
            if image is not None and hasattr(self, "_geom_x"):
                self._sync_geometry_fields(image.rect)
                return

        self._context_key = key
        self._box = text_box
        self._field = field
        self._shape = shape
        self._image = image
        while self._form.rowCount():
            self._form.removeRow(0)

        if text_box is not None:
            self._section("Text")
            self._build_textbox_editors(text_box)
            return
        if shape is not None:
            self._section("Shape")
            self._build_shape_editors(shape)
            return
        if image is not None:
            self._section("Image")
            self._build_image_editors(image)
            return
        if field is not None:
            self._section("Form field")
            self._build_field_editors(field)
            return
        if table is not None:
            self._section("Table")
            self._add_ro("Rows", str(getattr(table, "nrows", "?")))
            self._add_ro("Columns", str(getattr(table, "ncols", "?")))
            tip = QLabel("Use Forms ▸ Tables, or the toolbar, to add or delete rows and columns.")
            tip.setWordWrap(True)
            tip.setObjectName("ContextHint")
            self._form.addRow(tip)
            return

        meta = document.metadata()
        self._section("Document")
        name = _ElidedLabel(document.name)
        name.setToolTip(str(getattr(document, "path", "") or document.name))
        self._form.addRow("File:", name)
        self._add_ro("Status", "Unsaved changes" if (edit and edit.dirty) else "Saved")
        self._add_ro("Pages", str(meta.page_count))
        if page is not None:
            self._section(f"Page {page.index + 1}")
            w_pt, h_pt = page.display_width_pt, page.display_height_pt
            try:
                from core.page_geometry import label_page_size

                paper = label_page_size(w_pt, h_pt).display
            except Exception:  # noqa: BLE001
                paper = "Custom"
            self._add_ro("Paper", paper)
            self._add_ro("Size", f"{w_pt / 72 * 25.4:.0f} × {h_pt / 72 * 25.4:.0f} mm")
            if page.rotation:
                self._add_ro("Rotation", f"{page.rotation}°")
            resize = QPushButton("Change Page Size…")
            resize.setToolTip("Convert pages to A4, Letter, Legal, B5 … and fit the content")
            resize.clicked.connect(self.pageSizeRequested.emit)
            self._form.addRow("", resize)
        tip = QLabel("Select text, a shape, an image or a form field to see its properties.")
        tip.setWordWrap(True)
        tip.setObjectName("ContextHint")
        self._form.addRow(tip)

    def _compact_fields(self) -> None:
        """Let editors shrink to the panel width instead of forcing a horizontal overflow."""
        from PySide6.QtWidgets import QAbstractSpinBox, QComboBox as _Combo, QLineEdit as _Line, QSizePolicy

        for w in self._root.findChildren(QWidget):
            if isinstance(w, _Combo):
                w.setSizeAdjustPolicy(_Combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                w.setMinimumContentsLength(6)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            elif isinstance(w, QAbstractSpinBox):
                w.setMinimumWidth(64)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            elif isinstance(w, _Line):
                w.setMinimumWidth(60)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _section(self, title: str) -> None:
        lab = QLabel(title.upper())
        lab.setObjectName("InspectorSection")
        self._form.addRow(lab)

    def _add_ro(self, label: str, value: str) -> None:
        lab = QLabel(value)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._form.addRow(f"{label}:", lab)

    def _sync_geometry_fields(self, rect) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            if hasattr(self, "_geom_x"):
                self._geom_x.setValue(rect.x)
                self._geom_y.setValue(rect.y)
                self._geom_w.setValue(rect.w)
                self._geom_h.setValue(rect.h)
        finally:
            self._updating = False

    def _font_combo(self, current: str):
        """Font box — type a few letters to list matching fonts."""
        from ui.font_picker import FontPicker

        combo = FontPicker()
        combo.set_family(current or "Segoe UI")
        # Warm cache in background for search helpers (no UI cost on every rebuild)
        try:
            cached_font_families()
            _ = recently_used_fonts()
        except Exception:  # noqa: BLE001
            pass
        return combo

    _FIELD_TYPE_LABELS = {
        "text": "Text",
        "multiline": "Text (multi-line)",
        "checkbox": "Checkbox",
        "radio": "Radio button",
        "dropdown": "Drop-down list",
        "date": "Date",
        "signature": "Signature (visual only)",
    }

    def _build_field_editors(self, field) -> None:
        self._updating = True
        ftype = str(getattr(getattr(field, "field_type", None), "value", "") or "")
        multiline = bool(getattr(field, "multiline", False)) or ftype == "multiline"
        type_label = self._FIELD_TYPE_LABELS.get(ftype, ftype.title() or "Field")
        if ftype == "text" and multiline:
            type_label = self._FIELD_TYPE_LABELS["multiline"]
        self._add_ro("Type", type_label)

        tip_name = str(getattr(field, "alternate_name", "") or "").strip()
        raw_name = str(getattr(field, "name", "") or "")
        shown = tip_name or raw_name
        if "topmostSubform" in raw_name or "[" in raw_name:
            shown = tip_name or raw_name.split(".")[-1].split("[")[0] or "(unnamed field)"
        name_label = _ElidedLabel(shown or "—")
        name_label.setToolTip(raw_name if raw_name and raw_name != shown else shown)
        self._form.addRow("Name:", name_label)

        readonly = bool(getattr(field, "readonly", False))
        if readonly or getattr(field, "required", False):
            self._add_ro("Status", "Read-only" if readonly else "Required")

        # Value editor matches the field type
        self._field_value_kind = "line"
        if ftype in ("checkbox", "radio"):
            self._field_value_kind = "check"
            self._field_value = QCheckBox("Selected" if ftype == "radio" else "Checked")
            self._field_value.setChecked(bool(getattr(field, "checked", False)))
            self._field_value.toggled.connect(self._apply_field_value)
        elif ftype == "dropdown" and getattr(field, "options", None):
            self._field_value_kind = "combo"
            self._field_value = QComboBox()
            self._field_value.setEditable(True)
            self._field_value.addItems([str(o) for o in field.options])
            self._field_value.setCurrentText(str(getattr(field, "value", "") or ""))
            self._field_value.currentTextChanged.connect(self._apply_field_value)
        elif multiline:
            self._field_value_kind = "multi"
            self._field_value = _CommitTextEdit()
            self._field_value.setPlainText(str(getattr(field, "value", "") or ""))
            self._field_value.setFixedHeight(84)
            self._field_value.committed.connect(self._apply_field_value)
        else:
            self._field_value = QLineEdit(str(getattr(field, "value", "") or ""))
            self._field_value.setClearButtonEnabled(True)
            self._field_value.editingFinished.connect(self._apply_field_value)
        self._field_value.setEnabled(not readonly and ftype != "signature")
        self._form.addRow("Value:", self._field_value)

        if ftype == "signature":
            hint = "Visual placeholder — use Sign ▸ … to place a visual signature."
        elif readonly:
            hint = "This field is read-only in the PDF."
        elif ftype in ("checkbox", "radio"):
            hint = "Click the box on the page, or press Space when it is selected. Tab moves to the next field."
        else:
            hint = (
                "Click the field to type. Font, size, bold, italic, alignment, color and case are on "
                "the toolbar above the page. Tab / Shift+Tab move between fields."
            )
        tip = QLabel(hint)
        tip.setWordWrap(True)
        tip.setObjectName("ContextHint")
        self._form.addRow(tip)
        self._updating = False

    def sync_field_value(self, field_id: str, text: str) -> None:
        """Mirror live on-page typing into the Value box without rebuilding the panel."""
        if self._field is None or self._field.object_id != field_id or not hasattr(self, "_field_value"):
            return
        kind = getattr(self, "_field_value_kind", "line")
        self._updating = True
        try:
            if kind == "line" and self._field_value.text() != text:
                self._field_value.setText(text)
            elif kind == "multi" and self._field_value.toPlainText() != text:
                self._field_value.setPlainText(text)
            elif kind == "combo" and self._field_value.currentText() != text:
                self._field_value.setCurrentText(text)
        finally:
            self._updating = False

    def _pick_into(self, edit: QLineEdit, btn: QToolButton) -> None:
        c = QColorDialog.getColor(
            QColor(edit.text() or "#000000"),
            self,
            "Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if c.isValid():
            name = c.name(QColor.NameFormat.HexArgb) if c.alpha() < 255 else c.name()
            edit.setText(name)
            set_swatch(btn, name)
            if self._box is not None:
                self._apply()
            elif self._shape is not None:
                self._apply_shape()

    def _apply_field_value(self, *_args) -> None:
        if self._updating or self._edit is None or self._field is None:
            return
        fid = self._field.object_id
        field = self._edit.fields.get(fid)
        if field is None or field.readonly:
            return
        kind = getattr(self, "_field_value_kind", "line")
        if kind == "check":
            if bool(self._field_value.isChecked()) != bool(field.checked):
                self._edit.set_field_value(fid, checked=self._field_value.isChecked())
            return
        if kind == "multi":
            value = self._field_value.toPlainText()
        elif kind == "combo":
            value = self._field_value.currentText()
        else:
            value = self._field_value.text()
        if value != (field.value or ""):
            self._edit.set_field_value(fid, value)

    def _build_textbox_editors(self, box: TextBox) -> None:
        self._updating = True
        self._font = self._font_combo(box.style.font_family)
        self._font.fontPicked.connect(lambda _f: self._apply())
        self._form.addRow("Font:", self._font)

        try:
            from core.editing.font_resolver import resolve_font

            fres = resolve_font(box.style.font_family, box.text or "")
            generic = (box.style.font_family or "").strip().lower() in ("sans-serif", "serif", "monospace")
            if (box.font_substituted or fres.substituted) and not generic:  # a generic name is not a missing font
                note = QLabel(f"Shown with {box.resolved_font or fres.resolved} (font not installed)")
                note.setObjectName("InspectorWarn")
                note.setWordWrap(True)
                self._form.addRow("", note)
        except Exception:  # noqa: BLE001
            pass

        self._size = QDoubleSpinBox()
        self._size.setRange(4, 200)
        self._size.setDecimals(1)
        self._size.setSuffix(" pt")
        self._size.setValue(box.style.font_size)
        self._size.valueChanged.connect(self._apply)
        self._bold = _toggle("B", "Bold", box.style.bold, "setBold")
        self._italic = _toggle("I", "Italic", box.style.italic, "setItalic")
        self._underline = _toggle("U", "Underline", box.style.underline, "setUnderline")
        for t in (self._bold, self._italic, self._underline):
            t.toggled.connect(self._apply)
        self._form.addRow("Size:", self._size)
        self._form.addRow("Style:", _row(self._bold, self._italic, self._underline))

        self._tc = QLineEdit(box.style.text_color)
        btn = _color_btn(self._tc.text(), lambda b: self._pick_into(self._tc, b))
        self._form.addRow("Color:", _color_row(self._tc, btn))

        self._wrap = QCheckBox("Wrap text")
        self._wrap.setToolTip("Long lines continue on the next line inside the box")
        self._wrap.setChecked(bool(getattr(box.style, "wrap", True)))
        self._wrap.toggled.connect(self._apply)
        self._form.addRow("", self._wrap)

        self._section("Paragraph")
        self._align = QComboBox()
        for a in TextAlign:
            self._align.addItem(a.value.replace("_", " ").title(), a.value)
        self._align.setCurrentIndex(max(0, self._align.findData(box.align.value)))
        self._align.currentIndexChanged.connect(self._apply)
        self._form.addRow("Align:", self._align)

        self._valign = QComboBox()
        for a in VAlign:
            self._valign.addItem(a.value.replace("_", " ").title(), a.value)
        self._valign.setCurrentIndex(max(0, self._valign.findData(box.valign.value)))
        self._valign.currentIndexChanged.connect(self._apply)
        self._form.addRow("Vertical:", self._valign)

        self._lead = QDoubleSpinBox()
        self._lead.setRange(0.8, 3.0)
        self._lead.setSingleStep(0.05)
        self._lead.setSuffix(" ×")
        self._lead.setValue(box.style.line_spacing)
        self._lead.valueChanged.connect(self._apply)
        self._form.addRow("Line spacing:", self._lead)

        self._track = QDoubleSpinBox()
        self._track.setRange(-5, 20)
        self._track.setSingleStep(0.5)
        self._track.setSuffix(" pt")
        self._track.setValue(box.style.character_spacing)
        self._track.valueChanged.connect(self._apply)
        self._form.addRow("Letter spacing:", self._track)

        self._section("Box")
        self._add_geometry_editors(box.rect, oid=box.object_id, kind="text")
        self._size_mode = QComboBox()
        self._size_mode_map = {
            "Grow to fit text": SizeMode.AUTO_HEIGHT.value,
            "Size to text": SizeMode.AUTO_SIZE.value,
            "Shrink text to fit": SizeMode.SHRINK_TO_FIT.value,
            "Fixed size": SizeMode.FIXED.value,
        }
        self._size_mode.addItems(list(self._size_mode_map.keys()))
        rev = {v: k for k, v in self._size_mode_map.items()}
        self._size_mode.setCurrentText(rev.get(box.size_mode.value, "Grow to fit text"))
        self._size_mode.setToolTip("How the box reacts when the text gets longer")
        self._size_mode.currentTextChanged.connect(self._apply)
        self._form.addRow("Box sizing:", self._size_mode)

        self._rot = _angle_spin(box.style.rotation)
        self._rot.valueChanged.connect(self._apply)
        self._opacity = _percent_spin(box.style.opacity)
        self._opacity.valueChanged.connect(self._apply)
        self._form.addRow("Rotation:", self._rot)
        self._form.addRow("Opacity:", self._opacity)

        self._pad = QDoubleSpinBox()
        self._pad.setRange(0, 64)
        self._pad.setSuffix(" pt")
        self._pad.setValue(box.style.padding)
        self._pad.valueChanged.connect(self._apply)
        self._form.addRow("Padding:", self._pad)

        self._border = QLineEdit(box.style.border_color)
        bbtn = _color_btn(self._border.text(), lambda b: self._pick_into(self._border, b), compact=True)
        self._bw = QDoubleSpinBox()
        self._bw.setRange(0, 12)
        self._bw.setSingleStep(0.5)
        self._bw.setSuffix(" pt")
        self._bw.setToolTip("Border width (0 = no border)")
        self._bw.setValue(box.style.border_width)
        self._bw.valueChanged.connect(self._apply)
        border_row = _color_row(self._border, bbtn)
        border_row.layout().insertWidget(2, self._bw)
        self._form.addRow("Border:", border_row)

        self._fill = QLineEdit(box.style.background_color)
        fbtn = _color_btn(self._fill.text(), lambda b: self._pick_into(self._fill, b), compact=True)
        fill_row = _color_row(self._fill, fbtn)
        clear_fill = QPushButton("None")
        clear_fill.setToolTip("No background")
        clear_fill.clicked.connect(
            lambda: (self._fill.setText("#00000000"), set_swatch(fbtn, "#00000000"), self._apply())
        )
        fill_row.layout().insertWidget(2, clear_fill)
        self._form.addRow("Background:", fill_row)

        if box.overflow:
            warn = QLabel("The text does not fit in this fixed-size box.")
            warn.setObjectName("InspectorError")
            warn.setWordWrap(True)
            self._form.addRow(warn)
        self._updating = False

    def _add_geometry_editors(self, rect, *, oid: str, kind: str) -> None:
        self._geom_oid = oid
        self._geom_kind = kind

        def spin(prefix: str, value: float, minimum: float) -> QDoubleSpinBox:
            sp = QDoubleSpinBox()
            sp.setRange(minimum, 10000)
            sp.setDecimals(1)
            sp.setPrefix(prefix)
            sp.setValue(value)
            sp.setToolTip({"X ": "Left edge (pt)", "Y ": "Top edge (pt)", "W ": "Width (pt)", "H ": "Height (pt)"}[prefix])
            sp.valueChanged.connect(self._apply_geometry)
            return sp

        self._geom_x = spin("X ", rect.x, -10000)
        self._geom_y = spin("Y ", rect.y, -10000)
        self._geom_w = spin("W ", rect.w, 1)
        self._geom_h = spin("H ", rect.h, 1)
        self._form.addRow("Position:", _row(self._geom_x, self._geom_y, stretch_last=True))
        self._form.addRow("Size:", _row(self._geom_w, self._geom_h, stretch_last=True))

    def _apply_geometry(self, *_args) -> None:
        if self._updating or self._edit is None:
            return
        from core.editing.geometry import Rect

        rect = Rect(
            float(self._geom_x.value()),
            float(self._geom_y.value()),
            float(self._geom_w.value()),
            float(self._geom_h.value()),
        )
        oid = getattr(self, "_geom_oid", None)
        if not oid:
            return
        target = self._edit.objects.get(oid) or self._edit.shapes.get(oid) or self._edit.images.get(oid)
        if target is None:
            return
        before = {oid: Rect(*target.rect.as_tuple())}
        self._edit.set_rect(oid, rect, record_dirty=False)
        self._edit.commit_transform(before, name="Geometry")
        self.styleEdited.emit()

    def _apply(self, *_args) -> None:
        if self._updating or self._edit is None or self._box is None:
            return
        box = self._edit.get(self._box.object_id)
        if box is None:
            return
        style = box.style.copy()
        style.font_family = self._font.family() or style.font_family
        style.font_size = float(self._size.value())
        style.bold = self._bold.isChecked()
        style.italic = self._italic.isChecked()
        style.underline = self._underline.isChecked()
        style.padding = float(self._pad.value())
        style.opacity = float(self._opacity.value()) / 100.0
        style.rotation = float(self._rot.value())
        style.character_spacing = float(self._track.value())
        style.line_spacing = float(self._lead.value())
        style.background_color = self._fill.text().strip() or style.background_color
        style.border_color = self._border.text().strip() or style.border_color
        style.border_width = float(self._bw.value())
        style.text_color = self._tc.text().strip() or style.text_color
        style.wrap = self._wrap.isChecked() if hasattr(self, "_wrap") else True
        mode_label = self._size_mode.currentText()
        mode_val = getattr(self, "_size_mode_map", {}).get(mode_label, mode_label)
        remember_font(style.font_family)
        self._edit.change_style(
            box.object_id,
            style=style,
            align=TextAlign(self._align.currentData() or self._align.currentText()),
            valign=VAlign(self._valign.currentData() or self._valign.currentText()),
            size_mode=SizeMode(mode_val),
        )
        # Keep context key so we don't rebuild and steal focus
        self.styleEdited.emit()

    def _build_shape_editors(self, shape) -> None:
        self._updating = True
        self._add_ro("Type", str(getattr(shape.kind, "value", shape.kind)).replace("_", " ").title())
        self._shape_stroke = QLineEdit(shape.stroke_color)
        sbtn = _color_btn(shape.stroke_color, lambda b: self._pick_into(self._shape_stroke, b), compact=True)
        self._shape_sw = QDoubleSpinBox()
        self._shape_sw.setRange(0.25, 24)
        self._shape_sw.setSingleStep(0.5)
        self._shape_sw.setSuffix(" pt")
        self._shape_sw.setToolTip("Line width")
        self._shape_sw.setValue(shape.stroke_width)
        self._shape_sw.valueChanged.connect(self._apply_shape)
        line_row = _color_row(self._shape_stroke, sbtn)
        line_row.layout().insertWidget(2, self._shape_sw)
        self._form.addRow("Line:", line_row)

        self._shape_ss = QComboBox()
        for label, value in (("Solid", "solid"), ("Dashed", "dashed"), ("Dotted", "dotted")):
            self._shape_ss.addItem(label, value)
        self._shape_ss.setCurrentIndex(max(0, self._shape_ss.findData(getattr(shape.stroke_style, "value", "solid"))))
        self._shape_ss.currentIndexChanged.connect(self._apply_shape)
        self._form.addRow("Line style:", self._shape_ss)

        self._shape_fill = QLineEdit(shape.fill_color)
        fill_btn = _color_btn(shape.fill_color, lambda b: self._pick_into(self._shape_fill, b), compact=True)
        wrap = _color_row(self._shape_fill, fill_btn)
        none_btn = QPushButton("None")
        none_btn.setToolTip("No fill (transparent)")
        none_btn.clicked.connect(
            lambda: (self._shape_fill.setText("#00000000"), set_swatch(fill_btn, "#00000000"), self._apply_shape())
        )
        wrap.layout().insertWidget(2, none_btn)
        self._shape_fo = _percent_spin(shape.fill_opacity, minimum=0)
        self._shape_fo.setToolTip("Fill opacity")
        self._shape_fo.valueChanged.connect(self._apply_shape)
        wrap.layout().insertWidget(3, self._shape_fo)
        self._form.addRow("Fill:", wrap)

        self._section("Position")
        self._add_geometry_editors(shape.rect, oid=shape.object_id, kind="shape")
        self._shape_rot = _angle_spin(shape.rotation)
        self._shape_rot.valueChanged.connect(self._apply_shape)
        self._form.addRow("Rotation:", self._shape_rot)
        self._shape_op = _percent_spin(shape.opacity)
        self._shape_op.valueChanged.connect(self._apply_shape)
        self._form.addRow("Opacity:", self._shape_op)

        self._shape_lock = QCheckBox("Lock aspect ratio")
        self._shape_lock.setChecked(bool(shape.lock_aspect))
        self._shape_lock.toggled.connect(self._apply_shape)
        self._form.addRow(self._shape_lock)

        tip = QLabel("Hold Shift while drawing for a square, circle or straight line.")
        tip.setWordWrap(True)
        tip.setObjectName("ContextHint")
        self._form.addRow(tip)
        self._updating = False

    def _apply_shape(self, *_args) -> None:
        if self._updating or self._edit is None or self._shape is None:
            return
        from core.editing.shape_box import StrokeStyle

        sid = self._shape.object_id
        self._edit.update_shape(
            sid,
            stroke_color=self._shape_stroke.text().strip() or "#2563eb",
            stroke_width=float(self._shape_sw.value()),
            stroke_style=StrokeStyle(self._shape_ss.currentData() or "solid"),
            fill_color=self._shape_fill.text().strip() or "#00000000",
            fill_opacity=float(self._shape_fo.value()) / 100.0,
            opacity=float(self._shape_op.value()) / 100.0,
            rotation=float(self._shape_rot.value()),
            lock_aspect=self._shape_lock.isChecked(),
        )
        self.styleEdited.emit()

    def _build_image_editors(self, image) -> None:
        self._updating = True
        if getattr(image, "role", "") == "signature":
            note = QLabel("Visual signature: a picture of a signature. It is not a certificate-based "
                          "digital signature and does not prove who signed.")
            note.setWordWrap(True)
            note.setObjectName("ContextHint")
            self._form.addRow(note)
        else:
            self._add_ro("Source", _path_name(str(getattr(image, "source_path", "") or "")))
        self._section("Position")
        self._add_geometry_editors(image.rect, oid=image.object_id, kind="image")
        self._img_rot = _angle_spin(float(getattr(image, "rotation", 0.0)))
        self._img_rot.valueChanged.connect(self._apply_image)
        self._form.addRow("Rotation:", self._img_rot)
        self._img_op = _percent_spin(float(getattr(image, "opacity", 1.0)))
        self._img_op.valueChanged.connect(self._apply_image)
        self._form.addRow("Opacity:", self._img_op)

        self._img_lock = QCheckBox("Lock aspect ratio")
        self._img_lock.setChecked(bool(getattr(image, "lock_aspect", False)))
        self._img_lock.toggled.connect(self._apply_image)
        self._form.addRow(self._img_lock)

        tip = QLabel("Replace or save the image from Edit ▸ Selected Image or the toolbar.")
        tip.setWordWrap(True)
        tip.setObjectName("ContextHint")
        self._form.addRow(tip)
        self._updating = False

    def _apply_image(self, *_args) -> None:
        if self._updating or self._edit is None or self._image is None:
            return
        oid = self._image.object_id
        img = self._edit.images.get(oid)
        if img is None:
            return
        self._edit.set_overlay_attrs(  # undoable
            oid,
            opacity=float(self._img_op.value()) / 100.0,
            rotation=float(self._img_rot.value()),
            lock_aspect=self._img_lock.isChecked(),
        )
        self.styleEdited.emit()
