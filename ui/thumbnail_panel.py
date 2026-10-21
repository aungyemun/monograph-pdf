"""Left thumbnail panel with lazy thumbnails and optional drag-reorder."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal, Slot
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


class _ThumbSignals(QObject):
    """One long-lived hub owned by the panel.

    Each job used to own its own signals object; the auto-deleted QRunnable then
    destroyed it before the queued ``finished`` reached the GUI thread, so most
    thumbnails silently never appeared.
    """

    finished = Signal(int, int, QImage)  # page, generation, image
    failed = Signal(int, int, str)


class _ThumbJob(QRunnable):
    def __init__(self, document: PdfDocument, page_index: int, generation: int, hub: _ThumbSignals) -> None:
        super().__init__()
        self.document = document
        self.page_index = page_index
        self.generation = generation
        self.hub = hub
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            if self.document.is_closed:
                self.hub.failed.emit(self.page_index, self.generation, "closed")
                return
            png = self.document.render_thumbnail_png(self.page_index, max_edge_px=180)
            image = QImage.fromData(png, "PNG")
            self.hub.finished.emit(self.page_index, self.generation, image)
        except Exception as exc:  # noqa: BLE001
            self.hub.failed.emit(self.page_index, self.generation, str(exc))


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
        self._pending: set[int] = set()
        self._pool = QThreadPool.globalInstance()
        self._hub = _ThumbSignals(self)
        self._hub.finished.connect(self._on_thumb_ready)
        self._hub.failed.connect(self._on_fail)
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

    def clear_document(self) -> None:
        self._generation += 1
        self._pending.clear()
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
        for i in range(max(0, start - 2), min(self.count(), end + 6)):
            self._request(i)

    def _request(self, page_index: int) -> None:
        if self._document is None or page_index in self._pending:
            return
        item = self.item(page_index)
        if item is None:
            return
        if not item.icon().isNull():
            return
        self._pending.add(page_index)
        self._pool.start(_ThumbJob(self._document, page_index, self._generation, self._hub))

    @Slot(int, int, QImage)
    def _on_thumb_ready(self, page_index: int, generation: int, image: QImage) -> None:
        if generation != self._generation:
            return
        self._pending.discard(page_index)
        if self._document is None or self._document.is_closed or image.isNull():
            return
        item = self.item(page_index)
        if item is None:
            return
        item.setIcon(QIcon(QPixmap.fromImage(image)))

    @Slot(int, int, str)
    def _on_fail(self, page_index: int, generation: int, _message: str) -> None:
        if generation == self._generation:
            self._pending.discard(page_index)
