"""Print dialog with a live preview.

Windows' own print dialog shows "This app doesn't support print preview" for Qt programs, so
Monograph PDF uses its own dialog: printer, paper, orientation, scaling, pages, copies, colour and
two-sided settings on the left, and an exact preview of each printed sheet on the right. The
preview uses the same page placement as the print job (``core.printing.place_page``).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QProcess, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.organize.page_ops import parse_page_ranges
from core.printing import ColorMode, PageScaling, auto_landscape, order_print_pages, place_page

_FALLBACK_SIZES = (QPageSize.PageSizeId.A4, QPageSize.PageSizeId.Letter, QPageSize.PageSizeId.Legal,
                   QPageSize.PageSizeId.A3, QPageSize.PageSizeId.B5, QPageSize.PageSizeId.A5)


def _printer_com_safe() -> bool:
    """False under headless / offscreen CI where Win32 printer COM often SEH-faults."""
    if os.environ.get("MONOGRAPH_PDF_HEADLESS", "").strip() in ("1", "true", "yes"):
        return False
    return os.environ.get("QT_QPA_PLATFORM", "").strip().lower() != "offscreen"


def _list_printers() -> list[QPrinterInfo]:
    if not _printer_com_safe():
        return []
    try:
        return list(QPrinterInfo.availablePrinters())
    except Exception:  # noqa: BLE001
        return []


@dataclass
class PrintSettings:
    pages: list[int]
    scaling: PageScaling
    orientation: str  # "auto" | "portrait" | "landscape"
    color_mode: ColorMode
    comments: bool = True  # False: leave out comments and markup (form fields still print)


class _SheetPreview(QWidget):
    """Draws one printed sheet: paper, printable-area outline and the placed page image."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 380)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._paper = QRectF(0, 0, 595, 842)  # points
        self._paint = QRectF(18, 18, 559, 806)
        self._page_size = (595.0, 842.0)
        self._image: QImage | None = None
        self._scaling = PageScaling.FIT
        self._message = ""

    def set_sheet(self, paper: QRectF, paint: QRectF, page_size, image: QImage | None, scaling, message="") -> None:
        self._paper, self._paint, self._page_size = paper, paint, page_size
        self._image, self._scaling, self._message = image, scaling, message
        self.update()

    def sheet_rect(self) -> QRectF:
        """Where the paper is drawn inside the widget (keeps the paper's aspect ratio)."""
        m = 18.0
        avail_w, avail_h = max(10.0, self.width() - 2 * m), max(10.0, self.height() - 2 * m)
        k = min(avail_w / self._paper.width(), avail_h / self._paper.height())
        w, h = self._paper.width() * k, self._paper.height() * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), self.palette().color(self.backgroundRole()).darker(108))
        sheet = self.sheet_rect()
        k = sheet.width() / self._paper.width()
        p.fillRect(sheet.translated(2, 3), QColor(0, 0, 0, 60))
        p.fillRect(sheet, QColor("#ffffff"))
        if self._message:
            p.setPen(QColor("#5f6873"))
            p.drawText(sheet, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._message)
            return
        area = QRectF(sheet.x() + self._paint.x() * k, sheet.y() + self._paint.y() * k,
                      self._paint.width() * k, self._paint.height() * k)
        x, y, w, h = place_page(self._page_size[0], self._page_size[1],
                                self._paint.width(), self._paint.height(), self._scaling)
        target = QRectF(area.x() + x * k, area.y() + y * k, w * k, h * k)
        p.save()
        p.setClipRect(area)
        if self._image is not None and not self._image.isNull():
            p.drawImage(target, self._image)
        p.restore()
        pen = QPen(QColor(120, 130, 140, 110))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(area)
        p.end()


