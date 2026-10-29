"""Central PDF canvas — viewer + real-time non-destructive editing overlays."""

from __future__ import annotations

import bisect
import os
import time
from collections import OrderedDict
from enum import Enum

from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRegion,
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
from core.forms.display import (
    pending_button_states,
    should_paint_field_overlay,
    stale_appearance_widgets,
    visible_field_content,
)
from core.forms.fields import FieldType, effective_valign
from core.page_info import PageInfo
from core.render_cache import RenderCache, RenderKey


def resize_rect(base: Rect, handle: str, pt: Point, *, keep_ratio: bool, square: bool = False,
                min_size: float = 8.0) -> Rect:
    """The box ``base`` resized by dragging ``handle`` (n, ne, e, se, s, sw, w, nw) to ``pt``.

    Computed from the box as it was when the drag started, so it never drifts; the opposite edge or
    corner stays put and an edge cannot be dragged across it. ``keep_ratio`` keeps ``base``'s width :
    height (a side handle also centres the other direction); ``square`` makes width = height.
    """
    x0, y0, x1, y1 = base.x, base.y, base.x + base.w, base.y + base.h
    nx0, ny0, nx1, ny1 = x0, y0, x1, y1
    if "e" in handle:
        nx1 = max(pt.x, x0 + min_size)
    if "w" in handle:
        nx0 = min(pt.x, x1 - min_size)
    if "s" in handle:
        ny1 = max(pt.y, y0 + min_size)
    if "n" in handle:
        ny0 = min(pt.y, y1 - min_size)
    w, h = nx1 - nx0, ny1 - ny0
    corner = len(handle) == 2
    if (keep_ratio or square) and base.w > 0 and base.h > 0:
        ratio = 1.0 if square else base.w / base.h
        if corner:
            if square:
                w = h = max(w, h)
            else:
                scale = max(w / base.w, h / base.h)
                w, h = base.w * scale, base.h * scale
            w, h = max(w, min_size), max(h, min_size)
            nx0 = x1 - w if "w" in handle else x0
            ny0 = y1 - h if "n" in handle else y0
        elif handle in ("e", "w"):
            h = max(min_size, w / ratio)
            ny0 = (y0 + y1) / 2 - h / 2
        else:  # n, s
            w = max(min_size, h * ratio)
            nx0 = (x0 + x1) / 2 - w / 2
    return Rect(nx0, ny0, w, h)


class ZoomMode(str, Enum):
    MANUAL = "manual"
    FIT_WIDTH = "fit_width"
    FIT_PAGE = "fit_page"
    ACTUAL_SIZE = "actual_size"


_PT_TO_CSS = 96.0 / 72.0
# A page rendered larger than this many device pixels is shown as a low-resolution base plus sharp
# tiles of the visible part (very large pages — A0 posters — or high zoom on a high-DPI screen).
MAX_PAGE_PIXELS = 8_000_000  # larger pages (high zoom) are drawn as a quick low-resolution page plus sharp tiles
TILE_PX = 1024
MAX_TILES = 48
BASE_PAGE_PIXELS = 1_500_000  # placeholder of a zoomed-in page until its sharp tiles are drawn (fast to make)
TILE_BUDGET_S = 0.03  # sharp tiles drawn per pass; the rest follow in the next pass (scrolling never waits)


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


def _keep_selection_visible(editor) -> None:
    """Selected words stay highlighted while the font box or a colour menu has the focus (Windows
    draws the selection of an unfocused editor in an almost invisible colour)."""
    from PySide6.QtGui import QPalette

    pal = editor.palette()
    for role in (QPalette.ColorRole.Highlight, QPalette.ColorRole.HighlightedText):
        pal.setColor(QPalette.ColorGroup.Inactive, role, pal.color(QPalette.ColorGroup.Active, role))
    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#b3d4fc"))
    pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor("#b3d4fc"))
    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#000000"))
    pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor("#000000"))
    editor.setPalette(pal)


def _grapheme_span(text: str, index: int) -> tuple[int, int]:
    """Start/end indices of the extended grapheme cluster at *index* (BUG-16 CJK/emoji)."""
    import unicodedata

    if not text or index < 0 or index >= len(text):
        return max(0, index), max(0, index)
    # Walk back over combining marks / variation selectors; treat CJK ideographs as one unit each.
    start = index
    while start > 0:
        prev = text[start - 1]
        cat = unicodedata.category(prev)
        if cat.startswith("M") or ord(prev) in (0x200D, 0xFE0F) or 0x1F3FB <= ord(prev) <= 0x1F3FF:
            start -= 1
            continue
        break
    end = index + 1
    while end < len(text):
        ch = text[end]
        cat = unicodedata.category(ch)
        if cat.startswith("M") or ord(ch) in (0x200D, 0xFE0F) or 0x1F3FB <= ord(ch) <= 0x1F3FF:
            end += 1
            continue
        break
    return start, end


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

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # Qt WordUnderCursor splits poorly on CJK; select the grapheme (or Latin word) under the caret.
        cur = self.cursorForPosition(event.position().toPoint())
        text = self.toPlainText()
        pos = cur.position()
        if pos >= len(text) and pos > 0:
            pos -= 1
        if 0 <= pos < len(text):
            ch = text[pos]
            if ord(ch) > 0x2E7F or unicodedata_category_m_or_cjk(ch):
                a, b = _grapheme_span(text, pos)
                cur.setPosition(a)
                cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cur)
                return
        super().mouseDoubleClickEvent(event)

    def insertFromMimeData(self, source) -> None:  # noqa: N802 — keep bold/italic/colour when present (BUG-12)
        if source is None:
            return
        if source.hasHtml() and not self.single_line:
            from ui.rich_field_text import insert_html_fragment

            if insert_html_fragment(self, source.html(), self.px_per_pt, self.base_pt):
                return
        if source.hasText():
            text = source.text()
            if self.single_line:
                text = " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
            self.textCursor().insertText(text)


def unicodedata_category_m_or_cjk(ch: str) -> bool:
    import unicodedata

    cp = ord(ch)
    if unicodedata.category(ch).startswith("M"):
        return True
    return (
        0x3040 <= cp <= 0x30FF  # kana
        or 0x3400 <= cp <= 0x9FFF  # CJK
        or 0xF900 <= cp <= 0xFAFF
        or 0xFF66 <= cp <= 0xFF9D  # halfwidth kana
    )


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


