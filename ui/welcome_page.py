"""Professional empty-state welcome — shown only when no document is open."""

from __future__ import annotations

from pathlib import Path

import time

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

_PATH_ROLE = Qt.ItemDataRole.UserRole
_FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
_WHEN_ROLE = Qt.ItemDataRole.UserRole + 2


def _when(path: Path) -> str:
    """Short, friendly modified time: 'Today 14:05', 'Yesterday', '3 Oct', '2025-11-02'."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    now = time.localtime()
    t = time.localtime(ts)
    if t.tm_year == now.tm_year and t.tm_yday == now.tm_yday:
        return time.strftime("Today %H:%M", t)
    if t.tm_year == now.tm_year and t.tm_yday == now.tm_yday - 1:
        return "Yesterday"
    if t.tm_year == now.tm_year:
        return time.strftime("%d %b", t).lstrip("0")
    return time.strftime("%Y-%m-%d", t)


class _RecentDelegate(QStyledItemDelegate):
    """Two-line recent-file row: icon · name (+ date) over the folder path."""

    ROW = 46

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(0, self.ROW)

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = type(opt.icon)()
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        r = option.rect.adjusted(10, 5, -10, -5)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None and not icon.isNull():
            icon.paint(painter, QRect(r.left(), r.top() + (r.height() - 24) // 2, 24, 24))
        text_left = r.left() + 34
        pal = option.palette
        main = pal.color(QPalette.ColorRole.Text)  # the themed hover/selected fills are light
        muted = QColor(main)
        muted.setAlphaF(0.72)
        when = index.data(_WHEN_ROLE) or ""
        f = QFont(option.font)
        small = QFont(option.font)
        small.setPointSizeF(max(7.5, f.pointSizeF() - 1))
        painter.save()
        painter.setFont(small)
        when_w = painter.fontMetrics().horizontalAdvance(when) if when else 0
        painter.setPen(muted)
        if when:
            painter.drawText(QRect(r.right() - when_w, r.top(), when_w, r.height() // 2 + 2),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), when)
        folder = painter.fontMetrics().elidedText(
            index.data(_FOLDER_ROLE) or "", Qt.TextElideMode.ElideMiddle, r.right() - text_left
        )
        painter.drawText(QRect(text_left, r.top() + r.height() // 2, r.right() - text_left, r.height() // 2),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), folder)
        bold = QFont(f)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        painter.setPen(main)
        name_w = r.right() - text_left - (when_w + 12 if when else 0)
        name = painter.fontMetrics().elidedText(index.data(Qt.ItemDataRole.DisplayRole) or "", Qt.TextElideMode.ElideMiddle, name_w)
        painter.drawText(QRect(text_left, r.top(), name_w, r.height() // 2 + 2),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
        painter.restore()

from core.product_meta import PRODUCT_NAME, resolve_about_logo_path


class WelcomePage(QWidget):
    openRequested = Signal()
    openRecentRequested = Signal(str)
    combineRequested = Signal()
    imagesToPdfRequested = Signal()
    ocrRequested = Signal()
    toolRequested = Signal(str)
    removeRecentRequested = Signal(str)
    revealRequested = Signal(str)

    # (key, label, icon, tooltip, needs an open PDF)
    TOOLS = (
        ("merge", "Merge PDFs", "merge", "Combine several PDFs into one", False),
        ("office_to_pdf", "Word to PDF", "convert", "Word, Excel or PowerPoint to PDF", False),
        ("images_to_pdf", "Images to PDF", "import_images", "Create a PDF from images", False),
        ("pdf_to_word", "PDF to Word", "text_file", "Editable Word document that keeps the layout", True),
        ("rotate", "Rotate Pages", "rotate_cw", "Rotate all or some pages", True),
        ("protect", "Protect", "lock", "Add a password and set permissions", True),
        ("unlock", "Unlock", "unlock", "Remove a password you know", True),
        ("watermark", "Watermark", "watermark", "Add text such as CONFIDENTIAL", True),
        ("sign", "Sign", "sign", "Add a visual signature", True),
        ("ocr", "OCR a Scan", "ocr", "Make a scanned PDF searchable — offline", True),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomePage")
        self.setAcceptDrops(True)
        self.setAccessibleName("Welcome — open a PDF")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 40, 32, 40)
        root.addStretch(1)

        card = QFrame()
        card.setObjectName("WelcomeCard")
        card.setMaximumWidth(600)
        card.setMinimumWidth(520)
        cl = QVBoxLayout(card)
        cl.setSpacing(12)
        cl.setContentsMargins(28, 28, 28, 28)

        logo = QLabel()
        logo.setObjectName("WelcomeLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(72)
        path = resolve_about_logo_path()
        if path and path.is_file():
            pix = QPixmap(str(path))
            if not pix.isNull():
                dpr = self.devicePixelRatioF()
                target = int(64 * dpr)
                scaled = pix.scaled(
                    target,
                    target,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(dpr)
                logo.setPixmap(scaled)
        cl.addWidget(logo)

        title = QLabel(PRODUCT_NAME)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont(title.font())
        tf.setPointSize(tf.pointSize() + 6)
        tf.setBold(True)
        title.setFont(tf)
        cl.addWidget(title)

        sub = QLabel("Edit, convert, protect and sign PDFs — fully offline")
        sub.setObjectName("WelcomeSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)

        from ui.toolbar_icons import set_action_icon

        open_btn = QPushButton("Open PDF…")
        open_btn.setObjectName("WelcomePrimary")
        open_btn.setToolTip("Open a PDF  (Ctrl+O)")
        open_btn.setDefault(True)
        open_btn.setMinimumHeight(36)
        open_btn.clicked.connect(self.openRequested.emit)
        cl.addWidget(open_btn)

        drop = QLabel("or drag a PDF, image or Office file here  ·  Ctrl+O")
        drop.setObjectName("WelcomeDropHint")
        drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(drop)

        self._recent_label = QLabel("RECENT FILES")
        self._recent_label.setObjectName("WelcomeSection")
        self._recent = QListWidget()
        self._recent.setObjectName("WelcomeRecent")
        self._recent.setItemDelegate(_RecentDelegate(self._recent))
        self._recent.setFixedHeight((_RecentDelegate.ROW + 2) * 3 + 8)
        self._recent.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._recent.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._recent.setMouseTracking(True)
        self._recent.setToolTip("Click to open · right-click for more")
        self._recent.itemClicked.connect(self._on_recent)
        self._recent.itemActivated.connect(self._on_recent)
        self._recent.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recent.customContextMenuRequested.connect(self._recent_menu)
        self._recent_empty = QLabel("Files you open will be listed here.")
        self._recent_empty.setObjectName("WelcomeDropHint")
        self._recent_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self._recent_label)
        cl.addWidget(self._recent)
        cl.addWidget(self._recent_empty)

        quick = QLabel("TOOLS")
        quick.setObjectName("WelcomeSection")
        cl.addWidget(quick)
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QGridLayout, QSizePolicy, QToolButton

        grid = QGridLayout()
        grid.setSpacing(8)
        self._tool_buttons: dict[str, QToolButton] = {}
        for i, (key, label, icon_name, tip, needs_doc) in enumerate(self.TOOLS):
            btn = QToolButton()
            btn.setObjectName("ToolTile")
            btn.setText(label)
            btn.setToolTip(tip + (" — you’ll be asked to choose a PDF" if needs_doc else ""))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(24, 24))
            btn.setMinimumSize(QSize(86, 72))
            btn.setFixedHeight(72)
            # Every tile takes an equal share of the row so the grid lines up
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            set_action_icon(btn, icon_name)
            btn.clicked.connect(lambda _=False, k=key: self.toolRequested.emit(k))
            grid.addWidget(btn, i // 5, i % 5)
            self._tool_buttons[key] = btn
        for col in range(5):
            grid.setColumnStretch(col, 1)
        cl.addLayout(grid)

        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(card)
        wrap.addStretch(1)
        root.addLayout(wrap)
        root.addStretch(2)

    def set_recent(self, paths: list[Path]) -> None:
        from ui.toolbar_icons import make_icon

        self._recent.clear()
        self._recent_label.show()
        self._recent.setVisible(bool(paths))
        self._recent_empty.setVisible(not paths)
        for path in paths[:10]:
            item = QListWidgetItem(path.name)
            item.setData(_PATH_ROLE, str(path))
            item.setData(_FOLDER_ROLE, str(path.parent))
            item.setData(_WHEN_ROLE, _when(path))
            kind = "text_file" if path.suffix.lower() == ".pdf" else "import_images"
            item.setIcon(make_icon(kind))
            item.setToolTip(str(path))
            self._recent.addItem(item)

    def _recent_menu(self, pos) -> None:
        item = self._recent.itemAt(pos)
        if item is None:
            return
        path = str(item.data(_PATH_ROLE))
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.openRecentRequested.emit(path))
        menu.addAction("Show in Folder", lambda: self.revealRequested.emit(path))
        menu.addSeparator()
        menu.addAction("Remove from List", lambda: self.removeRecentRequested.emit(path))
        menu.exec(self._recent.viewport().mapToGlobal(pos))

    def _on_recent(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.openRecentRequested.emit(str(path))
