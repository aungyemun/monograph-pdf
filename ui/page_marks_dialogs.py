"""Dialogs for headers/footers, watermarks, backgrounds and removing them (Insert ▸ Page design).

Every dialog shows a live preview of the current page drawn by the same code that writes the
file (``core.convert.page_marks.render_preview``), restores the settings used last time, and
writes to a new PDF — the open document is not changed.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QToolButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.convert.page_marks import (
    ALL_KINDS,
    KIND_BACKGROUND,
    KIND_HEADER_FOOTER,
    KIND_WATERMARK,
    BackgroundSpec,
    HeaderFooterSpec,
    WatermarkSpec,
    count_marks,
    render_preview,
)

IMAGE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)"
PREVIEW_W, PREVIEW_H = 360, 470  # large enough to read header / footer text without zooming
ZOOMS = (("Fit page", "page"), ("Fit width", "width"), ("100 %", 1.0), ("150 %", 1.5), ("200 %", 2.0),
         ("300 %", 3.0), ("400 %", 4.0))
MAX_DPI = 400.0


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogHint")
    lab.setWordWrap(True)
    return lab


def _percent_box(value: int) -> QSpinBox:
    """5–100 % spin box wide enough for "100 %" at any display scale."""
    box = QSpinBox()
    box.setRange(5, 100)
    box.setValue(value)
    box.setSuffix(" %")
    box.setMinimumWidth(box.fontMetrics().horizontalAdvance("100 %") + 44)
    return box


def _ok_cancel(dialog: QDialog, ok_text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def _load_presets() -> dict:
    try:
        from core.user_prefs import UserPreferences

        return dict(UserPreferences.load().page_mark_presets or {})
    except Exception:  # noqa: BLE001 — presets are a convenience only
        return {}


def _save_preset(name: str, values: dict) -> None:
    try:
        from core.user_prefs import UserPreferences

        prefs = UserPreferences.load()
        data = dict(prefs.page_mark_presets or {})
        data[name] = values
        prefs.page_mark_presets = data
        prefs.save()
    except Exception:  # noqa: BLE001
        pass


class ColorButton(QPushButton):
    """Shows the chosen colour; a click offers curated colours (``palette``: "ink" for text and
    watermarks, "paper" for backgrounds) and "More colors…" for any other.

    The button's style is scoped to itself and the full picker is parented to the dialog: an
    unscoped ``background:`` style used to spread into the colour picker it opened, tinting the
    whole picker grey (watermark) or cream (background)."""

    def __init__(self, color: str, title: str, parent=None, *, palette: str = "ink") -> None:
        super().__init__(parent)
        from ui.color_swatches import INK_COLORS, PAPER_COLORS, SwatchMenu

        self._color = QColor(color)
        self._title = title
        self.setObjectName("PageMarkColorButton")
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance("#MMMMMM") + 28)
        self.setToolTip(f"{title} — choose a color")
        self.setAccessibleName(title)
        colors = PAPER_COLORS + INK_COLORS if palette == "paper" else INK_COLORS + PAPER_COLORS[:6]
        self._menu = SwatchMenu(colors, self.set_name, title=title, current=self.name, parent=self)
        self.setMenu(self._menu)
        self._sync()
        self.on_change = None

    def _sync(self) -> None:
        c = self._color
        text = "#ffffff" if c.lightness() < 128 else "#111827"
        self.setText(c.name().upper())
        self.setStyleSheet(
            f"QPushButton#PageMarkColorButton {{ background:{c.name()}; color:{text}; border:1px solid #9aa3af;"
            " border-radius: 4px; padding: 4px 10px; }"
        )

    def _pick(self) -> None:
        from ui.color_swatches import pick_color_dialog

        chosen = pick_color_dialog(self, self._color.name(), self._title)
        if chosen:
            self.set_name(chosen)

    def set_name(self, name: str) -> None:
        c = QColor(name)
        if c.isValid():
            self._color = c
            self._sync()
            if self.on_change:
                self.on_change()

    def name(self) -> str:
        return self._color.name()

    def rgb(self) -> tuple[float, float, float]:
        return (self._color.redF(), self._color.greenF(), self._color.blueF())


class PageScope(QWidget):
    """All pages / current page / custom range (1-based, e.g. 1-3,5)."""

    def __init__(self, page_count: int = 0, current: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._count = page_count
        self._current = current
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem("All pages", "all")
        self.combo.addItem("Current page", "current")
        self.combo.addItem("Page range…", "range")
        self.range = QLineEdit()
        self.range.setPlaceholderText("e.g. 1-3, 5")
        self.range.setEnabled(False)
        self.combo.currentIndexChanged.connect(lambda: self.range.setEnabled(self.combo.currentData() == "range"))
        row.addWidget(self.combo)
        row.addWidget(self.range, 1)

    def pages(self) -> list[int] | None:
        mode = self.combo.currentData()
        if mode == "current":
            return [self._current]
        if mode == "range" and self.range.text().strip() and self._count:
            from core.organize.page_ops import parse_page_ranges

            return parse_page_ranges(self.range.text().strip(), self._count)
        return None


def _fitz_doc(source):
    return source if hasattr(source, "load_page") else source._backend._doc  # noqa: SLF001


class PreviewView(QWidget):
    """Page preview with the marks as they will be written: zoom (fit page, fit width, 100–400 %,
    Ctrl + mouse wheel), scrolling when zoomed, and Previous / Next page. The page is rendered again
    at the chosen zoom, so text stays sharp instead of being enlarged pixels."""

    def __init__(self, source, page_index: int, parent=None, *, size: tuple[int, int] = (PREVIEW_W, PREVIEW_H)) -> None:
        super().__init__(parent)
        self._source = source
        self._page = page_index
        self._kwargs: dict = {}
        self.error = ""
        self._zoom: object = "page"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("MarksPreview")
        self.scroll.setStyleSheet("#MarksPreview { border: 1px solid #9aa3af; background: #6b7280; }")
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidgetResizable(False)
        self.scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.scroll.setMinimumSize(*size)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent; color: #ffffff;")
        self._label.setAccessibleName("Page preview")
        self.scroll.setWidget(self._label)
        self.scroll.viewport().installEventFilter(self)
        lay.addWidget(self.scroll, 1)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.prev_btn = QToolButton()
        self.prev_btn.setText("◀")
        self.prev_btn.setToolTip("Previous page")
        self.prev_btn.setAccessibleName("Previous page")
        self.next_btn = QToolButton()
        self.next_btn.setText("▶")
        self.next_btn.setToolTip("Next page")
        self.next_btn.setAccessibleName("Next page")
        self.page_label = QLabel()
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("−")
        self.zoom_out_btn.setToolTip("Zoom out")
        self.zoom_out_btn.setAccessibleName("Zoom out")
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("+")
        self.zoom_in_btn.setToolTip("Zoom in (or Ctrl + mouse wheel)")
        self.zoom_in_btn.setAccessibleName("Zoom in")
        self.zoom_box = QComboBox()
        self.zoom_box.setAccessibleName("Preview zoom")
        for label, value in ZOOMS:
            self.zoom_box.addItem(label, value)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.page_label)
        bar.addWidget(self.next_btn)
        bar.addStretch(1)
        bar.addWidget(self.zoom_out_btn)
        bar.addWidget(self.zoom_box)
        bar.addWidget(self.zoom_in_btn)
        lay.addLayout(bar)
        self.prev_btn.clicked.connect(lambda: self.set_page(self._page - 1))
        self.next_btn.clicked.connect(lambda: self.set_page(self._page + 1))
        self.zoom_box.currentIndexChanged.connect(lambda *_: self._zoom_changed())
        self.zoom_in_btn.clicked.connect(lambda: self.step_zoom(+1))
        self.zoom_out_btn.clicked.connect(lambda: self.step_zoom(-1))

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._render)
        self._sync_nav()

    # --- compatibility with a plain label -----------------------------------------------------
    def pixmap(self) -> QPixmap:
        return self._label.pixmap()

    def setText(self, text: str) -> None:  # noqa: N802
        self._label.setPixmap(QPixmap())
        self._label.setText(text)
        self._label.adjustSize()

    # --- state ----------------------------------------------------------------------------------
    def page_count(self) -> int:
        try:
            return int(_fitz_doc(self._source).page_count) if self._source is not None else 0
        except Exception:  # noqa: BLE001
            return 0

    def page(self) -> int:
        return self._page

    def set_page(self, index: int) -> None:
        n = self.page_count()
        if n <= 0:
            return
        index = max(0, min(int(index), n - 1))
        if index != self._page:
            self._page = index
            self._sync_nav()
            self.render_now()

    def set_zoom(self, value) -> None:
        idx = self.zoom_box.findData(value)
        if idx >= 0:
            self.zoom_box.setCurrentIndex(idx)

    def step_zoom(self, step: int) -> None:
        i = max(0, min(self.zoom_box.count() - 1, self.zoom_box.currentIndex() + step))
        if i < 2 and step > 0:  # from a "fit" choice, zooming in goes to the first percentage
            i = 2
        self.zoom_box.setCurrentIndex(i)

    def _zoom_changed(self) -> None:
        self._zoom = self.zoom_box.currentData()
        self.render_now()

    def _sync_nav(self) -> None:
        n = self.page_count()
        self.page_label.setText(f"Page {self._page + 1} of {n}" if n else "")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < n - 1)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if obj is self.scroll.viewport():
            if event.type() == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.step_zoom(+1 if event.angleDelta().y() > 0 else -1)
                return True
            if event.type() == QEvent.Type.Resize and isinstance(self._zoom, str):
                self._timer.start()
        return super().eventFilter(obj, event)

    # --- rendering ------------------------------------------------------------------------------
    def request(self, **kwargs) -> None:
        self._kwargs = kwargs
        if self._source is None:
            self.setText("No preview")
            return
        self._timer.start()

    def render_now(self) -> None:
        self._timer.stop()
        self._render()

    def _dpi(self, w: float, h: float) -> float:
        vp = self.scroll.viewport().size()
        avail_w = max(80, vp.width() - 12)
        avail_h = max(80, vp.height() - 12)
        if self._zoom == "page":
            dpi = 72.0 * min(avail_w / w, avail_h / h)
        elif self._zoom == "width":
            dpi = 72.0 * avail_w / w
        else:
            dpi = 72.0 * float(self._zoom)
        return dpi

    def _render(self) -> None:
        if self._source is None:
            return
        try:
            src = self._source
            page = _fitz_doc(src).load_page(self._page)
            w, h = page.rect.width, page.rect.height
            dpi = max(4.0, self._dpi(w, h))
            ratio = max(1.0, float(self.devicePixelRatioF()))
            rendered = min(MAX_DPI, dpi * ratio)
            pix = render_preview(src, self._page, dpi=rendered, **self._kwargs)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(rendered / dpi)  # shown at the zoom's size; sharp on high-DPI screens
            self._label.setText("")
            self._label.setWordWrap(False)
            self._label.setMinimumWidth(0)
            self._label.setMaximumWidth(16777215)  # undo the width set for an earlier error message
            self._label.setPixmap(pm)
            self._label.adjustSize()
            self.error = ""
            self._label.setToolTip(f"Preview of page {self._page + 1} — Ctrl + mouse wheel zooms")
        except Exception as exc:  # noqa: BLE001 — e.g. an unreadable picture: say so, keep the dialog usable
            self.error = str(exc)
            self._label.setWordWrap(True)
            self._label.setFixedWidth(max(160, self.scroll.viewport().width() - 16))
            self.setText("Preview unavailable:\n" + str(exc)[:120])


class MarksPreview(PreviewView):
    """The preview in each page-design dialog, with a button for a large, resizable preview window."""

    def __init__(self, source, page_index: int, parent=None) -> None:
        super().__init__(source, page_index, parent)
        self.large_btn = QPushButton("Larger Preview…")
        self.large_btn.setToolTip("Open the preview in a large window you can resize or maximise")
        self.large_btn.clicked.connect(self.open_large)
        self.layout().addWidget(self.large_btn)
        self.large_btn.setEnabled(source is not None)
        self._large: QDialog | None = None

    def request(self, **kwargs) -> None:
        super().request(**kwargs)
        if self._large is not None and self._large.isVisible():
            self._large.view.request(**kwargs)

    def open_large(self) -> None:
        if self._source is None:
            return
        if self._large is None:
            dlg = QDialog(self.window())
            dlg.setWindowTitle("Preview")
            dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
            lay = QVBoxLayout(dlg)
            dlg.view = PreviewView(self._source, self._page, dlg, size=(560, 700))
            lay.addWidget(dlg.view, 1)
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.rejected.connect(dlg.close)
            lay.addWidget(close)
            dlg.resize(760, 920)
            self._large = dlg
        view = self._large.view
        view.set_page(self._page)
        view._kwargs = dict(self._kwargs)  # noqa: SLF001
        self._large.show()
        self._large.raise_()
        view.render_now()


class _MarksDialog(QDialog):
    PRESET = ""

    def __init__(self, parent, title: str, heading: str, *, page_count: int, current_page: int, source) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.addWidget(_title(heading))
        body = QHBoxLayout()
        self.form = QFormLayout()
        self.form.setVerticalSpacing(8)
        left = QWidget()
        left.setLayout(self.form)
        body.addWidget(left, 1)
        self.preview = MarksPreview(source, current_page if source is not None else 0)
        side = QVBoxLayout()
        side.addWidget(self.preview)
        side.addStretch(1)
        body.addLayout(side)
        outer.addLayout(body)
        self.scope = PageScope(page_count, current_page)
        self.replace = QCheckBox("Replace the one added earlier by Monograph PDF")
        self.replace.setChecked(True)
        self.replace.setToolTip("Marks added by other programs cannot be recognised and are kept.")
        self._outer = outer

    def _finish(self, ok_text: str = "Save As…") -> None:
        self.form.addRow("Pages:", self.scope)
        self.form.addRow("", self.replace)
        self._outer.addWidget(_hint("Written to a new PDF — the open document is not changed."))
        self.buttons = _ok_cancel(self, ok_text)
        self._outer.addWidget(self.buttons)
        self._restore(_load_presets().get(self.PRESET, {}))
        self.refresh()
        self.preview.render_now()

    # subclasses
    def kwargs(self) -> dict:
        raise NotImplementedError

    def values(self) -> dict:
        return {}

    def _restore(self, values: dict) -> None:
        pass

    def refresh(self) -> None:
        try:
            kw = self.kwargs()
        except Exception:  # noqa: BLE001
            kw = {}
        self.preview.request(**kw)
        if not hasattr(self, "buttons"):
            return
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self._has_content())

    def _has_content(self) -> bool:
        return True

    def accept(self) -> None:
        _save_preset(self.PRESET, self.values())
        super().accept()

    def _watch(self, *widgets) -> None:
        for w in widgets:
            for sig in ("textChanged", "valueChanged", "currentIndexChanged", "toggled"):
                s = getattr(w, sig, None)
                if s is not None:
                    try:
                        s.connect(lambda *_a: self.refresh())
                    except (RuntimeError, TypeError):
                        pass


def _start_dir(dialog) -> str:
    """Folder of the open document (the main window's choice), so pickers do not start in the
    program folder."""
    fn = getattr(dialog.parent(), "_doc_dir", None)
    try:
        return str(fn()) if callable(fn) else ""
    except Exception:  # noqa: BLE001
        return ""


class HeaderFooterDialog(_MarksDialog):
    PRESET = "header_footer"
    NUMBER_FORMATS = (
        ("1 / 12", "{page} / {total}"),
        ("Page 1 of 12", "Page {page} of {total}"),
        ("1", "{page}"),
        ("- 1 -", "- {page} -"),
    )
    NUMBER_PLACES = (("Bottom right", "footer_right"), ("Bottom center", "footer_center"),
                     ("Bottom left", "footer_left"), ("Top right", "header_right"),
                     ("Top center", "header_center"), ("Top left", "header_left"))
    DATE_FORMATS = (("2026-10-20", "%Y-%m-%d"), ("20/10/2026", "%d/%m/%Y"), ("10/20/2026", "%m/%d/%Y"),
                    ("20 October 2026", "%d %B %Y"), ("2026年10月20日", "%Y年%m月%d日"))

    def __init__(self, parent=None, *, page_count: int = 0, current_page: int = 0, source=None) -> None:
        super().__init__(parent, "Header, Footer & Page Numbers", "Header, footer & page numbers",
                         page_count=page_count, current_page=current_page, source=source)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        for c, name in enumerate(("Left", "Center", "Right")):
            grid.addWidget(QLabel(name), 0, c + 1)
        self.slots: dict[str, QLineEdit] = {}
        for r, where in enumerate(("header", "footer")):
            grid.addWidget(QLabel(where.capitalize() + ":"), r + 1, 0)
            for c, align in enumerate(("left", "center", "right")):
                e = QLineEdit()
                e.setMinimumWidth(120)
                e.setPlaceholderText("—")
                self.slots[f"{where}_{align}"] = e
                grid.addWidget(e, r + 1, c + 1)
        box = QWidget()
        box.setLayout(grid)
        self.form.addRow(box)
        # Compatibility names used by the UI audit harness
        self.header = self.slots["header_left"]
        self.footer = self.slots["footer_left"]
        self.form.addRow("", _hint("{page}, {total}, {date} and {bates} are replaced on each page."))
        self.page_numbers = QCheckBox("Add page numbers")
        self.page_numbers.setChecked(True)
        self.number_format = QComboBox()
        for label, fmt in self.NUMBER_FORMATS:
            self.number_format.addItem(label, fmt)
        self.number_place = QComboBox()
        for label, slot in self.NUMBER_PLACES:
            self.number_place.addItem(label, slot)
        nrow = QHBoxLayout()
        nrow.addWidget(self.page_numbers)
        nrow.addWidget(self.number_format)
        nrow.addWidget(self.number_place)
        self.page_numbers.toggled.connect(self.number_format.setEnabled)
        self.page_numbers.toggled.connect(self.number_place.setEnabled)
        self.form.addRow("Numbers:", nrow)
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 99999)
        self.start_number.setValue(1)
        self.form.addRow("First page is number:", self.start_number)
        # Bates numbering: a fixed-width identifier on every page (legal / records work)
        self.bates = QCheckBox("Add Bates number")
        self.bates.setToolTip("A fixed-width page identifier such as CASE-000001, counted through the document")
        self.bates_place = QComboBox()
        for label, slot in self.NUMBER_PLACES:
            self.bates_place.addItem(label, slot)
        self.bates_place.setCurrentIndex(2)  # bottom left: page numbers default to bottom right
        brow = QHBoxLayout()
        brow.addWidget(self.bates)
        brow.addWidget(self.bates_place)
        brow.addStretch(1)
        self.form.addRow("Bates:", brow)
        self.bates_prefix = QLineEdit()
        self.bates_prefix.setPlaceholderText("Prefix")
        self.bates_prefix.setMaxLength(40)
        self.bates_suffix = QLineEdit()
        self.bates_suffix.setPlaceholderText("Suffix")
        self.bates_suffix.setMaxLength(40)
        self.bates_start = QSpinBox()
        self.bates_start.setRange(0, 999_999_999)
        self.bates_start.setValue(1)
        self.bates_start.setToolTip("Number of the first page")
        self.bates_digits = QSpinBox()
        self.bates_digits.setRange(1, 12)
        self.bates_digits.setValue(6)
        self.bates_digits.setToolTip("Number of digits (the number is padded with zeros)")
        self.bates_prefix.setToolTip("Text before the number, e.g. CASE-")
        self.bates_suffix.setToolTip("Text after the number")
        for w, width in ((self.bates_prefix, 80), (self.bates_start, 80), (self.bates_digits, 48),
                         (self.bates_suffix, 64)):
            w.setMinimumWidth(width)
        self.bates_prefix.setAccessibleName("Bates prefix")
        self.bates_start.setAccessibleName("Bates first number")
        self.bates_digits.setAccessibleName("Bates number of digits")
        self.bates_suffix.setAccessibleName("Bates suffix")
        b2 = QHBoxLayout()
        b2.setContentsMargins(0, 0, 0, 0)
        for w, stretch in ((self.bates_prefix, 2), (self.bates_start, 2), (self.bates_digits, 1), (self.bates_suffix, 2)):
            b2.addWidget(w, stretch)
        self._bates_row = QWidget()
        self._bates_row.setLayout(b2)
        self.form.addRow("", self._bates_row)
        self._bates_hint = _hint("Prefix · first number · digits · suffix — for example CASE-000001")
        self.form.addRow("", self._bates_hint)
        for w in (self.bates_place, self._bates_row, self._bates_hint):
            w.setEnabled(False)
            self.bates.toggled.connect(w.setEnabled)
        self.date_format = QComboBox()
        for label, fmt in self.DATE_FORMATS:
            self.date_format.addItem(label, fmt)
        self.form.addRow("Date style:", self.date_format)
        frow = QHBoxLayout()
        self.fontsize = QSpinBox()
        self.fontsize.setRange(6, 72)
        self.fontsize.setValue(9)
        self.fontsize.setSuffix(" pt")
        self.color = ColorButton("#333333", "Text color")
        self.color.on_change = self.refresh
        frow.addWidget(self.fontsize)
        frow.addWidget(self.color)
        frow.addStretch(1)
        self.form.addRow("Text:", frow)
        mrow = QHBoxLayout()
        self.margin_top, self.margin_bottom, self.margin_side = (self._margin(36), self._margin(22), self._margin(36))
        for i, (lab, w) in enumerate((("Top", self.margin_top), ("Bottom", self.margin_bottom), ("Sides", self.margin_side))):
            if i:
                mrow.addSpacing(12)  # keep each label with its own box ("36  Bottom", not "36Bottom")
            mrow.addWidget(QLabel(lab))
            mrow.addWidget(w)
        mrow.addStretch(1)
        self.form.addRow("Margins:", mrow)
        self._watch(*self.slots.values(), self.page_numbers, self.number_format, self.number_place,
                    self.start_number, self.bates, self.bates_place, self.bates_prefix, self.bates_suffix,
                    self.bates_start, self.bates_digits, self.date_format, self.fontsize, self.margin_top, self.margin_bottom,
                    self.margin_side)
        self._finish()

    @staticmethod
    def _margin(value: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0, 300)
        s.setDecimals(0)
        s.setValue(value)
        s.setSuffix(" pt")
        return s

    def spec(self) -> HeaderFooterSpec:
        texts = {k: e.text() for k, e in self.slots.items()}
        if self.page_numbers.isChecked():
            slot = str(self.number_place.currentData())
            fmt = str(self.number_format.currentData())
            texts[slot] = f"{texts[slot]}  {fmt}".strip() if texts[slot].strip() else fmt
        if self.bates.isChecked():
            slot = str(self.bates_place.currentData())
            texts[slot] = f"{texts[slot]}  {{bates}}".strip() if texts[slot].strip() else "{bates}"
        return HeaderFooterSpec(**texts, font_size=float(self.fontsize.value()), color=self.color.rgb(),
                                margin_top=self.margin_top.value(), margin_bottom=self.margin_bottom.value(),
                                margin_left=self.margin_side.value(), margin_right=self.margin_side.value(),
                                start_number=self.start_number.value(),
                                date_format=str(self.date_format.currentData()),
                                bates_prefix=self.bates_prefix.text(), bates_suffix=self.bates_suffix.text(),
                                bates_start=self.bates_start.value(), bates_digits=self.bates_digits.value())

    def kwargs(self) -> dict:
        return {"header_footer": self.spec()}

    def _has_content(self) -> bool:
        return not self.spec().is_empty()

    def values(self) -> dict:
        return {"slots": {k: e.text() for k, e in self.slots.items()}, "numbers": self.page_numbers.isChecked(),
                "number_format": self.number_format.currentIndex(), "number_place": self.number_place.currentIndex(),
                "date_format": self.date_format.currentIndex(), "font_size": self.fontsize.value(),
                "color": self.color.name(), "margins": [self.margin_top.value(), self.margin_bottom.value(),
                                                        self.margin_side.value()],
                "bates": {"on": self.bates.isChecked(), "place": self.bates_place.currentIndex(),
                          "prefix": self.bates_prefix.text(), "suffix": self.bates_suffix.text(),
                          "digits": self.bates_digits.value()}}

    def _restore(self, v: dict) -> None:
        for k, t in (v.get("slots") or {}).items():
            if k in self.slots and isinstance(t, str):
                self.slots[k].setText(t)
        if "numbers" in v:
            self.page_numbers.setChecked(bool(v["numbers"]))
        for combo, key in ((self.number_format, "number_format"), (self.number_place, "number_place"),
                           (self.date_format, "date_format")):
            if isinstance(v.get(key), int) and 0 <= v[key] < combo.count():
                combo.setCurrentIndex(v[key])
        if isinstance(v.get("font_size"), int):
            self.fontsize.setValue(v["font_size"])
        if isinstance(v.get("color"), str):
            self.color.set_name(v["color"])
        m = v.get("margins")
        if isinstance(m, list) and len(m) == 3:
            for w, val in zip((self.margin_top, self.margin_bottom, self.margin_side), m):
                w.setValue(float(val))
        b = v.get("bates")
        if isinstance(b, dict):
            self.bates.setChecked(bool(b.get("on")))
            if isinstance(b.get("place"), int) and 0 <= b["place"] < self.bates_place.count():
                self.bates_place.setCurrentIndex(b["place"])
            for w, key in ((self.bates_prefix, "prefix"), (self.bates_suffix, "suffix")):
                if isinstance(b.get(key), str):
                    w.setText(b[key][:40])
            if isinstance(b.get("digits"), int):
                self.bates_digits.setValue(b["digits"])


class WatermarkDialog(_MarksDialog):
    PRESET = "watermark"
    ANGLES = (("Diagonal (45°)", 45), ("Horizontal", 0), ("Vertical (90°)", 90), ("Diagonal (−45°)", -45))

    def __init__(self, parent=None, *, page_count: int = 0, current_page: int = 0, source=None) -> None:
        super().__init__(parent, "Watermark", "Add a watermark", page_count=page_count,
                         current_page=current_page, source=source)
        src_row = QHBoxLayout()
        self.use_text = QRadioButton("Text")
        self.use_image = QRadioButton("Picture")
        self.use_text.setChecked(True)
        src_row.addWidget(self.use_text)
        src_row.addWidget(self.use_image)
        src_row.addStretch(1)
        self.form.addRow("Source:", src_row)
        self.text = QLineEdit("CONFIDENTIAL")
        self.form.addRow("Text:", self.text)
        trow = QHBoxLayout()
        self.fontsize = QSpinBox()
        self.fontsize.setRange(8, 200)
        self.fontsize.setValue(48)
        self.fontsize.setSuffix(" pt")
        self.color_btn = ColorButton("#8c8c8c", "Watermark color")
        self.color_btn.on_change = self.refresh
        trow.addWidget(self.fontsize)
        trow.addWidget(self.color_btn)
        trow.addStretch(1)
        self.form.addRow("Size / color:", trow)
        prow = QHBoxLayout()
        self.image_path = QLineEdit()
        self.image_path.setPlaceholderText("Choose a picture…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        prow.addWidget(self.image_path, 1)
        prow.addWidget(browse)
        self.form.addRow("Picture:", prow)
        self.image_scale = QSpinBox()
        self.image_scale.setRange(5, 100)
        self.image_scale.setValue(50)
        self.image_scale.setSuffix(" % of page width")
        self.form.addRow("Picture size:", self.image_scale)
        self.rotation = QComboBox()
        for label, deg in self.ANGLES:
            self.rotation.addItem(label, deg)
        self.form.addRow("Orientation:", self.rotation)
        self.position = QComboBox()
        for label, key in (("Center", "center"), ("Top", "top"), ("Bottom", "bottom")):
            self.position.addItem(label, key)
        self.form.addRow("Position:", self.position)
        self.layer = QComboBox()
        self.layer.addItem("In front of the page content", False)
        self.layer.addItem("Behind the page content", True)
        self.layer.setToolTip("Behind: hidden where the page has an opaque background (for example a scan).")
        self.form.addRow("Placement:", self.layer)
        op_row = QHBoxLayout()
        self.opacity = _percent_box(25)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(5, 100)
        slider.setValue(25)
        slider.valueChanged.connect(self.opacity.setValue)
        self.opacity.valueChanged.connect(slider.setValue)
        op_row.addWidget(slider, 1)
        op_row.addWidget(self.opacity)
        self.form.addRow("Opacity:", op_row)
        self.use_text.toggled.connect(self._sync_source)
        self._watch(self.use_text, self.text, self.fontsize, self.image_path, self.image_scale, self.rotation,
                    self.position, self.layer, self.opacity)
        self._finish()
        self._sync_source()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose watermark picture", _start_dir(self), IMAGE_FILTER)
        if path:
            self.image_path.setText(path)
            self.use_image.setChecked(True)

    def _sync_source(self) -> None:
        text = self.use_text.isChecked()
        for w in (self.text, self.fontsize, self.color_btn):
            w.setEnabled(text)
        for w in (self.image_path, self.image_scale):
            w.setEnabled(not text)
        self.refresh()

    def color_rgb(self) -> tuple[float, float, float]:
        return self.color_btn.rgb()

    def spec(self) -> WatermarkSpec:
        img = self.image_path.text().strip()
        return WatermarkSpec(
            text=self.text.text() if self.use_text.isChecked() else "",
            image_path=Path(img) if (self.use_image.isChecked() and img) else None,
            font_size=float(self.fontsize.value()), color=self.color_rgb(), opacity=self.opacity.value() / 100.0,
            rotation=float(self.rotation.currentData()), image_scale=self.image_scale.value() / 100.0,
            position=str(self.position.currentData()), behind=bool(self.layer.currentData()),
        )

    def kwargs(self) -> dict:
        return {"watermark": self.spec()}

    def _has_content(self) -> bool:
        s = self.spec()
        if s.image_path is not None:
            return s.image_path.is_file() and not self.preview.error
        return bool(s.text.strip())

    def values(self) -> dict:
        return {"text": self.text.text(), "picture": self.use_image.isChecked(), "image": self.image_path.text(),
                "font_size": self.fontsize.value(), "color": self.color_btn.name(),
                "scale": self.image_scale.value(), "rotation": self.rotation.currentIndex(),
                "position": self.position.currentIndex(), "behind": self.layer.currentIndex(),
                "opacity": self.opacity.value()}

    def _restore(self, v: dict) -> None:
        if isinstance(v.get("text"), str) and v["text"].strip():
            self.text.setText(v["text"])
        if isinstance(v.get("image"), str):
            self.image_path.setText(v["image"])
        if v.get("picture") and Path(str(v.get("image") or "")).is_file():
            self.use_image.setChecked(True)
        for spin, key in ((self.fontsize, "font_size"), (self.image_scale, "scale"), (self.opacity, "opacity")):
            if isinstance(v.get(key), int):
                spin.setValue(v[key])
        for combo, key in ((self.rotation, "rotation"), (self.position, "position"), (self.layer, "behind")):
            if isinstance(v.get(key), int) and 0 <= v[key] < combo.count():
                combo.setCurrentIndex(v[key])
        if isinstance(v.get("color"), str):
            self.color_btn.set_name(v["color"])


class BackgroundDialog(_MarksDialog):
    PRESET = "background"

    def __init__(self, parent=None, *, page_count: int = 0, current_page: int = 0, source=None) -> None:
        super().__init__(parent, "Background", "Add a page background", page_count=page_count,
                         current_page=current_page, source=source)
        crow = QHBoxLayout()
        self.use_color = QCheckBox("Color")
        self.use_color.setChecked(True)
        self.color = ColorButton("#fff8e1", "Background color", palette="paper")
        self.color.on_change = self.refresh
        crow.addWidget(self.use_color)
        crow.addWidget(self.color)
        crow.addStretch(1)
        self.form.addRow("Fill:", crow)
        prow = QHBoxLayout()
        self.use_image = QCheckBox("Picture")
        self.image_path = QLineEdit()
        self.image_path.setPlaceholderText("Choose a picture…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        prow.addWidget(self.use_image)
        prow.addWidget(self.image_path, 1)
        prow.addWidget(browse)
        self.form.addRow("", prow)
        self.fit = QComboBox()
        self.fit.addItem("Fit (keep proportions)", "fit")
        self.fit.addItem("Stretch to the page", "stretch")
        self.form.addRow("Picture fit:", self.fit)
        self.opacity = _percent_box(100)
        self.form.addRow("Opacity:", self.opacity)
        self.form.addRow("", _hint("The background is drawn behind the page content. Scanned pages and pages "
                                   "with their own white background will hide it."))
        self._watch(self.use_color, self.use_image, self.image_path, self.fit, self.opacity)
        self._finish()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose background picture", _start_dir(self), IMAGE_FILTER)
        if path:
            self.image_path.setText(path)
            self.use_image.setChecked(True)

    def spec(self) -> BackgroundSpec:
        img = self.image_path.text().strip()
        return BackgroundSpec(color=self.color.rgb() if self.use_color.isChecked() else None,
                              image_path=Path(img) if (self.use_image.isChecked() and img) else None,
                              image_fit=str(self.fit.currentData()), opacity=self.opacity.value() / 100.0)

    def kwargs(self) -> dict:
        return {"background": self.spec()}

    def _has_content(self) -> bool:
        s = self.spec()
        if s.image_path is not None and (not s.image_path.is_file() or self.preview.error):
            return False
        return s.color is not None or s.image_path is not None

    def values(self) -> dict:
        return {"use_color": self.use_color.isChecked(), "color": self.color.name(),
                "use_image": self.use_image.isChecked(), "image": self.image_path.text(),
                "fit": self.fit.currentIndex(), "opacity": self.opacity.value()}

    def _restore(self, v: dict) -> None:
        if "use_color" in v:
            self.use_color.setChecked(bool(v["use_color"]))
        if isinstance(v.get("color"), str):
            self.color.set_name(v["color"])
        if isinstance(v.get("image"), str):
            self.image_path.setText(v["image"])
        self.use_image.setChecked(bool(v.get("use_image")) and Path(str(v.get("image") or "")).is_file())
        if isinstance(v.get("fit"), int) and 0 <= v["fit"] < self.fit.count():
            self.fit.setCurrentIndex(v["fit"])
        if isinstance(v.get("opacity"), int):
            self.opacity.setValue(v["opacity"])


class RemoveMarksDialog(QDialog):
    LABELS = {KIND_HEADER_FOOTER: "Headers, footers and page numbers", KIND_WATERMARK: "Watermarks",
              KIND_BACKGROUND: "Backgrounds"}

    def __init__(self, parent=None, *, source=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Remove Page Design")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Remove headers, footers, watermarks or backgrounds"))
        counts = count_marks(source) if source is not None else {k: 0 for k in ALL_KINDS}
        self.counts = counts
        self.checks: dict[str, QCheckBox] = {}
        for kind in ALL_KINDS:
            n = counts.get(kind, 0)
            cb = QCheckBox(f"{self.LABELS[kind]} — found on {n} page{'s' if n != 1 else ''}")
            cb.setChecked(n > 0)
            cb.setEnabled(n > 0)
            cb.toggled.connect(self._sync)
            self.checks[kind] = cb
            root.addWidget(cb)
        root.addWidget(_hint("Only marks added by Monograph PDF (0.2.1 or later) can be recognised. Text or pictures "
                             "added by other programs are part of the page and are kept."))
        root.addWidget(_hint("Written to a new PDF — the open document is not changed."))
        self.buttons = _ok_cancel(self, "Save As…")
        root.addWidget(self.buttons)
        self._sync()

    def _sync(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.kinds()))

    def kinds(self) -> set[str]:
        return {k for k, cb in self.checks.items() if cb.isChecked() and cb.isEnabled()}