def _apply_editor_h_alignment(editor: QTextEdit, h_align: Qt.AlignmentFlag) -> None:
    """Apply horizontal alignment so existing paragraphs update immediately (BUG-11).

    ``setDefaultTextOption`` alone only affects new blocks — prior text kept the old
    alignment until the editor was closed and reopened.
    """
    from PySide6.QtGui import QTextCursor

    opt = editor.document().defaultTextOption()
    if opt.alignment() != h_align:
        opt.setAlignment(h_align)
        if getattr(editor, "single_line", False):
            opt.setWrapMode(QTextOption.WrapMode.NoWrap)
        editor.document().setDefaultTextOption(opt)
    cur = editor.textCursor()
    saved_pos, saved_anchor = cur.position(), cur.anchor()
    cur.select(QTextCursor.SelectionType.Document)
    fmt = cur.blockFormat()
    if fmt.alignment() != h_align:
        fmt.setAlignment(h_align)
        cur.mergeBlockFormat(fmt)
    cur.setPosition(saved_anchor)
    mode = QTextCursor.MoveMode.KeepAnchor if saved_anchor != saved_pos else QTextCursor.MoveMode.MoveAnchor
    cur.setPosition(saved_pos, mode)
    editor.setTextCursor(cur)


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
    imageEditRequested = Signal(str)  # double-click on a placed picture / signature

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
        # Sharp tiles of very large renders: (page, zoom bucket, dpr bucket, tx, ty) -> QPixmap
        from collections import OrderedDict

        self._tiles: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._focus_page = 0
        self._fit_ref_page: int | None = None  # page Fit Width / Fit Page is measured on (see apply_zoom_for_viewport)
        self._retain_radius = 3
        self._highlights: list[tuple[int, object]] = []
        self._highlights_by_page: dict[int, list[object]] = {}
        self._highlight_active: int = -1  # index into _highlights for the current Find match
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
        self._line_before: dict | None = None
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
        # Undo / redo typed on the canvas go through the window (it also redraws a changed page)
        self.history_handler: Callable[[str], None] | None = None
        # Press-and-drag in a field selects its words at once (the press opened the editor)
        self._field_text_drag: bool = False
        # Second click on an already-selected field (no drag) opens the in-place editor
        self._field_click_edit: bool = False
        # Smooth dragging: repaint only where moved objects were and are (+ snap guides), skip
        # objects outside that area, and keep decoded / scaled pictures instead of reading the
        # image file on every repaint
        self._live_region: QRegion | None = None
        self._paint_region: QRegion | None = None
        self._image_base_cache: OrderedDict = OrderedDict()
        self._image_scaled_cache: OrderedDict = OrderedDict()
        # Rubber-band selection: drag over empty page area to select the text boxes / fields inside
        self._marquee_origin: Point | None = None
        self._marquee_current: Point | None = None
        self._marquee_page: int = 0
        self._marquee_additive: bool = False
        self._marquee_before: tuple[list[str], list[str]] = ([], [])
        # In-place text-box editor
        self._text_editor: _AlignedTextEdit | None = None
        self._text_editor_id: str | None = None
        self._text_editor_before: str = ""

    # --- document / edit model -------------------------------------------

    def rerender_all(self) -> None:
        """Draw every page again (after a change of how pixels are shown, e.g. the monitor profile)."""
        self._cache.clear()
        self._tiles.clear()
        self._rendered_hidden = {}
        self.update()

    # --- form fields being changed: their saved appearance stays out of the picture ----------

    def _stale_field_widgets(self, page_index: int) -> tuple[int, ...]:
        if self._edit is None:
            return ()
        try:
            return stale_appearance_widgets(self._edit.fields_on_page(page_index))
        except Exception:  # noqa: BLE001
            return ()

    def _pending_buttons(self, page_index: int) -> dict[int, bool]:
        if self._edit is None:
            return {}
        try:
            return pending_button_states(self._edit.fields_on_page(page_index))
        except Exception:  # noqa: BLE001
            return {}

    def _page_form_state(self, page_index: int) -> tuple:
        """What the page picture depends on: left-out text widgets, pending checkbox / radio states."""
        return (self._stale_field_widgets(page_index), tuple(sorted(self._pending_buttons(page_index).items())))

    def _button_previewable(self, field) -> bool:
        """A changed PDF checkbox / radio is shown by the page picture itself (its own on / off
        appearance), so the overlay draws no substitute glyph for it."""
        if not field.is_acroform or field.field_type not in (FieldType.CHECKBOX, FieldType.RADIO):
            return False
        xref = int(field.xref or 0)
        if xref <= 0 or self._document is None:
            return False
        cache = getattr(self, "_previewable", None)
        if cache is None:
            cache = self._previewable = {}
        if xref not in cache:
            check = getattr(self._document, "button_state_previewable", None)
            try:
                cache[xref] = bool(check(xref)) if check else False
            except Exception:  # noqa: BLE001
                cache[xref] = False
        return cache[xref]

    def _render_page_rgb(self, page_index: int, scale: float, clip=None):
        """Render for the screen without the out-of-date appearances of fields being changed
        (the overlay draws their current value) and with changed checkboxes / radio buttons in
        their new state; remembers what the picture was rendered with."""
        hidden = self._stale_field_widgets(page_index)
        states = self._pending_buttons(page_index)
        rendered = getattr(self, "_rendered_hidden", None)
        if rendered is None:
            rendered = self._rendered_hidden = {}
        rendered[page_index] = (hidden, tuple(sorted(states.items())))
        extra = {"clip": clip} if clip is not None else {}
        if hidden:
            extra["hidden_widgets"] = hidden
        if states:
            extra["widget_states"] = states
        return self._document.render_rgb(page_index, scale=scale, **extra)

    def _refresh_stale_field_pages(self) -> None:
        """Render again the pages whose set of fields being changed differs from their picture
        (a field was just changed, undone, or saved)."""
        if self._edit is None or self._document is None or self._document.is_closed or not self._layouts:
            return
        rendered = getattr(self, "_rendered_hidden", None) or {}
        pages = set(rendered)
        try:
            pages |= {int(f.page_index) for f in self._edit.fields.values()}
        except Exception:  # noqa: BLE001
            pass
        changed = [
            i for i in sorted(pages)
            if 0 <= i < len(self._layouts) and rendered.get(i, ((), ())) != self._page_form_state(i)
        ]
        if changed:
            self.refresh_page_content(changed)

    def clear_document(self) -> None:
        self._annot_sel = None
        self.invalidate_annotation_boxes()
        self.drop_stale()
        if self._edit is not None:
            self._edit.remove_listener(self._on_edit_changed)
        self._cache.clear()
        self._tiles.clear()
        self._rendered_hidden = {}
        self._previewable = {}
        self.close_note_popup()
        self._document = None
        self._edit = None
        self._pages = []
        self._layouts = []
        self._highlights = []
        self._highlights_by_page = {}
        self._highlight_active = -1
        self._focus_page = 0
        self._fit_ref_page = None
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
        self._marquee_origin = self._marquee_current = None
        self._field_text_drag = False
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
            region, self._live_region = self._live_region, None
            if region is not None and not region.isEmpty():
                self.update(region)  # a move: only where the moved boxes were and are now
            else:
                self.update()
            return
        self._refresh_stale_field_pages()
        self.editModelChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def _end_live_interaction(self) -> None:
        self._live_interaction = False
        self._refresh_stale_field_pages()
        self.editModelChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def set_highlights(self, hits: list[tuple[int, object]], *, active: int = -1) -> None:
        self._highlights = hits
        self._highlight_active = int(active)
        # by page: painting a page looks only at its own matches (a long document can have 100 000+)
        by_page: dict[int, list[object]] = {}
        for page_index, rect in hits:
            by_page.setdefault(page_index, []).append(rect)
        self._highlights_by_page = by_page
        self.update()

    def set_active_highlight(self, index: int) -> None:
        """Emphasize Find match ``index`` without rebuilding the hit list."""
        self._highlight_active = int(index)
        self.update()

    def clear_highlights(self) -> None:
        self._highlights = []
        self._highlights_by_page = {}
        self._highlight_active = -1
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
        elif kind in ("erase", "erase_stroke"):
            self.setCursor(self._eraser_cursor())
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        tip = "Esc cancels the stroke; Esc again exits" if kind in ("stroke", "erase_stroke") else "Esc to cancel"
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
        elif kind in ("erase", "erase_stroke"):
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
        self._fit_ref_page = self._focus_page
        self.apply_zoom_for_viewport(viewport_size)

    def set_fit_reference(self, index: int) -> None:
        """The page a later Fit Width / Fit Page refit (window or panel resize) is measured on."""
        self._fit_ref_page = index

    def _stash_for_zoom(self) -> None:
        """Keep the current picture of each page near the view: while zooming it is drawn scaled
        (instead of a blank page) until the sharp page at the new zoom is ready."""
        stale = getattr(self, "_stale_pix", None)
        if stale is None:
            stale = self._stale_pix = {}
        for key in list(self._cache.keys()):
            if abs(key.page_index - self._focus_page) <= 4:
                pix = self._cache.get(key)
                if pix is not None:
                    stale[key.page_index] = pix
        for k in [k for k in stale if abs(k - self._focus_page) > 4]:
            stale.pop(k, None)

    def drop_stale(self, pages=None) -> None:
        stale = getattr(self, "_stale_pix", None)
        if not stale:
            return
        if pages is None:
            stale.clear()
        else:
            for p in pages:
                stale.pop(int(p), None)

    def set_manual_zoom(self, zoom: float, viewport_size: QSize) -> None:
        self._zoom_mode = ZoomMode.MANUAL
        self._zoom = max(0.1, min(8.0, zoom))
        self._stash_for_zoom()
        self._recompute_layout()
        self._cache.clear()
        self._tiles.clear()
        self.zoomChanged.emit(self._zoom)
        # a burst of zoom steps (mouse wheel) renders once, after the last step; the scaled
        # pictures are shown meanwhile
        self._render_timer.start(90)
        _ = viewport_size

    def apply_zoom_for_viewport(self, viewport_size: QSize) -> None:
        if not self._pages or viewport_size.width() <= 0:
            return
        # Measured on a fixed reference page, not on whichever page is centred now: in a document with
        # portrait and landscape pages the refit moves the pages, a different page becomes centred, and
        # fitting to that one refits again — the view used to flip between two zooms forever.
        if self._fit_ref_page is None or not 0 <= self._fit_ref_page < len(self._pages):
            self._fit_ref_page = min(self._focus_page, len(self._pages) - 1)
        page = self._pages[self._fit_ref_page]
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
        changed = abs(self._zoom - max(0.1, min(8.0, z))) > 1e-9
        if changed:
            self._stash_for_zoom()
        self._zoom = max(0.1, min(8.0, z))
        self._recompute_layout()
        if changed or not self._cache.keys():
            self._cache.clear()
            self._tiles.clear()
        self.zoomChanged.emit(self._zoom)
        self._schedule_render()

    def page_at_y(self, y: int) -> int:
        """The page at canvas height ``y``; in the gap between two pages, the page above the gap.

        A y in a gap used to fall through to the *last* page: the visible range then reached to the end
        of the document and every page after the current one was rendered at once (multi-second
        freezes in long documents), and the current page jumped to the last page for a moment.
        """
        if not self._layouts:
            return 0
        # pages are laid out top to bottom: the last page whose top is at or above y
        i = bisect.bisect_right(self._layouts, y, key=lambda r: r.top()) - 1
        return max(0, min(i, len(self._layouts) - 1))

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
        sizes = [(int(p.display_width_pt * _PT_TO_CSS * self._zoom), int(p.display_height_pt * _PT_TO_CSS * self._zoom))
                 for p in self._pages]
        max_w = max((w for w, _h in sizes), default=0)
        for w, h in sizes:
            # each page at its own size and proportions; narrower pages of a mixed-size document centred
            self._layouts.append(QRect(self._side_pad + (max_w - w) // 2, y, w, h))
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

    def release_memory(self) -> None:
        """Drop rendered pages, tiles and decoded pictures (memory-saving mode while minimized). The
        page in view is kept (a few MB) so the window shows it at once when restored; everything
        else is drawn again when needed."""
        self._cache.retain_near_pages(self._focus_page, 0, lambda k: k.page_index)
        self._tiles.clear()
        self._image_base_cache.clear()
        self._image_scaled_cache.clear()

    def _schedule_render(self) -> None:
        if self._render_timer.isActive() and self._render_timer.remainingTime() > 16:
            return  # a zoom burst is waiting to render; do not render each step
        self._render_timer.start(16)

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

    def _widget_to_page_point(self, page_index: int, pos: QPoint) -> Point:
        """``pos`` in the coordinates of one page, kept on that page (a drag that leaves it)."""
        layout = self._layouts[page_index]
        sx, sy = self._scale(page_index)
        pt = Point((pos.x() - layout.left()) / max(sx, 1e-6), (pos.y() - layout.top()) / max(sy, 1e-6))
        return self._clamp_to_page(page_index, pt)

    def _live_dirty_rects(self, object_ids: list[str]) -> list[QRect]:
        """Widget areas the given objects are painted in (with selection handles, stroke, rotation
        and the overflow mark), plus the snap guides — what a move has to repaint."""
        out: list[QRect] = []
        if self._edit is None:
            return out
        pages: set[int] = set()
        for oid in object_ids:
            obj = (self._edit.objects.get(oid) or self._edit.fields.get(oid)
                   or self._edit.images.get(oid) or self._edit.shapes.get(oid))
            if obj is None:
                continue
            pages.add(int(obj.page_index))
            wr = self.pdf_rect_to_widget(obj.page_index, obj.rect.normalized())
            if wr is None:
                continue
            margin = _HANDLE + 6
            stroke = float(getattr(obj, "stroke_width", 0.0) or 0.0)
            if stroke:
                margin += int(stroke * max(self._zoom, 0.5)) + 12  # arrow heads
            if self._is_line_shape(obj):
                from core.editing.shape_box import head_length

                margin += int(head_length(stroke or 1.0, float(getattr(obj, "head_size", 0.0) or 0.0)) * max(self._zoom, 0.5) * 1.4)
            angle = float(getattr(obj, "rotation", 0.0) or getattr(getattr(obj, "style", None), "rotation", 0.0) or 0.0)
            if abs(angle) % 360.0 > 0.01:
                half = int((wr.width() ** 2 + wr.height() ** 2) ** 0.5 / 2) + 1
                c = wr.center()
                wr = QRect(c.x() - half, c.y() - half, 2 * half, 2 * half)
            out.append(wr.adjusted(-margin, -margin, margin, margin))
        # Snap guides are drawn across every page that is painted (_paint_overlays): repaint their
        # thin bands on every page, or a guide would be left behind on a neighbouring page
        for g in self._edit.guides:
            for page_index in range(len(self._layouts)):
                layout = self._layouts[page_index]
                sx, sy = self._scale(page_index)
                if g.orientation == "v":
                    x = layout.left() + int(g.position * sx)
                    out.append(QRect(x - 2, layout.top(), 5, layout.height()))
                else:
                    y = layout.top() + int(g.position * sy)
                    out.append(QRect(layout.left(), y - 2, layout.width(), 5))
        return out

    def _in_paint_region(self, wr: QRect | None, margin: int = _HANDLE + 6) -> bool:
        """False when a partial repaint (a move) does not touch ``wr``: skip painting it."""
        region = self._paint_region
        return region is None or wr is None or region.intersects(wr.adjusted(-margin, -margin, margin, margin))

    def _image_pixmap(self, path: str, target: QSize) -> QPixmap | None:
        """The picture for an image box, decoded once and kept scaled to its on-screen size.

        Reading and decoding the file on every repaint made dragging a photo slow. While a box is
        being resized the decoded picture (at most 2048 px) is drawn scaled instead of making a new
        smooth copy for every intermediate size."""
        try:
            st = os.stat(path)
        except OSError:
            return None
        base_key = (path, st.st_mtime_ns, st.st_size)
        base = self._image_base_cache.get(base_key)
        if base is None:
            from ui.display_color import image_for_screen

            img = QImage(path)
            if img.isNull():
                return None
            # a picture's own colour profile (Adobe RGB …) and the monitor's are taken into account
            pix = QPixmap.fromImage(image_for_screen(img))
            if pix.isNull():
                return None
            if max(pix.width(), pix.height()) > 2048:
                pix = pix.scaled(2048, 2048, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            base = pix
            self._image_base_cache[base_key] = base
            while len(self._image_base_cache) > 12:
                self._image_base_cache.popitem(last=False)
        else:
            self._image_base_cache.move_to_end(base_key)
        if self._mode == "drag_resize":
            return base
        dpr = self._device_pixel_ratio()
        tw, th = max(1, int(target.width() * dpr)), max(1, int(target.height() * dpr))
        if tw >= base.width() and th >= base.height():
            return base
        key = (base_key, tw, th)
        scaled = self._image_scaled_cache.get(key)
        if scaled is None:
            scaled = base.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._image_scaled_cache[key] = scaled
            while len(self._image_scaled_cache) > 24:
                self._image_scaled_cache.popitem(last=False)
        else:
            self._image_scaled_cache.move_to_end(key)
        return scaled

    def _finish_marquee(self) -> None:
        """Select the text boxes and fillable fields the rectangle touches (Ctrl adds to the selection)."""
        origin, current, page = self._marquee_origin, self._marquee_current, self._marquee_page
        self._marquee_origin = self._marquee_current = None
        if self._edit is None or origin is None or current is None:
            return
        rect = Rect.from_points(origin, current)
        if rect.w < 3 and rect.h < 3:
            return  # a click on empty paper: the selection was already cleared
        fields = [
            f.object_id for f in self._edit.fields_on_page(page)
            if not f.is_candidate and not f.readonly and f.rect.normalized().intersects(rect)
        ]
        # text boxes, shapes and pictures (shapes and pictures used to be left out of the selection)
        boxes = [
            oid for store in (self._edit.objects, self._edit.shapes, self._edit.images)
            for oid, box in store.items()
            if box.page_index == page and box.rect.normalized().intersects(rect)
        ]
        if self._marquee_additive:
            before_boxes, before_fields = self._marquee_before
            fields = list(dict.fromkeys([*before_fields, *fields]))
            known = (self._edit.objects, self._edit.shapes, self._edit.images)
            boxes = list(dict.fromkeys([*(b for b in before_boxes if any(b in s for s in known)), *boxes]))
        self._edit.field_selection = fields
        self._edit.selection = boxes
        self._edit.editing_field_id = None
        self._edit.editing_object_id = None
        self._edit._notify()  # noqa: SLF001
        count = len(fields) + len(boxes)
        graphics = sum(1 for b in boxes if b not in self._edit.objects)
        if count and not graphics:
            self.requestStatus.emit(
                f"{count} box{'es' if count != 1 else ''} selected — choose a font, size, style or colour on the toolbar"
            )
        elif count:
            self.requestStatus.emit(
                f"{count} object{'s' if count != 1 else ''} selected — drag one to move them all; Delete removes them"
            )

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

    def _render_scale(self, dpr: float) -> float:
        return self._zoom * _PT_TO_CSS * max(0.5, dpr)

    @staticmethod
    def _to_pixmap(rgb: tuple[bytes, int, int, int], dpr: float) -> QPixmap:
        samples, w, h, stride = rgb
        from ui.display_color import to_display

        # sRGB pixels from MuPDF; converted to the monitor's colour profile when it is not sRGB
        image = to_display(QImage(samples, w, h, stride, QImage.Format.Format_RGB888).copy())
        pix = QPixmap.fromImage(image)
        pix.setDevicePixelRatio(dpr)
        return pix

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
        scale = self._render_scale(dpr)
        self._tile_deadline = time.perf_counter() + TILE_BUDGET_S
        self._tiles_pending = False
        self._tiles_this_pass = 0
        for i in range(max(0, first - 1), min(len(self._layouts), last + 2)):
            page = self._pages[i]
            full_px = page.display_width_pt * scale * page.display_height_pt * scale
            key = RenderKey.make(i, self._zoom, page.rotation, dpr)
            try:
                if self._cache.get(key) is None:
                    if full_px <= MAX_PAGE_PIXELS:
                        self._cache.put(key, self._to_pixmap(self._render_page_rgb(i, scale), dpr))
                    else:
                        # low-resolution base for the whole page (shown while tiles are missing)
                        base = scale * (BASE_PAGE_PIXELS / full_px) ** 0.5
                        pix = self._to_pixmap(self._render_page_rgb(i, base), 1.0)
                        self._cache.put(key, pix)
                if full_px > MAX_PAGE_PIXELS and first <= i <= last:
                    self._render_tiles(i, visible, scale, dpr)
            except Exception:  # noqa: BLE001
                continue
        self._cache.retain_near_pages(self._focus_page, self._retain_radius, lambda k: k.page_index)
        self.update()
        if self._tiles_pending:  # more sharp tiles to draw: continue after this frame is shown
            QTimer.singleShot(0, self._render_visible)

    def refresh_page_content(self, pages) -> None:
        """Show what changed on ``pages`` (a highlight, comment or stamp added or removed) without
        resetting the view: the new picture of each visible page is rendered first and then replaces
        the old one, so the page never goes blank, nothing else is re-read and the scroll position,
        zoom and selection stay as they are."""
        if self._document is None or self._document.is_closed or not self._layouts:
            return
        wanted = {int(p) for p in pages if 0 <= int(p) < len(self._layouts)}
        if not wanted:
            return
        self.invalidate_annotation_boxes(wanted)
        self.drop_stale(wanted)
        dpr = self._device_pixel_ratio()
        scale = self._render_scale(dpr)
        visible = self.visibleRegion().boundingRect()
        for key in [k for k in self._cache.keys() if k.page_index in wanted]:
            if key != RenderKey.make(key.page_index, self._zoom, self._pages[key.page_index].rotation, dpr):
                self._cache.discard(key)  # other zooms: re-rendered when needed
        for i in wanted:
            page = self._pages[i]
            key = RenderKey.make(i, self._zoom, page.rotation, dpr)
            on_screen = not visible.isNull() and self._layouts[i].intersects(visible.adjusted(0, -400, 0, 400))
            full_px = page.display_width_pt * scale * page.display_height_pt * scale
            stale_tiles = [k for k in self._tiles if k[0] == i]
            if not on_screen:
                self._cache.discard(key)
                for k in stale_tiles:
                    self._tiles.pop(k, None)
                continue
            try:
                if full_px <= MAX_PAGE_PIXELS:
                    self._cache.put(key, self._to_pixmap(self._render_page_rgb(i, scale), dpr))
                else:
                    base = scale * (BASE_PAGE_PIXELS / full_px) ** 0.5
                    self._cache.put(key, self._to_pixmap(self._render_page_rgb(i, base), 1.0))
                    old = {k: self._tiles.pop(k) for k in stale_tiles}
                    self._render_tiles(i, visible, scale, dpr)
                    del old  # kept until the new tiles exist
            except Exception:  # noqa: BLE001
                self._cache.discard(key)
                for k in stale_tiles:
                    self._tiles.pop(k, None)
            self.update(self._layouts[i])
        self._schedule_render()  # pages just off screen follow in the background

    def _render_tiles(self, i: int, visible: QRect, scale: float, dpr: float) -> None:
        """Render the visible part of page ``i`` as sharp device-pixel tiles."""
        layout = self._layouts[i]
        part = visible.intersected(layout)
        if part.isEmpty():
            return
        x0 = int((part.left() - layout.left()) * dpr) // TILE_PX
        x1 = int((part.right() - layout.left()) * dpr) // TILE_PX
        y0 = int((part.top() - layout.top()) * dpr) // TILE_PX
        y1 = int((part.bottom() - layout.top()) * dpr) // TILE_PX
        zb, db = int(round(self._zoom * 100)), int(round(dpr * 100))
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                key = (i, zb, db, tx, ty)
                if key in self._tiles:
                    self._tiles.move_to_end(key)
                    continue
                # at least one tile per pass, so the work always moves forward
                if getattr(self, "_tiles_this_pass", 0) and time.perf_counter() > getattr(self, "_tile_deadline", float("inf")):
                    self._tiles_pending = True  # the low-resolution page shows here meanwhile
                    return
                clip = (tx * TILE_PX / scale, ty * TILE_PX / scale, (tx + 1) * TILE_PX / scale, (ty + 1) * TILE_PX / scale)
                self._tiles[key] = self._to_pixmap(self._render_page_rgb(i, scale, clip=clip), dpr)
                self._tiles_this_pass = getattr(self, "_tiles_this_pass", 0) + 1
                while len(self._tiles) > MAX_TILES:
                    self._tiles.popitem(last=False)

    def _paint_tiles(self, painter: QPainter, i: int, dpr: float) -> None:
        if not self._tiles:
            return
        layout = self._layouts[i]
        zb, db = int(round(self._zoom * 100)), int(round(dpr * 100))
        for (pi, z, d, tx, ty), pix in self._tiles.items():
            if pi != i or z != zb or d != db:
                continue
            x = layout.left() + tx * TILE_PX / dpr
            y = layout.top() + ty * TILE_PX / dpr
            painter.drawPixmap(QRectF(x, y, pix.width() / dpr, pix.height() / dpr), pix,
                               QRectF(0, 0, pix.width(), pix.height()))

    # --- painting --------------------------------------------------------

    # ------------------------------------------------------------------ sticky note pop-up
    def open_note_popup(self, page_index: int, xref: int, rect: Rect | None = None) -> bool:
        """Show the note's text in a pop-up next to it (stays open until closed)."""
        if self._document is None:
            return False
        try:
            page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
            annot = next((a for a in page.annots() or [] if int(a.xref) == int(xref)), None)
        except Exception:  # noqa: BLE001
            return False
        if annot is None or annot.type[1] != "Text":
            return False
        if rect is None:
            from core.page_space import rect_to_display

            r = rect_to_display(page, annot.rect)
            rect = Rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
        if getattr(self, "_note_popup", None) is None:
            from ui.note_popup import NotePopup

            self._note_popup = NotePopup(self)
            self._note_popup.editRequested.connect(self._edit_from_note_popup)
        info = annot.info or {}
        stroke = (annot.colors or {}).get("stroke") or (1.0, 0.85, 0.4)
        color = QColor.fromRgbF(*[max(0.0, min(1.0, float(c))) for c in stroke[:3]])
        self._note_popup_anchor = (page_index, rect)
        self._note_popup.show_note(page_index, xref, text=(info.get("content") or "").strip(),
                                   author=(info.get("title") or "").strip(),
                                   date=info.get("modDate") or info.get("creationDate") or "",
                                   color=color, at=self._note_popup_point())
        return True

    def _note_popup_point(self):
        page_index, rect = self._note_popup_anchor
        anchor = self.pdf_rect_to_widget(page_index, rect)
        if anchor is None:
            return QPoint(0, 0)
        return QPoint(anchor.right() + 6, anchor.top())

    def _edit_from_note_popup(self, page_index: int, xref: int) -> None:
        self.annotationEditRequested.emit(page_index, xref)

    def refresh_note_popup(self) -> None:
        """Show the open note's current text and colour again (after it was edited or undone)."""
        popup = getattr(self, "_note_popup", None)
        if popup is None or not popup.isVisible() or popup.key is None:
            return
        page_index, xref = popup.key
        if not self.open_note_popup(page_index, xref):
            popup.close_popup()

    def close_note_popup(self) -> None:
        popup = getattr(self, "_note_popup", None)
        if popup is not None:
            popup.close_popup()

    def note_popup(self):
        return getattr(self, "_note_popup", None)

    def paintEvent(self, event) -> None:  # noqa: N802
        popup = getattr(self, "_note_popup", None)
        if popup is not None and popup.isVisible():  # follows zoom and page layout changes
            at = self._note_popup_point()
            if popup.pos() != at:
                popup.move_to(at)
        painter = QPainter(self)
        pal = _theme_palette()
        # Neutral workspace distinct from white PDF pages (theme-aware)
        painter.fillRect(event.rect(), QColor(pal.canvas if pal else "#dde1e7"))
        if not self._layouts or self._document is None:
            painter.end()
            return
        dpr = self._device_pixel_ratio()
        clip = event.rect()
        # A partial repaint (moving a box) only needs the objects it touches
        self._paint_region = QRegion(event.region()) if clip != self.rect() else None
        try:
            self._paint_pages(painter, clip, dpr, pal)
        finally:
            self._paint_region = None
        self._paint_interaction(painter)
        painter.end()

    def _paint_pages(self, painter: QPainter, clip: QRect, dpr: float, pal) -> None:
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
            stale = getattr(self, "_stale_pix", None)
            if pix is not None:
                painter.drawPixmap(rect, pix)
                if stale:
                    stale.pop(i, None)
            elif stale and i in stale:
                # zooming: the previous picture, scaled, until the sharp one is rendered
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawPixmap(rect, stale[i])
                painter.restore()
            self._paint_tiles(painter, i, dpr)
            page_hits = getattr(self, "_highlights_by_page", {}).get(i, ())
            active = getattr(self, "_highlight_active", -1)
            active_rect = None
            if 0 <= active < len(self._highlights) and self._highlights[active][0] == i:
                active_rect = self._highlights[active][1]
            for pdf_rect in page_hits:
                hr = self._pdf_rect_to_widget(i, pdf_rect)
                if hr is None:
                    continue
                is_active = active_rect is not None and pdf_rect is active_rect
                if not is_active and active_rect is not None:
                    try:
                        is_active = (
                            abs(float(pdf_rect.x0) - float(active_rect.x0)) < 0.01
                            and abs(float(pdf_rect.y0) - float(active_rect.y0)) < 0.01
                            and abs(float(pdf_rect.x1) - float(active_rect.x1)) < 0.01
                            and abs(float(pdf_rect.y1) - float(active_rect.y1)) < 0.01
                        )
                    except Exception:  # noqa: BLE001
                        is_active = False
                if is_active:
                    painter.fillRect(hr, QColor(255, 180, 0, 160))
                    painter.setPen(QPen(QColor("#ea580c"), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(hr.adjusted(0, 0, -1, -1))
                else:
                    painter.fillRect(hr, QColor(255, 220, 0, 100))
            if self._edit is not None:
                self._paint_overlays(painter, i)
                self._paint_forms(painter, i)
                self._paint_tables(painter, i)

    def _paint_interaction(self, painter: QPainter) -> None:
        """Previews of what is being drawn or picked (on top of every page)."""
        if self._mode == "drag_create" and self._create_origin and self._create_current:
            from core.editing.shape_box import constrain_line_angle, constrain_rect_aspect

            painter.setPen(QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(37, 99, 235, 40))
            kind = self._shape_create_kind
            if kind == "freehand" and self._freehand_points:
                path = self._freehand_path(self._press_page, self._freehand_points)
                if path is not None:
                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
                    painter.restore()
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
        if self._mode == "marquee" and self._marquee_origin and self._marquee_current:
            mr = self.pdf_rect_to_widget(self._marquee_page, Rect.from_points(self._marquee_origin, self._marquee_current))
            if mr:
                painter.setPen(QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(37, 99, 235, 28))
                painter.drawRect(mr)
        if self._region_pick is not None and self._region_origin and self._region_current:
            kind = self._region_pick[2]
            if kind in ("stroke", "erase_stroke") and len(self._region_stroke) >= 2:
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
            if wr is None or not self._in_paint_region(wr):
                continue
            policy = should_paint_field_overlay(
                field, forms_mode=forms_mode, highlight_fillable=highlight
            )
            if policy == "content" and self._button_previewable(field):
                # The page picture shows the new state with the form's own appearance
                policy = "chrome" if forms_mode else ("highlight" if highlight and not field.readonly else "none")
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
                from core.forms.autofit import effective_form_font_size
                from core.forms.appearance import entry_overflows

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
                # Same predicate as the tooltip and Save/print layout (BUG-17) — not the rough autofit probe.
                if entry_overflows(field, text):
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
            if self._paint_region is not None and wr is not None:
                # Skip what a partial repaint does not touch (stroke, arrow heads, turned boxes)
                reach = _HANDLE + 18 + int(float(getattr(obj, "stroke_width", 0.0) or 0.0) * max(self._zoom, 0.5))
                if abs(float(getattr(obj, "rotation", 0.0) or getattr(getattr(obj, "style", None), "rotation", 0.0)
                             or 0.0)) % 360.0 > 0.01:
                    reach += max(wr.width(), wr.height())
                if not self._in_paint_region(wr.normalized(), reach):
                    continue
            if kind == "shape":
                self._paint_shape(painter, page_index, obj)
            elif wr is None:
                continue
            elif kind == "text":
                self._paint_textbox(painter, obj, wr)
            else:
                self._paint_image(painter, obj, wr)
            if wr is not None and obj.object_id in self._edit.selection and self._is_line_shape(obj):
                # a line or arrow: a round handle on each end (drag one to move that end)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(QColor("#2563eb"), 1.5))
                painter.setBrush(QColor("#ffffff"))
                for end in self._line_end_points(page_index, obj):
                    painter.drawEllipse(QPointF(end), _HANDLE * 0.9, _HANDLE * 0.9)
                painter.restore()
            elif wr is not None and obj.object_id in self._edit.selection:
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
            pix = getattr(self, "_annot_drag_pix", None)
            if ar is not None and pix is not None and (abs(dx) >= 0.5 or abs(dy) >= 0.5):
                # the note follows the pointer at once (the page itself is redrawn on release)
                src = self.pdf_rect_to_widget(page_index, self._annot_sel[3])
                if src is not None:
                    painter.save()
                    painter.setOpacity(0.35)
                    painter.setPen(QPen(QColor("#64748b"), 1, Qt.PenStyle.DotLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(src)
                    painter.restore()
                painter.drawPixmap(ar, pix)
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

    def _shape_pen(self, shape, color: QColor, *, dashed: bool = True) -> QPen:
        """Pen for a shape on screen: the saved line width at the current zoom and the saved dash
        pattern (core.editing.shape_box.dash_pattern), so the screen and the PDF match."""
        from core.editing.shape_box import dash_pattern

        scale = self._scale(shape.page_index)[0] if 0 <= shape.page_index < len(self._layouts) else self._zoom
        width = max(0.75, float(shape.stroke_width) * scale)
        pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        pattern = dash_pattern(shape.stroke_style, shape.stroke_width) if dashed else None
        if pattern:
            pen.setDashPattern([max(0.01, v / max(float(shape.stroke_width), 0.5)) for v in pattern])
        return pen

    def _paint_shape_upright(self, painter: QPainter, page_index: int, shape) -> None:
        from core.editing.shape_box import ShapeKind, line_geometry

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            from ui.display_color import qcolor

            stroke = qcolor(shape.stroke_color)
            stroke.setAlphaF(min(1.0, float(shape.opacity)) * (stroke.alphaF() if stroke.alpha() else 1.0))
            fill = qcolor(shape.fill_color)
            if fill.alpha() > 0:
                fill.setAlphaF(min(1.0, float(shape.fill_opacity) * float(shape.opacity) * fill.alphaF()))
            painter.setPen(self._shape_pen(shape, stroke))
            painter.setBrush(fill if fill.alpha() > 0 else Qt.BrushStyle.NoBrush)

            kind = shape.kind
            if kind in (ShapeKind.LINE, ShapeKind.ARROW):
                start, end = shape.heads()
                a, b, marks = line_geometry(shape.x0, shape.y0, shape.x1, shape.y1, width=shape.stroke_width,
                                            start=start, end=end, head_size=shape.head_size)
                p0 = self.pdf_to_widget_f(page_index, Point(*a))
                p1 = self.pdf_to_widget_f(page_index, Point(*b))
                if p0 is None or p1 is None:
                    return
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(p0, p1)
                solid = self._shape_pen(shape, stroke, dashed=False)  # heads are never dashed
                for style, pts in marks:
                    wpts = [self.pdf_to_widget_f(page_index, Point(x, y)) for x, y in pts]
                    if any(p is None for p in wpts):
                        continue
                    if style == "circle":
                        r = pts[1][0] * self._scale(page_index)[0]
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(stroke)
                        painter.drawEllipse(wpts[0], r, r)
                    elif style == "open":
                        painter.setPen(solid)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawPolyline(QPolygonF(wpts))
                    else:  # filled, stealth, bar
                        thin = QPen(solid)
                        thin.setWidthF(max(0.5, solid.widthF() * 0.35))
                        painter.setPen(thin)
                        painter.setBrush(stroke)
                        painter.drawPolygon(QPolygonF(wpts))
                return
            if kind == ShapeKind.FREEHAND and shape.points:
                path = self._freehand_path(page_index, shape.points)
                if path is not None:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
                return
            wr = self.pdf_rect_to_widget_f(page_index, shape.rect)
            if wr is None:
                return
            if kind == ShapeKind.ELLIPSE:
                painter.drawEllipse(wr)
            else:
                painter.drawRect(wr)
        finally:
            painter.restore()

    def _freehand_path(self, page_index: int, points) -> QPainterPath | None:
        """Smooth curves through a freehand stroke (core/editing/freehand.py) in widget coordinates."""
        from core.editing.freehand import smooth_segments

        segs = smooth_segments(points)
        if not segs:
            return None
        path = QPainterPath()
        first = self.pdf_to_widget_f(page_index, Point(*segs[0][0]))
        if first is None:
            return None
        path.moveTo(first)
        for _a, c1, c2, b in segs:
            w1 = self.pdf_to_widget_f(page_index, Point(*c1))
            w2 = self.pdf_to_widget_f(page_index, Point(*c2))
            wb = self.pdf_to_widget_f(page_index, Point(*b))
            if w1 is None or w2 is None or wb is None:
                return None
            path.cubicTo(w1, w2, wb)
        return path

    def pdf_to_widget_f(self, page_index: int, pt: Point) -> QPointF | None:
        """Like pdf_to_widget, without rounding to whole pixels (smooth thin lines and curves)."""
        if page_index < 0 or page_index >= len(self._layouts):
            return None
        layout = self._layouts[page_index]
        sx, sy = self._scale(page_index)
        return QPointF(layout.left() + pt.x * sx, layout.top() + pt.y * sy)

    def pdf_rect_to_widget_f(self, page_index: int, rect: Rect) -> QRectF | None:
        p0 = self.pdf_to_widget_f(page_index, Point(rect.x, rect.y))
        p1 = self.pdf_to_widget_f(page_index, Point(rect.x1, rect.y1))
        if p0 is None or p1 is None:
            return None
        return QRectF(p0, p1).normalized()

    def _paint_image(self, painter: QPainter, img, wr: QRect) -> None:
        from pathlib import Path

        source = str(getattr(img, "source_path", "") or "")
        if source:
            pix = self._image_pixmap(str(Path(source)), wr.size())
            if pix is not None and not pix.isNull():
                painter.save()
                painter.setOpacity(max(0.05, min(1.0, float(getattr(img, "opacity", 1.0)))))
                if getattr(img, "layer", "front") == "behind":
                    # the page's text shows through, as at Save (multiply blending, engines/bake_edits.py)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                cx, cy = float(wr.center().x()), float(wr.center().y())
                painter.translate(cx, cy)
                if abs(float(getattr(img, "rotation", 0.0))) > 0.01:
                    painter.rotate(float(img.rotation))
                sx = -1.0 if getattr(img, "flip_h", False) else 1.0
                sy = -1.0 if getattr(img, "flip_v", False) else 1.0
                if sx < 0 or sy < 0:
                    painter.scale(sx, sy)
                painter.translate(-cx, -cy)
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
        from ui.display_color import qcolor

        bg = qcolor(box.style.background_color)
        if bg.alpha() > 0:
            bg.setAlphaF(min(1.0, box.style.opacity) * (bg.alphaF() if bg.alpha() else 1.0))
            painter.fillRect(wr, bg)
        border = qcolor(box.style.border_color)
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
        color = qcolor(box.style.text_color)
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
        if box.runs:
            from types import SimpleNamespace

            from ui.rich_field_text import paint_runs

            entry = SimpleNamespace(value=box.text, runs=box.runs, text_color=box.style.text_color or "#000000")
            painter.save()
            painter.setOpacity(painter.opacity() * min(1.0, box.style.opacity))
            paint_runs(painter, entry, QRectF(text_rect), sx, font, align & Qt.AlignmentFlag.AlignHorizontal_Mask,
                       getattr(box.valign, "value", "top"), bool(getattr(box.style, "wrap", True)))
            painter.restore()
            return
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

    @staticmethod
    def _is_line_shape(obj) -> bool:
        return getattr(getattr(obj, "kind", None), "value", None) in ("line", "arrow")

    def _line_end_points(self, page_index: int, shape) -> list[QPoint]:
        out = []
        for x, y in ((shape.x0, shape.y0), (shape.x1, shape.y1)):
            p = self.pdf_to_widget(page_index, Point(x, y))
            if p is not None:
                out.append(p)
        return out

    def _hit_line_end(self, pos: QPoint, page_index: int, shape) -> str | None:
        grab = _HANDLE + 4
        for name, p in zip(("p0", "p1"), self._line_end_points(page_index, shape)):
            if abs(pos.x() - p.x()) <= grab and abs(pos.y() - p.y()) <= grab:
                return name
        return None

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
        grab = _HANDLE + 3  # a little larger than drawn: easier to catch with the mouse
        # the nearest handle wins (on a small object the side and corner handles overlap); corners
        # win a tie, so a corner drag still resizes both ways
        best = None
        for order, (name, (hx, hy)) in enumerate(zip(names, self._handle_points(wr))):
            dx, dy = abs(pos.x() - hx), abs(pos.y() - hy)
            if dx <= grab and dy <= grab:
                key = (dx * dx + dy * dy, 0 if len(name) == 2 else 1, order)
                if best is None or key < best[0]:
                    best = (key, name)
        return best[1] if best else None

    def _handle_grab_offset(self, oid: str, handle: str, press_pt: Point) -> tuple[float, float]:
        """Where the handle really is, relative to the press (PDF points). A handle can be caught a few
        pixels off its centre; without this offset the edge jumped to the pointer at the first move."""
        if self._edit is None or handle in ("p0", "p1"):
            return (0.0, 0.0)
        box = (self._edit.get(oid) or self._edit.fields.get(oid) or self._edit.shapes.get(oid)
               or self._edit.images.get(oid))
        if box is None or abs(float(getattr(box, "rotation", 0.0) or 0.0)) % 360 > 0.01:
            return (0.0, 0.0)  # a turned object: keep the previous behaviour
        r = box.rect.normalized()
        hx = r.x if "w" in handle else (r.x + r.w if "e" in handle else press_pt.x)
        hy = r.y if "n" in handle else (r.y + r.h if "s" in handle else press_pt.y)
        return (hx - press_pt.x, hy - press_pt.y)

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
        self.editModelChanged.emit()  # clears single-letter tool shortcuts while typing
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
        _apply_editor_h_alignment(editor, h_align)
        editor.valign = effective_valign(field)
        editor.update_vertical_offset()
        geo = wr.adjusted(-1, -1, 1, 1)
        if editor.geometry() != geo:
            editor.setGeometry(geo)

    # --- PDF annotations: select, move, delete ---------------------------------------------------

    ANNOT_MOVABLE = ("Stamp", "Text", "FreeText", "Square", "Circle", "FileAttachment")
    ANNOT_IGNORED = ("Popup", "Link", "Widget")

    def _annot_drag_widget_rect(self):
        if self._annot_sel is None:
            return None
        dx, dy = self._annot_drag or (0.0, 0.0)
        return self.pdf_rect_to_widget(self._annot_sel[0], self._annot_sel[3].translated(dx, dy))

    def _annotation_pixmap(self, page_index: int, xref: int):
        """The annotation's own appearance at the current zoom (drawn under the pointer while it is
        dragged); None when it cannot be drawn."""
        try:
            import fitz

            page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
            annot = page.load_annot(int(xref))
            if annot is None:
                return None
            dpr = self._device_pixel_ratio()
            z = self._zoom * _PT_TO_CSS * dpr
            pm = annot.get_pixmap(matrix=fitz.Matrix(z, z), alpha=True)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                         QImage.Format.Format_RGBA8888 if pm.alpha else QImage.Format.Format_RGB888).copy()
            from ui.display_color import to_display

            pix = QPixmap.fromImage(to_display(img))
            pix.setDevicePixelRatio(dpr)
            return pix
        except Exception:  # noqa: BLE001
            return None

    def _annotation_boxes(self, page_index: int) -> list[tuple[int, str, Rect]]:
        """(xref, kind, display rect) of the page's comment-type annotations, bottom to top.

        Cached per page: pointing at the page (every mouse move) used to load every annotation of
        the page again. The cache is checked against the page's /Annots array (annotations added or
        removed) and cleared when a page's content is refreshed (an annotation moved or edited)."""
        doc = self._document._backend._doc  # noqa: SLF001
        try:
            page_xref = doc.page_xref(page_index)
            sig = doc.xref_get_key(page_xref, "Annots")
        except Exception:  # noqa: BLE001
            sig = None
        cache = getattr(self, "_annot_box_cache", None)
        if cache is None:
            cache = self._annot_box_cache = {}
        hit = cache.get(page_index)
        if hit is not None and hit[0] == sig:
            return hit[1]
        from core.page_space import rect_to_display

        boxes: list[tuple[int, str, Rect]] = []
        try:
            page = doc.load_page(page_index)
            for annot in page.annots() or []:
                kind = annot.type[1]
                if kind in self.ANNOT_IGNORED:
                    continue
                r = rect_to_display(page, annot.rect)
                boxes.append((int(annot.xref), kind, Rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)))
        except Exception:  # noqa: BLE001
            return []
        cache[page_index] = (sig, boxes)
        return boxes

    def invalidate_annotation_boxes(self, pages=None) -> None:
        cache = getattr(self, "_annot_box_cache", None)
        if not cache:
            return
        if pages is None:
            cache.clear()
        else:
            for p in pages:
                cache.pop(int(p), None)

    def _annotation_at(self, page_index: int, pt: Point) -> tuple[int, int, str, Rect] | None:
        """Topmost comment-type annotation under ``pt`` (display space), as (page, xref, kind, rect)."""
        if self._document is None:
            return None
        for xref, kind, rect in reversed(self._annotation_boxes(page_index)):
            if rect.inflate(2.0).contains(pt):
                return (page_index, xref, kind, rect)
        return None

    def _annotation_tip(self, page_index: int, xref: int, kind: str) -> str:
        """Rich-text tooltip showing a comment's author and text (empty when it has no text)."""
        from html import escape

        try:
            page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
            annot = next((a for a in page.annots() or [] if int(a.xref) == int(xref)), None)
        except Exception:  # noqa: BLE001
            return ""
        if annot is None:
            return ""
        info = annot.info or {}
        text = (info.get("content") or "").strip()
        if not text:
            return ""
        label = {"Text": "Note", "FreeText": "Callout"}.get(kind, kind)
        author = (info.get("title") or "").strip()
        head = f"<b>{escape(label)}</b>" + (f" — {escape(author)}" if author else "")
        body = escape(text[:1200]).replace("\n", "<br>")
        return (f"<div style='max-width:340px'>{head}<br>{body}"
                f"<br><span style='color:#6b7280'>Double-click to edit</span></div>")

    def _update_annotation_hover(self, page_index: int, pdf_pt: Point) -> None:
        """Hovering a sticky note (or another comment with text) shows its text as a tooltip."""
        from PySide6.QtWidgets import QToolTip

        found = self._annotation_at(page_index, pdf_pt)
        key = (found[0], found[1]) if found else None
        if key == getattr(self, "_hover_annot_key", None):
            return
        self._hover_annot_key = key
        if found is None:
            # Hide immediately on leave — Qt's default linger made sticky-note tips stick around (BUG-15).
            self.setToolTip("")
            QToolTip.hideText()
            return
        if found[2] == "Text":
            # a sticky note keeps its text to itself until clicked (a click opens it, a double-click edits)
            self.setToolTip("Note — click to read, double-click to edit, drag to move")
            return
        self.setToolTip(self._annotation_tip(found[0], found[1], found[2]))

    def leaveEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtWidgets import QToolTip

        self._hover_annot_key = None
        self.setToolTip("")
        QToolTip.hideText()
        super().leaveEvent(event)

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
        """Font / size / bold / italic / colour for the selected words only — in a form field or in
        a text box being typed in. False = no words selected."""
        if self._field_editor is None and self._text_editor is not None:
            return self.format_text_selection(**change)
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

    def format_text_selection(self, **change) -> bool:
        """Font / size / bold / italic / colour for the words selected in the open text box (the rest
        keeps the box's style). False = no text box open or nothing selected."""
        ed = self._text_editor
        if ed is None or not ed.textCursor().hasSelection():
            return False
        from ui.rich_field_text import restyle_range

        cur = ed.textCursor()
        anchor, pos = cur.anchor(), cur.position()
        if min(anchor, pos) == 0 and max(anchor, pos) >= len(ed.toPlainText()):
            return False  # all of the text: the box's own style changes (no separate word formats)
        px = float(getattr(ed, "px_per_pt", 1.0) or 1.0)
        base = float(getattr(ed, "base_pt", 11.0) or 11.0)
        restyle_range(ed.document(), min(anchor, pos), max(anchor, pos), px, lambda: base, **change)
        cur = ed.textCursor()
        cur.setPosition(anchor)
        cur.setPosition(pos, cur.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        self._on_text_editor_changed()
        self._live_interaction = False
        ed.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def text_editor_has_selection(self) -> bool:
        ed = self._text_editor
        return bool(ed is not None and ed.textCursor().hasSelection())

    def _apply_editor_runs(self, editor, runs) -> None:
        """Word formats into the open text box editor (signals blocked: not a text change)."""
        from ui.rich_field_text import apply_runs

        cur = editor.textCursor()
        anchor, pos = cur.anchor(), cur.position()
        editor.blockSignals(True)
        try:
            apply_runs(editor.document(), list(runs or []), float(getattr(editor, "px_per_pt", 1.0) or 1.0))
            cur = editor.textCursor()
            cur.setPosition(min(anchor, len(editor.toPlainText())))
            cur.setPosition(min(pos, len(editor.toPlainText())), cur.MoveMode.KeepAnchor)
            editor.setTextCursor(cur)
        finally:
            editor.blockSignals(False)

    # --- keeping the text box open while its words are formatted ---------------------------------
    @staticmethod
    def _is_formatting_control(widget) -> bool:
        """The font box, size box, colour menus, the formatting toolbar or the Properties panel (and
        their drop-down lists): using them must not close the text box being typed in (its selected
        words would lose their selection before the change could reach them)."""
        from PySide6.QtWidgets import QColorDialog, QMenu

        try:
            win = widget.window()
            if isinstance(win, QColorDialog) or bool(win.property("keepsTextEditor")):  # Text color… dialog
                return True
        except RuntimeError:
            return False
        w = widget
        hops = 0
        while w is not None and hops < 40:
            if bool(w.property("keepsTextEditor")) or bool(w.property("keepsInlineEditor")) or isinstance(w, QMenu):
                return True
            parent = w.parentWidget()
            if parent is None and w.isWindow() and (w.windowFlags() & Qt.WindowType.Popup) == Qt.WindowType.Popup:
                return True  # a drop-down list window
            w = parent
            hops += 1
        return False

    def _watch_focus_for_text_editor(self, on: bool) -> None:
        app = QApplication.instance()
        if app is None:
            return
        watching = getattr(self, "_focus_watch", False)
        if on and not watching:
            app.focusChanged.connect(self._on_app_focus_changed_text)
            self._focus_watch = True
        elif not on and watching:
            try:
                app.focusChanged.disconnect(self._on_app_focus_changed_text)
            except (RuntimeError, TypeError):
                pass
            self._focus_watch = False

    def _on_app_focus_changed_text(self, _old, new) -> None:
        """While a text box is open: focus moving from a formatting control to anywhere else (another
        panel, the page list …) finishes typing, as leaving the box directly does."""
        ed = self._text_editor
        if ed is None or new is None or new is ed or new is self:
            return
        if self._is_formatting_control(new):
            return
        QTimer.singleShot(0, self._close_text_editor_unless_formatting)

    def _close_text_editor_unless_formatting(self) -> None:
        ed = self._text_editor
        if ed is None:
            return
        fw = QApplication.focusWidget()
        if fw is ed:
            return
        if fw is not None and self._is_formatting_control(fw):
            return
        if fw is None and QApplication.activePopupWidget() is not None:
            return
        self.close_text_editor(commit=True)

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
        old_px = getattr(editor, "px_per_pt", None)
        editor.px_per_pt = sx
        editor.base_pt = float(layout.font_size)
        if box.runs and old_px is not None and abs(old_px - sx) > 1e-6:
            self._apply_editor_runs(editor, box.runs)  # word sizes follow the zoom
        pad = max(0, int(box.style.padding * sx) - 1)
        color = QColor(box.style.text_color or "#000000").name()
        sheet = (
            "#TextBoxEditor { background: transparent; border: 1px dashed #2563eb; border-radius: 0;"
            f" padding: {pad}px; margin: 0; min-height: 0; color: {color};"
            " selection-background-color: #b3d4fc; selection-color: #000000; }"
        )
        if editor.styleSheet() != sheet:
            editor.setStyleSheet(sheet)
            _keep_selection_visible(editor)
        align = {TextAlign.CENTER: Qt.AlignmentFlag.AlignHCenter, TextAlign.RIGHT: Qt.AlignmentFlag.AlignRight}.get(
            box.align, Qt.AlignmentFlag.AlignLeft
        )
        _apply_editor_h_alignment(editor, align)
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
        self._text_editor = editor
        self._text_editor_id = object_id
        self._text_editor_before = box.text
        self._text_editor_before_runs = [dict(r) for r in (box.runs or [])]
        self._text_before = box.text  # keep legacy paths in sync with the open session
        self._edit.selection = [object_id]
        self._edit.editing_object_id = object_id
        self._style_text_editor(box)
        if box.runs:
            self._apply_editor_runs(editor, box.runs)
        editor.document().clearUndoRedoStacks()
        editor.textChanged.connect(self._on_text_editor_changed)
        editor.installEventFilter(self)
        # the handles sit on the box edge, half inside the editor: presses there resize the box
        editor.viewport().installEventFilter(self)
        self._watch_focus_for_text_editor(True)
        self._mode = "typing"
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        self.editModelChanged.emit()  # clears single-letter tool shortcuts while typing
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
        from ui.rich_field_text import runs_from_document

        text, runs = runs_from_document(self._text_editor.document())
        self._edit.live_set_text(self._text_editor_id, text, notify=True, runs=runs)
        box = self._edit.objects.get(self._text_editor_id)
        if box is not None:
            self._style_text_editor(box)  # auto-height boxes grow while typing
            self._fit_editor_height(box)

    def _fit_editor_height(self, box: TextBox) -> None:
        """Keep every typed line visible: when the on-screen editor wraps into more lines than the
        box has room for, the box grows (downwards only, its top-left corner stays where it is)."""
        from core.editing.text_box import SizeMode

        editor = self._text_editor
        if editor is None or box.size_mode not in (SizeMode.AUTO_HEIGHT, SizeMode.AUTO_SIZE):
            return
        wr = editor.geometry()
        sx = wr.width() / max(box.rect.w, 1.0)
        needed_px = editor.document().size().height() + editor.contentsMargins().top() \
            + editor.contentsMargins().bottom() + 2 * max(0, int(box.style.padding * sx) - 1) + 2
        if needed_px > wr.height() + 1 and sx > 0:
            box.rect = box.rect.with_size(box.rect.w, needed_px / sx)
            self._style_text_editor(box)
            self.update()

    def _discard_text_editor(self) -> None:
        editor = self._text_editor
        self._text_editor = None
        self._text_editor_id = None
        self._watch_focus_for_text_editor(False)
        if editor is not None:
            editor.removeEventFilter(self)
            editor.hide()
            editor.deleteLater()

    def close_text_editor(self, *, commit: bool = True) -> None:
        editor, oid = self._text_editor, self._text_editor_id
        if editor is None or oid is None:
            return
        from ui.rich_field_text import runs_from_document

        text, runs = runs_from_document(editor.document())
        had_focus = editor.hasFocus()
        before = self._text_editor_before
        before_runs = list(getattr(self, "_text_editor_before_runs", None) or [])
        self._discard_text_editor()
        self._live_interaction = False
        if self._mode == "typing":
            self._mode = "idle"
        if self._edit is None:
            return
        if oid in self._edit.objects:
            if not commit:
                self._edit.live_set_text(oid, before, notify=False, runs=before_runs)
                text, runs = before, before_runs
            else:
                self._edit.live_set_text(oid, text, notify=False, runs=runs)
            self._edit.editing_object_id = None
            self._edit.commit_text_edit(oid, before, text, before_runs=before_runs, after_runs=runs)
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
        # a whole-box change (font of the box …) also reaches the words given their own value
        from ui.rich_field_text import runs_from_document

        _text, runs = runs_from_document(self._text_editor.document())
        if runs != (box.runs or []):
            self._apply_editor_runs(self._text_editor, box.runs)

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
        self.editModelChanged.emit()  # restore single-letter tool shortcuts
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

    def _forward_mouse(self, src, event, kind) -> None:
        from PySide6.QtGui import QMouseEvent

        try:
            pc = src.mapTo(self, event.position().toPoint())
        except RuntimeError:
            return
        ev = QMouseEvent(kind, QPointF(pc), event.globalPosition(), event.button(), event.buttons(), event.modifiers())
        if kind == QEvent.Type.MouseButtonPress:
            self.mousePressEvent(ev)
        elif kind == QEvent.Type.MouseMove:
            self.mouseMoveEvent(ev)
        else:
            self.mouseReleaseEvent(ev)

    def _editor_handle_event(self, obj, event) -> bool:
        """A press on a resize handle of the box being typed in (the handles lie half inside the
        editor) resizes the box instead of placing the caret; the drag continues on the canvas."""
        et = event.type()
        if getattr(self, "_editor_handle_drag", False):
            if et == QEvent.Type.MouseMove:
                self._forward_mouse(obj, event, QEvent.Type.MouseMove)
                return True
            if et == QEvent.Type.MouseButtonRelease:
                self._editor_handle_drag = False
                self._forward_mouse(obj, event, QEvent.Type.MouseButtonRelease)
                return True
            return False
        if et != QEvent.Type.MouseButtonPress or event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._edit is None or self._text_editor_id is None:
            return False
        box = self._edit.objects.get(self._text_editor_id)
        if box is None:
            return False
        wr = self.pdf_rect_to_widget(box.page_index, box.rect)
        if wr is None:
            return False
        try:
            pc = obj.mapTo(self, event.position().toPoint())
        except RuntimeError:
            return False
        if not self._hit_handle(pc, wr):
            return False
        self._editor_handle_drag = True
        self._forward_mouse(obj, event, QEvent.Type.MouseButtonPress)
        return True

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        ed = self._text_editor
        if getattr(self, "_editor_handle_drag", False) or (ed is not None and obj is ed.viewport()):
            try:
                if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                                    QEvent.Type.MouseButtonRelease) and isinstance(obj, QWidget) \
                        and self._editor_handle_event(obj, event):
                    return True
            except RuntimeError:
                pass
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
                    QTimer.singleShot(0, self._close_text_editor_unless_formatting)
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
        popup = getattr(self, "_note_popup", None)
        if popup is not None and popup.isVisible():
            on_open_note = False
            if mapped is not None and popup.key is not None and mapped[0] == popup.key[0]:
                found = self._annotation_at(mapped[0], mapped[1])
                on_open_note = found is not None and int(found[1]) == popup.key[1]
            if not on_open_note:
                self.close_note_popup()  # a click elsewhere closes an open note (its own note toggles it on release)
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
        self._field_text_drag = False
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._marquee_before = (list(self._edit.selection), list(self._edit.field_selection))

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
                    self._resize_grab = self._handle_grab_offset(fsel.object_id, handle, pdf_pt)
                    self._drag_before = {fsel.object_id: Rect(*fsel.rect.as_tuple())}
                    self._live_interaction = True
                    self._shift_constrain = False
                    self._drag_perf.clear()
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return

        # Select mode: click selects / moves fields; double-click (or Enter) fills text.
        # Opening the editor on every single click made created fields undraggable (BUG-19/21).
        if self._edit.tool == EditTool.SELECT:
            field = self._hit_form_field(page_index, pdf_pt)
            if field is not None and not field.is_candidate:
                if ctrl and not field.readonly:
                    # Ctrl+click adds / removes boxes without typing, e.g. to change their font together
                    sel_boxes, sel_fields = self._marquee_before
                    if field.object_id in sel_fields:
                        sel_fields = [i for i in sel_fields if i != field.object_id]
                    else:
                        sel_fields = [*sel_fields, field.object_id]
                    self._edit.field_selection = sel_fields
                    self._edit.selection = [o for o in sel_boxes if o in self._edit.objects]
                    self._edit.editing_field_id = None
                    self._edit._notify()  # noqa: SLF001
                    self.update()
                    return
                if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
                    self._activate_form_fill(field)
                    return
                if field.field_type == FieldType.DROPDOWN and field.options:
                    self._activate_form_fill(field)
                    return
                was_selected = (
                    field.object_id in self._edit.field_selection
                    and len(self._edit.field_selection) == 1
                    and not self._edit.selection
                )
                self._edit.field_selection = [field.object_id]
                self._edit.selection = []
                self._edit.editing_field_id = None
                if was_selected and not field.readonly and field.field_type not in (
                    FieldType.CHECKBOX, FieldType.RADIO, FieldType.SIGNATURE,
                ):
                    # Second press on the selected field: type / drag to select words (BUG-19).
                    # First press still selects+moves so newly created fields stay draggable (BUG-21).
                    if self.open_field_editor(field, click_pos=event.position().toPoint()):
                        self._field_text_drag = True
                        self._mode = "typing_field"
                        return
                self._field_click_edit = False
                self._mode = "drag_move"
                self._drag_before = {field.object_id: Rect(*field.rect.as_tuple())}
                self._live_interaction = True
                self._edit._notify()  # noqa: SLF001
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
            if self._is_line_shape(target):
                handle = self._hit_line_end(event.position().toPoint(), page_index, target)
                if handle is None:
                    continue
                self._line_before = {k: getattr(target, k) for k in ("x0", "y0", "x1", "y1", "rect")}
            else:
                handle = self._hit_handle(event.position().toPoint(), wr)
            if handle:
                self._mode = "drag_resize"
                self._resize_handle = handle
                self._resize_oid = oid
                self._resize_grab = self._handle_grab_offset(oid, handle, pdf_pt)
                self._drag_before = self._edit.begin_transform_snapshot()
                self._live_interaction = True
                self._shift_constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._drag_perf.clear()
                return

        hit = self._edit.hit_test(page_index, pdf_pt)
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._collapse_on_release = None
        if hit:
            if hit not in self._edit.selection:
                self._edit.selection = [hit] if not additive else list(
                    dict.fromkeys([*self._edit.selection, hit])
                )
                self._edit.field_selection = []
                self._edit._notify()  # noqa: SLF001
            elif not additive and len(self._edit.selection) > 1:
                # Pressing on one of several selected objects keeps them all selected, so a drag moves
                # them together; a click without moving selects only this one (on release).
                self._collapse_on_release = hit
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
                self._annot_drag_pix = self._annotation_pixmap(found[0], found[1]) if self._mode == "annot_move" else None
                self.annotationSelected.emit(found[0], found[1])
                if found[2] != "Text":
                    self.close_note_popup()
                # a sticky note opens on release when it was clicked, not dragged
            elif self._edit.tool in (EditTool.SELECT, EditTool.FORM_SELECT, EditTool.LAYOUT_SELECT):
                # Empty paper: a drag draws a selection rectangle (a click just deselects, as before)
                self._mode = "marquee"
                self._marquee_page = page_index
                self._marquee_origin = self._marquee_current = pdf_pt
                self._marquee_additive = ctrl
        if hit:
            self.clear_annotation_selection()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        import time

        if self._edit is None:
            return super().mouseMoveEvent(event)
        if self._field_text_drag:
            ed = self._field_editor
            if ed is not None and event.buttons() & Qt.MouseButton.LeftButton:
                from PySide6.QtGui import QTextCursor

                spot = ed.viewport().mapFrom(self, event.position().toPoint())
                cur = ed.textCursor()
                cur.setPosition(ed.cursorForPosition(spot).position(), QTextCursor.MoveMode.KeepAnchor)
                ed.setTextCursor(cur)
                return
            self._field_text_drag = False
        if self._mode == "marquee" and self._marquee_origin is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._marquee_current = self._widget_to_page_point(self._marquee_page, event.position().toPoint())
                self.update()
            return
        mapped = self.widget_to_pdf(event.position().toPoint())
        if mapped is None:
            return
        page_index, pdf_pt = mapped

        if self._mode == "annot_move" and self._annot_sel is not None and self._press_pdf is not None \
                and event.buttons() & Qt.MouseButton.LeftButton and page_index == self._annot_sel[0]:
            old = self._annot_drag_widget_rect()
            self._annot_drag = (pdf_pt.x - self._press_pdf.x, pdf_pt.y - self._press_pdf.y)
            new = self._annot_drag_widget_rect()
            popup = getattr(self, "_note_popup", None)
            if popup is not None and popup.isVisible() and (abs(self._annot_drag[0]) >= 1 or abs(self._annot_drag[1]) >= 1):
                self.close_note_popup()
            if old is not None and new is not None:
                self.update(old.united(new).adjusted(-6, -6, 6, 6))  # only where the note was and is
            else:
                self.update()
            return

        if self._region_pick is not None:
            if self._region_origin is not None:
                pt = self._clamp_to_page(self._region_page, pdf_pt)
                self._region_current = pt
                if self._region_pick[2] in ("stroke", "erase_stroke"):
                    if not self._region_stroke or (
                        abs(pt.x - self._region_stroke[-1].x) > 0.4
                        or abs(pt.y - self._region_stroke[-1].y) > 0.4
                    ):
                        self._region_stroke.append(pt)
                        # repaint only the newest piece of the stroke (the whole page was redrawn on
                        # every mouse move, which made long strokes lag)
                        if len(self._region_stroke) >= 2:
                            a = self.pdf_to_widget(self._region_page, self._region_stroke[-2])
                            b = self.pdf_to_widget(self._region_page, self._region_stroke[-1])
                            if a is not None and b is not None:
                                w = int(max(4.0, 11.0 * self._zoom)) + 4
                                self.update(QRect(a, b).normalized().adjusted(-w, -w, w, w))
                                return
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
                self._hover_annot_key = None
                self.update()
            if not hid:
                self._update_annotation_hover(page_index, pdf_pt)

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
            ids = list(self._drag_before.keys())
            before = self._live_dirty_rects(ids)  # where they are drawn now (the previous move)
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
            self._edit.live_translate(ids, dx, dy, snap=True, notify=False)
            region = QRegion()
            for r in before + self._live_dirty_rects(ids):
                region = region.united(QRegion(r))
            self._live_region = region
            self._edit._notify()  # noqa: SLF001
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
            if self._resize_handle in ("p0", "p1") and self._is_line_shape(box):
                from core.editing.shape_box import constrain_line_angle

                ids = [self._resize_oid]
                before_rects = self._live_dirty_rects(ids)
                fixed = Point(box.x1, box.y1) if self._resize_handle == "p0" else Point(box.x0, box.y0)
                pt = self._clamp_to_page(box.page_index, pdf_pt)
                pt = constrain_line_angle(fixed, pt, snap=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                if self._resize_handle == "p0":
                    box.x0, box.y0 = pt.x, pt.y
                else:
                    box.x1, box.y1 = pt.x, pt.y
                box.sync_rect_from_line()
                self._live_interaction = True
                region = QRegion()
                for r in before_rects + self._live_dirty_rects(ids):
                    region = region.united(QRegion(r))
                self._live_region = region
                self._edit._notify()  # noqa: SLF001
                self._drag_perf.append((time.perf_counter() - t0) * 1000)
                return
            base = self._drag_before.get(self._resize_oid, box.rect)
            gx, gy = getattr(self, "_resize_grab", (0.0, 0.0))
            pdf_pt = Point(pdf_pt.x + gx, pdf_pt.y + gy)  # the edge moves with the mouse, without a jump
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._shift_constrain = shift
            shape = self._edit.shapes.get(self._resize_oid)
            image = self._edit.images.get(self._resize_oid)
            if image is not None:
                # Pictures keep their proportions (Shift: stretch freely; or when unlocked, Shift keeps them)
                keep = bool(getattr(image, "lock_aspect", True)) != shift
                rect = resize_rect(base, self._resize_handle, pdf_pt, keep_ratio=keep)
            elif shape is not None and (shift or shape.lock_aspect) and shape.kind.value not in ("line", "arrow", "freehand"):
                rect = resize_rect(base, self._resize_handle, pdf_pt, keep_ratio=True, square=shift and not shape.lock_aspect)
            else:
                rect = resize_rect(base, self._resize_handle, pdf_pt, keep_ratio=False, square=shift)
            self._live_interaction = True
            ids = [self._resize_oid]
            before = self._live_dirty_rects(ids)
            self._edit.live_resize(self._resize_oid, rect, notify=False, constrained=True)
            # repaint only where the box was and is now (not the whole page) — smooth on large pages
            region = QRegion()
            for r in before + self._live_dirty_rects(ids):
                region = region.united(QRegion(r))
            self._live_region = region
            self._edit._notify()  # noqa: SLF001
            self._drag_perf.append((time.perf_counter() - t0) * 1000)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._editor_handle_drag = False  # a handle drag that began inside the text editor ends here
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
        self._field_text_drag = False
        if self._mode == "marquee":
            self._mode = "idle"
            self._finish_marquee()
            self.update()
            return
        if self._mode == "annot_move" and self._annot_sel is not None:
            self._mode = "idle"
            dx, dy = self._annot_drag or (0.0, 0.0)
            self._annot_drag = None
            self._annot_drag_pix = None
            if abs(dx) < 1.0 and abs(dy) < 1.0 and self._annot_sel[2] == "Text":
                # a click on a sticky note: open it (a second click closes it)
                popup = getattr(self, "_note_popup", None)
                key = (self._annot_sel[0], int(self._annot_sel[1]))
                if popup is not None and popup.isVisible() and popup.key == key:
                    self.close_note_popup()
                else:
                    self.open_note_popup(self._annot_sel[0], self._annot_sel[1], self._annot_sel[3])
                self.update()
                return
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
                    # about half a screen pixel: jitter goes, the hand's shape stays
                    self._edit.create_shape(self._press_page, Rect(0, 0, 1, 1), kind, points=pts,
                                            tolerance=0.6 / max(self._zoom, 0.25))
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
                    circle = bool(getattr(self._edit, "_force_shape_lock", False))
                    self._edit._force_shape_lock = False  # noqa: SLF001
                    if circle and kind == "ellipse":
                        side = max(rect.w, rect.h, 8.0)
                        rect = Rect(rect.x, rect.y, side, side)
                    # Drawn as a circle / square, but free to be reshaped afterwards: drag a side
                    # handle for an oval (Shift while resizing keeps the proportions)
                    self._edit.create_shape(self._press_page, rect, kind, lock_aspect=False)
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
                created_type = self._form_create_type
                self._edit.create_form_field(self._press_page, rect, created_type)
                # Sync toolbar/cursor to Forms Select so the new field can be dragged (BUG-21).
                self._edit.tool = EditTool.FORM_SELECT
                self.set_tool(EditTool.FORM_SELECT)
                self.requestStatus.emit(
                    f"Form field ({created_type}) created — drag to move, double-click to fill"
                )
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
                elif oid in self._edit.shapes:  # moving a shape was not undoable
                    cur = self._edit.shapes[oid].rect
                if cur is not None and (
                    abs(cur.x - before.x) > 0.5
                    or abs(cur.y - before.y) > 0.5
                    or abs(cur.w - before.w) > 0.5
                    or abs(cur.h - before.h) > 0.5
                ):
                    moved = True
                    break
            self._live_interaction = False
            pending_field_edit = bool(getattr(self, "_field_click_edit", False)) and not moved
            self._field_click_edit = False
            collapse = getattr(self, "_collapse_on_release", None)
            self._collapse_on_release = None
            if moved:
                self._edit.commit_transform(self._drag_before, name="Move")
            elif collapse is not None and collapse in self._edit.selection:
                self._edit.select([collapse])  # a click on one of several selected objects
                self._end_live_interaction()
            else:
                # Click without move: edit a previously selected text field, else keep selection
                field_id = next(iter(self._drag_before), None)
                field = self._edit.fields.get(field_id) if field_id else None
                if pending_field_edit and field is not None and not field.readonly and not field.is_candidate:
                    if field.field_type not in (FieldType.CHECKBOX, FieldType.RADIO, FieldType.SIGNATURE):
                        self._end_live_interaction()
                        self.open_field_editor(field, click_pos=self._press_pos)
                    else:
                        self._end_live_interaction()
                else:
                    self._end_live_interaction()
            self._write_drag_perf("move")
        elif self._mode == "drag_resize" and self._resize_handle in ("p0", "p1") and getattr(self, "_line_before", None):
            # moving a line's end: undo restores both ends exactly (direction included)
            from core.editing.edit_commands import SetOverlayAttrsCommand

            self._live_interaction = False
            shape = self._edit.shapes.get(self._resize_oid)
            before, self._line_before = self._line_before, None
            if shape is not None:
                after = {k: getattr(shape, k) for k in ("x0", "y0", "x1", "y1", "rect")}
                if after != before:
                    self._edit.commands.push_executed(SetOverlayAttrsCommand(self._edit, shape.object_id, before, after))
                    self._edit.mark_dirty()
            self._write_drag_perf("resize")
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
        if kind in ("stroke", "erase_stroke"):
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
        if own and own in self._edit.images:  # a signature: change its text / style / ink; a picture: replace it
            self._edit.select([own])
            self._mode = "idle"
            self._live_interaction = False
            self.imageEditRequested.emit(own)
            return
        # A fillable field — also one just added in Forms mode, where a click selects / moves it:
        # double-click fills it (type, tick, choose). Never falls through to editing the page text
        # printed underneath the field.
        field = self._hit_form_field(page_index, pdf_pt)
        if field is not None and not field.is_candidate:
            if self._field_editor is not None and self._field_editor_id == field.object_id:
                return  # already typing here: the editor selects the word itself
            if field.readonly:
                self.requestStatus.emit("This field is read-only")
                return
            if field.field_type == FieldType.SIGNATURE:
                self.requestStatus.emit("Signature field: use Sign ▸ Type / Draw a Signature to sign it")
                return
            if field.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
                return  # the first click of the double-click already ticked it; a second toggle would undo it
            self._press_pos = event.position().toPoint()
            self._mode = "idle"
            self._live_interaction = False
            self._activate_form_fill(field)
            self.update()
            return
        # A comment (sticky note, callout, stamp ...) on top of the page: edit its text
        if not own and self._edit.tool == EditTool.SELECT:
            found = self._annotation_at(page_index, pdf_pt)
            if found is not None and found[2] not in ("Highlight", "Underline", "StrikeOut", "Squiggly", "Ink"):
                self._annot_sel = found
                self.close_note_popup()  # the first click of the double-click opened it
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
        popup = getattr(self, "_note_popup", None)
        if event.key() == Qt.Key.Key_Escape and popup is not None and popup.isVisible():
            popup.close_popup()
            return
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
                if self.history_handler is not None:
                    self.history_handler("undo")  # the window also redraws a changed page
                else:
                    self._edit.undo()
                return
            if key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and (mod & Qt.KeyboardModifier.ShiftModifier)):
                if self.try_editor_redo():
                    return
                if self.history_handler is not None:
                    self.history_handler("redo")
                else:
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

        # Keyboard nudging (shapes, text boxes, images, form fields; annotations via move signal)
        if (
            self._edit.editing_object_id is None
            and self._edit.editing_field_id is None
            and self._field_editor is None
            and self._text_editor is None
            and key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
        ):
            step = 10.0 if mod & Qt.KeyboardModifier.ShiftModifier else 1.0
            dx = -step if key == Qt.Key.Key_Left else step if key == Qt.Key.Key_Right else 0.0
            dy = -step if key == Qt.Key.Key_Up else step if key == Qt.Key.Key_Down else 0.0
            if self._edit.selection or self._edit.field_selection:
                self._edit.nudge_selection(dx, dy)
                return
            if self._annot_sel is not None:
                page_index, xref, _kind, rect = self._annot_sel
                # Keep the annotation on the page (same clamp as overlay objects).
                try:
                    page = self._edit.pdf.page(page_index)
                    pw, ph = float(page.display_width_pt), float(page.display_height_pt)
                    r = rect.normalized()
                    ndx = min(max(dx, min(0.0, pw - r.w) - r.x), max(0.0, pw - r.w) - r.x)
                    ndy = min(max(dy, min(0.0, ph - r.h) - r.y), max(0.0, ph - r.h) - r.y)
                except Exception:  # noqa: BLE001
                    ndx, ndy = dx, dy
                if ndx or ndy:
                    self._annot_sel = (page_index, xref, _kind, rect.translated(ndx, ndy))
                    self.annotationMoveRequested.emit(page_index, xref, float(ndx), float(ndy))
                    self.viewport().update()
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
    imageEditRequested = Signal(str)  # double-click on a placed picture / signature

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
        self._canvas.imageEditRequested.connect(self.imageEditRequested.emit)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        from ui.autoscroll import AutoScroller

        # Scroll button: middle-click / hold on a page, or View ▸ Automatic Scrolling
        self.autoscroll = AutoScroller(self)
        self._canvas.installEventFilter(self)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.MiddleButton
            and obj in (self._canvas, self.viewport())
            and self._canvas._layouts  # noqa: SLF001
        ):
            pos = self.viewport().mapFromGlobal(event.globalPosition().toPoint())
            self.autoscroll.begin_middle(pos)
            return True
        return super().eventFilter(obj, event)

    def start_reading_scroll(self) -> None:
        """View ▸ Automatic Scrolling: steady scrolling (↓/↑ change the speed, Esc stops)."""
        if self._canvas._layouts:  # noqa: SLF001
            self.autoscroll.start_reading()

    def clear_document(self) -> None:
        self.autoscroll.stop()
        self._canvas.clear_document()

    def open_note_popup(self, page_index: int, xref: int) -> bool:
        return self._canvas.open_note_popup(page_index, xref)

    def refresh_note_popup(self) -> None:
        self._canvas.refresh_note_popup()

    def close_note_popup(self) -> None:
        self._canvas.close_note_popup()

    def note_popup(self):
        return self._canvas.note_popup()

    def set_document(self, document: PdfDocument) -> None:
        self.autoscroll.stop()
        self._canvas.set_document(document)
        self._canvas.apply_zoom_for_viewport(self._fit_size())
        self._center_fit_page()
        self._on_scroll()

    def set_edit_model(self, edit: EditableDocument | None) -> None:
        self._canvas.set_edit_model(edit)

    def set_tool(self, tool: EditTool) -> None:
        self._canvas.set_tool(tool)
        self._canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_highlights(self, hits: list[tuple[int, object]], *, active: int = -1) -> None:
        self._canvas.set_highlights(hits, active=active)

    def set_active_highlight(self, index: int) -> None:
        self._canvas.set_active_highlight(index)

    def ensure_pdf_rect_visible(self, page_index: int, pdf_rect) -> None:
        """Scroll so a Find match (or similar) is visible on screen."""
        try:
            x0, y0 = float(pdf_rect.x0), float(pdf_rect.y0)
            x1, y1 = float(pdf_rect.x1), float(pdf_rect.y1)
        except Exception:  # noqa: BLE001
            self.go_to_page(page_index)
            return
        wr = self._canvas.pdf_rect_to_widget(page_index, Rect(x0, y0, x1 - x0, y1 - y0))
        if wr is None:
            self.go_to_page(page_index)
            return
        self.ensureVisible(wr.center().x(), wr.center().y(), max(40, wr.width() // 2 + 40), max(40, wr.height() // 2 + 60))
        # After the scroll: scrolling recomputes the focus page from the middle of the viewport, which is
        # still the previous page when the match is only just brought into view at the edge. The page of
        # the match is the current page (page commands, Select All and the page box act on it).
        self._canvas._focus_page = page_index  # noqa: SLF001
        self.pageChanged.emit(page_index)

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

    def refresh_page_content(self, pages) -> None:
        self._canvas.refresh_page_content(pages)

    def clear_annotation_selection(self) -> None:
        self._canvas.clear_annotation_selection()

    def release_memory(self) -> None:
        self._canvas.release_memory()

    def restore_after_release(self) -> None:
        self._canvas._schedule_render()  # noqa: SLF001

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
        self._canvas.set_fit_reference(index)
        self._center_fit_page()
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
        self._center_fit_page()

    def _center_fit_page(self) -> None:
        """Fit Width / Fit Page: centre the page the fit was measured on. In a document whose pages differ in
        width the canvas is as wide as the widest page; without this the fitted page sat off-centre and was
        cut off at the right edge, with a horizontal scroll bar."""
        inner = self._canvas
        if inner.zoom_mode not in (ZoomMode.FIT_WIDTH, ZoomMode.FIT_PAGE):
            return
        ref = inner._fit_ref_page  # noqa: SLF001
        if ref is None or not 0 <= ref < len(inner._layouts):  # noqa: SLF001
            return
        rect = inner._layouts[ref]  # noqa: SLF001
        bar = self.horizontalScrollBar()
        bar.setValue(max(bar.minimum(), min(bar.maximum(), rect.center().x() - self.viewport().width() // 2)))

    def set_manual_zoom(self, zoom: float, anchor: QPoint | None = None) -> None:
        """Zoom keeping the point under ``anchor`` (viewport coordinates; default: the centre of
        the view) where it is, so the text being read does not jump away."""
        inner = self._canvas
        vp = self.viewport()
        if anchor is None:
            anchor = QPoint(vp.width() // 2, vp.height() // 2)
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        content = QPoint(hb.value() + anchor.x(), vb.value() + anchor.y())
        page = inner.page_at_y(content.y())
        old = inner._layouts[page] if 0 <= page < len(inner._layouts) else None  # noqa: SLF001
        fx = fy = None
        if old is not None and old.width() > 0 and old.height() > 0:
            fx = (content.x() - old.left()) / old.width()
            fy = (content.y() - old.top()) / old.height()
        inner.set_manual_zoom(zoom, vp.size())
        new = inner._layouts[page] if 0 <= page < len(inner._layouts) else None  # noqa: SLF001
        if new is not None and fx is not None:
            hb.setValue(int(round(new.left() + fx * new.width() - anchor.x())))
            vb.setValue(int(round(new.top() + fy * new.height() - anchor.y())))

    def zoom_in(self, anchor: QPoint | None = None) -> None:
        self.set_manual_zoom(self.zoom * 1.15, anchor)

    def zoom_out(self, anchor: QPoint | None = None) -> None:
        self.set_manual_zoom(self.zoom / 1.15, anchor)

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
            self._center_fit_page()
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
            at = event.position().toPoint()  # viewport coordinates: the wheel event comes from the viewport
            # smooth for touchpads (small deltas) and one 15 % step per wheel notch
            steps = delta / 120.0
            if abs(steps) > 0:
                factor = 1.15 ** max(-3.0, min(3.0, steps))
                self.set_manual_zoom(self.zoom * factor, at)
            event.accept()
            return
        super().wheelEvent(event)