class PrintDialog(QDialog):
    """Choose printer and options with a live preview; ``printer()`` returns the configured QPrinter."""

    previewChanged = Signal()

    def __init__(
        self,
        document,
        *,
        doc_name: str,
        current_page: int = 0,
        selected_pages: list[int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Print — {doc_name}")
        self.setObjectName("PrintDialog")
        self.setMinimumSize(860, 600)
        self._doc = document
        self._doc_name = doc_name
        self._n = int(document.page_count)
        self._current = max(0, min(self._n - 1, int(current_page)))
        self._selected = sorted(set(selected_pages or []))
        self._cache: dict[tuple[int, bool], QImage] = {}
        self._margin_cache: dict[tuple, tuple[float, float, float, float]] = {}
        self._sheet = 0
        self._printers = _list_printers()
        self._printer: QPrinter | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(18)

        # --- settings ---------------------------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(10)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.printer_combo = QComboBox()
        default_name = ""
        if self._printers and _printer_com_safe():
            try:
                default_name = QPrinterInfo.defaultPrinterName()
            except Exception:  # noqa: BLE001
                default_name = ""
        for info in self._printers:
            self.printer_combo.addItem(info.printerName())
        if not self._printers:
            self.printer_combo.addItem("No printer installed")
            self.printer_combo.setEnabled(False)
        elif default_name:
            self.printer_combo.setCurrentText(default_name)
        self._props = QPushButton("Printing preferences…")
        self._props.setToolTip("Open this printer's own settings (paper tray, quality, finishing …)")
        self._props.setEnabled(bool(self._printers))
        form.addRow("Printer:", self.printer_combo)
        form.addRow("", self._props)

        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        self.copies.setMinimumWidth(76)
        self.collate = QCheckBox("Collate")
        self.collate.setChecked(True)
        crow = QHBoxLayout()
        crow.setContentsMargins(0, 0, 0, 0)
        crow.addWidget(self.copies)
        crow.addWidget(self.collate)
        crow.addStretch(1)
        cw = QWidget()
        cw.setLayout(crow)
        form.addRow("Copies:", cw)

        # Pages
        self.r_all = QRadioButton(f"All ({self._n})")
        self.r_current = QRadioButton(f"Current page ({self._current + 1})")
        self.r_selected = QRadioButton(f"Selected pages ({len(self._selected)})")
        self.r_custom = QRadioButton("Pages:")
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("e.g. 1-3, 5")
        self.custom.setClearButtonEnabled(True)
        self._range_error = QLabel("")
        self._range_error.setObjectName("DialogError")
        self._range_error.setWordWrap(True)
        self._range_error.hide()
        group = QButtonGroup(self)
        for b in (self.r_all, self.r_current, self.r_selected, self.r_custom):
            group.addButton(b)
        self.r_all.setChecked(True)
        self.r_selected.setVisible(len(self._selected) > 1)
        pages_box = QVBoxLayout()
        pages_box.setSpacing(4)
        pages_box.setContentsMargins(0, 0, 0, 0)
        pages_box.addWidget(self.r_all)
        pages_box.addWidget(self.r_current)
        pages_box.addWidget(self.r_selected)
        custom_row = QHBoxLayout()
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.addWidget(self.r_custom)
        custom_row.addWidget(self.custom, 1)
        pages_box.addLayout(custom_row)
        pages_box.addWidget(self._range_error)
        subset_row = QHBoxLayout()
        subset_row.setContentsMargins(0, 0, 0, 0)
        self.subset = QComboBox()
        self.subset.setObjectName("PrintSubset")
        self.subset.addItem("All pages", "all")
        self.subset.addItem("Odd pages", "odd")
        self.subset.addItem("Even pages", "even")
        self.subset.setToolTip("Odd and even refer to page numbers — useful for printing two-sided by hand")
        self.reverse = QCheckBox("Reverse order")
        self.reverse.setObjectName("PrintReverse")
        subset_row.addWidget(self.subset, 1)
        subset_row.addWidget(self.reverse)
        pages_box.addLayout(subset_row)
        pw = QWidget()
        pw.setLayout(pages_box)
        form.addRow("Pages:", pw)

        self.paper = QComboBox()
        form.addRow("Paper:", self.paper)
        self.orientation = QComboBox()
        self.orientation.addItem("Auto (match each page)", "auto")
        self.orientation.addItem("Portrait", "portrait")
        self.orientation.addItem("Landscape", "landscape")
        form.addRow("Orientation:", self.orientation)
        self.scaling = QComboBox()
        self.scaling.addItem("Fit to paper", PageScaling.FIT.value)
        self.scaling.addItem("Actual size (100 %)", PageScaling.ACTUAL.value)
        self.scaling.addItem("Shrink large pages only", PageScaling.SHRINK.value)
        form.addRow("Scaling:", self.scaling)
        self.color = QComboBox()
        self.color.addItem("Color", ColorMode.COLOR.value)
        self.color.addItem("Black & white", ColorMode.GRAYSCALE.value)
        form.addRow("Color:", self.color)
        self.comments = QComboBox()
        self.comments.setObjectName("PrintComments")
        self.comments.addItem("Document and comments", True)
        self.comments.addItem("Document only", False)
        self.comments.setToolTip("Comments are notes, highlights, shapes and stamps. Form fields always print.")
        form.addRow("Comments:", self.comments)
        self.duplex = QComboBox()
        form.addRow("Two-sided:", self.duplex)
        left.addLayout(form)
        left.addStretch(1)

        hint = QLabel("Typed form entries, text boxes, shapes and images are printed as they appear on screen.")
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        left.addWidget(hint)

        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(340)
        root.addWidget(lw)

        # --- preview ----------------------------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(8)
        self.preview = _SheetPreview()
        self.preview.setObjectName("PrintPreview")
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        nav.addStretch(1)
        self._prev_btn = QToolButton()
        self._prev_btn.setText("‹")
        self._prev_btn.setToolTip("Previous sheet")
        self._next_btn = QToolButton()
        self._next_btn.setText("›")
        self._next_btn.setToolTip("Next sheet")
        self.sheet_label = QLabel("")
        self.sheet_label.setMinimumWidth(160)
        self.sheet_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self.sheet_label)
        nav.addWidget(self._next_btn)
        nav.addStretch(1)
        right.addLayout(nav)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._print_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._print_btn.setText("Print")
        self._buttons.accepted.connect(self._accept)
        self._buttons.rejected.connect(self.reject)
        right.addWidget(self._buttons)
        root.addLayout(right, 1)

        # --- wiring -------------------------------------------------------------------------
        self.printer_combo.currentIndexChanged.connect(self._printer_changed)
        self._props.clicked.connect(self._system_settings)
        for combo in (self.paper, self.orientation, self.scaling, self.color, self.comments):
            combo.currentIndexChanged.connect(self._refresh)
        self.subset.currentIndexChanged.connect(self._pages_changed)
        self.reverse.toggled.connect(self._pages_changed)
        for b in (self.r_all, self.r_current, self.r_selected, self.r_custom):
            b.toggled.connect(self._pages_changed)
        self.custom.textEdited.connect(lambda _t: self.r_custom.setChecked(True))
        self.custom.textChanged.connect(self._pages_changed)
        self._prev_btn.clicked.connect(lambda: self._go(-1))
        self._next_btn.clicked.connect(lambda: self._go(1))
        self._printer_changed()

    # --- printer & paper ---------------------------------------------------------------------

    def _document_paper_index(self) -> int:
        """Index of the paper that matches the document's first page (either orientation, within
        2 mm), or -1 when the printer has no such paper."""
        try:
            w, h = sorted(self._page_pt(0))
        except Exception:  # noqa: BLE001
            return -1
        for i in range(self.paper.count()):
            ps = self.paper.itemData(i)
            if not isinstance(ps, QPageSize):
                continue
            size = ps.size(QPageSize.Unit.Point)
            pw, ph = sorted((size.width(), size.height()))
            if abs(pw - w) <= 6 and abs(ph - h) <= 6:
                return i
        return -1

    def _info(self) -> QPrinterInfo | None:
        i = self.printer_combo.currentIndex()
        return self._printers[i] if 0 <= i < len(self._printers) else None

    def _printer_changed(self, *_args) -> None:
        info = self._info()
        current = self.paper.currentData()
        self.paper.blockSignals(True)
        self.paper.clear()
        # Printer COM (Win32 spooler) can raise under offscreen / headless CI; fall back to stock sizes.
        sizes: list[QPageSize] = []
        if info is not None:
            try:
                sizes = list(info.supportedPageSizes())
            except Exception:  # noqa: BLE001
                sizes = []
        if not sizes:
            sizes = [QPageSize(s) for s in _FALLBACK_SIZES]
        seen = set()
        for ps in sizes:
            key = ps.key() or ps.name()
            if key in seen:
                continue
            seen.add(key)
            self.paper.addItem(ps.name(), ps)
        want = None
        idx = -1
        if current is not None:
            want = current.name()
        else:
            idx = self._document_paper_index()  # A4 form → A4 paper, when the printer has it
            if idx < 0 and info is not None:
                try:
                    default = info.defaultPageSize()
                    if default.isValid():
                        want = default.name()
                except Exception:  # noqa: BLE001
                    want = None
            if idx < 0 and want is None:
                want = QPageSize(QPageSize.PageSizeId.A4).name()
        if idx < 0:
            idx = self.paper.findText(want)
        self.paper.setCurrentIndex(max(0, idx))
        self.paper.blockSignals(False)

        self.duplex.blockSignals(True)
        prev = self.duplex.currentData()
        self.duplex.clear()
        self.duplex.addItem("Off", QPrinter.DuplexMode.DuplexNone)
        modes: list = []
        if info is not None:
            try:
                modes = list(info.supportedDuplexModes())
            except Exception:  # noqa: BLE001
                modes = []
        if QPrinter.DuplexMode.DuplexLongSide in modes:
            self.duplex.addItem("Flip on long edge", QPrinter.DuplexMode.DuplexLongSide)
        if QPrinter.DuplexMode.DuplexShortSide in modes:
            self.duplex.addItem("Flip on short edge", QPrinter.DuplexMode.DuplexShortSide)
        if prev is not None:
            self.duplex.setCurrentIndex(max(0, self.duplex.findData(prev)))
        self.duplex.setEnabled(self.duplex.count() > 1)
        self.duplex.blockSignals(False)
        self._printer = None
        self._print_btn.setEnabled(info is not None)
        self._refresh()

    def _system_settings(self) -> None:
        """The printer driver's own preferences window (paper tray, quality, finishing …).

        On Windows this opens the driver's "Printing preferences" (printui) rather than Windows'
        print dialog, which would offer a second Print button and say "This app doesn't support
        print preview". The choices are saved by the driver and picked up for this job.
        """
        info = self._info()
        if info is None:
            return
        if sys.platform == "win32":
            if '"' in info.printerName():
                # The name is placed inside a quoted command-line argument: a name that itself
                # contains a quote could add arguments, so such a printer is not handed to rundll32.
                return
            proc = QProcess(self)
            from core.safe_paths import windows_tool

            proc.setProgram(windows_tool("rundll32.exe"))  # full path, never from the current folder
            proc.setNativeArguments(f'printui.dll,PrintUIEntry /e /n "{info.printerName()}"')
            self._props.setEnabled(False)
            self._props.setText("Waiting for printer preferences…")

            def done(*_args) -> None:
                self._props.setText("Printing preferences…")
                self._props.setEnabled(True)
                self._printer = None  # new QPrinter picks up the driver's updated defaults
                self._margin_cache.clear()
                self._printer_changed()
                proc.deleteLater()

            proc.finished.connect(done)
            proc.errorOccurred.connect(done)
            proc.start()
            return
        from PySide6.QtPrintSupport import QPrintDialog

        printer = self.printer()
        if printer is None:
            return
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Printer settings")
        dlg.setOptions(QPrintDialog.PrintDialogOption(0))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._printer = printer  # keep driver settings (tray, quality …)
        name = printer.printerName()
        if name and name != self.printer_combo.currentText():
            self.printer_combo.blockSignals(True)
            self.printer_combo.setCurrentText(name)
            self.printer_combo.blockSignals(False)
        self.copies.setValue(max(1, printer.copyCount()))
        self.collate.setChecked(printer.collateCopies())
        idx = self.paper.findText(printer.pageLayout().pageSize().name())
        if idx >= 0:
            self.paper.blockSignals(True)
            self.paper.setCurrentIndex(idx)
            self.paper.blockSignals(False)
        gray = printer.colorMode() == QPrinter.ColorMode.GrayScale
        self.color.setCurrentIndex(1 if gray else 0)
        d = self.duplex.findData(printer.duplex())
        if d >= 0:
            self.duplex.setCurrentIndex(d)
        self._refresh()

    def _page_size(self) -> QPageSize:
        ps = self.paper.currentData()
        return ps if isinstance(ps, QPageSize) and ps.isValid() else QPageSize(QPageSize.PageSizeId.A4)

    def _margins_pt(self, landscape: bool) -> tuple[float, float, float, float]:
        """Unprintable margins (left, top, right, bottom) of the selected printer and paper, in points."""
        info = self._info()
        if info is None:
            return 18.0, 18.0, 18.0, 18.0
        key = (info.printerName(), self._page_size().key(), landscape)
        if key in self._margin_cache:
            return self._margin_cache[key]
        try:
            pr = QPrinter(info, QPrinter.PrinterMode.ScreenResolution)
            pr.setPageSize(self._page_size())
            pr.setPageOrientation(
                QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait
            )
            lay = pr.pageLayout()
            full = lay.fullRectPoints()
            paint = lay.paintRectPoints()
            margins = (float(paint.left() - full.left()), float(paint.top() - full.top()),
                       float(full.right() - paint.right()), float(full.bottom() - paint.bottom()))
        except Exception:  # noqa: BLE001
            margins = (18.0, 18.0, 18.0, 18.0)
        self._margin_cache[key] = margins
        return margins

    def _sheet_geometry(self, page_index: int) -> tuple[QRectF, QRectF, bool]:
        size = self._page_size().size(QPageSize.Unit.Point)
        pw, ph = float(size.width()), float(size.height())
        landscape = self._landscape_for(page_index)
        ml, mt, mr, mb = self._margins_pt(landscape)
        if landscape:
            pw, ph = ph, pw
        paper = QRectF(0, 0, pw, ph)
        paint = QRectF(ml, mt, max(1.0, pw - ml - mr), max(1.0, ph - mt - mb))
        return paper, paint, landscape

    def _page_pt(self, index: int) -> tuple[float, float]:
        try:
            info = self._doc.page(index)
            return float(info.display_width_pt), float(info.display_height_pt)
        except Exception:  # noqa: BLE001
            return 595.0, 842.0

    def _landscape_for(self, page_index: int) -> bool:
        mode = self.orientation.currentData()
        if mode == "landscape":
            return True
        if mode == "portrait":
            return False
        return auto_landscape(*self._page_pt(page_index))

    # --- pages ---------------------------------------------------------------------------------

    def selected_pages(self) -> list[int]:
        """Pages to print, in print order (range, then odd/even subset, then reverse)."""
        return order_print_pages(self._range_pages(), subset=str(self.subset.currentData() or "all"),
                                 reverse=self.reverse.isChecked())

    def _range_pages(self) -> list[int]:
        if self.r_current.isChecked():
            return [self._current]
        if self.r_selected.isChecked() and self._selected:
            return list(self._selected)
        if self.r_custom.isChecked():
            try:
                return parse_page_ranges(self.custom.text(), self._n)
            except ValueError:
                return []
        return list(range(self._n))

    def _pages_changed(self, *_args) -> None:
        bad = self.r_custom.isChecked() and not self._range_pages()
        if bad and self.custom.text().strip():
            self._range_error.setText(f"Enter pages between 1 and {self._n}, e.g. 1-3, 5")
            self._range_error.show()
        else:
            self._range_error.hide()
        self._sheet = 0
        self._refresh()

    def _go(self, step: int) -> None:
        pages = self.selected_pages()
        if not pages:
            return
        self._sheet = max(0, min(len(pages) - 1, self._sheet + step))
        self._refresh()

    # --- preview -------------------------------------------------------------------------------

    def _image(self, index: int, gray: bool) -> QImage | None:
        comments = bool(self.comments.currentData())
        key = (index, gray, comments)
        img = self._cache.get(key)
        if img is None:
            dpr = max(1.0, float(self.devicePixelRatioF()))
            try:
                png = None
                if not comments:
                    from core.printing.ops import _render_without_comments

                    png = _render_without_comments(self._doc, index, 110 / 72.0 * dpr)
                if png is None:
                    png = self._doc.render_pixmap_png(index, zoom=110 / 72.0, dpr=dpr)
            except Exception:  # noqa: BLE001
                return None
            img = QImage.fromData(png, "PNG")
            if gray and not img.isNull():
                img = img.convertToFormat(QImage.Format.Format_Grayscale8)
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[key] = img
        return img

    def _refresh(self, *_args) -> None:
        pages = self.selected_pages()
        scaling = PageScaling(self.scaling.currentData() or PageScaling.FIT.value)
        has_printer = self._info() is not None
        self._print_btn.setEnabled(bool(pages) and has_printer)
        if not pages:
            paper, paint, _ = self._sheet_geometry(self._current)
            self.preview.set_sheet(paper, paint, (595, 842), None, scaling, "No pages selected")
            self.sheet_label.setText("")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        self._sheet = max(0, min(len(pages) - 1, self._sheet))
        index = pages[self._sheet]
        paper, paint, _land = self._sheet_geometry(index)
        gray = self.color.currentData() == ColorMode.GRAYSCALE.value
        self.preview.set_sheet(paper, paint, self._page_pt(index), self._image(index, gray), scaling)
        sheets = len(pages)
        self.sheet_label.setText(f"Sheet {self._sheet + 1} of {sheets}  ·  page {index + 1}")
        self._prev_btn.setEnabled(self._sheet > 0)
        self._next_btn.setEnabled(self._sheet < sheets - 1)
        self.previewChanged.emit()

    # --- result ----------------------------------------------------------------------------------

    def settings(self) -> PrintSettings:
        return PrintSettings(
            pages=self.selected_pages(),
            scaling=PageScaling(self.scaling.currentData() or PageScaling.FIT.value),
            orientation=str(self.orientation.currentData() or "auto"),
            color_mode=ColorMode(self.color.currentData() or ColorMode.COLOR.value),
            comments=bool(self.comments.currentData()),
        )

    def printer(self) -> QPrinter | None:
        """The QPrinter configured from the dialog (None without an installed printer)."""
        info = self._info()
        if info is None:
            return None
        pr = self._printer
        if pr is None or pr.printerName() != info.printerName():
            pr = QPrinter(info, QPrinter.PrinterMode.HighResolution)
            self._printer = pr
        pr.setDocName(self._doc_name)
        pr.setFullPage(False)
        pr.setPageSize(self._page_size())
        first = (self.selected_pages() or [self._current])[0]
        pr.setPageOrientation(
            QPageLayout.Orientation.Landscape if self._landscape_for(first) else QPageLayout.Orientation.Portrait
        )
        pr.setCopyCount(self.copies.value())
        pr.setCollateCopies(self.collate.isChecked())
        gray = self.color.currentData() == ColorMode.GRAYSCALE.value
        pr.setColorMode(QPrinter.ColorMode.GrayScale if gray else QPrinter.ColorMode.Color)
        duplex = self.duplex.currentData()
        if duplex is not None:
            pr.setDuplex(duplex)
        return pr

    def _accept(self) -> None:
        if not self.selected_pages():
            self._pages_changed()
            self.custom.setFocus()
            return
        if self._info() is None:
            return
        self.accept()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(960, 680)


def print_document_pages(
    printer: QPrinter,
    document,
    pages: list[int],
    *,
    dpi: int,
    color_mode: ColorMode = ColorMode.COLOR,
    scaling: PageScaling = PageScaling.FIT,
    orientation: str = "fixed",
    comments: bool = True,
) -> int:
    """Send pages to ``printer``. ``orientation='auto'`` turns the paper to match each page."""
    from core.printing import render_page_png_for_print

    painter = QPainter()

    def set_orientation(index: int) -> None:
        if orientation != "auto":
            return
        w, h = _page_pt(document, index)
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape if auto_landscape(w, h) else QPageLayout.Orientation.Portrait
        )

    valid = [i for i in pages if 0 <= i < document.page_count]
    if not valid:
        return 0
    set_orientation(valid[0])
    if not painter.begin(printer):
        raise RuntimeError("Could not start the print job.")
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    printed = 0
    try:
        for n, index in enumerate(valid):
            if n > 0:
                set_orientation(index)
                printer.newPage()
            png = render_page_png_for_print(document, index, dpi=dpi, color_mode=color_mode, comments=comments)
            img = QImage.fromData(png, "PNG")
            if img.isNull():
                continue
            res = float(printer.resolution()) or 72.0
            area = printer.pageLayout().paintRectPixels(int(res))
            pw, ph = _page_pt(document, index)
            x, y, w, h = place_page(pw, ph, area.width() * 72 / res, area.height() * 72 / res, scaling)
            k = res / 72.0
            target = QRectF(x * k, y * k, w * k, h * k)
            painter.save()
            painter.setClipRect(QRectF(QPointF(0, 0), QPointF(area.width(), area.height())))
            painter.drawImage(target, img)
            painter.restore()
            printed += 1
    finally:
        painter.end()
    return printed


def _page_pt(document, index: int) -> tuple[float, float]:
    try:
        info = document.page(index)
        return float(info.display_width_pt), float(info.display_height_pt)
    except Exception:  # noqa: BLE001
        return 595.0, 842.0
