"""Application-level dialogs: shortcuts reference, user guide, document properties,
signature pad, page-image export, and go-to-page."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogHint")
    lab.setWordWrap(True)
    return lab


# --------------------------------------------------------------------------- shortcuts

# Canvas keys handled by the page view itself (not menu actions)
CANVAS_KEYS: list[tuple[str, str]] = [
    ("Arrow keys", "Nudge selected objects 1 pt"),
    ("Shift + Arrow keys", "Nudge selected objects 10 pt"),
    ("Shift + drag", "Constrain shape: square / circle / 45° lines"),
    ("Ctrl + click", "Add / remove object from selection"),
    ("Double-click text", "Edit existing PDF text in place"),
    ("Esc", "Finish typing / cancel placement / back to Select"),
    ("Ctrl + Enter", "Commit text box and return to Select"),
    ("Tab / Shift + Tab", "Next / previous fillable form field"),
    ("Ctrl + mouse wheel", "Zoom in / out"),
]


def _clean(text: str) -> str:
    return text.replace("&&", "\u0000").replace("&", "").replace("\u0000", "&").replace("…", "").strip()


def collect_shortcuts(menubar: QMenuBar) -> list[tuple[str, str, str]]:
    """(menu, command, shortcut) for every menu action that has a key binding."""
    rows: list[tuple[str, str, str]] = []
    seen: set[int] = set()

    def walk(menu: QMenu, path: str) -> None:
        for act in menu.actions():
            if act.isSeparator():
                continue
            sub = act.menu()
            if sub is not None:
                walk(sub, path)
                continue
            if id(act) in seen:
                continue
            keys = [k.toString(QKeySequence.SequenceFormat.NativeText) for k in act.shortcuts() if not k.isEmpty()]
            if not keys:
                continue
            seen.add(id(act))
            rows.append((path, _clean(act.text()), "  or  ".join(keys)))

    for top in menubar.actions():
        m = top.menu()
        if m is not None:
            walk(m, _clean(top.text()))
    return rows


class ShortcutsDialog(QDialog):
    """Searchable reference of every keyboard shortcut."""

    def __init__(self, menubar: QMenuBar, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(620, 620)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Keyboard shortcuts"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter by command or key…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Command", "Shortcut"])
        self._tree.setRootIsDecorated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setAlternatingRowColors(True)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._tree, 1)

        groups: dict[str, list[tuple[str, str]]] = {}
        for menu, cmd, keys in collect_shortcuts(menubar):
            groups.setdefault(menu, []).append((cmd, keys))
        groups["Page view"] = list(CANVAS_KEYS)
        bold = QFont(self.font())
        bold.setBold(True)
        for menu, rows in groups.items():
            head = QTreeWidgetItem([menu, ""])
            head.setFont(0, bold)
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            head.setData(0, Qt.ItemDataRole.UserRole, "header")
            self._tree.addTopLevelItem(head)
            for cmd, keys in rows:
                item = QTreeWidgetItem([f"    {cmd}", keys])
                self._tree.addTopLevelItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._filter.setFocus()

    def row_count(self) -> int:
        return sum(
            1
            for i in range(self._tree.topLevelItemCount())
            if self._tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) != "header"
        )

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        header: QTreeWidgetItem | None = None
        header_has_rows = False
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == "header":
                if header is not None:
                    header.setHidden(not header_has_rows)
                header, header_has_rows = item, False
                continue
            match = not needle or needle in item.text(0).lower() or needle in item.text(1).lower()
            item.setHidden(not match)
            header_has_rows = header_has_rows or match
        if header is not None:
            header.setHidden(not header_has_rows)


# --------------------------------------------------------------------------- user guide


def find_user_guide() -> Path | None:
    from app.paths import BUNDLE_ROOT, DOCS_DIR

    for base in (DOCS_DIR, BUNDLE_ROOT / "docs"):
        path = base / "USER_GUIDE.md"
        if path.is_file():
            return path
    return None


class UserGuideDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("User Guide")
        self.setMinimumSize(640, 560)
        self.resize(780, 740)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(10)
        view = QTextBrowser()
        view.setObjectName("LegalDocumentBrowser")
        view.setOpenExternalLinks(False)
        view.document().setDefaultStyleSheet(
            """
            body { font-family: "Segoe UI", "Yu Gothic UI", sans-serif; font-size: 13px;
                   line-height: 1.5; text-align: justify; margin: 8px 12px; }
            h1, h2, h3, h4 { text-align: left; line-height: 1.3; margin-top: 1.1em; margin-bottom: 0.45em; }
            p { margin: 0 0 0.85em 0; text-align: justify; }
            li { text-align: justify; margin-bottom: 0.25em; }
            table { text-align: left; border-collapse: collapse; margin: 0.6em 0 1em 0; }
            th, td { text-align: left; padding: 4px 10px 4px 0; vertical-align: top; }
            pre, code { text-align: left; font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
            """
        )
        path = find_user_guide()
        if path is not None:
            view.setMarkdown(path.read_text(encoding="utf-8"))
            view.setSearchPaths([str(path.parent)])
        else:
            view.setMarkdown(
                "# User Guide\n\nThe offline guide (`docs/USER_GUIDE.md`) was not found beside the "
                "application. Use **Help → Keyboard Shortcuts** for the full key reference."
            )
        root.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)


# --------------------------------------------------------------------------- properties


def _fmt_bytes(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} bytes"


def _fmt_pdf_date(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("D:"):
        raw = raw[2:]
    if len(raw) >= 8 and raw[:8].isdigit():
        out = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        if len(raw) >= 12 and raw[8:12].isdigit():
            out += f" {raw[8:10]}:{raw[10:12]}"
        return out
    return raw or "—"


class DocumentPropertiesDialog(QDialog):
    def __init__(self, document, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Document Properties — {document.name}")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        meta = document.metadata()

        desc = QWidget()
        form = QFormLayout(desc)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(8)
        path = Path(document.path).resolve()
        try:
            size = _fmt_bytes(path.stat().st_size)
        except OSError:
            size = "—"

        def ro(text: str) -> QLabel:
            lab = QLabel(text or "—")
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return lab

        form.addRow("File:", ro(path.name))
        form.addRow("Location:", ro(str(path.parent)))
        form.addRow("File size:", ro(size))
        form.addRow("Title:", ro(meta.title))
        form.addRow("Author:", ro(meta.author))
        form.addRow("Subject:", ro(meta.subject))
        form.addRow("Keywords:", ro(meta.keywords))
        form.addRow("Created:", ro(_fmt_pdf_date(meta.creation_date)))
        form.addRow("Modified:", ro(_fmt_pdf_date(meta.mod_date)))
        form.addRow("Application:", ro(meta.creator))
        form.addRow("PDF producer:", ro(meta.producer))
        tabs.addTab(desc, "Description")

        adv = QWidget()
        f2 = QFormLayout(adv)
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        f2.setVerticalSpacing(8)
        f2.addRow("Format:", ro(meta.format))
        f2.addRow("Pages:", ro(str(meta.page_count)))
        try:
            first = document.page(0)
            from core.page_geometry import label_page_size

            paper = label_page_size(first.display_width_pt, first.display_height_pt)
            f2.addRow(
                "Page size:",
                ro(f"{paper.display}  ({first.display_width_pt:.0f} × {first.display_height_pt:.0f} pt)"),
            )
        except Exception:  # noqa: BLE001
            pass
        f2.addRow("Encrypted:", ro("Yes" if meta.encrypted else "No"))
        f2.addRow("Fillable form:", ro("Yes" if meta.has_acroform else "No"))
        f2.addRow("Digitally signed:", ro("Yes" if meta.has_digital_signatures else "No"))
        if meta.permissions:
            allowed = ", ".join(k for k, v in meta.permissions.items() if v) or "none"
            f2.addRow("Permissions:", ro(allowed))
        tabs.addTab(adv, "Advanced")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


# --------------------------------------------------------------------------- signature pad


class SignaturePad(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SignaturePad")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(QSize(460, 180))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._strokes: list[list[QPointF]] = []
        self._ink = QColor("#0d0d59")

    def strokes(self) -> list[list[tuple[float, float]]]:
        return [[(p.x(), p.y()) for p in s] for s in self._strokes if len(s) > 1]

    def is_empty(self) -> bool:
        return not self.strokes()

    def clear(self) -> None:
        self._strokes.clear()
        self.update()
        self.changed.emit()

    def undo_stroke(self) -> None:
        if self._strokes:
            self._strokes.pop()
            self.update()
            self.changed.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._strokes.append([event.position()])
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._strokes and event.buttons() & Qt.MouseButton.LeftButton:
            self._strokes[-1].append(event.position())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # baseline guide
        p.setPen(QPen(QColor("#cbd1d9"), 1, Qt.PenStyle.DashLine))
        y = int(self.height() * 0.72)
        p.drawLine(24, y, self.width() - 24, y)
        p.setPen(QColor("#9aa3af"))
        p.drawText(28, y + 18, "Sign above the line")
        pen = QPen(self._ink, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for stroke in self._strokes:
            if len(stroke) == 1:
                p.drawPoint(stroke[0])
                continue
            path = QPainterPath(stroke[0])
            for pt in stroke[1:]:
                path.lineTo(pt)
            p.drawPath(path)
        p.end()


class SignaturePadDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Draw a Signature")
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Draw your signature"))
        warn = _hint("Visual signature only — not a cryptographic digital certificate signature.")
        warn.setObjectName("DialogWarning")
        root.addWidget(warn)
        self.pad = SignaturePad()
        root.addWidget(self.pad, 1)
        row = QHBoxLayout()
        undo = QPushButton("Undo Stroke")
        undo.setAutoDefault(False)  # Place on Page is the main action; Enter never just undoes a stroke
        undo.clicked.connect(self.pad.undo_stroke)
        clear = QPushButton("Clear")
        clear.setAutoDefault(False)
        clear.clicked.connect(self.pad.clear)
        row.addWidget(undo)
        row.addWidget(clear)
        row.addStretch(1)
        root.addLayout(row)
        root.addWidget(_hint("After you click Place, drag a box on the page where the signature should go."))
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Place on Page")
        ok.setEnabled(False)
        self.pad.changed.connect(lambda: ok.setEnabled(not self.pad.is_empty()))
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def strokes(self) -> list[list[tuple[float, float]]]:
        return self.pad.strokes()


def fit_strokes_into(
    strokes: list[list[tuple[float, float]]], x: float, y: float, w: float, h: float
) -> list[list[tuple[float, float]]]:
    """Scale stroke points (any space) uniformly into the target box, centred."""
    pts = [pt for s in strokes for pt in s]
    if not pts:
        return []
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    sw = max(maxx - minx, 1e-6)
    sh = max(maxy - miny, 1e-6)
    scale = min(w / sw, h / sh)
    ox = x + (w - sw * scale) / 2
    oy = y + (h - sh * scale) / 2
    return [[(ox + (px - minx) * scale, oy + (py - miny) * scale) for px, py in s] for s in strokes]


# --------------------------------------------------------------------------- export images


@dataclass
class ImageExportOptions:
    fmt: str = "png"
    dpi: int = 150
    jpeg_quality: int = 85
    scope: str = "all"  # all | current | selected


class ExportImagesDialog(QDialog):
    def __init__(self, page_count: int, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF to Images")
        self.setMinimumWidth(400)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Convert pages to images"))
        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.fmt = QComboBox()
        self.fmt.addItem("PNG — lossless", "png")
        self.fmt.addItem("JPEG — smaller files", "jpeg")
        self.fmt.addItem("TIFF — archival", "tiff")
        form.addRow("Format:", self.fmt)
        self.dpi = QComboBox()
        for d in (72, 96, 150, 200, 300, 600):
            self.dpi.addItem(f"{d} dpi", d)
        self.dpi.setCurrentIndex(2)
        form.addRow("Resolution:", self.dpi)
        self.quality = QSpinBox()
        self.quality.setRange(30, 100)
        self.quality.setValue(85)
        self.quality.setSuffix(" %")
        form.addRow("JPEG quality:", self.quality)
        root.addLayout(form)

        scope_box = QFrame()
        sl = QVBoxLayout(scope_box)
        sl.setContentsMargins(0, 4, 0, 0)
        self._scope = QButtonGroup(self)
        self.all_pages = QRadioButton(f"All pages ({page_count})")
        self.current_page = QRadioButton("Current page")
        self.selected_pages = QRadioButton(f"Selected pages ({selected_count})")
        self.selected_pages.setEnabled(selected_count > 1)
        for i, rb in enumerate((self.all_pages, self.current_page, self.selected_pages)):
            self._scope.addButton(rb, i)
            sl.addWidget(rb)
        (self.selected_pages if selected_count > 1 else self.all_pages).setChecked(True)
        root.addWidget(QLabel("Pages:"))
        root.addWidget(scope_box)

        self.fmt.currentIndexChanged.connect(self._sync)
        self._sync()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose Folder…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _sync(self) -> None:
        self.quality.setEnabled(self.fmt.currentData() == "jpeg")

    def options(self) -> ImageExportOptions:
        scope = {0: "all", 1: "current", 2: "selected"}.get(self._scope.checkedId(), "all")
        return ImageExportOptions(
            fmt=str(self.fmt.currentData()),
            dpi=int(self.dpi.currentData()),
            jpeg_quality=int(self.quality.value()),
            scope=scope,
        )


# --------------------------------------------------------------------------- stamp picker


class StampDialog(QDialog):
    def __init__(self, names: list[str], parent=None, default: str = "Draft") -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Stamp")
        root = QVBoxLayout(self)
        root.addWidget(_title("Choose a stamp"))
        self.combo = QComboBox()
        pretty = {
            "ForComment": "For Comment",
            "NotApproved": "Not Approved",
            "AsIs": "As Is",
            "NotForPublicRelease": "Not for Public Release",
            "ForPublicRelease": "For Public Release",
            "TopSecret": "Top Secret",
        }
        for n in names:
            self.combo.addItem(pretty.get(n, n), n)
        idx = self.combo.findData(default)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        root.addWidget(self.combo)
        root.addWidget(_hint("Next, drag a box on the page (or click to place at the default size)."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Place")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def value(self) -> str:
        return str(self.combo.currentData())
