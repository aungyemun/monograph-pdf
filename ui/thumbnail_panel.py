"""Left thumbnail panel with lazy thumbnails and optional drag-reorder."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from core.document import PdfDocument

THUMB_EDGE_PX = 180  # longest edge of a thumbnail picture
THUMB_STEP_BUDGET_S = 0.010  # thumbnails drawn per event-loop turn (at least one), then input is handled
THUMB_BUSY_RETRY_MS = 60  # the page view is scrolling or drawing: thumbnails wait this long and look again


def render_thumbnail_image(document: PdfDocument, page_index: int, max_edge_px: int = THUMB_EDGE_PX) -> QImage:
    """The thumbnail picture of a page, straight from the renderer's pixels (no PNG round trip).

    Drawn on the GUI thread: PyMuPDF keeps Python's GIL while it renders, so a worker thread froze the
    window just as long, and the open document was used from two threads at once."""
    page = document.page(page_index)
    edge = max(page.display_width_pt, page.display_height_pt) or 1.0
    samples, w, h, stride = document.render_rgb(page_index, scale=max_edge_px / edge)
    from ui.display_color import to_display

    return to_display(QImage(samples, w, h, stride, QImage.Format.Format_RGB888).copy())


def _pal():
    try:
        from ui.theme import current_palette

        return current_palette()
    except Exception:  # noqa: BLE001
        return None


class _ThumbDelegate(QStyledItemDelegate):
    """Page card: centered thumbnail with shadow, accent ring when selected, number below."""

    _LABEL_H = 20

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(132, 186)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        pal = _pal()
        accent = QColor(pal.accent if pal else "#0f766e")
        muted = QColor(pal.text_muted if pal else "#5f6b7a")
        hover_bg = QColor(pal.hover if pal else "#eef1f4")
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if hovered and not selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover_bg)
            painter.drawRoundedRect(QRectF(r), 8, 8)

        icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
        area = QRect(r.left() + 10, r.top() + 8, r.width() - 20, r.height() - self._LABEL_H - 20)
        page_rect = QRect(area.left() + area.width() // 2 - 45, area.top(), 90, int(90 * 1.294))
        pix = None
        if isinstance(icon, QIcon) and not icon.isNull():
            pix = icon.pixmap(area.size())
            if not pix.isNull():
                size = pix.deviceIndependentSize().toSize()
                size.scale(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
                page_rect = QRect(
                    area.left() + (area.width() - size.width()) // 2,
                    area.top() + (area.height() - size.height()) // 2,
                    size.width(),
                    size.height(),
                )
        # shadow + paper
        painter.setPen(Qt.PenStyle.NoPen)
        for spread, alpha in ((3, 16), (1, 30)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRect(page_rect.adjusted(-spread + 1, -spread + 2, spread + 1, spread + 2))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page_rect)
        if pix is not None and not pix.isNull():
            painter.drawPixmap(page_rect, pix)
        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(accent, 2.5))
            painter.drawRoundedRect(QRectF(page_rect.adjusted(-3, -3, 3, 3)), 3, 3)
        # page number pill
        label = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        lab_rect = QRect(r.left(), r.bottom() - self._LABEL_H - 1, r.width(), self._LABEL_H)
        f = painter.font()
        f.setBold(selected)
        painter.setFont(f)
        if selected:
            w = max(26, painter.fontMetrics().horizontalAdvance(label) + 14)
            pill = QRect(lab_rect.center().x() - w // 2, lab_rect.top() + 1, w, lab_rect.height() - 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(QRectF(pill), pill.height() / 2, pill.height() / 2)
            painter.setPen(QColor(pal.on_accent if pal else "#ffffff"))
        else:
            painter.setPen(muted)
        painter.drawText(lab_rect, int(Qt.AlignmentFlag.AlignCenter), label)
        painter.restore()


MAX_THUMB_IMAGES = 160  # thumbnails kept in memory; far-away ones are drawn again when scrolled to


class ThumbnailPanel(QListWidget):
    pageActivated = Signal(int)
    pagesReordered = Signal(list)  # new order of old indices
    selectionPagesChanged = Signal(list)  # selected 0-based indices

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Thumbnails")
        self.setMinimumWidth(140)
        # no maximum: a cap left an empty grey strip beside the thumbnails when the panel was widened
        self.setIconSize(QSize(120, 160))
        self.setSpacing(2)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(_ThumbDelegate(self))
        self.setToolTip("Click to go to a page · Ctrl/Shift-click to select several · drag to reorder")
        self.setMovement(QListWidget.Movement.Free)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.itemClicked.connect(self._on_click)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self._document: PdfDocument | None = None
        self._generation = 0
        # Thumbnails waiting to be drawn (front = most wanted) and the pages among them that already
        # show an older picture (drawn again after a change, kept until the new one is ready).
        self._pending: set[int] = set()
        self._queue: deque[int] = deque()
        self._refresh: set[int] = set()
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._thumb_step)
        self._busy_probe: Callable[[], bool] | None = None
        self._reorder_enabled = True
        self.verticalScrollBar().valueChanged.connect(self._schedule_visible)
        self._context_actions: list = []
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_context_actions(self, actions: list) -> None:
        """Actions offered on right-click (None = separator); they act on the selected pages."""
        self._context_actions = list(actions)

    def _context_menu(self, pos) -> None:
        menu = self.build_context_menu(pos)
        if menu is not None:
            menu.exec(self.viewport().mapToGlobal(pos))

    def build_context_menu(self, pos):
        """The right-click menu for the thumbnail at ``pos`` (selects it first); None off the pages."""
        from PySide6.QtWidgets import QMenu

        item = self.itemAt(pos)
        if item is None or not self._context_actions:
            return None
        if not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        self.setCurrentItem(item)
        self.pageActivated.emit(self.row(item))
        menu = QMenu(self)
        for act in self._context_actions:
            if act is None:
                menu.addSeparator()
            else:
                menu.addAction(act)
        return menu

    def set_reorder_enabled(self, enabled: bool) -> None:
        self._reorder_enabled = enabled
        mode = (
            QAbstractItemView.DragDropMode.InternalMove
            if enabled
            else QAbstractItemView.DragDropMode.NoDragDrop
        )
        self.setDragDropMode(mode)

    def set_busy_probe(self, probe: Callable[[], bool] | None) -> None:
        """``probe()`` is True while the page view is scrolling or drawing: thumbnails then wait, so
        they never take turns away from the pages being looked at."""
        self._busy_probe = probe

    def clear_document(self) -> None:
        self._generation += 1
        self._pending.clear()
        self._queue.clear()
        self._refresh.clear()
        self._thumb_timer.stop()
        self._document = None
        self.clear()

    def set_document(self, document: PdfDocument) -> None:
        self.clear_document()
        self._document = document
        for i in range(document.page_count):
            item = QListWidgetItem(f"{i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(132, 186))
            item.setToolTip(f"Page {i + 1}")
            self.addItem(item)
        self._schedule_visible()

    def set_current_page(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        self.setCurrentRow(index)

    def refresh_pages(self, indices) -> None:
        """Redraw the thumbnails of ``indices`` (content changed); each keeps its old picture until
        the new one is ready, and the other thumbnails are left alone. Thumbnails far from the view
        only forget their picture (drawn again when scrolled to): refreshing every page of a long
        document used to queue thousands of renders at once."""
        if self._document is None or self._document.is_closed:
            return
        if not self.isVisible():
            # hidden (another left-panel tab): which rows are in view is not known; forget the pictures,
            # they are drawn again when the panel is shown
            for i in {int(i) for i in indices}:
                item = self.item(i) if 0 <= i < self.count() else None
                if item is not None and not item.icon().isNull():
                    item.setIcon(QIcon())
            return
        start, end = self._visible_rows()
        near = range(max(0, start - 8), end + 9)
        for i in sorted({int(i) for i in indices}):
            if not 0 <= i < self.count():
                continue
            item = self.item(i)
            if i in near:
                self._refresh.add(i)
                self._enqueue(i, front=True)
            elif item is not None and not item.icon().isNull():
                item.setIcon(QIcon())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._schedule_visible)  # after the layout: the rows really in view

    def _visible_rows(self) -> tuple[int, int]:
        viewport = self.viewport().rect()
        first = self.indexAt(viewport.topLeft())
        last = self.indexAt(viewport.bottomLeft())
        start = first.row() if first.isValid() else 0
        end = last.row() if last.isValid() else min(self.count() - 1, start + 8)
        return start, end

    def release_images(self, *, keep_visible: bool = False) -> int:
        """Forget thumbnail pictures (all, or all but the visible ones); they are drawn again when
        scrolled to. Returns how many were released."""
        keep = range(0)
        if keep_visible:
            start, end = self._visible_rows()
            keep = range(max(0, start - 4), end + 9)
        released = 0
        for i in range(self.count()):
            if i in keep:
                continue
            item = self.item(i)
            if item is not None and not item.icon().isNull():
                item.setIcon(QIcon())
                released += 1
        return released

    def restore_images(self) -> None:
        self._schedule_visible()

    def _limit_images(self) -> None:
        loaded = sum(1 for i in range(self.count()) if not self.item(i).icon().isNull())
        if loaded > MAX_THUMB_IMAGES:
            self.release_images(keep_visible=True)

    def selected_page_indices(self) -> list[int]:
        rows = sorted({self.row(i) for i in self.selectedItems()})
        return rows

    def _on_click(self, item: QListWidgetItem) -> None:
        idx = self.row(item)
        self.pageActivated.emit(idx)

    def _on_selection_changed(self) -> None:
        self.selectionPagesChanged.emit(self.selected_page_indices())

    def dropEvent(self, event) -> None:  # noqa: N802
        if not self._reorder_enabled:
            event.ignore()
            return
        before = [int(self.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.count())]
        super().dropEvent(event)
        after_labels = []
        for i in range(self.count()):
            after_labels.append(int(self.item(i).data(Qt.ItemDataRole.UserRole)))
        # Relabel display numbers; emit old-index order
        for i in range(self.count()):
            self.item(i).setText(str(i + 1))
        if after_labels != before and after_labels:
            self.pagesReordered.emit(after_labels)

    def _schedule_visible(self) -> None:
        if self._document is None or self._document.is_closed:
            return
        viewport = self.viewport().rect()
        first = self.indexAt(viewport.topLeft())
        last = self.indexAt(viewport.bottomLeft())
        start = first.row() if first.isValid() else 0
        end = last.row() if last.isValid() else min(self.count() - 1, start + 8)
        wanted = [i for i in range(max(0, start - 2), min(self.count(), end + 6))]
        # visible rows first, in order, ahead of anything queued for rows scrolled away from
        for i in reversed(wanted):
            self._request(i, front=True)

    def _request(self, page_index: int, *, front: bool = False) -> None:
        if self._document is None:
            return
        item = self.item(page_index)
        if item is None or not item.icon().isNull():
            return
        self._enqueue(page_index, front=front)

    def _enqueue(self, page_index: int, *, front: bool) -> None:
        if page_index in self._pending:
            if front:
                try:
                    self._queue.remove(page_index)
                except ValueError:
                    pass
                self._queue.appendleft(page_index)
        else:
            self._pending.add(page_index)
            if front:
                self._queue.appendleft(page_index)
            else:
                self._queue.append(page_index)
        if not self._thumb_timer.isActive():
            self._thumb_timer.start(0)

    def _thumb_step(self) -> None:
        """Draw queued thumbnails for about one frame (at least one), then let input be handled."""
        doc = self._document
        if doc is None or doc.is_closed:
            self._queue.clear()
            self._pending.clear()
            self._refresh.clear()
            return
        probe = self._busy_probe
        if probe is not None:
            try:
                busy = bool(probe())
            except Exception:  # noqa: BLE001 — never let a probe stop the thumbnails
                busy = False
            if busy:
                self._thumb_timer.start(THUMB_BUSY_RETRY_MS)
                return
        if not self.isVisible():
            # nothing is seen: drawn when the panel is shown (showEvent); a changed page forgets its
            # old picture so it is not shown out of date then
            for i in self._refresh:
                item = self.item(i)
                if item is not None:
                    item.setIcon(QIcon())
            self._queue.clear()
            self._pending.clear()
            self._refresh.clear()
            return
        start, end = self._visible_rows()
        keep = range(max(0, start - 12), end + 13)
        deadline = time.perf_counter() + THUMB_STEP_BUDGET_S
        generation = self._generation
        while self._queue:
            i = self._queue.popleft()
            refresh = i in self._refresh
            self._refresh.discard(i)
            self._pending.discard(i)
            item = self.item(i)
            if item is None or (not refresh and (not item.icon().isNull() or i not in keep)):
                continue  # already drawn, or scrolled far away: drawn when it is shown again
            try:
                image = render_thumbnail_image(doc, i)
            except Exception as exc:  # noqa: BLE001
                self._on_fail(i, generation, str(exc))
            else:
                self._on_thumb_ready(i, generation, image)
            if self._generation != generation or self._document is not doc:
                return  # the document changed while drawing
            if time.perf_counter() >= deadline:
                break
        if self._queue:
            self._thumb_timer.start(0)

    @Slot(int, int, QImage)
    def _on_thumb_ready(self, page_index: int, generation: int, image: QImage) -> None:
        if generation != self._generation:
            return
        if self._document is None or self._document.is_closed or image.isNull():
            return
        item = self.item(page_index)
        if item is None:
            return
        item.setIcon(QIcon(QPixmap.fromImage(image)))
        if self.count() > MAX_THUMB_IMAGES and page_index % 16 == 0:  # cheap, occasional check
            self._limit_images()

    @Slot(int, int, str)
    def _on_fail(self, page_index: int, generation: int, _message: str) -> None:
        if generation == self._generation:
            self._pending.discard(page_index)
