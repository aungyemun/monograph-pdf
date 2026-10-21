"""Left navigation rail: Pages, Bookmarks, Search — compact icons when narrow."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.document import PdfDocument
from ui.thumbnail_panel import ThumbnailPanel
from ui.toolbar_icons import icon_bookmarks, icon_pages, icon_search, make_icon, set_action_icon


class _RailTabBar(QTabBar):
    """Tabs without a label are only as wide as their icon plus a small margin (the style's default added
    about 20 px per tab), so all five fit a narrow panel instead of sliding out of view."""

    def _narrow(self, index: int, size: QSize) -> QSize:
        if not self.tabText(index):
            size.setWidth(min(size.width(), self.iconSize().width() + 16))
        return size

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802
        return self._narrow(index, super().tabSizeHint(index))

    def minimumTabSizeHint(self, index: int) -> QSize:  # noqa: N802
        return self._narrow(index, super().minimumTabSizeHint(index))


class LeftRail(QTabWidget):
    pageActivated = Signal(int)
    pagesReordered = Signal(list)
    searchRequested = Signal(str)
    bookmarkActivated = Signal(int)
    # Bookmark editing requests (index in the flat outline; -1 = none selected)
    bookmarkAddRequested = Signal(int)
    bookmarkRenameRequested = Signal(int)
    bookmarkDeleteRequested = Signal(int)
    bookmarkMoveRequested = Signal(int, int)
    bookmarkRetargetRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTabBar(_RailTabBar())
        self.setObjectName("LeftRail")
        self.setDocumentMode(True)
        self.setMovable(False)
        self.setMinimumWidth(170)  # the five tab icons always fit (narrower: drag the splitter to hide the panel)
        # Never hide tabs behind scroll arrows: a label that does not fit is shortened ("Bookm…")
        self.tabBar().setUsesScrollButtons(False)
        self.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
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
        self._bookmarks.itemClicked.connect(self._on_bookmark)
        self._bookmarks.currentRowChanged.connect(lambda _r: self._sync_bookmark_buttons())
        self._bookmarks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._bookmarks.customContextMenuRequested.connect(self._bookmark_menu)
        self._bookmarks_empty = QLabel("No bookmarks yet. Use Add Bookmark to mark the current page.")
        self._bookmarks_empty.setWordWrap(True)
        self._bookmarks_empty.setObjectName("ContextHint")
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(2)
        self._bm_buttons: dict[str, QToolButton] = {}
        for key, icon_name, tip, slot in (
            ("add", "bookmark_add", "Add a bookmark for the current page (Ctrl+B)",
             lambda: self.bookmarkAddRequested.emit(self._bookmarks.currentRow())),
            ("rename", "rename", "Rename the selected bookmark (F2)",
             lambda: self.bookmarkRenameRequested.emit(self._bookmarks.currentRow())),
            ("target", "bookmark_target", "Point the selected bookmark at the current page",
             lambda: self.bookmarkRetargetRequested.emit(self._bookmarks.currentRow())),
            ("up", "move_up", "Move the selected bookmark up",
             lambda: self.bookmarkMoveRequested.emit(self._bookmarks.currentRow(), -1)),
            ("down", "move_down", "Move the selected bookmark down",
             lambda: self.bookmarkMoveRequested.emit(self._bookmarks.currentRow(), 1)),
            ("delete", "delete", "Delete the selected bookmark and the bookmarks under it",
             lambda: self.bookmarkDeleteRequested.emit(self._bookmarks.currentRow())),
        ):
            b = QToolButton()
            b.setObjectName(f"Bookmark_{key}")
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            set_action_icon(b, icon_name)
            b.setToolTip(tip)
            b.setAccessibleName(tip.split(" (")[0])
            b.clicked.connect(slot)
            tools.addWidget(b)
            self._bm_buttons[key] = b
        tools.addStretch(1)
        bl.addLayout(tools)
        bl.addWidget(self._bookmarks_empty)
        bl.addWidget(self._bookmarks, 1)
        self._bookmarks_tab = self.addTab(bookmarks_page, "Bookmarks")
        self.setTabIcon(self._bookmarks_tab, icon_bookmarks())
        self.setTabToolTip(self._bookmarks_tab, "Bookmarks — go to, add, rename, reorder or delete")

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

        from ui.comments_panel import CommentsPanel

        self.comments = CommentsPanel()
        self._comments_tab = self.addTab(self.comments, "Comments")
        self.setTabIcon(self._comments_tab, make_icon("comments_panel"))
        self.setTabToolTip(self._comments_tab, "Comments and markup by page — go to, edit or delete")

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
        self.currentChanged.connect(lambda _i: self._apply_tab_mode(compact=self.width() < 150))
        self._apply_tab_mode(compact=False)

    def refresh_icons(self) -> None:
        """Re-tint tab icons after a theme switch."""
        self.setTabIcon(self._pages_tab, icon_pages())
        self.setTabIcon(self._bookmarks_tab, icon_bookmarks())
        self.setTabIcon(self._search_tab, icon_search())
        self.setTabIcon(self._comments_tab, make_icon("comments_panel"))
        self.setTabIcon(self._attach_tab, make_icon("attachments"))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_tab_mode(compact=self.width() < 150)

    TAB_LABELS = ("Pages", "Bookmarks", "Search", "Comments", "Files")

    def _apply_tab_mode(self, *, compact: bool) -> None:
        """Tab labels that fit the panel: every label when there is room; otherwise only the
        current tab keeps its label and the others show their icon (each tab has a tooltip);
        icons only when the panel is very narrow. Tabs never hide behind scroll arrows when
        icons alone fit."""
        self._compact = compact
        tabs = (self._pages_tab, self._bookmarks_tab, self._search_tab, self._comments_tab, self._attach_tab)
        if getattr(self, "_relabelling", False) or not all(0 <= t < self.count() for t in tabs):
            return
        self._relabelling = True
        try:
            current = self.currentIndex()

            def label(show) -> None:
                for idx, text in zip(tabs, self.TAB_LABELS):
                    want = text if show(idx) else ""
                    if self.tabText(idx) != want:
                        self.setTabText(idx, want)

            if compact:
                label(lambda _i: False)
                return
            label(lambda _i: True)
            if self.tabBar().sizeHint().width() > self.width():
                label(lambda i: i == current)
            if self.tabBar().sizeHint().width() > self.width():
                # still too wide (a long label such as "Comments" in a narrow panel): Qt would slide the first
                # tabs out of view and leave icon fragments at the edge, so show icons only
                label(lambda _i: False)
        finally:
            self._relabelling = False

    def clear_document(self) -> None:
        self._document = None
        self.thumbs.clear_document()
        self.comments.set_document(None)
        self._bookmarks.clear()
        self._search_results.clear()
        self._attachments.clear()
        self._bookmarks_empty.show()
        self._attach_empty.show()
        self.setTabVisible(self._bookmarks_tab, False)
        self._sync_bookmark_buttons()
        self.setTabVisible(self._attach_tab, False)
        self._apply_tab_mode(compact=self.width() < 150)

    def set_document(self, document: PdfDocument) -> None:
        self._document = document
        self.thumbs.set_document(document)
        self.comments.set_document(document)
        self._load_bookmarks(document)
        self._load_attachments(document)
        self._apply_tab_mode(compact=self.width() < 150)

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
        if idx < 0:
            return
        self.bookmarkActivated.emit(idx)
        self.pageActivated.emit(idx)

    def _load_bookmarks(self, document: PdfDocument, *, select: int | None = None) -> None:
        from core.organize.bookmarks import list_bookmarks

        self._bookmarks.clear()
        marks = list_bookmarks(document)
        self.setTabVisible(self._bookmarks_tab, True)
        self._bookmarks_empty.setVisible(not marks)
        for bm in marks:
            indent = "    " * max(0, bm.level - 1)
            item = QListWidgetItem(f"{indent}{bm.title}")
            item.setData(Qt.ItemDataRole.UserRole, bm.page)
            item.setData(Qt.ItemDataRole.UserRole + 1, bm.index)
            item.setToolTip(f"{bm.title} — page {bm.page + 1}" if bm.page >= 0 else f"{bm.title} — no page in this file")
            self._bookmarks.addItem(item)
        if select is not None and 0 <= select < self._bookmarks.count():
            self._bookmarks.setCurrentRow(select)
        self._sync_bookmark_buttons()

    def reload_bookmarks(self, select: int | None = None) -> None:
        if self._document is not None:
            self._load_bookmarks(self._document, select=select)

    def current_bookmark(self) -> int:
        return self._bookmarks.currentRow()

    def show_bookmarks(self) -> None:
        self.setTabVisible(self._bookmarks_tab, True)
        self.setCurrentIndex(self._bookmarks_tab)

    def set_bookmarks_editable(self, editable: bool) -> None:
        self._bookmarks_editable = bool(editable)
        self._sync_bookmark_buttons()

    def _sync_bookmark_buttons(self) -> None:
        editable = getattr(self, "_bookmarks_editable", True) and self._document is not None
        has = self._bookmarks.currentRow() >= 0
        self._bm_buttons["add"].setEnabled(editable)
        for key in ("rename", "target", "up", "down", "delete"):
            self._bm_buttons[key].setEnabled(editable and has)

    def _bookmark_menu(self, pos) -> None:
        if self._document is None:
            return
        row = self._bookmarks.indexAt(pos).row()
        if row >= 0:
            self._bookmarks.setCurrentRow(row)
        menu = QMenu(self)
        for key, text in (("add", "Add Bookmark"), ("rename", "Rename…"), ("target", "Set to Current Page"),
                          ("up", "Move Up"), ("down", "Move Down"), ("delete", "Delete")):
            b = self._bm_buttons[key]
            act = menu.addAction(b.icon(), text)
            act.setEnabled(b.isEnabled())
            act.triggered.connect(b.click)
        menu.exec(self._bookmarks.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.currentIndex() == self._bookmarks_tab and self._bookmarks.hasFocus():
            if event.key() == Qt.Key.Key_F2 and self._bm_buttons["rename"].isEnabled():
                self._bm_buttons["rename"].click()
                return
            if event.key() == Qt.Key.Key_Delete and self._bm_buttons["delete"].isEnabled():
                self._bm_buttons["delete"].click()
                return
        super().keyPressEvent(event)

    def _load_attachments(self, document: PdfDocument) -> None:
        self._attachments.clear()
        try:
            from core.security import inspect_attachments

            items = inspect_attachments(document)
        except Exception:  # noqa: BLE001
            items = []
        if not items:
            self._attach_empty.show()
            if self.currentIndex() == self._attach_tab:
                self.setCurrentIndex(self._pages_tab)  # never leave a hidden tab selected
            self.setTabVisible(self._attach_tab, False)
            return
        self._attach_empty.hide()
        self.setTabVisible(self._attach_tab, True)
        for a in items:
            label = a.name if a.size is None else f"{a.name} ({a.size} bytes)"
            self._attachments.addItem(label)
