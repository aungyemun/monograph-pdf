"""Application status footer with window-centered copyright."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QStatusBar, QWidget

from core.product_meta import COPYRIGHT_DISPLAY, COPYRIGHT_OWNER, COPYRIGHT_START_YEAR


class AppStatusBar(QStatusBar):
    """
    Left: page / zoom
    Center: copyright (full window width)
    Right: progress (while busy) / Saved · Modified
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(True)
        self.setObjectName("AppStatusBar")

        self.page_label = QLabel("No document")
        self.page_label.setObjectName("StatusLeft")
        self.zoom_label = QLabel("")
        self.zoom_label.setObjectName("StatusLeft")
        self.dirty_label = QLabel("")
        self.dirty_label.setObjectName("StatusDirty")
        self.doc_state_label = QLabel("")
        self.doc_state_label.setObjectName("StatusRight")
        self.doc_state_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        # Idle is shown by "Saved" / "Modified"; a separate "Ready" word was redundant.
        self.ready_label = QLabel("")
        self.ready_label.setObjectName("StatusRight")
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("StatusRight")
        self.progress_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.progress_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self.addWidget(self.page_label)
        self.addWidget(self._sep())
        self.addWidget(self.zoom_label)

        # Permanent widgets appear right-to-left in reverse add order on some styles;
        # add so visual right edge is Ready / state / progress.
        self.addPermanentWidget(self.progress_label)
        self.addPermanentWidget(self.dirty_label)
        self.addPermanentWidget(self.doc_state_label)
        self.addPermanentWidget(self.ready_label)

        self.copyright_label = QLabel(COPYRIGHT_DISPLAY, self)
        self.copyright_label.setObjectName("StatusCopyright")
        self.copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.copyright_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        font = QFont(self.font())
        # Slightly more readable while remaining subtle
        font.setPointSize(max(9, font.pointSize()))
        self.copyright_label.setFont(font)
        self.copyright_label.setToolTip(COPYRIGHT_DISPLAY)
        self.copyright_label.show()
        # A temporary message hides the left widgets; when it ends, re-apply the width rules (and the
        # copyright steps aside while a long message would run under it)
        self.messageChanged.connect(lambda _m: self._relayout_for_width())

    def _sep(self) -> QLabel:
        lab = QLabel("·")
        lab.setObjectName("StatusSep")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lab

    def set_ready(self, text: str = "") -> None:
        self.ready_label.setText("" if text == "Ready" else text)
        self.ready_label.setVisible(bool(self.ready_label.text()))

    def set_analysis_progress(self, message: str) -> None:
        text = message or ""
        self.progress_label.setProperty("fullText", text)
        self.progress_label.setText(text)
        self.ready_label.setText("")
        self.ready_label.setVisible(False)
        self._relayout_for_width()

    def clear_analysis_progress(self) -> None:
        self.set_analysis_progress("")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_copyright()
        self._relayout_for_width()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.copyright_label.show()
        self._relayout_for_width()

    def _fit_copyright_text(self, max_width: int) -> str:
        metrics = self.copyright_label.fontMetrics()
        full = COPYRIGHT_DISPLAY
        if metrics.horizontalAdvance(full) <= max_width:
            return full
        short = f"© {COPYRIGHT_START_YEAR} {COPYRIGHT_OWNER}"
        if metrics.horizontalAdvance(short) <= max_width:
            return short
        return metrics.elidedText(short, Qt.TextElideMode.ElideRight, max_width)

    def _position_copyright(self) -> None:
        label = self.copyright_label
        label.show()
        bar_w = max(1, self.width())
        bar_h = max(1, self.height())
        max_w = max(40, bar_w - 8)
        text = self._fit_copyright_text(max_w)
        label.setText(text)
        label.setMaximumWidth(max_w)
        label.adjustSize()
        text_w = min(max_w, label.sizeHint().width())
        x = max(0, (bar_w - text_w) // 2)
        y = max(0, (bar_h - label.sizeHint().height()) // 2)
        label.setGeometry(x, y, text_w, label.sizeHint().height())
        label.raise_()
        message = self.currentMessage()
        if message:
            needed = self.fontMetrics().horizontalAdvance(message) + 16
            label.setVisible(needed < x)
        else:
            label.setVisible(True)

    def _relayout_for_width(self) -> None:
        w = self.width()
        show_doc = w >= 780
        show_sep = w >= 480
        show_zoom = w >= 420
        busy = bool(self.currentMessage())  # Qt hides the left widgets while a message is shown
        self.doc_state_label.setVisible(show_doc and bool(self.doc_state_label.text()))
        # Qt hides the left widgets for a message, but not if the message was shown before the window was
        # (the text then ran over "No document"): keep them in step with the message ourselves.
        self.page_label.setVisible(not busy)
        self.zoom_label.setVisible(not busy and show_zoom and bool(self.zoom_label.text()))
        if w < 560 and self.progress_label.text():
            metrics = self.progress_label.fontMetrics()
            full = self.progress_label.property("fullText") or self.progress_label.text()
            self.progress_label.setProperty("fullText", full)
            self.progress_label.setText(
                metrics.elidedText(
                    str(full), Qt.TextElideMode.ElideRight, max(60, w // 5)
                )
            )
            self.progress_label.setVisible(True)
        else:
            full = self.progress_label.property("fullText")
            if full and self.progress_label.text() != full and w >= 560:
                self.progress_label.setText(str(full))
            self.progress_label.setVisible(bool(self.progress_label.text()))
        for sep in self.findChildren(QLabel):
            if sep.objectName() == "StatusSep":
                sep.setVisible(not busy and show_sep and show_zoom)
        self._position_copyright()
