"""Left navigation rail: Pages, Bookmarks, Search — compact icons when narrow."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.document import PdfDocument
from ui.thumbnail_panel import ThumbnailPanel
from ui.toolbar_icons import icon_bookmarks, icon_pages, icon_search, make_icon


class LeftRail(QTabWidget):
    pageActivated = Signal(int)
    pagesReordered = Signal(list)
    searchRequested = Signal(str)
    bookmarkActivated = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LeftRail")
        self.setDocumentMode(True)
        self.setMovable(False)
        self.setMinimumWidth(72)
        self.setMaximumWidth(360)
        self.setAccessibleName("Document navigation")
        self._compact = False

        self.thumbs = ThumbnailPanel()
        self.thumbs.setAccessibleName("Page thumbnails")
        self.thumbs.pageActivated.connect(self.pageActivated.emit)
        self.thumbs.pagesReordered.connect(self.pagesReordered.emit)
        self._pages_tab = self.addTab(self.thumbs, "Pages")
        self.setTabIcon(self._pages_tab, icon_pages())
        self.setTabToolTip(self._pages_tab, "Page thumbnails — drag to reorder")

        bookmarks_page = QWidget()
        bl = QVBoxLayout(bookmarks_page)
        bl.setContentsMargins(8, 8, 8, 8)
        self._bookmarks = QListWidget()
        self._bookmarks.setAccessibleName("Bookmarks")
        self._bookmarks.itemActivated.connect(self._on_bookmark)
        self._bookmarks_empty = QLabel("No bookmarks in this document.")
        self._bookmarks_empty.setWordWrap(True)
        self._bookmarks_empty.setObjectName("ContextHint")
        bl.addWidget(self._bookmarks_empty)
        bl.addWidget(self._bookmarks, 1)
        self._bookmarks_tab = self.addTab(bookmarks_page, "Bookmarks")
        self.setTabIcon(self._bookmarks_tab, icon_bookmarks())
        self.setTabToolTip(self._bookmarks_tab, "Outline / bookmarks when present")

        search_page = QWidget()
        sl = QVBoxLayout(search_page)
        sl.setContentsMargins(8, 8, 8, 8)
        sl.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search document…  (Enter)")
        self._search.setClearButtonEnabled(True)
        self._search.setAccessibleName("Document search")
        self._search.returnPressed.connect(self._emit_search)
        self._search_results = QListWidget()
        self._search_results.setAccessibleName("Search results")
        self._search_results.setWordWrap(True)
        self._search_count = QLabel("")
        self._search_count.setObjectName("ContextHint")
        self._search_results.itemActivated.connect(self._on_result)
        sl.addWidget(self._search)
        sl.addWidget(self._search_count)
        sl.addWidget(self._search_results, 1)
        self._search_tab = self.addTab(search_page, "Search")
        self.setTabIcon(self._search_tab, icon_search())
        self.setTabToolTip(self._search_tab, "Find text in the open document")

        # Attachments (optional)
        attach_page = QWidget()
        al = QVBoxLayout(attach_page)
        al.setContentsMargins(8, 8, 8, 8)
        self._attachments = QListWidget()
        self._attachments.setAccessibleName("Attachments")
        self._attach_empty = QLabel("No embedded attachments.")
        self._attach_empty.setWordWrap(True)
        self._attach_empty.setObjectName("ContextHint")
        al.addWidget(self._attach_empty)
        al.addWidget(self._attachments, 1)
        self._attach_tab = self.addTab(attach_page, "Files")
        self.setTabIcon(self._attach_tab, make_icon("attachments"))
        self.setTabToolTip(self._attach_tab, "Embedded file attachments when present")

        self._document: PdfDocument | None = None
        self._apply_tab_mode(compact=False)

    def refresh_icons(self) -> None:
        """Re-tint tab icons after a theme switch."""
        self.setTabIcon(self._pages_tab, icon_pages())
        self.setTabIcon(self._bookmarks_tab, icon_bookmarks())
        self.setTabIcon(self._search_tab, icon_search())
        self.setTabIcon(self._attach_tab, make_icon("attachments"))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_tab_mode(compact=self.width() < 150)

    def _apply_tab_mode(self, *, compact: bool) -> None:
        if compact == self._compact and self.count() > 0:
            # Still refresh labels if first call skipped
            pass
        self._compact = compact
        labels = {
            self._pages_tab: ("" if compact else "Pages"),
            self._bookmarks_tab: ("" if compact else "Bookmarks"),
            self._search_tab: ("" if compact else "Search"),
            self._attach_tab: ("" if compact else "Files"),
        }
        for idx, text in labels.items():
            if 0 <= idx < self.count():
                self.setTabText(idx, text)

    def clear_document(self) -> None:
        self._document = None
        self.thumbs.clear_document()
        self._bookmarks.clear()
        self._search_results.clear()
        self._attachments.clear()
        self._bookmarks_empty.show()
        self._attach_empty.show()
        self.setTabVisible(self._bookmarks_tab, False)
        self.setTabVisible(self._attach_tab, False)

    def set_document(self, document: PdfDocument) -> None:
        self._document = document
        self.thumbs.set_document(document)
        self._load_bookmarks(document)
        self._load_attachments(document)

    def set_current_page(self, index: int) -> None:
        self.thumbs.set_current_page(index)

    def selected_page_indices(self) -> list[int]:
        return self.thumbs.selected_page_indices()

    def set_search_hits(self, labels: list[tuple[int, str]]) -> None:
        self._search_results.clear()
        for page_index, snippet in labels:
            item = QListWidgetItem(f"Page {page_index + 1}\n{snippet}")
            item.setData(Qt.ItemDataRole.UserRole, page_index)
            item.setToolTip(snippet)
            self._search_results.addItem(item)
        n = len(labels)
        self._search_count.setText("" if not n else f"Found on {n} page{'s' if n != 1 else ''}")
        if labels:
            self.setCurrentIndex(self._search_tab)

    def _emit_search(self) -> None:
        self.searchRequested.emit(self._search.text())

    def _on_result(self, item: QListWidgetItem) -> None:
        idx = int(item.data(Qt.ItemDataRole.UserRole))
        self.pageActivated.emit(idx)

    def _on_bookmark(self, item: QListWidgetItem) -> None:
        idx = int(item.data(Qt.ItemDataRole.UserRole))
        self.bookmarkActivated.emit(idx)
        self.pageActivated.emit(idx)

    def _load_bookmarks(self, document: PdfDocument) -> None:
        self._bookmarks.clear()
        doc = document._backend._doc  # noqa: SLF001
        toc = []
        try:
            toc = doc.get_toc(simple=True) or []
        except Exception:  # noqa: BLE001
            toc = []
        if not toc:
            self._bookmarks_empty.show()
            self.setTabVisible(self._bookmarks_tab, False)
            return
        self._bookmarks_empty.hide()
        self.setTabVisible(self._bookmarks_tab, True)
        for entry in toc:
            if not entry or len(entry) < 3:
                continue
            level, title, page1 = int(entry[0]), str(entry[1] or "Untitled"), int(entry[2])
            page0 = max(0, min(document.page_count - 1, page1 - 1))
            indent = "  " * max(0, level - 1)
            item = QListWidgetItem(f"{indent}{title}")
            item.setData(Qt.ItemDataRole.UserRole, page0)
            self._bookmarks.addItem(item)

    def _load_attachments(self, document: PdfDocument) -> None:
        self._attachments.clear()
        try:
            from core.security import inspect_attachments

            items = inspect_attachments(document)
        except Exception:  # noqa: BLE001
            items = []
        if not items:
            self._attach_empty.show()
            self.setTabVisible(self._attach_tab, False)
            return
        self._attach_empty.hide()
        self.setTabVisible(self._attach_tab, True)
        for a in items:
            label = a.name if a.size is None else f"{a.name} ({a.size} bytes)"
            self._attachments.addItem(label)
