"""Compress PDF: Lossless / Balanced / Smallest file / Target size, with a target in KB/MB/GB (numeric
entry kept in step with a slider), an estimate before running, the measured size after, a side-by-side
preview of a representative page, and Cancel. Compression runs in a worker thread."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.convert import compress as cz

PROFILES: tuple[tuple[str, str, int | None], ...] = (
    ("High quality — lossless", "lossless", None),
    ("Balanced", "balanced", None),
    ("Small file", "smallest", None),
    ("Email attachment — at most 10 MB", "target", 10 * cz.MB),
    ("Online form upload — at most 2 MB", "target", 2 * cz.MB),
    ("Custom maximum size", "target", None),
    ("Custom resolution and quality", "custom", None),
)
# The "Custom maximum size" entry (found by name, so adding profiles never shifts it)
CUSTOM_TARGET_INDEX = next(i for i, p in enumerate(PROFILES) if p[0] == "Custom maximum size")
CUSTOM_QUALITY_INDEX = next(i for i, p in enumerate(PROFILES) if p[1] == "custom")
UNIT_NAMES = ("KB", "MB", "GB")
SLIDER_STEPS = 1000


class _Worker(QThread):
    progress = Signal(str, float)
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, data: bytes, kwargs: dict[str, Any]) -> None:
        super().__init__()
        self._data = data
        self._kwargs = kwargs
        self.cancelled = False

    def run(self) -> None:  # noqa: D401
        try:
            res = cz.compress(self._data, cancel=lambda: self.cancelled,
                              progress=lambda t, f: self.progress.emit(t, f), **self._kwargs)
            self.done.emit(res)
        except BaseException as exc:  # noqa: BLE001 — reported in the dialog
            self.failed.emit(exc)


PREVIEW_W, PREVIEW_H = 200, 270


def render_page(data: bytes, index: int, width_px: int, password: str | None = None,
                height_px: int | None = None) -> QImage:
    """A small rendering of one page, fitted into width × height (for the preview only — never a
    full-resolution page)."""
    import fitz

    with fitz.open("pdf", data) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        page = doc[max(0, min(index, doc.page_count - 1))]
        zoom = width_px / max(1.0, page.rect.width)
        if height_px:
            zoom = min(zoom, height_px / max(1.0, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()


class CompressDialog(QDialog):
    def __init__(self, data: bytes, *, password: str | None = None, doc_name: str = "", parent=None) -> None:
        super().__init__(parent)
        import fitz

        self.setWindowTitle("Compress PDF")
        self.setMinimumWidth(980)
        self._data = data
        self._password = password
        self._worker: _Worker | None = None
        self._results: dict[tuple, cz.CompressResult] = {}
        self.result_: cz.CompressResult | None = None
        self._accept_after = False
        with fitz.open("pdf", data) as doc:
            if doc.needs_pass:
                doc.authenticate(password or "")
            self.profile = cz.analyze(doc, len(data))
            self._preview_page = self._pick_preview_page(doc)

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(18)
        outer.addLayout(body, 1)
        root = QVBoxLayout()  # settings and results (left)
        root.setSpacing(10)
        body.addLayout(root, 1)
        title = QLabel("Compress PDF")
        title.setObjectName("DialogTitle")
        root.addWidget(title)
        info = QLabel(f"Current size: <b>{cz.format_size(len(data), exact=True)}</b>"
                      f"{' — ' + doc_name if doc_name else ''} (the document as shown, including unsaved "
                      f"changes).<br>{self.profile.summary()}.")
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.profile_combo = QComboBox()
        for label, _mode, _t in PROFILES:
            self.profile_combo.addItem(label)
        form.addRow("Profile:", self.profile_combo)
        modes = QWidget()
        mrow = QHBoxLayout(modes)
        mrow.setContentsMargins(0, 0, 0, 0)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QRadioButton] = {}
        from ui.toolbar_icons import make_icon

        for key, icon in (("lossless", "quality_high"), ("balanced", "quality_balanced"),
                          ("smallest", "quality_smallest"), ("custom", "quality_balanced"), ("target", "target_size")):
            b = QRadioButton(cz.MODE_LABELS[key])
            b.setIcon(make_icon(icon))
            b.setMinimumWidth(b.sizeHint().width())  # never squeezed so the label is cut
            self.mode_group.addButton(b)
            self.mode_buttons[key] = b
            mrow.addWidget(b)
        mrow.addStretch(1)
        form.addRow("Mode:", modes)

        # Custom: choose the picture resolution and JPEG quality yourself
        custom = QWidget()
        crow = QHBoxLayout(custom)
        crow.setContentsMargins(0, 0, 0, 0)
        self.ppi_spin = QSpinBox()
        self.ppi_spin.setObjectName("CompressPpi")
        self.ppi_spin.setRange(*cz.CUSTOM_PPI_RANGE)
        self.ppi_spin.setSingleStep(10)
        self.ppi_spin.setValue(200)
        self.ppi_spin.setSuffix(" ppi")
        self.ppi_spin.setToolTip("Picture resolution (pixels per inch at the size shown on the page). Pictures "
                                 "already below it are not enlarged. 300 ppi = print quality, 150 ppi = screen.")
        self.quality_spin = QSpinBox()
        self.quality_spin.setObjectName("CompressQuality")
        self.quality_spin.setRange(*cz.CUSTOM_QUALITY_RANGE)
        self.quality_spin.setValue(80)
        self.quality_spin.setToolTip("JPEG quality of reduced pictures: higher = sharper and larger "
                                     "(85–95 very good, 70–80 good, below 60 visible artefacts)")
        crow.addWidget(QLabel("Resolution"))
        crow.addWidget(self.ppi_spin)
        crow.addSpacing(12)
        crow.addWidget(QLabel("JPEG quality"))
        crow.addWidget(self.quality_spin)
        crow.addStretch(1)
        form.addRow("Pictures:", custom)

        target = QWidget()
        trow = QHBoxLayout(target)
        trow.setContentsMargins(0, 0, 0, 0)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setDecimals(2)
        self.size_spin.setRange(0.01, 999999.0)
        self.size_spin.setAccelerated(True)
        self.unit = QComboBox()
        self.unit.addItems(UNIT_NAMES)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        trow.addWidget(self.size_spin)
        trow.addWidget(self.unit)
        trow.addWidget(self.slider, 1)
        form.addRow("Maximum size:", target)
        self.margin = QSpinBox()
        self.margin.setRange(0, 10)
        self.margin.setSuffix(" % below the maximum")
        self.margin.setValue(1)
        form.addRow("Safety margin:", self.margin)
        root.addLayout(form)
        units = QLabel("1 KB = 1,000 bytes · 1 MB = 1,000,000 bytes. The size is a maximum: success is "
                       "reported only when the saved file is at or below it, measured in bytes. Upload limits "
                       "differ — check the requirement you need to meet.")
        units.setObjectName("DialogHint")
        units.setWordWrap(True)
        root.addWidget(units)
        self.mode_note = QLabel()
        self.mode_note.setWordWrap(True)
        root.addWidget(self.mode_note)
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        root.addWidget(self.estimate_label)
        self.result_label = QLabel("Measured size: not yet measured — press Preview or Compress.")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.result_label)

        root.addStretch(1)

        prev = QGridLayout()  # preview (right): original and compressed side by side
        prev.setHorizontalSpacing(10)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, max(1, self.profile.pages))
        self.page_spin.setValue(self._preview_page + 1)
        self.page_spin.setPrefix("Page ")
        digits = len(str(max(1, self.profile.pages)))
        self.page_spin.setMinimumWidth(self.page_spin.fontMetrics().horizontalAdvance("Page " + "8" * digits) + 48)
        self.page_spin.setToolTip("Page to compare (the page with the most picture data is chosen first)")
        head = QLabel("Preview")
        head.setObjectName("DialogSection")
        prev.addWidget(head, 0, 0)
        prev.addWidget(self.page_spin, 0, 1, Qt.AlignmentFlag.AlignRight)
        prev.addWidget(QLabel("Original"), 1, 0)
        prev.addWidget(QLabel("Compressed"), 1, 1)
        self.orig_view = QLabel()
        self.new_view = QLabel()
        for v in (self.orig_view, self.new_view):
            v.setFixedSize(PREVIEW_W, PREVIEW_H)
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setObjectName("PreviewPane")
        prev.addWidget(self.orig_view, 2, 0)
        prev.addWidget(self.new_view, 2, 1)
        prev.setRowStretch(3, 1)
        body.addLayout(prev)
        root = outer  # progress, status and buttons span the whole width

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        self.status = QLabel()
        self.status.setObjectName("DialogHint")
        root.addWidget(self.bar)
        root.addWidget(self.status)
        buttons = QDialogButtonBox()
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setIcon(make_icon("preview"))
        self.ok_btn = buttons.addButton("Compress…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok_btn.setIcon(make_icon("optimize"))
        buttons.addButton(self.preview_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.cancel_btn = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.ok_btn.clicked.connect(self._on_ok)
        self.preview_btn.clicked.connect(lambda: self._start(accept_after=False))
        self.cancel_btn.clicked.connect(self._on_cancel)
        root.addWidget(buttons)

        self._syncing = False
        self.profile_combo.currentIndexChanged.connect(self._apply_profile)
        self.mode_group.buttonToggled.connect(self._mode_toggled)
        self.size_spin.valueChanged.connect(self._spin_changed)
        self.unit.currentIndexChanged.connect(self._unit_changed)
        self.slider.valueChanged.connect(self._slider_changed)
        self.margin.valueChanged.connect(lambda *_: self._sync())
        self.ppi_spin.valueChanged.connect(lambda *_: self._sync())
        self.quality_spin.valueChanged.connect(lambda *_: self._sync())
        self.page_spin.valueChanged.connect(lambda *_: self._show_preview())
        self._unit_name = "KB"
        default_target = max(self.min_bytes(), int(len(data) * 0.5))
        self.set_target_bytes(default_target)
        self.profile_combo.setCurrentIndex(1)
        self._apply_profile()
        self._show_preview()

    # ------------------------------------------------------------ target size: spin <-> slider

    def min_bytes(self) -> int:
        return max(10 * cz.KB, min(len(self._data), int(len(self._data) * 0.01)))

    def max_bytes(self) -> int:
        return max(len(self._data), self.min_bytes() + 1)

    def _bytes_to_slider(self, n: int) -> int:
        lo, hi = math.log(self.min_bytes()), math.log(self.max_bytes())
        n = max(self.min_bytes(), min(self.max_bytes(), n))
        return round((math.log(n) - lo) / (hi - lo) * SLIDER_STEPS) if hi > lo else SLIDER_STEPS

    def _slider_to_bytes(self, v: int) -> int:
        lo, hi = math.log(self.min_bytes()), math.log(self.max_bytes())
        return int(math.exp(lo + (hi - lo) * v / SLIDER_STEPS))

    def target_bytes(self) -> int:
        """Exact byte limit from the numeric entry (rounded down, never up)."""
        return cz.parse_size(f"{self.size_spin.value():.2f} {self.unit.currentText()}")

    def set_target_bytes(self, n: int) -> None:
        unit = "MB" if n >= cz.MB else "KB"
        if n >= cz.GB:
            unit = "GB"
        self._syncing = True
        try:
            self.unit.setCurrentText(unit)
            self._unit_name = unit
            self.size_spin.setValue(math.floor(n / cz.UNITS[unit] * 100) / 100)
            self.slider.setValue(self._bytes_to_slider(n))
        finally:
            self._syncing = False
        self._sync()

    def _spin_changed(self, *_a) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.slider.setValue(self._bytes_to_slider(self.target_bytes()))
        finally:
            self._syncing = False
        self._choose_custom()

    def _unit_changed(self, *_a) -> None:
        if self._syncing:
            return
        # keep the same byte value when the unit changes (956 KB -> 0.95 MB is not used: keep the number)
        old = self._unit_name
        new = self.unit.currentText()
        self._unit_name = new
        n = int(self.size_spin.value() * cz.UNITS[old])
        self._syncing = True
        try:
            self.size_spin.setValue(math.floor(n / cz.UNITS[new] * 100) / 100)
        finally:
            self._syncing = False
        self._spin_changed()

    def _slider_changed(self, v: int) -> None:
        if self._syncing:
            return
        n = self._slider_to_bytes(v)
        self._syncing = True
        try:
            unit = self.unit.currentText()
            self.size_spin.setValue(math.floor(n / cz.UNITS[unit] * 100) / 100)
        finally:
            self._syncing = False
        self._choose_custom()

    def _choose_custom(self) -> None:
        if not self.mode_buttons["target"].isChecked():
            self.mode_buttons["target"].setChecked(True)
        last = CUSTOM_TARGET_INDEX
        if self.profile_combo.currentIndex() != last and PROFILES[self.profile_combo.currentIndex()][2] != self.target_bytes():
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(last)
            self.profile_combo.blockSignals(False)
        self._sync()

    # ------------------------------------------------------------ modes

    def mode(self) -> str:
        for key, b in self.mode_buttons.items():
            if b.isChecked():
                return key
        return "lossless"

    def _apply_profile(self, *_a) -> None:
        _label, mode, target = PROFILES[self.profile_combo.currentIndex()]
        self.mode_buttons[mode].setChecked(True)
        if target:
            self.set_target_bytes(target)
        self._sync()

    def _mode_toggled(self, _button, checked: bool) -> None:
        """A mode chosen directly selects the matching profile (Target size: the custom maximum unless a
        size profile is already chosen), so the two never contradict each other."""
        if checked:
            mode = self.mode()
            current = PROFILES[self.profile_combo.currentIndex()][1]
            if current != mode:
                index = {"lossless": 0, "balanced": 1, "smallest": 2, "custom": CUSTOM_QUALITY_INDEX,
                         "target": CUSTOM_TARGET_INDEX}[mode]
                self.profile_combo.blockSignals(True)
                self.profile_combo.setCurrentIndex(index)
                self.profile_combo.blockSignals(False)
        self._sync()

    def _key(self) -> tuple:
        mode = self.mode()
        if mode == "target":
            return (mode, self.target_bytes(), self.margin.value())
        if mode == "custom":
            return (mode, self.ppi_spin.value(), self.quality_spin.value())
        return (mode,)

    def _sync(self) -> None:
        mode = self.mode()
        for w in (self.size_spin, self.unit, self.slider, self.margin):
            w.setEnabled(mode == "target")
        for w in (self.ppi_spin, self.quality_spin):
            w.setEnabled(mode == "custom")
        notes = {
            "lossless": "Lossless: no picture, text or drawing is changed; only the way the file is stored.",
            "balanced": "Balanced (lossy for pictures): pictures above 150 ppi are reduced and re-encoded "
                        "(JPEG quality 75). Text, fonts, drawings, annotations and forms are not changed.",
            "smallest": "Smallest file (lossy for pictures): pictures reduced to 110 ppi (scanned pages 150 ppi), "
                        "JPEG quality 55. Text stays sharp — it is never turned into a picture.",
            "custom": f"Custom (lossy for pictures): pictures above {self.ppi_spin.value()} ppi are reduced to it "
                      f"and re-encoded at JPEG quality {self.quality_spin.value()} (scanned pages stay at 150 ppi or "
                      "more). Text, fonts, drawings, annotations and forms are not changed.",
            "target": "Target size: lossless first; pictures are reduced only as far as needed, best quality "
                      "first, never below 100 ppi (scanned pages 150 ppi) or JPEG quality 40.",
        }
        self.mode_note.setText(notes[mode])
        if self.profile.signed:
            self.mode_note.setText(self.mode_note.text() + " This document is digitally signed: any rewrite "
                                   "removes the signature's validity.")
        if mode == "lossless":
            est = cz.estimate_size(self.profile, None, None)
            self.estimate_label.setText("Estimated size: about the same or smaller (lossless — the gain depends on "
                                        "how the file was written; measure with Preview).")
        elif mode in cz.MODE_SETTINGS or mode == "custom":
            settings = cz.MODE_SETTINGS.get(mode) or (self.ppi_spin.value(), self.quality_spin.value())
            est = cz.estimate_size(self.profile, *settings)
            self.estimate_label.setText(f"Estimated size: about {cz.format_size(est)} "
                                        f"({_pct(est, len(self._data))}) — an estimate; Preview measures it.")
        else:
            floor = cz.estimate_size(self.profile, *cz.LADDER[-1])
            t = self.target_bytes()
            verdict = "likely reachable" if floor <= t else "probably not reachable without unacceptable loss"
            self.estimate_label.setText(f"Target {cz.format_size(t, exact=True)}: {verdict} (estimated smallest "
                                        f"acceptable size about {cz.format_size(floor)}). Preview measures it.")
        res = self._results.get(self._key())
        self._show_result(res)

    # ------------------------------------------------------------ running

    def _start(self, *, accept_after: bool) -> None:
        if self._worker is not None:
            return
        key = self._key()
        if key in self._results:
            self.result_ = self._results[key]
            self._show_result(self.result_)
            if accept_after:
                self._finish_accept()
            return
        if self.profile.signed and not getattr(self, "_signed_ok", False):
            if not self._headless():
                resp = QMessageBox.question(self, "Digitally signed document",
                                            "This PDF is digitally signed. The compressed copy is a new file and "
                                            "its signature will no longer be valid. Continue?")
                if resp != QMessageBox.StandardButton.Yes:
                    return
            self._signed_ok = True
        kwargs: dict[str, Any] = {"mode": self.mode(), "password": self._password}
        if self.mode() == "custom":
            kwargs["ppi"] = float(self.ppi_spin.value())
            kwargs["quality"] = int(self.quality_spin.value())
        if self.mode() == "target":
            kwargs["target_bytes"] = self.target_bytes()
            kwargs["safety_margin"] = self.margin.value() / 100.0
        self._accept_after = accept_after
        self._run_key = key
        self._set_running(True)
        self._worker = _Worker(self._data, kwargs)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        if self._headless():
            self._worker.run()  # synchronous in automated runs (signals are delivered directly)
        else:
            self._worker.start()

    def _headless(self) -> bool:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        return app is not None and app.platformName().lower() in ("offscreen", "minimal")

    def _set_running(self, on: bool) -> None:
        self.bar.setVisible(on)
        self.bar.setValue(0)
        for w in (self.profile_combo, self.preview_btn, self.ok_btn, *self.mode_buttons.values(), self.size_spin,
                  self.unit, self.slider, self.margin, self.ppi_spin, self.quality_spin):
            w.setEnabled(not on)
        self.cancel_btn.setText("Stop" if on else "Cancel")
        self.status.setText("Working…" if on else "")
        if not on:
            self.ok_btn.setDefault(True)  # disabling moved the default to Cancel
            self._sync()

    def _on_progress(self, text: str, frac: float) -> None:
        self.status.setText(text)
        self.bar.setValue(int(frac * 100))

    def _cleanup_worker(self) -> None:
        w, self._worker = self._worker, None
        if w is not None and w.isRunning():
            w.wait()

    def _on_done(self, res: cz.CompressResult) -> None:
        self._cleanup_worker()
        self._results[self._run_key] = res
        self.result_ = res
        self._set_running(False)
        self._show_result(res)
        self._show_preview()
        if self._accept_after:
            self._finish_accept()

    def _on_failed(self, exc: BaseException) -> None:
        self._cleanup_worker()
        self._set_running(False)
        if isinstance(exc, cz.CompressCancelled):
            self.status.setText("Stopped. Nothing was written.")
            return
        self.status.setText(f"Compression failed: {exc}")
        if not self._headless():
            QMessageBox.warning(self, "Compress PDF", f"The PDF could not be compressed: {exc}")

    def _show_result(self, res: cz.CompressResult | None) -> None:
        if res is None:
            self.result_label.setText("Measured size: not yet measured — press Preview or Compress.")
            return
        lossy = "lossy for pictures" if res.lossy else "lossless"
        how = res.candidate.label if res.candidate.ppi is None else \
            f"pictures at {res.candidate.ppi:.0f} ppi, JPEG quality {res.candidate.quality}"
        text = (f"<b>{res.status()}</b><br>Measured size: {cz.format_size(res.output_bytes, exact=True)} "
                f"({_pct(res.output_bytes, res.source_bytes)}; {lossy}; {how}; "
                f"{res.candidate.images_changed} picture(s) changed).")
        if res.notes:
            text += "<br>" + "<br>".join(res.notes)
        self.result_label.setText(text)

    def _show_preview(self) -> None:
        idx = self.page_spin.value() - 1
        try:
            self.orig_view.setPixmap(QPixmap.fromImage(render_page(self._data, idx, PREVIEW_W - 6, self._password, PREVIEW_H - 6)))
            res = self._results.get(self._key()) if hasattr(self, "_results") else None
            if res is not None:
                self.new_view.setPixmap(QPixmap.fromImage(render_page(res.data, idx, PREVIEW_W - 6, self._password, PREVIEW_H - 6)))
                self.new_view.setText("")
            else:
                self.new_view.setPixmap(QPixmap())
                self.new_view.setText("Press Preview")
        except Exception:  # noqa: BLE001 — preview is optional
            pass

    def _pick_preview_page(self, doc) -> int:
        """The page with the most picture data (where compression is most visible)."""
        best, best_bytes = 0, -1
        by_xref = {i.xref: i.stream_bytes for i in self.profile.images}
        for page in doc:
            total = sum(by_xref.get(x[0], 0) for x in page.get_images(full=True))
            if total > best_bytes:
                best, best_bytes = page.number, total
        return best

    # ------------------------------------------------------------ accept / cancel

    def _on_ok(self) -> None:
        self._start(accept_after=True)

    def _finish_accept(self) -> None:
        res = self.result_
        if res is None:
            return
        if res.target_met is False and not self._headless():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Target size not reached")
            box.setText(res.status())
            box.setInformativeText("Keep this smallest acceptable result anyway?")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        if res.output_bytes >= res.source_bytes and not self._headless():
            resp = QMessageBox.question(self, "Compress PDF", "The result is not smaller than the current file. "
                                        "Save it anyway?")
            if resp != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancelled = True
            self.status.setText("Stopping…")
            return
        self.reject()

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.cancelled = True
            self._worker.wait()
            self._worker = None
        super().reject()


def _pct(new: int, old: int) -> str:
    if not old:
        return ""
    p = (1 - new / old) * 100
    return f"{p:.1f}% smaller" if p >= 0 else f"{-p:.1f}% larger"
