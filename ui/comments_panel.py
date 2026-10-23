"""Comments panel: every comment and markup in the document, grouped by page.

Lists sticky notes, text callouts, stamps, highlights and other markup (imported ones included; links,
form fields and pop-up windows are not comments). Selecting an entry goes to its page; the buttons
edit its text, change its colour or opacity, or delete it — each change is undoable (the main window
runs them as commands). The list refreshes itself shortly after the document changes, and only while
the panel is visible. Nothing leaves the computer.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.toolbar_icons import set_action_icon

NOT_COMMENTS = {"Popup", "Link", "Widget", "PrinterMark", "TrapNet", "Watermark", "3D", "Screen", "Movie"}

KIND_LABELS = {
    "Text": "Note", "FreeText": "Text callout", "Stamp": "Stamp", "Highlight": "Highlight",
    "Underline": "Underline", "StrikeOut": "Strikethrough", "Squiggly": "Squiggly underline",
    "Ink": "Drawing", "Line": "Line", "Square": "Rectangle", "Circle": "Ellipse", "Polygon": "Polygon",
    "PolyLine": "Polyline", "FileAttachment": "Attached file", "Caret": "Insert mark", "Redact": "Redaction mark",
    "Sound": "Sound",
}
# Whose text can be edited from the panel
EDITABLE_TEXT = {"Text", "FreeText", "Stamp", "Highlight", "Underline", "StrikeOut", "Squiggly", "Ink",
                 "Line", "Square", "Circle", "Polygon", "PolyLine", "Caret"}
ROLE = Qt.ItemDataRole.UserRole


@dataclass(frozen=True)
class CommentRef:
    page_index: int
    xref: int
    kind: str
    rect: tuple[float, float, float, float]


class CommentsPanel(QWidget):
    commentActivated = Signal(object)  # CommentRef
    editTextRequested = Signal(object)
    colorRequested = Signal(object)
    opacityRequested = Signal(object)
    deleteRequested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._document = None
        self._stale = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(2)
        self._buttons: dict[str, QToolButton] = {}
        for key, icon, tip, signal in (
            ("edit", "rename", "Edit the selected comment's text", self.editTextRequested),
            ("color", "color", "Change the selected comment's colour", self.colorRequested),
            ("opacity", "background", "Change the selected comment's opacity", self.opacityRequested),
            ("delete", "delete", "Delete the selected comment (Undo restores it)", self.deleteRequested),
        ):
            b = QToolButton()
            b.setObjectName(f"Comment_{key}")
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            set_action_icon(b, icon)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.clicked.connect(lambda _c=False, s=signal: self._emit(s))
            tools.addWidget(b)
            self._buttons[key] = b
        tools.addStretch(1)
        self._count = QLabel("")
        self._count.setObjectName("ContextHint")
        tools.addWidget(self._count)
        layout.addLayout(tools)
        self._empty = QLabel("No comments or markup in this document.")
        self._empty.setWordWrap(True)
        self._empty.setObjectName("ContextHint")
        layout.addWidget(self._empty)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Comments")
        self.tree.setWordWrap(True)
        self.tree.setUniformRowHeights(False)
        self.tree.currentItemChanged.connect(lambda *_a: self._sync_buttons())
        self.tree.itemActivated.connect(self._activate)
        self.tree.itemClicked.connect(self._activate)
        self.tree.itemDoubleClicked.connect(lambda item, _c: self._double(item))
        layout.addWidget(self.tree, 1)
        layout.addStretch(0)  # no comments (list hidden): keep the tools and the message at the top
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self._sync_buttons()

    # --- data ------------------------------------------------------------------------------------

    def set_document(self, document) -> None:
        self._document = document
        self.mark_stale()

    def mark_stale(self) -> None:
        """The document changed: refresh soon if visible, else when next shown."""
        self._stale = True
        if self.isVisible():
            self._timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._stale:
            self._timer.start(0)

    def comments(self) -> list[CommentRef]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                out.append(group.child(j).data(0, ROLE))
        return out

    def refresh(self) -> None:
        from core.annotations import list_annotations

        self._stale = False
        selected = self.selected()
        expanded = {self.tree.topLevelItem(i).data(0, ROLE) for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        self.tree.clear()
        infos = []
        if self._document is not None:
            try:
                infos = [a for a in list_annotations(self._document)
                         if a.kind not in NOT_COMMENTS and not a.is_reply_or_popup]
            except Exception:  # noqa: BLE001 — a damaged annotation must not break the panel
                infos = []
        by_page: dict[int, list] = {}
        for a in infos:
            by_page.setdefault(a.page_index, []).append(a)
        current = None
        for page in sorted(by_page):
            group = QTreeWidgetItem([f"Page {page + 1}  ({len(by_page[page])})"])
            group.setData(0, ROLE, page)
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for a in sorted(by_page[page], key=lambda a: (round(a.rect[1]), a.rect[0])):
                label = KIND_LABELS.get(a.kind, a.kind)
                if a.kind == "Ink" and a.opacity < 0.95:
                    label = "Highlight"  # a free-area highlight stroke (see-through ink), not a drawing
                text = " ".join(a.content.split())
                marked = getattr(a, "marked_text", "")
                if not text and marked:
                    text = f"“{marked}”"
                preview = (text[:80] + "…") if len(text) > 80 else text
                line = label + (f" — {preview}" if preview else "")
                if a.author:
                    line += f"   ({a.author})"
                item = QTreeWidgetItem([line])
                if a.color:
                    from ui.color_swatches import swatch_icon

                    item.setIcon(0, swatch_icon(a.color, 14))
                ref = CommentRef(a.page_index, a.xref, a.kind, a.rect)
                item.setData(0, ROLE, ref)
                tip = label + (f"\n{a.content}" if a.content else "") + (f"\nAuthor: {a.author}" if a.author else "")
                item.setToolTip(0, tip)
                group.addChild(item)
                if selected and selected.xref == a.xref and selected.page_index == a.page_index:
                    current = item
            group.setExpanded(not expanded or page in expanded or len(by_page) <= 20)
        n = len(infos)
        self._count.setText(f"{n} item{'s' if n != 1 else ''}" if n else "")
        self._empty.setVisible(n == 0)
        self.tree.setVisible(n > 0)
        if current is not None:
            self.tree.setCurrentItem(current)
        self._sync_buttons()

    # --- selection -------------------------------------------------------------------------------

    def selected(self) -> CommentRef | None:
        item = self.tree.currentItem()
        data = item.data(0, ROLE) if item is not None else None
        return data if isinstance(data, CommentRef) else None

    def select(self, page_index: int, xref: int) -> bool:
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                ref = group.child(j).data(0, ROLE)
                if ref.page_index == page_index and ref.xref == xref:
                    group.setExpanded(True)
                    self.tree.setCurrentItem(group.child(j))
                    return True
        return False

    def _sync_buttons(self) -> None:
        ref = self.selected()
        for key, b in self._buttons.items():
            enabled = ref is not None
            if key == "edit":
                enabled = enabled and ref.kind in EDITABLE_TEXT
            if key in ("color", "opacity"):
                enabled = enabled and ref.kind not in ("FileAttachment", "Sound", "Redact")
            b.setEnabled(enabled)

    def _emit(self, signal) -> None:
        ref = self.selected()
        if ref is not None:
            signal.emit(ref)

    def _activate(self, item: QTreeWidgetItem, *_a) -> None:
        ref = item.data(0, ROLE)
        if isinstance(ref, CommentRef):
            self.commentActivated.emit(ref)

    def _double(self, item: QTreeWidgetItem) -> None:
        ref = item.data(0, ROLE)
        if isinstance(ref, CommentRef) and ref.kind in EDITABLE_TEXT:
            self.editTextRequested.emit(ref)
