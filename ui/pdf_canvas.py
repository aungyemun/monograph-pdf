"""Central PDF canvas — viewer + real-time non-destructive editing overlays."""

from __future__ import annotations

from enum import Enum

from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
    QTextOption,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QScrollArea, QSizePolicy, QTextEdit, QWidget

from core.document import PdfDocument
from core.editing.edit_model import EditableDocument, EditTool, WorkspaceMode
from core.editing.geometry import Point, Rect
from core.editing.text_box import TextAlign, TextBox, VAlign
from core.editing.text_layout import layout_text_box
from core.forms.display import should_paint_field_overlay, visible_field_content
from core.forms.fields import FieldType, effective_valign
from core.page_info import PageInfo
from core.render_cache import RenderCache, RenderKey


class ZoomMode(str, Enum):
    MANUAL = "manual"
    FIT_WIDTH = "fit_width"
    FIT_PAGE = "fit_page"
    ACTUAL_SIZE = "actual_size"


_PT_TO_CSS = 96.0 / 72.0


def _theme_palette():
    try:
        from ui.theme import current_palette

        return current_palette()
    except Exception:  # noqa: BLE001
        return None
_HANDLE = 6  # logical px handle half-size


class _AlignedTextEdit(QTextEdit):
    """Plain-text editor whose text can be centred / right-aligned and placed top, middle or bottom.

    QTextEdit (not QPlainTextEdit): QPlainTextEdit shows aligned text but keeps the caret at the
    left edge, so typing in a centred field looked broken.
    """

    valign = "top"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.textChanged.connect(self.update_vertical_offset)
        # Re-centre when the text's height changes (new font size, wrapping, width)
        self.document().documentLayout().documentSizeChanged.connect(lambda _s: self.update_vertical_offset())

    def text(self) -> str:  # same API as QLineEdit for the canvas
        return self.toPlainText()

    def insertFromMimeData(self, source) -> None:  # noqa: N802 — paste keeps only the text
        if source is not None and source.hasText():
            self.textCursor().insertText(source.text())

    def update_vertical_offset(self) -> None:
        content = self.document().size().height()
        frame = self.height() - self.viewport().height() - self.viewportMargins().top()
        free = max(0, int(self.height() - frame - content))
        top = {"middle": free // 2, "bottom": free}.get(self.valign, 0)
        if self.viewportMargins().top() != top:
            self.setViewportMargins(0, top, 0, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update_vertical_offset()


class _FieldTextEdit(_AlignedTextEdit):
    """In-place editor for a text field — one line or wrapped — that keeps word formatting."""

    def __init__(self, parent=None, *, single_line: bool = False) -> None:
        super().__init__(parent)
        self.single_line = single_line
        self.px_per_pt = 1.0  # screen pixels per PDF point at the current zoom
        self.base_pt = 10.0  # size of text without its own size
        if single_line:
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    def setText(self, text: str) -> None:  # noqa: N802 — QLineEdit-style API kept for callers
        self.setPlainText(text)

    def insertFromMimeData(self, source) -> None:  # noqa: N802
        if source is not None and source.hasText():
            text = source.text()
            if self.single_line:
                text = " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
            self.textCursor().insertText(text)


def _field_qt_alignment(field) -> Qt.AlignmentFlag:
    """Qt alignment for a field's horizontal (align) and vertical (valign) setting."""
    h = {
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify if getattr(field, "multiline", False) else Qt.AlignmentFlag.AlignLeft,
    }.get(str(getattr(field, "align", "left") or "left"), Qt.AlignmentFlag.AlignLeft)
    v = {"top": Qt.AlignmentFlag.AlignTop, "bottom": Qt.AlignmentFlag.AlignBottom}.get(
        effective_valign(field), Qt.AlignmentFlag.AlignVCenter
    )
    return h | v


class _CanvasWidget(QWidget):
    fieldValueEdited = Signal(str, str)  # field id, live text
    fieldEditorFormatChanged = Signal(dict)  # look at the caret while typing in a field
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    selectionChanged = Signal()
    editModelChanged = Signal()
    requestStatus = Signal(str)
    regionPickCancelled = Signal()
    # PDF annotations (comments, stamps ...) selected with the Select tool: page, xref
    annotationSelected = Signal(int, int)
    annotationMoveRequested = Signal(int, int, float, float)  # page, xref, dx, dy (unrotated page space)
    annotationDeleteRequested = Signal(int, int)
    annotationEditRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._document: PdfDocument | None = None
        self._edit: EditableDocument | None = None
        self._pages: list[PageInfo] = []
        self._zoom = 1.0
        self._zoom_mode = ZoomMode.FIT_WIDTH
        self._page_gap = 12
        self._side_pad = 16
        self._layouts: list[QRect] = []
        self._cache: RenderCache[RenderKey, QPixmap] = RenderCache(max_entries=20)
        self._focus_page = 0
        self._retain_radius = 3
        self._highlights: list[tuple[int, object]] = []
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(16)
        self._render_timer.timeout.connect(self._render_visible)
        self.setAutoFillBackground(True)

        # Interaction state
        self._mode = "idle"  # idle|drag_create|drag_move|drag_resize|typing
        self._press_pos: QPoint | None = None
        self._press_pdf: Point | None = None
        self._press_page: int = 0
        self._drag_before: dict[str, Rect] = {}
        self._resize_handle: str | None = None
        self._resize_oid: str | None = None
        self._create_origin: Point | None = None
        self._create_current: Point | None = None
        self._text_before: str = ""
        self._field_value_before: str = ""
        self._object_clipboard: list[dict] = []
        self._form_create_type: str | None = None
        self._shape_create_kind: str | None = None
        self._freehand_points: list[tuple[float, float]] = []
        self._shift_constrain: bool = False
        self._drag_shape_lines: dict[str, tuple[float, float, float, float]] = {}
        self._drag_shape_points: dict[str, list[tuple[float, float]]] = {}
        # During drag/resize/typing: repaint overlays only — do not rebuild inspector/toolbar
        self._live_interaction: bool = False
        self._hover_field_id: str | None = None
        self._drag_perf: list[float] = []
        # Region pick (draw-to-place for annotations, redaction, stamps, signatures)
        self._region_pick: tuple[str, Callable[[int, Rect, bool], None], str] | None = None
        # Selected PDF annotation: (page, xref, kind, display rect); drag offset while moving
        self._annot_sel: tuple[int, int, str, Rect] | None = None
        self._annot_drag: tuple[float, float] | None = None
        self._region_origin: Point | None = None
        self._region_current: Point | None = None
        self._region_page: int = 0
        self._region_stroke: list[Point] = []
        self._region_stroke_color = QColor(255, 235, 59)
        self._stroke_locked_color: QColor | None = None
        self._region_stroke_aborted: bool = False
        self._last_region_stroke: list[Point] = []
        # In-place form-field editor (real text widget: selection, caret, clipboard, undo)
        self._field_editor: QWidget | None = None
        self._field_editor_id: str | None = None
        # In-place text-box editor
        self._text_editor: _AlignedTextEdit | None = None
        self._text_editor_id: str | None = None
        self._text_editor_before: str = ""

    # --- document / edit model -------------------------------------------

    def clear_document(self) -> None:
        self._annot_sel = None
        if self._edit is not None:
            self._edit.remove_listener(self._on_edit_changed)
        self._cache.clear()
        self._document = None
        self._edit = None
        self._pages = []
        self._layouts = []
        self._highlights = []
        self._focus_page = 0
        self._mode = "idle"
        self._live_interaction = False
        self._hover_field_id = None
        self._region_pick = None
        self._region_origin = None
        self._region_current = None
        self._region_stroke = []
        self._stroke_locked_color = None
        self._region_stroke_aborted = False
        self._last_region_stroke = []
        self._discard_field_editor()
        self._discard_text_editor()
        self.updateGeometry()
        self.update()

    def set_document(self, document: PdfDocument) -> None:
        self.clear_document()
        self._document = document
        self._pages = list(document.pages())
        self._recompute_layout()
        self._schedule_render()

    def set_edit_model(self, edit: EditableDocument | None) -> None:
        if self._edit is not None:
            self._edit.remove_listener(self._on_edit_changed)
        self._edit = edit
        if edit is not None:
            edit.add_listener(self._on_edit_changed)
        self.update()

    def _on_edit_changed(self) -> None:
        if self._text_editor is not None:
            self.refresh_text_editor()
        if self._field_editor is not None:
            self.restyle_field_editor()  # toolbar change, undo / redo
        # Overlay-only path during interactive drag/type — native PDF cache stays untouched
        if self._live_interaction:
            self.update()
            return
        self.editModelChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def _end_live_interaction(self) -> None:
        self._live_interaction = False
        self.editModelChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def set_highlights(self, hits: list[tuple[int, object]]) -> None:
        self._highlights = hits
        self.update()

    def clear_highlights(self) -> None:
        self._highlights = []
        self.update()

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    @property
    def focus_page(self) -> int:
        return self._focus_page

    @property
    def edit_model(self) -> EditableDocument | None:
        return self._edit

    def set_tool(self, tool: EditTool) -> None:
        if self._edit is None:
            return
        self._edit.tool = tool
        shape_tools = {
            EditTool.SHAPE_RECT,
            EditTool.SHAPE_ELLIPSE,
            EditTool.SHAPE_LINE,
            EditTool.SHAPE_ARROW,
            EditTool.SHAPE_FREEHAND,
        }
        if tool == EditTool.TEXT_BOX or tool in shape_tools:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    # --- region pick ---------------------------------------------------------

    @property
    def region_pick_active(self) -> bool:
        return self._region_pick is not None

    def begin_region_pick(
        self,
        prompt: str,
        callback: Callable[[int, Rect, bool], None],
        *,
        kind: str = "rect",
        stroke_color: QColor | None = None,
    ) -> None:
        """Next drag (or click) on a page calls ``callback(page, rect, was_click)``.

        ``rect`` is in display PDF points (same space as overlays). ``kind`` is
        ``"rect"`` (drag a box), ``"point"`` / ``"erase"`` (single click), or ``"stroke"``
        (freehand pen — stroke samples available via ``take_region_stroke``). Esc cancels.
        """
        self._region_pick = (prompt, callback, kind)
        self._region_stroke_color = QColor(stroke_color) if stroke_color is not None else QColor(255, 235, 59)
        self._region_origin = None
        self._region_current = None
        self._region_stroke = []
        self._stroke_locked_color = None
        self._region_stroke_aborted = False
        self._last_region_stroke = []
        if kind == "stroke":
            self.setCursor(self._marker_cursor())
        elif kind == "erase":
            self.setCursor(self._eraser_cursor())
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        tip = "Esc cancels the stroke; Esc again exits" if kind == "stroke" else "Esc to cancel"
        self.requestStatus.emit(f"{prompt} — {tip}")
        self.update()

    @property
    def region_stroke_in_progress(self) -> bool:
        """True while the mouse is down (or a stroke was started) during a region pick."""
        return self._region_pick is not None and (
            self._region_origin is not None or bool(self._region_stroke)
        )

    def set_region_stroke_color(self, color: QColor) -> None:
        """Update the pen preview colour for the next stroke (does not recolour a stroke in progress)."""
        self._region_stroke_color = QColor(color)
        if self._region_pick is not None and self._region_pick[2] == "stroke" and not self.region_stroke_in_progress:
            self.setCursor(self._marker_cursor())
            self.update()

    def take_stroke_locked_color(self) -> QColor | None:
        """Colour frozen when the current/last stroke began (RGB for MuPDF)."""
        c = self._stroke_locked_color
        self._stroke_locked_color = None
        return QColor(c) if c is not None else None

    def abort_active_region_stroke(self) -> bool:
        """Discard an unfinished stroke preview; keep the pick armed. Returns True if a stroke was aborted."""
        if self._region_pick is None or not self.region_stroke_in_progress:
            return False
        self._region_stroke_aborted = True
        self._region_origin = None
        self._region_current = None
        self._region_stroke = []
        self._last_region_stroke = []
        self._stroke_locked_color = None
        kind = self._region_pick[2]
        if kind == "stroke":
            self.setCursor(self._marker_cursor())
        elif kind == "erase":
            self.setCursor(self._eraser_cursor())
        self.requestStatus.emit("Stroke cancelled — keep drawing, or Esc to exit")
        self.update()
        return True

    def _marker_cursor(self):
        """Highlighter cursor: a crosshair with a swatch of the chosen colour beside it."""
        from PySide6.QtGui import QCursor, QPixmap

        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(30, 30, 30), 1))
        p.drawLine(4, 12, 20, 12)
        p.drawLine(12, 4, 12, 20)
        sw = QColor(self._region_stroke_color)
        p.setBrush(sw)
        p.setPen(QPen(QColor(30, 30, 30), 1))
        p.drawRoundedRect(18, 18, 12, 10, 2, 2)
        p.end()
        return QCursor(pm, 12, 12)

    def _eraser_cursor(self):
        """Eraser cursor: a small angled rectangle tip."""
        from PySide6.QtGui import QCursor, QPixmap, QTransform

        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(40, 40, 40), 1.2))
        p.setBrush(QColor(245, 245, 245))
        p.translate(16, 16)
        p.rotate(-35)
        p.drawRoundedRect(-5, -3, 14, 8, 1.5, 1.5)
        p.setBrush(QColor(180, 80, 80))
        p.drawRect(6, -3, 4, 8)
        p.end()
        return QCursor(pm, 10, 22)

    def cancel_region_pick(self, *, announce: bool = True) -> None:
        if self._region_pick is None:
            return
        self._region_pick = None
        self._region_origin = None
        self._region_current = None
        self._region_stroke = []
        self._stroke_locked_color = None
        self._region_stroke_aborted = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if announce:
            self.requestStatus.emit("Cancelled")
            self.regionPickCancelled.emit()
        self.update()

    def take_region_stroke(self) -> list[Point]:
        """Stroke samples from the last finished ``stroke`` region pick (display PDF points)."""
        pts = list(self._last_region_stroke)
        self._last_region_stroke = []
        return pts

    def set_zoom_mode(self, mode: ZoomMode, viewport_size: QSize) -> None:
        self._zoom_mode = mode
        self.apply_zoom_for_viewport(viewport_size)

    def set_manual_zoom(self, zoom: float, viewport_size: QSize) -> None:
        self._zoom_mode = ZoomMode.MANUAL
        self._zoom = max(0.1, min(8.0, zoom))
        self._recompute_layout()
        self._cache.clear()
        self.zoomChanged.emit(self._zoom)
        self._schedule_render()
        _ = viewport_size

    def apply_zoom_for_viewport(self, viewport_size: QSize) -> None:
        if not self._pages or viewport_size.width() <= 0:
            return
        page = self._pages[min(self._focus_page, len(self._pages) - 1)]
        avail_w = max(50, viewport_size.width() - 2 * self._side_pad)
        avail_h = max(50, viewport_size.height() - 2 * self._page_gap)
        page_w = page.display_width_pt * _PT_TO_CSS
        page_h = page.display_height_pt * _PT_TO_CSS
        if self._zoom_mode == ZoomMode.ACTUAL_SIZE:
            z = 1.0
        elif self._zoom_mode == ZoomMode.FIT_WIDTH:
            z = avail_w / page_w
        elif self._zoom_mode == ZoomMode.FIT_PAGE:
            z = min(avail_w / page_w, avail_h / page_h)
        else:
            z = self._zoom
        self._zoom = max(0.1, min(8.0, z))
        self._recompute_layout()
        self._cache.clear()
        self.zoomChanged.emit(self._zoom)
        self._schedule_render()

    def page_at_y(self, y: int) -> int:
        for i, rect in enumerate(self._layouts):
            if rect.top() <= y <= rect.bottom():
                return i
        if not self._layouts:
            return 0
        if y < self._layouts[0].top():
            return 0
        return len(self._layouts) - 1

    def page_top(self, index: int) -> int:
        if 0 <= index < len(self._layouts):
            return self._layouts[index].top()
        return 0

    def _recompute_layout(self) -> None:
        if self._field_editor is not None:
            self.close_field_editor(commit=True)
        if self._text_editor is not None:
            self.close_text_editor(commit=True)
        self._layouts = []
        y = self._page_gap
        max_w = 0
        for page in self._pages:
            w = int(page.display_width_pt * _PT_TO_CSS * self._zoom)
            h = int(page.display_height_pt * _PT_TO_CSS * self._zoom)
            max_w = max(max_w, w)
            self._layouts.append(QRect(self._side_pad, y, w, h))
            y += h + self._page_gap
        self.setMinimumSize(QSize(max_w + 2 * self._side_pad, y + self._page_gap))
        self.resize(self.minimumSize())
        self.updateGeometry()
        self.update()

    def notify_viewport(self, visible: QRect) -> None:
        if not self._layouts:
            return
        mid_y = visible.center().y()
        page = self.page_at_y(mid_y)
        if page != self._focus_page:
            self._focus_page = page
            self.pageChanged.emit(page)
        self._schedule_render()

    def _schedule_render(self) -> None:
        self._render_timer.start()

    def _device_pixel_ratio(self) -> float:
        window = self.window()
        if window is not None:
            screen = window.screen()
            if screen is not None:
                return float(screen.devicePixelRatio())
        app = QApplication.instance()
        if app is not None:
            return float(app.devicePixelRatio())
        return 1.0

    def _scale(self, page_index: int) -> tuple[float, float]:
        page = self._pages[page_index]
        layout = self._layouts[page_index]
        sx = layout.width() / max(page.display_width_pt, 1.0)
        sy = layout.height() / max(page.display_height_pt, 1.0)
        return sx, sy

    def widget_to_pdf(self, pos: QPoint) -> tuple[int, Point] | None:
        page_index = self.page_at_y(pos.y())
        if page_index < 0 or page_index >= len(self._layouts):
            return None
        layout = self._layouts[page_index]
        if not layout.contains(pos) and not (
            layout.left() <= pos.x() <= layout.right()
        ):
            # Still map onto nearest page vertically
            pass
        sx, sy = self._scale(page_index)
        x = (pos.x() - layout.left()) / max(sx, 1e-6)
        y = (pos.y() - layout.top()) / max(sy, 1e-6)
        return page_index, Point(x, y)

    def pdf_rect_to_widget(self, page_index: int, rect: Rect) -> QRect | None:
        if page_index < 0 or page_index >= len(self._layouts):
            return None
        layout = self._layouts[page_index]
        sx, sy = self._scale(page_index)
        return QRect(
            layout.left() + int(rect.x * sx),
            layout.top() + int(rect.y * sy),
            max(1, int(rect.w * sx)),
            max(1, int(rect.h * sy)),
        )

    def pdf_to_widget(self, page_index: int, pt: Point) -> QPoint | None:
        if page_index < 0 or page_index >= len(self._layouts):
            return None
        layout = self._layouts[page_index]
        sx, sy = self._scale(page_index)
        return QPoint(layout.left() + int(pt.x * sx), layout.top() + int(pt.y * sy))

    def _render_visible(self) -> None:
        if self._document is None or self._document.is_closed or not self._layouts:
            return
        visible = self.visibleRegion().boundingRect()
        if visible.isNull():
            top = self.page_top(self._focus_page)
            visible = QRect(0, max(0, top - 200), self.width(), 1200)
        first = self.page_at_y(visible.top())
        last = self.page_at_y(visible.bottom())
        dpr = self._device_pixel_ratio()
        for i in range(max(0, first - 1), min(len(self._layouts), last + 2)):
            key = RenderKey.make(i, self._zoom, self._pages[i].rotation, dpr)
            if self._cache.get(key) is not None:
                continue
            try:
                png = self._document.render_pixmap_png(i, zoom=self._zoom * _PT_TO_CSS, dpr=dpr)
                image = QImage.fromData(png, "PNG")
                pix = QPixmap.fromImage(image)
                pix.setDevicePixelRatio(dpr)
                self._cache.put(key, pix)
            except Exception:  # noqa: BLE001
                continue
        self._cache.retain_near_pages(self._focus_page, self._retain_radius, lambda k: k.page_index)
        self.update()

    # --- painting --------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        pal = _theme_palette()
        # Neutral workspace distinct from white PDF pages (theme-aware)
        painter.fillRect(event.rect(), QColor(pal.canvas if pal else "#dde1e7"))
        if not self._layouts or self._document is None:
            painter.end()
            return
        dpr = self._device_pixel_ratio()
        clip = event.rect()
        for i, rect in enumerate(self._layouts):
            if not rect.intersects(clip):
                continue
            # Soft layered page shadow + clear boundary
            for spread, alpha in ((4, 14), (2, 26), (1, 34)):
                painter.fillRect(rect.adjusted(-spread + 1, -spread + 2, spread + 1, spread + 2), QColor(0, 0, 0, alpha))
            painter.fillRect(rect, QColor("#ffffff"))
            painter.setPen(QPen(QColor(pal.page_border if pal else "#c3c9d2"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            key = RenderKey.make(i, self._zoom, self._pages[i].rotation, dpr)
            pix = self._cache.get(key)
            if pix is not None:
                painter.drawPixmap(rect, pix)
            for page_index, pdf_rect in self._highlights:
                if page_index != i:
                    continue
                hr = self._pdf_rect_to_widget(i, pdf_rect)
                if hr is not None:
                    painter.fillRect(hr, QColor(255, 220, 0, 100))
            if self._edit is not None:
                self._paint_overlays(painter, i)
                self._paint_forms(painter, i)
                self._paint_tables(painter, i)
        if self._mode == "drag_create" and self._create_origin and self._create_current:
            from core.editing.shape_box import constrain_line_angle, constrain_rect_aspect

            painter.setPen(QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(37, 99, 235, 40))
            kind = self._shape_create_kind
            if kind == "freehand" and self._freehand_points:
                pts = []
                for x, y in self._freehand_points:
                    wp = self.pdf_to_widget(self._press_page, Point(x, y))
                    if wp is not None:
                        pts.append(wp)
                for i in range(1, len(pts)):
                    painter.drawLine(pts[i - 1], pts[i])
            elif kind in ("line", "arrow"):
                end = constrain_line_angle(
                    self._create_origin, self._create_current, snap=self._shift_constrain
                )
                p0 = self.pdf_to_widget(self._press_page, self._create_origin)
                p1 = self.pdf_to_widget(self._press_page, end)
                if p0 and p1:
                    painter.drawLine(p0, p1)
            elif kind in ("rectangle", "ellipse"):
                r = constrain_rect_aspect(
                    self._create_origin, self._create_current, square=self._shift_constrain
                )
                wr = self.pdf_rect_to_widget(self._press_page, r)
                if wr:
                    if kind == "ellipse":
                        painter.drawEllipse(wr)
                    else:
                        painter.drawRect(wr)
            else:
                r = Rect.from_points(self._create_origin, self._create_current)
                wr = self.pdf_rect_to_widget(self._press_page, r)
                if wr:
                    painter.drawRect(wr)
        if self._region_pick is not None and self._region_origin and self._region_current:
            kind = self._region_pick[2]
            if kind == "stroke" and len(self._region_stroke) >= 2:
                from PySide6.QtGui import QPainterPath

                path = QPainterPath()
                first = True
                for pt in self._region_stroke:
                    wp = self.pdf_to_widget(self._region_page, pt)
                    if wp is None:
                        continue
                    if first:
                        path.moveTo(wp)
                        first = False
                    else:
                        path.lineTo(wp)
                if not first:
                    # Marker preview: the chosen color, see-through like the saved highlight,
                    # about one text line tall at the current zoom, with a flat marker tip.
                    ink = QColor(self._region_stroke_color)
                    ink.setAlpha(110)
                    pen = QPen(ink, max(4.0, 11.0 * self._zoom), Qt.PenStyle.SolidLine)
                    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    pen.setJoinStyle(Qt.PenJoinStyle.BevelJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
            else:
                r = Rect.from_points(self._region_origin, self._region_current)
                wr = self.pdf_rect_to_widget(self._region_page, r)
                if wr:
                    pen = QPen(QColor("#d97706"), 1.5, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(QColor(217, 119, 6, 38))
                    painter.drawRect(wr)
        painter.end()

    def _paint_forms(self, painter: QPainter, page_index: int) -> None:
        """
        Form overlays must never replace PDF page /AP with field names or SOM paths.

        Unmodified AcroForm widgets: trust MuPDF page render (appearance streams).
        Forms mode: optional outline chrome only. User-placed / dirty fields: value text.
        Highlight fillable: UI-only light overlay (never baked into Save).
        """
        assert self._edit is not None
        forms_mode = self._edit.mode == WorkspaceMode.FORMS
        highlight = bool(getattr(self._edit, "highlight_fillable_fields", False))
        for field in self._edit.fields_on_page(page_index):
            wr = self.pdf_rect_to_widget(page_index, field.rect)
            if wr is None:
                continue
            policy = should_paint_field_overlay(
                field, forms_mode=forms_mode, highlight_fillable=highlight
            )
            selected = field.object_id in self._edit.field_selection
            focused = field.object_id == getattr(self._edit, "editing_field_id", None)
            hovered = field.object_id == self._hover_field_id

            if policy == "none":
                if selected or focused:
                    painter.setPen(QPen(QColor("#2563eb"), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(wr)
                    self._paint_field_handles(painter, field, wr)
                continue

            if policy == "highlight":
                # Subtle UI-only fillable hint — never replaces /AP text
                alpha = 70 if hovered or focused else 36
                if field.readonly:
                    painter.fillRect(wr, QColor(148, 163, 184, 28))
                else:
                    painter.fillRect(wr, QColor(147, 197, 253, alpha))
                pen_w = 2 if focused else (1 + int(hovered or selected))
                painter.setPen(QPen(QColor("#2563eb" if (focused or selected) else "#60a5fa"), pen_w))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wr)
                if selected or focused:
                    self._paint_field_handles(painter, field, wr)
                if focused and self._field_editor is None and field.field_type not in (FieldType.CHECKBOX, FieldType.RADIO):
                    # caret hint for active fill
                    painter.setPen(QPen(QColor("#111827"), 1))
                    painter.drawLine(wr.left() + 4, wr.top() + 3, wr.left() + 4, wr.bottom() - 3)
                continue

            if policy == "chrome":
                painter.setPen(QPen(QColor("#2563eb" if selected or focused else "#93c5fd"), 1 + int(selected or focused)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wr)
                continue

            if policy == "candidate":
                painter.setPen(QPen(QColor("#d97706"), 1, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(251, 191, 36, 50))
                painter.drawRect(wr)
                label = (field.candidate_label or "").strip()
                if label and "topmostSubform" not in label:
                    painter.setPen(QColor("#92400e"))
                    font = QFont("Segoe UI")
                    font.setPixelSize(max(9, int(11 * (wr.height() / max(field.rect.h, 1)))))
                    painter.setFont(font)
                    painter.drawText(
                        wr.adjusted(3, 1, -3, -1),
                        Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine,
                        label,
                    )
                if selected:
                    painter.setPen(QPen(QColor("#2563eb"), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(wr)
                continue

            # content — user-placed or dirty value; never fall back to field.name
            # Only the field's own border / background — none when the PDF field has none
            fill = QColor(field.fill_color or "#00000000")
            if fill.isValid() and fill.alpha() > 0:
                painter.fillRect(wr, fill)
            border = QColor(field.border_color or "#00000000")
            if border.isValid() and border.alpha() > 0 and float(field.border_width or 0) > 0:
                painter.setPen(QPen(border, max(1, round(float(field.border_width) * wr.height() / max(field.rect.h, 1)))))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wr)
            text = visible_field_content(field)
            if text:
                from core.forms.autofit import effective_form_font_size, form_text_overflows

                painter.setPen(QColor(field.text_color))
                font = QFont(field.font_family or "Segoe UI")
                font.setBold(bool(getattr(field, "bold", False)))
                font.setItalic(bool(getattr(field, "italic", False)))
                fs = effective_form_font_size(field, text)
                font.setPixelSize(max(8, int(fs * (wr.height() / max(field.rect.h, 1)))))
                painter.setFont(font)
                if field.runs and "".join(r["text"] for r in field.runs) == text:
                    from ui.rich_field_text import paint_runs

                    paint_runs(
                        painter, field, QRectF(wr.adjusted(3, 1, -3, -1)), wr.height() / max(field.rect.h, 1),
                        font, _field_qt_alignment(field) & Qt.AlignmentFlag.AlignHorizontal_Mask,
                        effective_valign(field), bool(field.multiline),
                    )
                else:
                    flags = _field_qt_alignment(field) | (
                        Qt.TextFlag.TextWordWrap if field.multiline else Qt.TextFlag.TextSingleLine
                    )
                    painter.drawText(wr.adjusted(3, 1, -3, -1), flags, text)
                from core.forms.appearance import entry_overflows

                # Part of the entry is hidden (box too small for the size): it would not print
                if form_text_overflows(field, text) or entry_overflows(field, text):
                    painter.setPen(QPen(QColor("#dc2626"), 1))
                    painter.drawText(
                        wr.adjusted(0, 0, -2, -1),
                        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                        "!",
                    )
            if selected or focused:
                painter.setPen(QPen(QColor("#2563eb"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wr)
                self._paint_field_handles(painter, field, wr)
            if focused and self._field_editor is None and field.field_type not in (FieldType.CHECKBOX, FieldType.RADIO):
                metrics = painter.fontMetrics()
                caret_x = wr.left() + 3 + metrics.horizontalAdvance(text or "")
                painter.setPen(QPen(QColor("#111827"), 1))
                painter.drawLine(caret_x, wr.top() + 2, caret_x, wr.bottom() - 2)

    def _paint_tables(self, painter: QPainter, page_index: int) -> None:
        assert self._edit is not None
        for table in self._edit.tables.values():
            if table.page_index != page_index:
                continue
            for r in range(table.nrows):
                for c in range(table.ncols):
                    cell = table.cells.get((r, c))
                    if cell is None:
                        continue
                    wr = self.pdf_rect_to_widget(page_index, table.cell_rect(r, c))
                    if wr is None:
                        continue
                    painter.setPen(QPen(QColor(cell.border_color), max(1, int(cell.border_width))))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(wr)
                    if cell.text:
                        painter.setPen(QColor("#111827"))
                        font = QFont("Segoe UI")
                        font.setPixelSize(max(8, int(wr.height() * 0.45)))
                        painter.setFont(font)
                        painter.drawText(wr.adjusted(2, 1, -2, -1), Qt.TextFlag.TextWordWrap, cell.text)

    def _paint_overlays(self, painter: QPainter, page_index: int) -> None:
        assert self._edit is not None
        # Guides
        layout = self._layouts[page_index]
        sx, sy = self._scale(page_index)
        for g in self._edit.guides:
            painter.setPen(QPen(QColor("#f59e0b"), 1, Qt.PenStyle.DashLine))
            if g.orientation == "v":
                x = layout.left() + int(g.position * sx)
                painter.drawLine(x, layout.top(), x, layout.bottom())
            else:
                y = layout.top() + int(g.position * sy)
                painter.drawLine(layout.left(), y, layout.right(), y)

        # Existing text being replaced: cover the original glyphs with the page's background colour
        # (Save removes them from the page content; see core/editing/native_text.py)
        prefix = f"p{page_index}-"
        for sid, plan in self._edit.native_replacements.items():
            rect_t = plan.get("rect")
            if not str(sid).startswith(prefix) or not rect_t:
                continue
            cr = self.pdf_rect_to_widget(page_index, Rect(*rect_t))
            if cr is not None:
                painter.fillRect(cr.adjusted(-1, -1, 1, 1), QColor(str(plan.get("cover") or "#ffffff")))

        # Text boxes, pictures and shapes in their stacking order — the same order Save uses
        # (engines/bake_edits.py overlays_in_order)
        items = [("text", o) for o in self._edit.objects_on_page(page_index)]
        items += [("image", o) for o in self._edit.images_on_page(page_index)]
        items += [("shape", o) for o in self._edit.shapes_on_page(page_index)]
        rank = {"text": 0, "image": 1, "shape": 2}
        items.sort(key=lambda it: (int(getattr(it[1], "z_index", 0)), rank[it[0]]))
        for kind, obj in items:
            wr = self.pdf_rect_to_widget(page_index, obj.rect)
            if kind == "shape":
                self._paint_shape(painter, page_index, obj)
            elif wr is None:
                continue
            elif kind == "text":
                self._paint_textbox(painter, obj, wr)
            else:
                self._paint_image(painter, obj, wr)
            if wr is not None and obj.object_id in self._edit.selection:
                painter.setPen(QPen(QColor("#2563eb"), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wr)
                for hx, hy in self._handle_points(wr):
                    painter.fillRect(QRect(hx - _HANDLE // 2, hy - _HANDLE // 2, _HANDLE, _HANDLE), QColor("#2563eb"))
            if kind == "text" and wr is not None and obj.overflow:
                painter.setPen(QPen(QColor("#dc2626"), 2))
                painter.drawRect(wr.adjusted(1, 1, -1, -1))
                painter.drawText(wr.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "!")

        if self._annot_sel is not None and self._annot_sel[0] == page_index:
            dx, dy = self._annot_drag or (0.0, 0.0)
            ar = self.pdf_rect_to_widget(page_index, self._annot_sel[3].translated(dx, dy))
            if ar is not None:
                pen = QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(ar.adjusted(-2, -2, 2, 2))

    def _paint_shape(self, painter: QPainter, page_index: int, shape) -> None:
        angle = float(getattr(shape, "rotation", 0.0) or 0.0) % 360.0
        wr = self.pdf_rect_to_widget(page_index, shape.rect)
        if min(angle, 360.0 - angle) > 0.01 and wr is not None:
            # Turned clockwise about the shape's box centre — the same as Save
            painter.save()
            c = QRectF(wr).center()
            painter.translate(c)
            painter.rotate(angle)
            painter.translate(-c)
            try:
                self._paint_shape_upright(painter, page_index, shape)
            finally:
                painter.restore()
            return
        self._paint_shape_upright(painter, page_index, shape)

    def _paint_shape_upright(self, painter: QPainter, page_index: int, shape) -> None:
        from core.editing.shape_box import ShapeKind, StrokeStyle

        stroke = QColor(shape.stroke_color)
        stroke.setAlphaF(min(1.0, float(shape.opacity)))
        fill = QColor(shape.fill_color)
        if fill.alpha() > 0:
            fill.setAlphaF(min(1.0, float(shape.fill_opacity) * float(shape.opacity) * fill.alphaF()))
        else:
            fill = Qt.GlobalColor.transparent
        style = Qt.PenStyle.SolidLine
        if shape.stroke_style == StrokeStyle.DASHED:
            style = Qt.PenStyle.DashLine
        elif shape.stroke_style == StrokeStyle.DOTTED:
            style = Qt.PenStyle.DotLine
        pen = QPen(stroke, max(1, int(shape.stroke_width * max(self._zoom, 0.5))))
        pen.setStyle(style)
        painter.setPen(pen)
        if fill == Qt.GlobalColor.transparent or (isinstance(fill, QColor) and fill.alpha() == 0):
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setBrush(fill)

        kind = shape.kind
        if kind in (ShapeKind.LINE, ShapeKind.ARROW):
            p0 = self.pdf_to_widget(page_index, Point(shape.x0, shape.y0))
            p1 = self.pdf_to_widget(page_index, Point(shape.x1, shape.y1))
            if p0 is None or p1 is None:
                return
            painter.drawLine(p0, p1)
            if kind == ShapeKind.ARROW:
                import math

                ang = math.atan2(p1.y() - p0.y(), p1.x() - p0.x())
                ah = 10
                for aoff in (2.5, -2.5):
                    ax = int(p1.x() - ah * math.cos(ang + aoff))
                    ay = int(p1.y() - ah * math.sin(ang + aoff))
                    painter.drawLine(p1, QPoint(ax, ay))
            return
        if kind == ShapeKind.FREEHAND and shape.points:
            pts = []
            for x, y in shape.points:
                wp = self.pdf_to_widget(page_index, Point(x, y))
                if wp is not None:
                    pts.append(wp)
            if len(pts) >= 2:
                for i in range(1, len(pts)):
                    painter.drawLine(pts[i - 1], pts[i])
            return
        wr = self.pdf_rect_to_widget(page_index, shape.rect)
        if wr is None:
            return
        if kind == ShapeKind.ELLIPSE:
            painter.drawEllipse(wr)
        else:
            painter.drawRect(wr)

    def _paint_image(self, painter: QPainter, img, wr: QRect) -> None:
        from pathlib import Path

        path = Path(getattr(img, "source_path", "") or "")
        if path.is_file():
            pix = QPixmap(str(path))
            if not pix.isNull():
                painter.save()
                painter.setOpacity(max(0.05, min(1.0, float(getattr(img, "opacity", 1.0)))))
                if abs(float(getattr(img, "rotation", 0.0))) > 0.01:
                    painter.translate(wr.center())
                    painter.rotate(float(img.rotation))
                    painter.translate(-wr.center())
                painter.drawPixmap(wr, pix)
                painter.restore()
                return
        painter.fillRect(wr, QColor(200, 200, 210, 120))
        painter.setPen(QPen(QColor("#64748b"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(wr)
        painter.drawText(wr, Qt.AlignmentFlag.AlignCenter, "Image")

    def _paint_textbox(self, painter: QPainter, box: TextBox, wr: QRect) -> None:
        angle = float(getattr(box.style, "rotation", 0.0) or 0.0) % 360.0
        if min(angle, 360.0 - angle) > 0.01 and box.object_id != self._text_editor_id:
            # Turned about the box centre, clockwise — the same as Save (engines/bake_edits.py)
            painter.save()
            c = QRectF(wr).center()
            painter.translate(c)
            painter.rotate(angle)
            painter.translate(-c)
            try:
                self._paint_textbox_upright(painter, box, wr)
            finally:
                painter.restore()
            return
        self._paint_textbox_upright(painter, box, wr)

    def _paint_textbox_upright(self, painter: QPainter, box: TextBox, wr: QRect) -> None:
        layout = layout_text_box(box)
        bg = QColor(box.style.background_color)
        if bg.alpha() > 0:
            bg.setAlphaF(min(1.0, box.style.opacity) * (bg.alphaF() if bg.alpha() else 1.0))
            painter.fillRect(wr, bg)
        border = QColor(box.style.border_color)
        if border.alpha() > 0 and box.style.border_width > 0:
            border.setAlphaF(border.alphaF() * min(1.0, box.style.opacity))
            painter.setPen(QPen(border, max(1, int(box.style.border_width))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(wr)
        # Text
        pad = int(box.style.padding * (wr.width() / max(box.rect.w, 1)))
        text_rect = wr.adjusted(pad, pad, -pad, -pad)
        font = QFont(layout.resolved_font or box.style.font_family)
        # Scale font to widget pixels
        sx = wr.width() / max(box.rect.w, 1)
        font.setPointSizeF(max(1.0, layout.font_size * sx * (72.0 / 96.0) * (_PT_TO_CSS)))
        # Simpler: size in logical px ≈ font_size * sx * (96/72) / something
        font.setPixelSize(max(8, int(layout.font_size * sx)))
        font.setBold(box.style.bold)
        font.setItalic(box.style.italic)
        font.setUnderline(box.style.underline)
        tracking = float(getattr(box.style, "character_spacing", 0.0) or 0.0)
        if tracking:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking * sx)
        painter.setFont(font)
        color = QColor(box.style.text_color)
        color.setAlphaF(min(1.0, box.style.opacity))
        painter.setPen(color)
        align = Qt.AlignmentFlag.AlignLeft
        if box.align == TextAlign.CENTER:
            align = Qt.AlignmentFlag.AlignHCenter
        elif box.align == TextAlign.RIGHT:
            align = Qt.AlignmentFlag.AlignRight
        if box.valign == VAlign.MIDDLE:
            align |= Qt.AlignmentFlag.AlignVCenter
        elif box.valign == VAlign.BOTTOM:
            align |= Qt.AlignmentFlag.AlignBottom
        else:
            align |= Qt.AlignmentFlag.AlignTop
        flags = int(align) | (int(Qt.TextFlag.TextWordWrap) if getattr(box.style, "wrap", True) else 0)
        if box.object_id == self._text_editor_id:
            return  # the live editor draws the text (with caret + selection)
        painter.drawText(text_rect, flags, box.text)
        if box.object_id == (self._edit.editing_object_id if self._edit else None):
            # caret hint at end
            painter.setPen(QPen(QColor("#111827"), 1))
            metrics = painter.fontMetrics()
            lines = box.text.split("\n") or [""]
            last = lines[-1]
            caret_x = text_rect.left() + metrics.horizontalAdvance(last)
            caret_y = text_rect.top() + metrics.lineSpacing() * (len(lines) - 1)
            painter.drawLine(caret_x, caret_y, caret_x, caret_y + metrics.height())

    def _field_resizable(self, field) -> bool:
        return bool(
            self._edit is not None
            and not field.readonly
            and not field.is_candidate
            and self._edit.tool in (EditTool.SELECT, EditTool.FORM_SELECT, EditTool.LAYOUT_SELECT)
            and len(self._edit.field_selection) == 1
        )

    @staticmethod
    def _field_overflow_tip(field) -> str:
        """Tooltip for a field whose entry does not fit its box (the red ! marker)."""
        from core.forms.appearance import entry_overflows
        from core.forms.display import visible_field_content

        try:
            if entry_overflows(field, visible_field_content(field)):
                return ("Part of this entry does not fit the box and will not be printed or shown in "
                        "other PDF apps. Make the text smaller (A−), or drag the box's handles to enlarge it.")
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _paint_field_handles(self, painter: QPainter, field, wr: QRect) -> None:
        if not self._field_resizable(field):
            return
        outer = wr.adjusted(-2, -2, 2, 2)
        for hx, hy in self._handle_points(outer):
            r = QRect(hx - _HANDLE // 2 - 1, hy - _HANDLE // 2 - 1, _HANDLE + 2, _HANDLE + 2)
            painter.fillRect(r, QColor("#ffffff"))
            painter.setPen(QPen(QColor("#2563eb"), 1))
            painter.drawRect(r)

    def _handle_points(self, wr: QRect) -> list[tuple[int, int]]:
        return [
            (wr.left(), wr.top()),
            (wr.center().x(), wr.top()),
            (wr.right(), wr.top()),
            (wr.left(), wr.center().y()),
            (wr.right(), wr.center().y()),
            (wr.left(), wr.bottom()),
            (wr.center().x(), wr.bottom()),
            (wr.right(), wr.bottom()),
        ]

    def _hit_handle(self, pos: QPoint, wr: QRect) -> str | None:
        names = ["nw", "n", "ne", "w", "e", "sw", "s", "se"]
        for name, (hx, hy) in zip(names, self._handle_points(wr)):
            if abs(pos.x() - hx) <= _HANDLE and abs(pos.y() - hy) <= _HANDLE:
                return name
        return None

    def _pdf_rect_to_widget(self, page_index: int, pdf_rect: object) -> QRect | None:
        x0 = float(getattr(pdf_rect, "x0"))
        y0 = float(getattr(pdf_rect, "y0"))
        x1 = float(getattr(pdf_rect, "x1"))
        y1 = float(getattr(pdf_rect, "y1"))
        return self.pdf_rect_to_widget(page_index, Rect(x0, y0, x1 - x0, y1 - y0))

    # --- mouse / keyboard ------------------------------------------------

    def _hit_form_field(self, page_index: int, pdf_pt: Point):
        assert self._edit is not None
        for field in reversed(self._edit.fields_on_page(page_index)):
            if field.rect.contains(pdf_pt):
                return field
        return None

    def _activate_form_fill(self, field) -> None:
        """Direct fill of existing AcroForm/user field in Select mode (not form design)."""
        assert self._edit is not None
        if field.readonly or field.is_candidate:
            return
        if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
            self._edit.set_field_value(field.object_id, checked=not field.checked)
            self._edit.field_selection = [field.object_id]
            self._edit.editing_field_id = None
            self.requestStatus.emit("Form field toggled")
            return
        if field.field_type == FieldType.DROPDOWN and field.options:
            from PySide6.QtWidgets import QMenu

            menu = QMenu(self)
            for opt in field.options:
                act = menu.addAction(opt)
                act.setData(opt)
            chosen = menu.exec(self.mapToGlobal(self._press_pos or QPoint()))
            if chosen is not None:
                self._edit.set_field_value(field.object_id, str(chosen.data()))
            self._edit.field_selection = [field.object_id]
            return
        self.open_field_editor(field, click_pos=self._press_pos)

    # --- in-place field editor ------------------------------------------------

    @property
    def field_editor(self) -> QWidget | None:
        return self._field_editor

    def open_field_editor(self, field, *, click_pos: QPoint | None = None) -> bool:
        """Overlay a real QLineEdit / QPlainTextEdit on a text-type field."""
        if self._edit is None:
            return False
        if self._field_editor is not None:
            self.close_field_editor(commit=True)
        if field.readonly or field.is_candidate:
            return False
        if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO, FieldType.SIGNATURE):
            self._edit.field_selection = [field.object_id]
            self._edit.editing_field_id = None
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self._edit._notify()  # noqa: SLF001
            return False
        wr = self.pdf_rect_to_widget(field.page_index, field.rect)
        if wr is None:
            return False
        if not self._edit.begin_field_edit(field.object_id):
            return False
        self._field_value_before = field.value or ""
        self._field_runs_before = [dict(r) for r in (field.runs or [])]
        multiline = bool(field.multiline) or field.field_type == FieldType.MULTILINE
        editor = _FieldTextEdit(self, single_line=not multiline)
        editor.setObjectName("FieldEditor")
        editor.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if multiline else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.document().setDocumentMargin(1)
        editor.setPlainText(field.value or "")
        self._field_editor = editor
        self._field_editor_id = field.object_id
        self._style_field_editor(field)  # base font + scale first, then the words' own formats
        if field.runs:
            from ui.rich_field_text import apply_runs

            apply_runs(editor.document(), field.runs, editor.px_per_pt)
            editor.document().clearUndoRedoStacks()
        editor.textChanged.connect(self._on_field_editor_changed)
        editor.cursorPositionChanged.connect(self._emit_field_editor_format)
        editor.installEventFilter(self)
        self._mode = "typing_field"
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        # Caret where the user clicked; otherwise select all (one line) or go to the end
        if click_pos is not None and wr.contains(click_pos):
            editor.setTextCursor(editor.cursorForPosition(editor.viewport().mapFrom(self, click_pos)))
        elif not multiline:
            editor.selectAll()
        else:
            editor.moveCursor(editor.textCursor().MoveOperation.End)
        self._watch_focus(True)
        self._emit_field_editor_format()
        self._ensure_widget_visible(wr)
        self.update()
        return True

    def _style_field_editor(self, field) -> None:
        """Font, colour, alignment and geometry of the open field editor — follows toolbar changes live."""
        editor = self._field_editor
        if editor is None or field is None:
            return
        wr = self.pdf_rect_to_widget(field.page_index, field.rect)
        if wr is None:
            return
        from core.forms.autofit import effective_form_font_size

        font = QFont(field.font_family or "Segoe UI")
        font.setBold(bool(getattr(field, "bold", False)))
        font.setItalic(bool(getattr(field, "italic", False)))
        fs = effective_form_font_size(field, field.value or "M")
        font.setPixelSize(max(8, int(round(fs * (wr.height() / max(field.rect.h, 1.0))))))
        if editor.font() != font:
            editor.setFont(font)
        text_color = QColor(field.text_color or "#000000").name()
        sheet = (
            "#FieldEditor {"
            f" background: #ffffff; color: {text_color}; border: 2px solid #2563eb; border-radius: 0;"
            " padding: 0 1px; margin: 0; min-height: 0; selection-background-color: #b3d4fc;"
            " selection-color: #000000; }"
        )
        if editor.styleSheet() != sheet:
            editor.setStyleSheet(sheet)
        editor.px_per_pt = wr.height() / max(field.rect.h, 1.0)
        editor.base_pt = float(fs)
        h_align = _field_qt_alignment(field) & Qt.AlignmentFlag.AlignHorizontal_Mask
        opt = editor.document().defaultTextOption()
        if opt.alignment() != h_align:
            opt.setAlignment(h_align)
            if editor.single_line:
                opt.setWrapMode(QTextOption.WrapMode.NoWrap)
            editor.document().setDefaultTextOption(opt)
        editor.valign = effective_valign(field)
        editor.update_vertical_offset()
        geo = wr.adjusted(-1, -1, 1, 1)
        if editor.geometry() != geo:
            editor.setGeometry(geo)

    # --- PDF annotations: select, move, delete ---------------------------------------------------

    ANNOT_MOVABLE = ("Stamp", "Text", "FreeText", "Square", "Circle", "FileAttachment")
    ANNOT_IGNORED = ("Popup", "Link", "Widget")

    def _annotation_at(self, page_index: int, pt: Point) -> tuple[int, int, str, Rect] | None:
        """Topmost comment-type annotation under ``pt`` (display space), as (page, xref, kind, rect)."""
        if self._document is None:
            return None
        from core.page_space import rect_to_display

        try:
            page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
            annots = list(page.annots() or [])
        except Exception:  # noqa: BLE001
            return None
        for annot in reversed(annots):
            kind = annot.type[1]
            if kind in self.ANNOT_IGNORED:
                continue
            r = rect_to_display(page, annot.rect)
            rect = Rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
            if rect.inflate(2.0).contains(pt):
                return (page_index, int(annot.xref), kind, rect)
        return None

    def select_annotation(self, page_index: int, xref: int) -> bool:
        """Select the annotation ``xref`` on ``page_index`` (e.g. again after it was moved)."""
        if self._document is None:
            return False
        from core.page_space import rect_to_display

        page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
        for annot in page.annots() or []:
            if int(annot.xref) == int(xref):
                r = rect_to_display(page, annot.rect)
                self._annot_sel = (page_index, int(xref), annot.type[1], Rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0))
                self.update()
                return True
        return False

    def selected_annotation(self) -> tuple[int, int, str] | None:
        return self._annot_sel[:3] if self._annot_sel else None

    def clear_annotation_selection(self) -> None:
        if self._annot_sel is not None:
            self._annot_sel = None
            self._annot_drag = None
            self.update()

    def deselect_all(self) -> None:
        """Finish any typing and select nothing — selection boxes and handles disappear."""
        self.clear_annotation_selection()
        if self._edit is None:
            return
        if self._text_editor is not None:
            self.close_text_editor(commit=True)
        if self._field_editor is not None:
            self.close_field_editor(commit=True)
        elif self._edit.editing_field_id:
            self._edit.commit_field_edit()
        # Legacy typing without the widget editor (rare); editor path already committed above
        if self._edit.editing_object_id and self._text_editor is None:
            box = self._edit.get(self._edit.editing_object_id)
            if box is not None:
                before = self._text_editor_before or self._text_before
                self._edit.commit_text_edit(box.object_id, before, box.text)
            self._edit.editing_object_id = None
        self._mode = "idle"
        self._hover_field_id = None
        self._edit.clear_selection()
        self.selectionChanged.emit()
        self.update()

    def restyle_field_editor(self) -> None:
        """Re-apply the edited field's style to the open editor (after a toolbar change)."""
        if self._field_editor is None or self._edit is None or self._field_editor_id is None:
            return
        self._style_field_editor(self._edit.fields.get(self._field_editor_id))

    # --- word formatting inside the open field editor ---------------------------------------

    def field_editor_has_selection(self) -> bool:
        ed = self._field_editor
        return ed is not None and ed.textCursor().hasSelection()

    def format_field_selection(self, **change) -> bool:
        """Font / size / bold / italic / colour for the selected words only. False = no selection."""
        ed = self._field_editor
        if ed is None or not ed.textCursor().hasSelection():
            return False
        from ui.rich_field_text import restyle_range

        cur = ed.textCursor()
        anchor, pos = cur.anchor(), cur.position()
        restyle_range(ed.document(), min(anchor, pos), max(anchor, pos), ed.px_per_pt, lambda: ed.base_pt, **change)
        cur = ed.textCursor()
        cur.setPosition(anchor)
        cur.setPosition(pos, cur.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        self._on_field_editor_changed()
        ed.setFocus(Qt.FocusReason.OtherFocusReason)
        self._emit_field_editor_format()
        return True

    def field_editor_change_case(self, convert) -> bool:
        """UPPER / lower case for the selected words only, keeping their formatting."""
        ed = self._field_editor
        if ed is None or not ed.textCursor().hasSelection():
            return False
        sel = ed.textCursor()
        a, b = sorted((sel.anchor(), sel.position()))
        doc = ed.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        for k in range(a, b):
            cur.setPosition(k)
            cur.setPosition(k + 1, QTextCursor.MoveMode.KeepAnchor)
            old = cur.selectedText()
            new = convert(old)
            if new != old and len(new) == 1:
                fmt = cur.charFormat()
                cur.insertText(new, fmt)
        cur.endEditBlock()
        sel.setPosition(a)
        sel.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(sel)
        ed.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def capture_field_editor(self) -> None:
        """Copy the editor's text and word formats into the field (editor stays open)."""
        if self._field_editor is not None:
            self._on_field_editor_changed()

    def reload_field_editor_runs(self) -> None:
        """Show the field's word formats in the open editor again (after a whole-field change)."""
        ed = self._field_editor
        if ed is None or self._edit is None or self._field_editor_id is None:
            return
        field = self._edit.fields.get(self._field_editor_id)
        if field is None:
            return
        self._style_field_editor(field)
        from ui.rich_field_text import apply_runs

        cur = ed.textCursor()
        anchor, pos = cur.anchor(), cur.position()
        ed.blockSignals(True)
        apply_runs(ed.document(), field.runs, ed.px_per_pt)
        ed.blockSignals(False)
        cur = ed.textCursor()
        cur.setPosition(anchor)
        cur.setPosition(pos, cur.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        ed.update_vertical_offset()

    def field_editor_style(self) -> dict | None:
        """Look of the text at the caret / selection start, for the toolbar to show."""
        ed = self._field_editor
        if ed is None or self._edit is None or self._field_editor_id is None:
            return None
        field = self._edit.fields.get(self._field_editor_id)
        if field is None:
            return None
        from core.forms.rich_text import STYLE_KEYS, resolve
        from ui.rich_field_text import style_at

        cur = ed.textCursor()
        pos = min(cur.anchor(), cur.position())
        if not cur.hasSelection() and pos > 0:
            pos -= 1  # the character just typed
        own = dict(zip(STYLE_KEYS, style_at(ed.document(), pos)))
        style = resolve(own, field)
        style["own_size"] = own.get("size")
        return style

    def _emit_field_editor_format(self) -> None:
        style = self.field_editor_style()
        if style is not None:
            self.fieldEditorFormatChanged.emit(style)

    def _watch_focus(self, on: bool) -> None:
        app = QApplication.instance()
        if app is None:
            return
        try:
            if on:
                app.focusChanged.connect(self._on_app_focus_changed)
            else:
                app.focusChanged.disconnect(self._on_app_focus_changed)
        except (RuntimeError, TypeError):
            pass

    def _on_app_focus_changed(self, _old, new) -> None:
        """Close the field editor when focus really leaves it.

        Staying open for the formatting toolbar (font / size boxes and their drop-downs) keeps
        the selected words selected; other windows (colour picker, dialogs) don't close it
        either — focus comes back to the editor afterwards.
        """
        ed = self._field_editor
        if ed is None or new is None or new is ed or ed.isAncestorOf(new):
            return
        if new.window() is not self.window():
            return
        w = new
        while w is not None:
            if w.property("keepsInlineEditor"):
                return
            w = w.parentWidget()
        QTimer.singleShot(0, lambda: self.close_field_editor(commit=True))

    # --- in-place text-box editor ---------------------------------------------

    @property
    def text_editor(self) -> QTextEdit | None:
        return self._text_editor

    def _style_text_editor(self, box: TextBox) -> None:
        editor = self._text_editor
        if editor is None:
            return
        wr = self.pdf_rect_to_widget(box.page_index, box.rect)
        if wr is None:
            return
        layout = layout_text_box(box)
        sx = wr.width() / max(box.rect.w, 1)
        font = QFont(layout.resolved_font or box.style.font_family)
        font.setPixelSize(max(8, int(layout.font_size * sx)))
        font.setBold(box.style.bold)
        font.setItalic(box.style.italic)
        font.setUnderline(box.style.underline)
        tracking = float(getattr(box.style, "character_spacing", 0.0) or 0.0)
        if tracking:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking * sx)
        if editor.font() != font:
            editor.setFont(font)
        pad = max(0, int(box.style.padding * sx) - 1)
        color = QColor(box.style.text_color or "#000000").name()
        sheet = (
            "#TextBoxEditor { background: transparent; border: 1px dashed #2563eb; border-radius: 0;"
            f" padding: {pad}px; margin: 0; min-height: 0; color: {color};"
            " selection-background-color: #b3d4fc; selection-color: #000000; }"
        )
        if editor.styleSheet() != sheet:
            editor.setStyleSheet(sheet)
        align = {TextAlign.CENTER: Qt.AlignmentFlag.AlignHCenter, TextAlign.RIGHT: Qt.AlignmentFlag.AlignRight}.get(
            box.align, Qt.AlignmentFlag.AlignLeft
        )
        opt = editor.document().defaultTextOption()
        if opt.alignment() != align:
            opt.setAlignment(align)
            editor.document().setDefaultTextOption(opt)
        wrap = QTextEdit.LineWrapMode.WidgetWidth if getattr(box.style, "wrap", True) else QTextEdit.LineWrapMode.NoWrap
        if editor.lineWrapMode() != wrap:
            editor.setLineWrapMode(wrap)
        if editor.geometry() != wr:
            editor.setGeometry(wr)
        editor.valign = getattr(getattr(box, "valign", None), "value", "top")
        editor.update_vertical_offset()

    def open_text_editor(self, object_id: str, *, click_pos: QPoint | None = None, at_end: bool = False) -> bool:
        """Real text editing on a text box: caret, mouse/keyboard selection, clipboard, undo."""
        if self._edit is None:
            return False
        box = self._edit.objects.get(object_id)
        if box is None:
            return False
        if self._text_editor is not None:
            if self._text_editor_id == object_id:
                self._text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            self.close_text_editor(commit=True)
        if self._field_editor is not None:
            self.close_field_editor(commit=True)
        editor = _AlignedTextEdit(self)
        editor.setObjectName("TextBoxEditor")
        editor.setFrameShape(QTextEdit.Shape.NoFrame)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.viewport().setAutoFillBackground(False)
        editor.document().setDocumentMargin(1)
        editor.setPlainText(box.text)
        editor.document().clearUndoRedoStacks()
        self._text_editor = editor
        self._text_editor_id = object_id
        self._text_editor_before = box.text
        self._text_before = box.text  # keep legacy paths in sync with the open session
        self._edit.selection = [object_id]
        self._edit.editing_object_id = object_id
        self._style_text_editor(box)
        editor.textChanged.connect(self._on_text_editor_changed)
        editor.installEventFilter(self)
        self._mode = "typing"
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        if click_pos is not None and editor.geometry().contains(click_pos) and not at_end:
            editor.setTextCursor(editor.cursorForPosition(editor.mapFrom(self, click_pos)))
        else:
            editor.moveCursor(editor.textCursor().MoveOperation.End)
        self.update()
        return True

    def try_editor_undo(self) -> bool:
        """Undo inside the open text/field editor (Qt document stack). Syncs the model."""
        editor = self._text_editor or self._field_editor
        if editor is None:
            return False
        doc = editor.document()
        if not doc.isUndoAvailable():
            return False
        doc.undo()
        if self._text_editor is not None:
            self._on_text_editor_changed()
        elif self._field_editor is not None and self._field_editor_id and self._edit is not None:
            self._on_field_editor_changed()
        return True

    def try_editor_redo(self) -> bool:
        editor = self._text_editor or self._field_editor
        if editor is None:
            return False
        doc = editor.document()
        if not doc.isRedoAvailable():
            return False
        doc.redo()
        if self._text_editor is not None:
            self._on_text_editor_changed()
        elif self._field_editor is not None and self._field_editor_id and self._edit is not None:
            self._on_field_editor_changed()
        return True

    def editor_active(self) -> bool:
        return self._text_editor is not None or self._field_editor is not None

    def _on_text_editor_changed(self) -> None:
        if self._edit is None or self._text_editor is None or self._text_editor_id is None:
            return
        self._live_interaction = True
        self._edit.live_set_text(self._text_editor_id, self._text_editor.toPlainText(), notify=True)
        box = self._edit.objects.get(self._text_editor_id)
        if box is not None:
            self._style_text_editor(box)  # auto-height boxes grow while typing

    def _discard_text_editor(self) -> None:
        editor = self._text_editor
        self._text_editor = None
        self._text_editor_id = None
        if editor is not None:
            editor.removeEventFilter(self)
            editor.hide()
            editor.deleteLater()

    def close_text_editor(self, *, commit: bool = True) -> None:
        editor, oid = self._text_editor, self._text_editor_id
        if editor is None or oid is None:
            return
        text = editor.toPlainText()
        had_focus = editor.hasFocus()
        before = self._text_editor_before
        self._discard_text_editor()
        self._live_interaction = False
        if self._mode == "typing":
            self._mode = "idle"
        if self._edit is None:
            return
        if oid in self._edit.objects:
            if not commit:
                self._edit.live_set_text(oid, before, notify=False)
                text = before
            self._edit.editing_object_id = None
            self._edit.commit_text_edit(oid, before, text)
            # Opened on existing text and closed without a change: leave the original untouched
            self._edit.discard_unchanged_native_edit(oid)
        if had_focus:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.editModelChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def refresh_text_editor(self) -> None:
        """Re-apply font/size/colour/alignment after a style change from the toolbar."""
        if self._edit is None or self._text_editor_id is None:
            return
        box = self._edit.objects.get(self._text_editor_id)
        if box is None:
            self._discard_text_editor()
            return
        self._style_text_editor(box)

    def _ensure_widget_visible(self, wr: QRect) -> None:
        area = self.parent()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parent()
        if isinstance(area, QScrollArea):
            area.ensureVisible(wr.center().x(), wr.center().y(), wr.width() // 2 + 40, wr.height() // 2 + 60)

    def _on_field_editor_changed(self) -> None:
        if self._edit is None or self._field_editor is None or self._field_editor_id is None:
            return
        from ui.rich_field_text import runs_from_document

        text, runs = runs_from_document(self._field_editor.document())
        field = self._edit.fields.get(self._field_editor_id)
        if field is None:
            return
        field.value = text
        field.runs = runs  # kept live so toolbar changes and redraws see the words' formats
        self.fieldValueEdited.emit(self._field_editor_id, text)

    def _discard_field_editor(self) -> None:
        editor = self._field_editor
        self._field_editor = None
        self._field_editor_id = None
        if editor is not None:
            editor.removeEventFilter(self)
            editor.hide()
            editor.deleteLater()

    def close_field_editor(self, *, commit: bool = True) -> None:
        """Finish in-place editing. Only a real change marks the document modified."""
        editor, fid = self._field_editor, self._field_editor_id
        if editor is None or fid is None:
            return
        from ui.rich_field_text import runs_from_document

        text, runs = runs_from_document(editor.document())
        had_focus = editor.hasFocus()
        self._watch_focus(False)
        self._discard_field_editor()
        if self._mode == "typing_field":
            self._mode = "idle"
        if self._edit is None:
            return
        field = self._edit.fields.get(fid)
        before = self._field_value_before
        runs_before = getattr(self, "_field_runs_before", [])
        if field is not None and commit and (text != before or runs != runs_before):
            field.value, field.runs = before, [dict(r) for r in runs_before]
            self._edit.set_field_rich_text(fid, text, runs, notify=False)
            self._edit.commit_field_edit(fid)
        else:
            if field is not None:
                field.value = text if commit else before
                field.runs = runs if commit else [dict(r) for r in runs_before]
            self._edit.editing_field_id = None
            self._edit._notify()  # noqa: SLF001
        if had_focus:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def tab_to_next_field(self, *, reverse: bool = False) -> None:
        if self._edit is None:
            return
        self.close_field_editor(commit=True)
        nxt = self._edit.tab_to_field(reverse=reverse)
        field = self._edit.fields.get(nxt) if nxt else None
        if field is None:
            return
        if not self.open_field_editor(field):
            # Checkbox / radio / signature: keep it selected; Space toggles
            self._edit.editing_field_id = None
            self._edit.field_selection = [field.object_id]
            wr = self.pdf_rect_to_widget(field.page_index, field.rect)
            if wr is not None:
                self._ensure_widget_visible(wr)
            self._edit._notify()  # noqa: SLF001

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._text_editor:
            et = event.type()
            if et == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if self._handle_editor_undo_redo_keys(key, mods):
                    return True
                if key == Qt.Key.Key_Escape or (
                    key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods & Qt.KeyboardModifier.ControlModifier
                ):
                    self.close_text_editor(commit=True)
                    return True
            elif et == QEvent.Type.FocusOut:
                reason = event.reason()
                if reason not in (Qt.FocusReason.PopupFocusReason, Qt.FocusReason.ActiveWindowFocusReason):
                    QTimer.singleShot(0, lambda: self.close_text_editor(commit=True))
            return super().eventFilter(obj, event)
        if obj is self._field_editor:
            et = event.type()
            if et == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if self._handle_editor_undo_redo_keys(key, mods):
                    return True
                multiline = not getattr(obj, "single_line", False)
                if key == Qt.Key.Key_Tab and not (mods & Qt.KeyboardModifier.ControlModifier):
                    self.tab_to_next_field(reverse=bool(mods & Qt.KeyboardModifier.ShiftModifier))
                    return True
                if key == Qt.Key.Key_Backtab:
                    self.tab_to_next_field(reverse=True)
                    return True
                if key == Qt.Key.Key_Escape:
                    self.close_field_editor(commit=True)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                    not multiline or mods & Qt.KeyboardModifier.ControlModifier
                ):
                    self.close_field_editor(commit=True)
                    return True
        return super().eventFilter(obj, event)

    def _handle_editor_undo_redo_keys(self, key: int, mods) -> bool:
        """Route Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z to the open editor's document stack."""
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if not ctrl:
            return False
        if key == Qt.Key.Key_Z and not shift:
            return self.try_editor_undo()
        if key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift):
            return self.try_editor_redo()
        return False

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edit is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        mapped = self.widget_to_pdf(event.position().toPoint())
        if mapped is None:
            # Grey area around the pages: finish typing and deselect (like clicking blank paper)
            if self._region_pick is None:
                self.deselect_all()
            return
        page_index, pdf_pt = mapped
        if self._region_pick is not None:
            self._region_page = page_index
            pt = self._clamp_to_page(page_index, pdf_pt)
            self._region_origin = pt
            self._region_current = pt
            self._region_stroke = [pt]
            self._region_stroke_aborted = False
            # Freeze appearance for this stroke so a mid-stroke colour change does not recolour it.
            self._stroke_locked_color = QColor(self._region_stroke_color)
            self.update()
            return
        self._press_pos = event.position().toPoint()
        self._press_pdf = pdf_pt
        self._press_page = page_index

        if self._text_editor is not None:
            self.close_text_editor(commit=True)
        # Commit prior field edit when clicking elsewhere
        if self._field_editor is not None:
            self.close_field_editor(commit=True)
        elif self._edit.editing_field_id:
            self._edit.commit_field_edit()

        form_create_tools = {
            EditTool.FORM_TEXT: "text",
            EditTool.FORM_MULTILINE: "multiline",
            EditTool.FORM_CHECKBOX: "checkbox",
            EditTool.FORM_RADIO: "radio",
            EditTool.FORM_DROPDOWN: "dropdown",
            EditTool.FORM_DATE: "date",
            EditTool.FORM_SIGNATURE: "signature",
        }
        shape_tools = {
            EditTool.SHAPE_RECT: "rectangle",
            EditTool.SHAPE_ELLIPSE: "ellipse",
            EditTool.SHAPE_LINE: "line",
            EditTool.SHAPE_ARROW: "arrow",
            EditTool.SHAPE_FREEHAND: "freehand",
        }
        if self._edit.tool in shape_tools:
            self._mode = "drag_create"
            self._create_origin = pdf_pt
            self._create_current = pdf_pt
            self._shape_create_kind = shape_tools[self._edit.tool]
            self._form_create_type = None
            self._shift_constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._freehand_points = [(pdf_pt.x, pdf_pt.y)] if self._shape_create_kind == "freehand" else []
            self._live_interaction = True
            self.update()
            return
        if self._edit.tool == EditTool.TEXT_BOX or self._edit.tool in form_create_tools:
            self._mode = "drag_create"
            self._create_origin = pdf_pt
            self._create_current = pdf_pt
            self._form_create_type = form_create_tools.get(self._edit.tool)
            self._shape_create_kind = None
            self.update()
            return

        # Resize a selected fillable field by its handles (expand to fit longer text)
        if self._edit.field_selection and self._edit.tool in (
            EditTool.SELECT,
            EditTool.FORM_SELECT,
            EditTool.LAYOUT_SELECT,
        ):
            fsel = self._edit.fields.get(self._edit.field_selection[0])
            if fsel is not None and fsel.page_index == page_index and self._field_resizable(fsel):
                fwr = self.pdf_rect_to_widget(page_index, fsel.rect)
                handle = self._hit_handle(event.position().toPoint(), fwr.adjusted(-2, -2, 2, 2)) if fwr else None
                if handle:
                    self._mode = "drag_resize"
                    self._resize_handle = handle
                    self._resize_oid = fsel.object_id
                    self._drag_before = {fsel.object_id: Rect(*fsel.rect.as_tuple())}
                    self._live_interaction = True
                    self._shift_constrain = False
                    self._drag_perf.clear()
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return

        # Select mode: direct form fill (no Forms Mode required)
        if self._edit.tool == EditTool.SELECT:
            field = self._hit_form_field(page_index, pdf_pt)
            if field is not None and not field.is_candidate:
                self._activate_form_fill(field)
                return

        # Forms / Layout design: select + move/resize fields
        if self._edit.tool in (EditTool.FORM_SELECT, EditTool.LAYOUT_SELECT):
            for field in reversed(self._edit.fields_on_page(page_index)):
                if field.rect.contains(pdf_pt):
                    additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                    if additive:
                        if field.object_id in self._edit.field_selection:
                            self._edit.field_selection = [
                                i for i in self._edit.field_selection if i != field.object_id
                            ]
                        else:
                            self._edit.field_selection.append(field.object_id)
                    else:
                        self._edit.field_selection = [field.object_id]
                        if (
                            field.field_type in (FieldType.CHECKBOX, FieldType.RADIO)
                            and event.modifiers() == Qt.KeyboardModifier.NoModifier
                        ):
                            self._edit.set_field_value(field.object_id, checked=not field.checked)
                    self._mode = "drag_move"
                    self._drag_before = {field.object_id: Rect(*field.rect.as_tuple())}
                    self._live_interaction = True
                    self._edit._notify()  # noqa: SLF001
                    return
            self._edit.field_selection = []
            self._edit._notify()  # noqa: SLF001

        # Select tool — handles on current selection (text / shape / image)
        for oid in list(self._edit.selection):
            target = (
                self._edit.get(oid)
                or self._edit.shapes.get(oid)
                or self._edit.images.get(oid)
            )
            if target is None or getattr(target, "page_index", -1) != page_index:
                continue
            wr = self.pdf_rect_to_widget(page_index, target.rect)
            if wr is None:
                continue
            handle = self._hit_handle(event.position().toPoint(), wr)
            if handle:
                self._mode = "drag_resize"
                self._resize_handle = handle
                self._resize_oid = oid
                self._drag_before = self._edit.begin_transform_snapshot()
                self._live_interaction = True
                self._shift_constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._drag_perf.clear()
                return

        hit = self._edit.hit_test(page_index, pdf_pt)
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if hit:
            if hit not in self._edit.selection or not additive:
                self._edit.selection = [hit] if not additive else list(
                    dict.fromkeys([*self._edit.selection, hit])
                )
                self._edit.field_selection = []
                self._edit._notify()  # noqa: SLF001
            self._mode = "drag_move"
            self._drag_before = self._edit.begin_transform_snapshot()
            self._drag_shape_lines = {}
            self._drag_shape_points = {}
            for oid in self._drag_before:
                sh = self._edit.shapes.get(oid)
                if sh is None:
                    continue
                if sh.kind.value in ("line", "arrow"):
                    self._drag_shape_lines[oid] = (sh.x0, sh.y0, sh.x1, sh.y1)
                if sh.kind.value == "freehand":
                    self._drag_shape_points[oid] = list(sh.points)
            if hit in self._edit.objects:
                self._edit.editing_object_id = hit
                self._text_before = self._edit.get(hit).text if self._edit.get(hit) else ""
            else:
                self._edit.editing_object_id = None
            self._edit.editing_field_id = None
            self._live_interaction = True
            self._drag_perf.clear()
        else:
            if self._edit.editing_object_id:
                oid = self._edit.editing_object_id
                box = self._edit.get(oid)
                if box is not None:
                    self._edit.commit_text_edit(oid, self._text_before, box.text)
                self._edit.editing_object_id = None
            self._edit.clear_selection()
            self._mode = "idle"
            found = self._annotation_at(page_index, pdf_pt) if self._edit.tool == EditTool.SELECT else None
            self._annot_sel = found
            self._annot_drag = None
            if found is not None:
                self._mode = "annot_move" if found[2] in self.ANNOT_MOVABLE else "idle"
                self._annot_drag = (0.0, 0.0)
                self.annotationSelected.emit(found[0], found[1])
        if hit:
            self.clear_annotation_selection()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        import time

        if self._edit is None:
            return super().mouseMoveEvent(event)
        mapped = self.widget_to_pdf(event.position().toPoint())
        if mapped is None:
            return
        page_index, pdf_pt = mapped

        if self._mode == "annot_move" and self._annot_sel is not None and self._press_pdf is not None \
                and event.buttons() & Qt.MouseButton.LeftButton and page_index == self._annot_sel[0]:
            self._annot_drag = (pdf_pt.x - self._press_pdf.x, pdf_pt.y - self._press_pdf.y)
            self.update()
            return

        if self._region_pick is not None:
            if self._region_origin is not None:
                pt = self._clamp_to_page(self._region_page, pdf_pt)
                self._region_current = pt
                if self._region_pick[2] == "stroke":
                    if not self._region_stroke or (
                        abs(pt.x - self._region_stroke[-1].x) > 0.4
                        or abs(pt.y - self._region_stroke[-1].y) > 0.4
                    ):
                        self._region_stroke.append(pt)
                self.update()
            return

        # Hover feedback for fillable fields (Select mode)
        if self._mode == "idle" and self._edit.tool == EditTool.SELECT:
            field = self._hit_form_field(page_index, pdf_pt)
            hid = field.object_id if field and not field.is_candidate else None
            if hid != self._hover_field_id:
                self._hover_field_id = hid
                if hid:
                    self.setCursor(Qt.CursorShape.IBeamCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                self.setToolTip(self._field_overflow_tip(field) if hid else "")
                self.update()

        if self._mode == "drag_create" and self._create_origin is not None:
            self._shift_constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self._shape_create_kind == "freehand":
                self._freehand_points.append((pdf_pt.x, pdf_pt.y))
                self._create_current = pdf_pt
            else:
                self._create_current = pdf_pt
            self.update()
            return
        if self._mode == "drag_move" and self._press_pdf is not None:
            t0 = time.perf_counter()
            dx = pdf_pt.x - self._press_pdf.x
            dy = pdf_pt.y - self._press_pdf.y
            for oid, rect in self._drag_before.items():
                if oid in self._edit.objects:
                    self._edit.objects[oid].rect = rect
                elif oid in self._edit.fields:
                    self._edit.fields[oid].rect = rect
                elif oid in self._edit.images:
                    self._edit.images[oid].rect = rect
                elif oid in self._edit.shapes:
                    shape = self._edit.shapes[oid]
                    shape.rect = rect
                    if oid in self._drag_shape_lines:
                        x0, y0, x1, y1 = self._drag_shape_lines[oid]
                        shape.x0, shape.y0, shape.x1, shape.y1 = x0, y0, x1, y1
                    if oid in self._drag_shape_points:
                        shape.points = list(self._drag_shape_points[oid])
            self._live_interaction = True
            self._edit.live_translate(
                list(self._drag_before.keys()), dx, dy, snap=True, notify=True
            )
            self._drag_perf.append((time.perf_counter() - t0) * 1000)
            return
        if self._mode == "drag_resize" and self._resize_oid and self._resize_handle:
            t0 = time.perf_counter()
            box = (
                self._edit.get(self._resize_oid)
                or self._edit.fields.get(self._resize_oid)
                or self._edit.shapes.get(self._resize_oid)
                or self._edit.images.get(self._resize_oid)
            )
            if box is None:
                return
            base = self._drag_before.get(self._resize_oid, box.rect)
            x, y, w, h = base.x, base.y, base.w, base.h
            hx = self._resize_handle
            if "e" in hx:
                w = max(8.0, pdf_pt.x - x)
            if "s" in hx:
                h = max(8.0, pdf_pt.y - y)
            if "w" in hx:
                new_x = pdf_pt.x
                w = max(8.0, x + w - new_x)
                x = new_x
            if "n" in hx:
                new_y = pdf_pt.y
                h = max(8.0, y + h - new_y)
                y = new_y
            self._shift_constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            shape = self._edit.shapes.get(self._resize_oid)
            if self._shift_constrain or (shape and shape.lock_aspect):
                side = max(w, h)
                w = h = side
            self._live_interaction = True
            self._edit.live_resize(self._resize_oid, Rect(x, y, w, h), notify=True)
            self._drag_perf.append((time.perf_counter() - t0) * 1000)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edit is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        if self._region_pick is not None:
            if self._region_stroke_aborted:
                self._region_stroke_aborted = False
                self._region_origin = None
                self._region_current = None
                self._region_stroke = []
                self._last_region_stroke = []
                self.update()
                return
            self._finish_region_pick()
            return
        if self._mode == "annot_move" and self._annot_sel is not None:
            self._mode = "idle"
            dx, dy = self._annot_drag or (0.0, 0.0)
            self._annot_drag = None
            if abs(dx) >= 1.0 or abs(dy) >= 1.0:
                page_index, xref, kind, rect = self._annot_sel
                from core.page_space import point_to_page

                page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
                a = point_to_page(page, rect.x, rect.y)
                b = point_to_page(page, rect.x + dx, rect.y + dy)
                self._annot_sel = (page_index, xref, kind, rect.translated(dx, dy))
                self.annotationMoveRequested.emit(page_index, xref, float(b.x - a.x), float(b.y - a.y))
            self.update()
            return
        if self._mode == "drag_create" and self._create_origin and self._create_current:
            from core.editing.shape_box import constrain_line_angle, constrain_rect_aspect

            click = (
                abs(self._create_current.x - self._create_origin.x) < 3
                and abs(self._create_current.y - self._create_origin.y) < 3
            )
            if self._shape_create_kind:
                kind = self._shape_create_kind
                if kind == "freehand":
                    pts = self._freehand_points or [
                        (self._create_origin.x, self._create_origin.y),
                        (self._create_current.x, self._create_current.y),
                    ]
                    self._edit.create_shape(self._press_page, Rect(0, 0, 1, 1), kind, points=pts)
                elif kind in ("line", "arrow"):
                    end = constrain_line_angle(
                        self._create_origin, self._create_current, snap=self._shift_constrain
                    )
                    self._edit.create_shape(
                        self._press_page,
                        Rect.from_points(self._create_origin, end),
                        kind,
                        x0=self._create_origin.x,
                        y0=self._create_origin.y,
                        x1=end.x,
                        y1=end.y,
                    )
                else:
                    rect = constrain_rect_aspect(
                        self._create_origin,
                        self._create_current,
                        square=self._shift_constrain,
                    )
                    if click:
                        rect = Rect(self._create_origin.x, self._create_origin.y, 80, 80 if kind == "ellipse" else 120)
                    lock = bool(
                        (self._shift_constrain and kind in ("rectangle", "ellipse"))
                        or getattr(self._edit, "_force_shape_lock", False)
                    )
                    self._edit._force_shape_lock = False  # noqa: SLF001
                    if lock and kind == "ellipse":
                        side = max(rect.w, rect.h, 8.0)
                        rect = Rect(rect.x, rect.y, side, side)
                    self._edit.create_shape(
                        self._press_page, rect, kind, lock_aspect=lock
                    )
                self._live_interaction = False
                self._edit.tool = EditTool.SELECT
                self.set_tool(EditTool.SELECT)
                self.requestStatus.emit(f"{kind.title()} created")
                self._shape_create_kind = None
                self._freehand_points = []
                self._end_live_interaction()
            elif self._form_create_type:
                rect = Rect.from_points(self._create_origin, self._create_current)
                if click:
                    if self._form_create_type == "checkbox":
                        rect = Rect(self._create_origin.x, self._create_origin.y, 14, 14)
                    else:
                        rect = Rect(self._create_origin.x, self._create_origin.y, 140, 24)
                self._edit.create_form_field(self._press_page, rect, self._form_create_type)
                self._edit.tool = EditTool.FORM_SELECT
                self.requestStatus.emit(f"Form field ({self._form_create_type}) created")
                self._form_create_type = None
            else:
                rect = Rect.from_points(self._create_origin, self._create_current)
                if click:
                    rect = Rect(self._create_origin.x, self._create_origin.y, 160, 40)
                box = self._edit.create_text_box(self._press_page, rect, text="")
                self._edit.tool = EditTool.SELECT
                self.set_tool(EditTool.SELECT)
                self._text_before = ""
                self._live_interaction = False
                self._mode = "idle"
                self.open_text_editor(box.object_id)
                self.requestStatus.emit("Text box created — type now; Esc or click outside to finish")
        elif self._mode == "drag_move" and self._drag_before:
            self._edit.guides = []
            moved = False
            for oid, before in self._drag_before.items():
                cur = None
                if oid in self._edit.objects:
                    cur = self._edit.objects[oid].rect
                elif oid in self._edit.fields:
                    cur = self._edit.fields[oid].rect
                elif oid in self._edit.images:
                    cur = self._edit.images[oid].rect
                if cur is not None and (
                    abs(cur.x - before.x) > 0.5
                    or abs(cur.y - before.y) > 0.5
                    or abs(cur.w - before.w) > 0.5
                    or abs(cur.h - before.h) > 0.5
                ):
                    moved = True
                    break
            self._live_interaction = False
            if moved:
                self._edit.commit_transform(self._drag_before, name="Move")
            else:
                # Click without move on text box → keep editing focus
                self._end_live_interaction()
            self._write_drag_perf("move")
        elif self._mode == "drag_resize" and self._drag_before:
            self._live_interaction = False
            self._edit.commit_transform(self._drag_before, name="Resize")
            self._write_drag_perf("resize")
        if self._mode != "typing_field":
            self._mode = "idle"
        self._create_origin = None
        self._create_current = None
        self._resize_handle = None
        self._resize_oid = None
        self.update()

    def _clamp_to_page(self, page_index: int, pt: Point) -> Point:
        if 0 <= page_index < len(self._pages):
            page = self._pages[page_index]
            return Point(
                max(0.0, min(page.display_width_pt, pt.x)),
                max(0.0, min(page.display_height_pt, pt.y)),
            )
        return pt

    def _finish_region_pick(self) -> None:
        pick = self._region_pick
        origin, current = self._region_origin, self._region_current
        if pick is None or origin is None or current is None:
            return
        _prompt, callback, kind = pick
        rect = Rect.from_points(origin, current)
        was_click = rect.w < 3 and rect.h < 3
        if kind in ("point", "erase"):
            rect = Rect(origin.x, origin.y, 0, 0)
            was_click = True
        if kind == "stroke":
            stroke = list(self._region_stroke) if self._region_stroke else [origin, current]
            self._last_region_stroke = stroke
            if len(stroke) >= 2:
                xs = [p.x for p in stroke]
                ys = [p.y for p in stroke]
                rect = Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                was_click = rect.w < 2 and rect.h < 2 and len(stroke) < 3
            else:
                was_click = True
        else:
            self._last_region_stroke = []
        page = self._region_page
        self._region_pick = None
        self._region_origin = None
        self._region_current = None
        self._region_stroke = []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        callback(page, rect, was_click)

    def event(self, event) -> bool:  # noqa: D401
        """Let in-place typing win over window shortcuts (Delete, Home, letters, Ctrl+Z…)."""
        if event.type() == QEvent.Type.ShortcutOverride and self._edit is not None:
            typing = bool(
                self._text_editor is not None
                or self._field_editor is not None
                or self._edit.editing_object_id
                or self._edit.editing_field_id
            )
            key = event.key()
            mods = event.modifiers()
            if self._region_pick is not None and key == Qt.Key.Key_Escape:
                event.accept()
                return True
            if typing:
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
                alt = bool(mods & Qt.KeyboardModifier.AltModifier)
                # Keep clipboard / undo / redo / select-all inside the editor, not the window stack
                if ctrl and not alt and key in (
                    Qt.Key.Key_Z,
                    Qt.Key.Key_Y,
                    Qt.Key.Key_V,
                    Qt.Key.Key_C,
                    Qt.Key.Key_X,
                    Qt.Key.Key_A,
                ):
                    event.accept()
                    return True
                plain = not (ctrl or alt)
                editing_keys = {
                    Qt.Key.Key_Delete,
                    Qt.Key.Key_Backspace,
                    Qt.Key.Key_Home,
                    Qt.Key.Key_End,
                    Qt.Key.Key_Left,
                    Qt.Key.Key_Right,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                    Qt.Key.Key_Escape,
                    Qt.Key.Key_Tab,
                }
                if plain and (event.text() or key in editing_keys):
                    event.accept()
                    return True
        return super().event(event)

    def _write_drag_perf(self, kind: str) -> None:
        if not self._drag_perf:
            return
        try:
            from app.paths import INSTALLED_READ_ONLY, TEST_LOGS
            from core import app_env

            # Developer diagnostics only: an installed copy records nothing unless asked to
            if INSTALLED_READ_ONLY and app_env.get("PERF_LOG") != "1":
                return
            out = TEST_LOGS
            out.mkdir(parents=True, exist_ok=True)
            avg = sum(self._drag_perf) / len(self._drag_perf)
            peak = max(self._drag_perf)
            line = f"{kind} n={len(self._drag_perf)} avg_ms={avg:.2f} peak_ms={peak:.2f}\n"
            log = out / "textbox_interaction_perf.log"
            if log.exists() and log.stat().st_size > 256_000:  # bounded: keep the newer half
                data = log.read_bytes()
                log.write_bytes(data[len(data) // 2:].split(b"\n", 1)[-1])
            with log.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._drag_perf.clear()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edit is None:
            return
        mapped = self.widget_to_pdf(event.position().toPoint())
        if mapped is None:
            return
        page_index, pdf_pt = mapped
        own = self._edit.hit_test(page_index, pdf_pt)
        if own and own in self._edit.objects:
            self._edit.select([own])
            self.open_text_editor(own, click_pos=event.position().toPoint())
            return
        # A comment (sticky note, callout, stamp ...) on top of the page: edit its text
        if not own and self._edit.tool == EditTool.SELECT:
            found = self._annotation_at(page_index, pdf_pt)
            if found is not None and found[2] not in ("Highlight", "Underline", "StrikeOut", "Squiggly", "Ink"):
                self._annot_sel = found
                self.annotationEditRequested.emit(found[0], found[1])
                return
        # Try native span edit
        try:
            spans = self._edit.extract_native_spans(page_index)
            for span in spans:
                if span.rect.contains(pdf_pt):
                    box = self._edit.begin_native_edit(span, span.text)
                    self.open_text_editor(box.object_id, click_pos=event.position().toPoint())
                    self.requestStatus.emit(
                        "Editing existing text: the original is replaced when you save (Undo restores it)"
                    )
                    return
        except Exception:  # noqa: BLE001
            pass
        hit = self._edit.hit_test(page_index, pdf_pt)
        if hit and hit in self._edit.objects:
            self._edit.select([hit])
            self.open_text_editor(hit, click_pos=event.position().toPoint())
            return
        if hit:
            self._edit.select([hit])
            self._edit.editing_object_id = hit
            box = self._edit.get(hit)
            self._text_before = box.text if box else ""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._edit is None:
            return super().keyPressEvent(event)
        mod = event.modifiers()
        key = event.key()

        # Tab / Shift+Tab through fillable fields
        if key == Qt.Key.Key_Tab and (
            self._edit.editing_field_id or self._edit.field_selection or self._edit.fields
        ):
            if not (mod & Qt.KeyboardModifier.ControlModifier):
                self.tab_to_next_field(reverse=bool(mod & Qt.KeyboardModifier.ShiftModifier))
                return

        # Shortcuts that should not type into box
        if mod & Qt.KeyboardModifier.ControlModifier:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Ctrl+Enter commits current text/field and returns to Select
                if self._text_editor is not None:
                    self.close_text_editor(commit=True)
                elif self._edit.editing_object_id:
                    oid = self._edit.editing_object_id
                    box = self._edit.get(oid)
                    if box is not None:
                        before = self._text_editor_before or self._text_before
                        self._edit.commit_text_edit(oid, before, box.text)
                    self._edit.editing_object_id = None
                if self._field_editor is not None:
                    self.close_field_editor(commit=True)
                elif self._edit.editing_field_id:
                    self._edit.commit_field_edit()
                self.set_tool(EditTool.SELECT)
                self._mode = "idle"
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            if key == Qt.Key.Key_Z and not (mod & Qt.KeyboardModifier.ShiftModifier):
                if self.try_editor_undo():
                    return
                self._edit.undo()
                return
            if key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and (mod & Qt.KeyboardModifier.ShiftModifier)):
                if self.try_editor_redo():
                    return
                self._edit.redo()
                return
            if key == Qt.Key.Key_C:
                self._object_clipboard = self._edit.clipboard_copy()
                if self._edit.selected_objects():
                    self._edit.copy_style_selection()
                return
            if key == Qt.Key.Key_V:
                if self._object_clipboard:
                    self._edit.clipboard_paste(self._object_clipboard, page_index=self._focus_page)
                else:
                    self._edit.paste_style_selection()
                return
            if key == Qt.Key.Key_D:
                self._edit.duplicate_selection()
                return
            if key == Qt.Key.Key_A:
                self._edit.select([o.object_id for o in self._edit.all_objects()])
                return
            return super().keyPressEvent(event)

        if (
            key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not self._edit.editing_field_id
            and not self._edit.editing_object_id
            and self._edit.field_selection
            and self._edit.tool == EditTool.SELECT
        ):
            field = self._edit.fields.get(self._edit.field_selection[0])
            if field is not None and not field.readonly:
                if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
                    self._edit.set_field_value(field.object_id, checked=not field.checked)
                    return
                if self.open_field_editor(field):
                    return
        if key == Qt.Key.Key_Escape and self._region_pick is not None:
            if self.abort_active_region_stroke():
                return
            self.cancel_region_pick()
            return
        if key == Qt.Key.Key_Escape:
            if self._text_editor is not None:
                self.close_text_editor(commit=True)
                self.set_tool(EditTool.SELECT)
                self.requestStatus.emit("Select mode")
                return
            if self._field_editor is not None:
                self.close_field_editor(commit=True)
                self.set_tool(EditTool.SELECT)
                return
            if self._edit.editing_field_id:
                self._edit.commit_field_edit()
                self._mode = "idle"
                self.set_tool(EditTool.SELECT)
                return
            if self._edit.editing_object_id:
                oid = self._edit.editing_object_id
                box = self._edit.get(oid)
                if box is not None:
                    before = self._text_editor_before or self._text_before
                    self._edit.commit_text_edit(oid, before, box.text)
                self._edit.editing_object_id = None
                self._mode = "idle"
                self.set_tool(EditTool.SELECT)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.requestStatus.emit("Select mode")
                return
            if self._edit.tool != EditTool.SELECT:
                self.set_tool(EditTool.SELECT)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            if self._edit.selection or self._edit.field_selection or getattr(self._edit, "table_selection", None):
                self.deselect_all()  # Esc after typing: the field / object is no longer selected
                return

        if (
            key == Qt.Key.Key_T
            and self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
        ):
            self.set_tool(EditTool.TEXT_BOX)
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.requestStatus.emit("Text Box tool (click or drag)")
            return

        if (
            key == Qt.Key.Key_V
            and self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
        ):
            self.set_tool(EditTool.SELECT)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.requestStatus.emit("Select mode")
            return

        if (
            self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
        ):
            if key == Qt.Key.Key_R:
                self.set_tool(EditTool.SHAPE_RECT)
                self.requestStatus.emit("Rectangle tool — drag to draw (Shift = square)")
                return
            if key == Qt.Key.Key_E:
                self.set_tool(EditTool.SHAPE_ELLIPSE)
                self.requestStatus.emit("Ellipse tool — drag to draw (Shift = circle)")
                return
            if key == Qt.Key.Key_L:
                self.set_tool(EditTool.SHAPE_LINE)
                self.requestStatus.emit("Line tool — drag (Shift = angle snap)")
                return

        if (
            key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
        ):
            if not self._edit.selection and self._annot_sel is not None:
                page_index, xref = self._annot_sel[:2]
                self.clear_annotation_selection()
                self.annotationDeleteRequested.emit(page_index, xref)
                return
            self._edit.delete_selection()
            return
        if key == Qt.Key.Key_Escape and self._annot_sel is not None:
            self.clear_annotation_selection()
            return

        # Keyboard nudging
        if (
            self._edit.selection
            and self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
        ):
            step = 10.0 if mod & Qt.KeyboardModifier.ShiftModifier else 1.0
            if key == Qt.Key.Key_Left:
                self._edit.nudge_selection(-step, 0)
                return
            if key == Qt.Key.Key_Right:
                self._edit.nudge_selection(step, 0)
                return
            if key == Qt.Key.Key_Up:
                self._edit.nudge_selection(0, -step)
                return
            if key == Qt.Key.Key_Down:
                self._edit.nudge_selection(0, step)
                return

        # Typing into active form field (direct fill)
        fid = self._edit.editing_field_id
        if fid and fid in self._edit.fields:
            field = self._edit.fields[fid]
            text = field.value or ""
            self._live_interaction = True
            if key == Qt.Key.Key_Return and not field.multiline:
                self._live_interaction = False
                self._edit.commit_field_edit(fid)
                self._mode = "idle"
                return
            if key == Qt.Key.Key_Return:
                text += "\n"
            elif key == Qt.Key.Key_Backspace:
                text = text[:-1]
            else:
                ch = event.text()
                if ch:
                    text += ch
                else:
                    self._live_interaction = False
                    return super().keyPressEvent(event)
            self._edit.set_field_value(fid, text, notify=True)
            # keep live so inspector doesn't rebuild every keystroke
            return

        # Typing on a selected text box opens the real editor and forwards the key
        oid = self._edit.editing_object_id or (
            self._edit.selection[0] if len(self._edit.selection) == 1 and self._edit.selection[0] in self._edit.objects else None
        )
        if oid and oid in self._edit.objects and (event.text() and event.text().isprintable() or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2)):
            if self.open_text_editor(oid, at_end=True):
                if key not in (Qt.Key.Key_F2,) and self._text_editor is not None:
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self._edit.objects[oid].text == "":
                        return  # Enter on a selected box = start editing
                    self._text_editor.insertPlainText("\n" if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) else event.text())
                return
        # Typing into active text box (legacy fallback)
        oid = self._edit.editing_object_id
        if oid and oid in self._edit.objects:
            box = self._edit.objects[oid]
            if self._mode != "typing":
                self._text_before = box.text
            self._mode = "typing"
            self._live_interaction = True
            text = box.text
            if key == Qt.Key.Key_Return:
                text += "\n"
            elif key == Qt.Key.Key_Backspace:
                text = text[:-1]
            else:
                ch = event.text()
                if ch:
                    text += ch
                else:
                    self._live_interaction = False
                    return super().keyPressEvent(event)
            self._edit.live_set_text(oid, text, notify=True)
            return

        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        # Widget editors commit via their own FocusOut filter; avoid double-commit with a stale before.
        if self._text_editor is None and self._edit and self._edit.editing_object_id:
            oid = self._edit.editing_object_id
            box = self._edit.get(oid)
            if box is not None:
                self._live_interaction = False
                before = self._text_editor_before or self._text_before
                self._edit.commit_text_edit(oid, before, box.text)
                self._edit.editing_object_id = None
        if self._edit and self._edit.editing_field_id and self._field_editor is None:
            self._live_interaction = False
            self._edit.commit_field_edit()
        super().focusOutEvent(event)


class PdfCanvas(QScrollArea):
    fieldValueEdited = Signal(str, str)
    fieldEditorFormatChanged = Signal(dict)
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    selectionChanged = Signal()
    editModelChanged = Signal()
    requestStatus = Signal(str)
    regionPickCancelled = Signal()
    # PDF annotations (comments, stamps ...) selected with the Select tool: page, xref
    annotationSelected = Signal(int, int)
    annotationMoveRequested = Signal(int, int, float, float)  # page, xref, dx, dy (unrotated page space)
    annotationDeleteRequested = Signal(int, int)
    annotationEditRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas = _CanvasWidget()
        self.setWidget(self._canvas)
        self._canvas.pageChanged.connect(self.pageChanged.emit)
        self._canvas.zoomChanged.connect(self.zoomChanged.emit)
        self._canvas.selectionChanged.connect(self.selectionChanged.emit)
        self._canvas.editModelChanged.connect(self.editModelChanged.emit)
        self._canvas.requestStatus.connect(self.requestStatus.emit)
        self._canvas.regionPickCancelled.connect(self.regionPickCancelled.emit)
        self._canvas.fieldValueEdited.connect(self.fieldValueEdited.emit)
        self._canvas.fieldEditorFormatChanged.connect(self.fieldEditorFormatChanged.emit)
        self._canvas.annotationSelected.connect(self.annotationSelected.emit)
        self._canvas.annotationMoveRequested.connect(self.annotationMoveRequested.emit)
        self._canvas.annotationDeleteRequested.connect(self.annotationDeleteRequested.emit)
        self._canvas.annotationEditRequested.connect(self.annotationEditRequested.emit)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)

    def clear_document(self) -> None:
        self._canvas.clear_document()

    def set_document(self, document: PdfDocument) -> None:
        self._canvas.set_document(document)
        self._canvas.apply_zoom_for_viewport(self._fit_size())
        self._on_scroll()

    def set_edit_model(self, edit: EditableDocument | None) -> None:
        self._canvas.set_edit_model(edit)

    def set_tool(self, tool: EditTool) -> None:
        self._canvas.set_tool(tool)
        self._canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_highlights(self, hits: list[tuple[int, object]]) -> None:
        self._canvas.set_highlights(hits)

    def select_annotation(self, page_index: int, xref: int) -> bool:
        return self._canvas.select_annotation(page_index, xref)

    def selected_annotation(self):
        return self._canvas.selected_annotation()

    def clear_highlights(self) -> None:
        self._canvas.clear_highlights()

    def close_field_editor(self, *, commit: bool = True) -> None:
        self._canvas.close_field_editor(commit=commit)
        self._canvas.close_text_editor(commit=commit)

    def begin_region_pick(self, prompt: str, callback, *, kind: str = "rect", stroke_color=None) -> None:
        self._canvas.begin_region_pick(prompt, callback, kind=kind, stroke_color=stroke_color)

    def cancel_region_pick(self, *, announce: bool = True) -> None:
        self._canvas.cancel_region_pick(announce=announce)

    def take_region_stroke(self) -> list:
        return self._canvas.take_region_stroke()

    def take_stroke_locked_color(self):
        return self._canvas.take_stroke_locked_color()

    def set_region_stroke_color(self, color) -> None:
        self._canvas.set_region_stroke_color(color)

    def abort_active_region_stroke(self) -> bool:
        return self._canvas.abort_active_region_stroke()

    def try_editor_undo(self) -> bool:
        return self._canvas.try_editor_undo()

    def try_editor_redo(self) -> bool:
        return self._canvas.try_editor_redo()

    def editor_active(self) -> bool:
        return self._canvas.editor_active()

    @property
    def region_pick_active(self) -> bool:
        return self._canvas.region_pick_active

    @property
    def region_stroke_in_progress(self) -> bool:
        return self._canvas.region_stroke_in_progress

    def go_to_first(self) -> None:
        self.go_to_page(0)

    def go_to_last(self) -> None:
        self.go_to_page(len(self._canvas._layouts) - 1)  # noqa: SLF001

    def refresh_theme(self) -> None:
        pal = _theme_palette()
        if pal is not None:
            self.setStyleSheet(f"QScrollArea {{ background: {pal.canvas}; border: none; }}")
            self.viewport().setStyleSheet(f"background: {pal.canvas};")
        self._canvas.update()

    @property
    def zoom(self) -> float:
        return self._canvas.zoom

    @property
    def focus_page(self) -> int:
        return self._canvas.focus_page

    @property
    def edit_model(self) -> EditableDocument | None:
        return self._canvas.edit_model

    def go_to_page(self, index: int) -> None:
        if not self._canvas._layouts:
            return
        index = max(0, min(index, len(self._canvas._layouts) - 1))
        y = self._canvas.page_top(index)
        self.verticalScrollBar().setValue(y)
        self._canvas._focus_page = index  # noqa: SLF001
        self.pageChanged.emit(index)
        # Schedule render for the visible region but keep explicit navigation target.
        # notify_viewport() derives focus from scroll center and can clobber go_to_page
        # in small/offscreen viewports or when adjacent pages remain partially visible.
        visible = QRect(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
            max(1, self.viewport().width()),
            max(1, self.viewport().height()),
        )
        self._canvas._schedule_render()
        _ = visible

    def set_zoom_mode(self, mode: ZoomMode) -> None:
        self._canvas.set_zoom_mode(mode, self._fit_size())

    def set_manual_zoom(self, zoom: float) -> None:
        self._canvas.set_manual_zoom(zoom, self.viewport().size())

    def zoom_in(self) -> None:
        self.set_manual_zoom(self.zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_manual_zoom(self.zoom / 1.15)

    def _on_scroll(self) -> None:
        visible = QRect(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
            self.viewport().width(),
            self.viewport().height(),
        )
        self._canvas.notify_viewport(visible)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._canvas.zoom_mode in (ZoomMode.FIT_WIDTH, ZoomMode.FIT_PAGE):
            self._canvas.apply_zoom_for_viewport(self._fit_size())
        self._on_scroll()

    def _fit_size(self) -> QSize:
        """Viewport size for Fit Width / Fit Page that does not depend on the scrollbar showing.

        Using the current viewport made some page sizes flip forever: the fitted page needed a
        scrollbar, the scrollbar made the page smaller so it no longer needed one, and so on —
        the page was never drawn. The scrollbar's width is always kept free instead.
        """
        full = self.maximumViewportSize()
        bar = self.style().pixelMetric(self.style().PixelMetric.PM_ScrollBarExtent, None, self)
        return QSize(max(1, full.width() - bar), max(1, full.height()))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)
