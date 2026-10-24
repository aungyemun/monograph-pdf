"""Colour picker used for every colour choice (text, highlight, shapes, notes, stamps, fields, page design).

Replaces Qt's generic ``QColorDialog``, which looked out of place, had a small hue/saturation field
and no memory of the colours used. This dialog:

* a large saturation/brightness field and a hue strip (an opacity strip where transparency is
  allowed), all drawn smoothly and dragged with the mouse or the arrow keys;
* the **current** colour beside the **new** one, so the change is visible before OK;
* **Hex** (``#1d4ed8``, also ``1d4ed8``, ``#abc`` or a CSS name such as ``navy``) and **R G B** fields;
* curated **standard** colours (readable on paper), the **recent** colours (kept between sessions),
  and **Pick from Screen** (an eyedropper with a magnifier; Esc cancels);
* for text colours, the **contrast on white paper** (WCAG ratio) so faint text is noticed early.

Colours are sRGB, the colour space of PDF DeviceRGB. A colour picked from the screen is converted
back from the monitor profile when Monograph PDF converts pages to it (ui/display_color.py), so
picking a colour off a page gives the colour stored in the PDF.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

RECENT_MAX = 16

# Standard colours: a row of greys, then strong and light versions of eight hues (all sRGB)
STANDARD_COLORS: list[tuple[str, str]] = [
    ("Black", "#000000"), ("Charcoal", "#333333"), ("Dark gray", "#595959"), ("Gray", "#808080"),
    ("Silver", "#BFBFBF"), ("Light gray", "#D9D9D9"), ("Near white", "#F2F2F2"), ("White", "#FFFFFF"),
    ("Dark red", "#9B1C1C"), ("Red", "#DC2626"), ("Orange", "#EA580C"), ("Amber", "#D97706"),
    ("Yellow", "#FACC15"), ("Green", "#16A34A"), ("Teal", "#0F766E"), ("Cyan", "#0891B2"),
    ("Blue", "#1D4ED8"), ("Navy", "#1F3A5F"), ("Indigo", "#4338CA"), ("Purple", "#7E22CE"),
    ("Magenta", "#C026D3"), ("Pink", "#DB2777"), ("Brown", "#7C4A1E"), ("Olive", "#4D7C0F"),
    ("Light red", "#FECACA"), ("Light orange", "#FED7AA"), ("Light yellow", "#FEF08A"),
    ("Light green", "#BBF7D0"), ("Light teal", "#99F6E4"), ("Light blue", "#BFDBFE"),
    ("Lavender", "#DDD6FE"), ("Light pink", "#FBCFE8"),
]


# ------------------------------------------------------------------------------- helpers
def parse_color(text: str) -> QColor:
    """``#1d4ed8``, ``1d4ed8``, ``#abc``, ``#801d4ed8`` (with alpha) or a CSS colour name; invalid
    QColor when not understood."""
    t = (text or "").strip()
    if not t:
        return QColor()
    if not t.startswith("#") and len(t) in (3, 6, 8) and all(ch in "0123456789abcdefABCDEF" for ch in t):
        t = "#" + t
    c = QColor(t)
    return c if c.isValid() else QColor()


def _lum(c: QColor) -> float:
    def ch(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c.redF()) + 0.7152 * ch(c.greenF()) + 0.0722 * ch(c.blueF())


def contrast_ratio(a: QColor, b: QColor) -> float:
    """WCAG 2.x contrast ratio of two opaque colours (1 … 21)."""
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex(c: QColor, alpha: bool) -> str:
    if alpha and c.alpha() < 255:
        return c.name(QColor.NameFormat.HexArgb)
    return c.name()


def _checker(p: QPainter, rect: QRectF, size: int = 6) -> None:
    p.save()
    p.setClipRect(rect)
    p.fillRect(rect, QColor("#ffffff"))
    y = int(rect.top())
    row = 0
    while y < rect.bottom():
        x = int(rect.left()) + (size if row % 2 else 0)
        while x < rect.right():
            p.fillRect(QRectF(x, y, size, size), QColor("#d4d4d8"))
            x += size * 2
        y += size
        row += 1
    p.restore()


def _recent_load() -> list[str]:
    try:
        from core.user_prefs import UserPreferences

        values = UserPreferences.load().recent_colors or []
        return [v for v in values if isinstance(v, str) and QColor(v).isValid()][:RECENT_MAX]
    except Exception:  # noqa: BLE001 — recent colours are a convenience
        return []


def remember_color(value: str) -> None:
    """Put ``value`` first in the recent colours (kept in the settings)."""
    c = QColor(value)
    if not c.isValid() or c.alpha() == 0:
        return
    try:
        from core.user_prefs import UserPreferences

        prefs = UserPreferences.load()
        name = _hex(c, True).lower()
        values = [v for v in (prefs.recent_colors or []) if isinstance(v, str) and v.lower() != name]
        prefs.recent_colors = [name, *values][:RECENT_MAX]
        prefs.save()
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------------------- widgets
class _SVField(QWidget):
    """Saturation (x) × brightness (y) field for the current hue."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(QSize(240, 200))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Saturation and brightness")
        self.hue = 0.0  # 0..1
        self.sat = 1.0
        self.val = 1.0
        self._cache: tuple[float, QSize, QImage] | None = None

    PAD = 8  # room for the marker ring at the edges

    def _area(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD)

    def _image(self) -> QImage:
        area = self._area().toRect()
        size = area.size()
        if self._cache and self._cache[0] == self.hue and self._cache[1] == size:
            return self._cache[2]
        img = QImage(size, QImage.Format.Format_RGB32)
        p = QPainter(img)
        base = QColor.fromHsvF(self.hue, 1.0, 1.0)
        g = QLinearGradient(0, 0, size.width(), 0)
        g.setColorAt(0, QColor("#ffffff"))
        g.setColorAt(1, base)
        p.fillRect(img.rect(), g)
        g2 = QLinearGradient(0, 0, 0, size.height())
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(img.rect(), g2)
        p.end()
        self._cache = (self.hue, size, img)
        return img

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self._area()
        path = QPainterPath()
        path.addRoundedRect(area, 6, 6)
        p.setClipPath(path)
        p.drawImage(area.topLeft(), self._image())
        p.setClipping(False)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawPath(path)
        if self.hasFocus():
            from ui.theme import current_palette

            p.setPen(QPen(QColor(current_palette().accent), 2))
            p.drawRoundedRect(area.adjusted(-3, -3, 3, 3), 8, 8)
        x = area.left() + self.sat * area.width()
        y = area.top() + (1.0 - self.val) * area.height()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 120), 3))
        p.drawEllipse(QPointF(x, y), 7, 7)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(QPointF(x, y), 7, 7)
        p.end()

    def _set_from(self, pos: QPointF) -> None:
        area = self._area()
        self.sat = max(0.0, min(1.0, (pos.x() - area.left()) / max(1.0, area.width())))
        self.val = max(0.0, min(1.0, 1.0 - (pos.y() - area.top()) / max(1.0, area.height())))
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._set_from(e.position())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._set_from(e.position())

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        step = 0.1 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.01
        k = e.key()
        if k == Qt.Key.Key_Left:
            self.sat = max(0.0, self.sat - step)
        elif k == Qt.Key.Key_Right:
            self.sat = min(1.0, self.sat + step)
        elif k == Qt.Key.Key_Up:
            self.val = min(1.0, self.val + step)
        elif k == Qt.Key.Key_Down:
            self.val = max(0.0, self.val - step)
        else:
            return super().keyPressEvent(e)
        self.update()
        self.changed.emit()


class _Strip(QWidget):
    """Vertical strip: hue (0..1, top = red) or opacity (top = opaque)."""

    changed = Signal()

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self.value = 0.0 if kind == "hue" else 1.0
        self.color = QColor("#000000")  # opacity strip: the colour being made transparent
        self.setFixedWidth(22)
        self.setMinimumHeight(200)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Hue" if kind == "hue" else "Opacity")

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = QRectF(4, _SVField.PAD, self.width() - 8, self.height() - 2 * _SVField.PAD)
        path = QPainterPath()
        path.addRoundedRect(bar, 4, 4)
        p.setClipPath(path)
        g = QLinearGradient(0, bar.top(), 0, bar.bottom())
        if self.kind == "hue":
            for i in range(13):
                g.setColorAt(i / 12, QColor.fromHsvF((i / 12) % 1.0, 1.0, 1.0))
        else:
            _checker(p, bar, 5)
            top = QColor(self.color)
            top.setAlpha(255)
            bottom = QColor(self.color)
            bottom.setAlpha(0)
            g.setColorAt(0, top)
            g.setColorAt(1, bottom)
        p.fillRect(bar, g)
        p.setClipping(False)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawPath(path)
        pos = self.value if self.kind == "hue" else 1.0 - self.value
        y = bar.top() + pos * bar.height()
        handle = QRectF(1, y - 4, self.width() - 2, 8)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor(0, 0, 0, 150), 1.2))
        p.drawRoundedRect(handle, 3, 3)
        if self.hasFocus():
            from ui.theme import current_palette

            p.setPen(QPen(QColor(current_palette().accent), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(handle.adjusted(-1, -1, 1, 1), 3, 3)
        p.end()

    def _set_from(self, y: float) -> None:
        span = max(1.0, self.height() - 2 * _SVField.PAD)
        frac = max(0.0, min(1.0, (y - _SVField.PAD) / span))
        self.value = frac if self.kind == "hue" else 1.0 - frac
        if self.kind == "hue":
            self.value = min(self.value, 0.9999)
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._set_from(e.position().y())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._set_from(e.position().y())

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        step = 0.05 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.005
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            down = e.key() == Qt.Key.Key_Down
            if self.kind == "hue":
                self.value = max(0.0, min(0.9999, self.value + (step if down else -step)))
            else:
                self.value = max(0.0, min(1.0, self.value + (-step if down else step)))
            self.update()
            self.changed.emit()
            return
        super().keyPressEvent(e)


class _Preview(QWidget):
    """Current colour (left) beside the new colour (right)."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(46)
        self.old = QColor("#000000")
        self.new = QColor("#000000")
        self.setAccessibleName("Current and new colour")

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setClipPath(path)
        _checker(p, r)
        half = r.width() / 2
        p.fillRect(QRectF(r.left(), r.top(), half, r.height()), self.old)
        p.fillRect(QRectF(r.left() + half, r.top(), half, r.height()), self.new)
        p.setClipping(False)
        p.setPen(QPen(QColor(0, 0, 0, 70), 1))
        p.drawPath(path)
        p.end()


class _Swatch(QToolButton):
    picked = Signal(str)
    chosen = Signal(str)  # double-click: pick and accept

    def __init__(self, name: str, value: str, size: int = 20) -> None:
        super().__init__()
        self.value = value
        self.setObjectName("PickerSwatch")
        self.setFixedSize(size + 4, size + 4)
        self.setToolTip(f"{name} ({value.upper()})" if name else value.upper())
        self.setAccessibleName(f"{name or 'Colour'} {value}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: self.picked.emit(self.value))
        self.selected = False

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.chosen.emit(self.value)

    def paintEvent(self, _e) -> None:  # noqa: N802
        from ui.theme import current_palette

        pal = current_palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        c = QColor(self.value)
        if c.alpha() < 255:
            _checker(p, r, 4)
        p.setBrush(c)
        p.setPen(QPen(QColor(0, 0, 0, 55), 1))
        p.drawRoundedRect(r, 4, 4)
        if self.selected or self.hasFocus() or self.underMouse():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(pal.accent if (self.selected or self.hasFocus()) else pal.border_strong), 2))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)
        p.end()

    def enterEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(e)


class ScreenColorPicker(QWidget):
    """Full-screen eyedropper over a still image of the screen under the pointer."""

    picked = Signal(QColor)
    cancelled = Signal()

    LOUPE = 9  # pixels across the magnifier
    ZOOM = 11

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self._screen = screen
        self._shot = screen.grabWindow(0) if screen is not None else QPixmap()
        self._image = self._shot.toImage()
        self._pos = QPoint()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def start(self) -> None:
        self.show()
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()
        self._pos = self.mapFromGlobal(QCursor.pos())
        self.update()

    def _pixel(self, pos: QPoint) -> QColor:
        if self._image.isNull():
            return QColor()
        dpr = self._shot.devicePixelRatio() or 1.0
        x = int(pos.x() * dpr)
        y = int(pos.y() * dpr)
        x = max(0, min(self._image.width() - 1, x))
        y = max(0, min(self._image.height() - 1, y))
        return QColor(self._image.pixel(x, y))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)
        pos = self._pos
        dpr = self._shot.devicePixelRatio() or 1.0
        half = self.LOUPE // 2
        src = QRect(int(pos.x() * dpr) - half, int(pos.y() * dpr) - half, self.LOUPE, self.LOUPE)
        size = self.LOUPE * self.ZOOM
        x = pos.x() + 24
        y = pos.y() + 24
        if x + size + 4 > self.width():
            x = pos.x() - 24 - size
        if y + size + 40 > self.height():
            y = pos.y() - 24 - size - 34
        target = QRect(x, y, size, size)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.fillRect(target.adjusted(-2, -2, 2, 34), QColor(20, 20, 24, 230))
        p.drawImage(target, self._image, src)
        p.setPen(QPen(QColor("#ffffff"), 1))
        mid = QRect(target.left() + half * self.ZOOM, target.top() + half * self.ZOOM, self.ZOOM, self.ZOOM)
        p.drawRect(mid)
        c = self._pixel(pos)
        p.fillRect(QRect(target.left(), target.bottom() + 8, 18, 18), c)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(target.left() + 24, target.bottom() + 6, size - 24, 22),
                   Qt.AlignmentFlag.AlignVCenter, c.name().upper())
        p.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        self._pos = e.position().toPoint()
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            c = self._pixel(e.position().toPoint())
            self._finish()
            self.picked.emit(c)
        else:
            self._finish()
            self.cancelled.emit()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self._finish()
            self.cancelled.emit()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            c = self._pixel(self._pos)
            self._finish()
            self.picked.emit(c)

    def _finish(self) -> None:
        try:
            self.releaseKeyboard()
        except RuntimeError:
            pass
        self.close()


# ------------------------------------------------------------------------------- dialog
class ColorPickerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, initial: str | QColor = "#000000",
                 title: str = "Color", allow_alpha: bool = False, text_contrast: bool | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ColorPickerDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        # Opening this from the text toolbar must not close the text box being typed in (ui/pdf_canvas.py)
        self.setProperty("keepsTextEditor", True)
        self._alpha = allow_alpha
        start = initial if isinstance(initial, QColor) else parse_color(str(initial))
        if not start.isValid():
            start = QColor("#000000")
        if not allow_alpha:
            start.setAlpha(255)
        self._initial = QColor(start)
        self._color = QColor(start)
        self._updating = False
        self._picker: ScreenColorPicker | None = None
        if text_contrast is None:
            text_contrast = "text" in title.lower()
        self._show_contrast = bool(text_contrast)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)
        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # left: field + strips
        left = QHBoxLayout()
        left.setSpacing(8)
        self.field = _SVField()
        self.hue = _Strip("hue")
        left.addWidget(self.field, 1)
        left.addWidget(self.hue)
        self.alpha = _Strip("alpha")
        self.alpha.setVisible(allow_alpha)
        left.addWidget(self.alpha)
        body.addLayout(left, 3)

        # right: preview, values, swatches
        right = QVBoxLayout()
        right.setSpacing(8)
        body.addLayout(right, 2)
        labels = QHBoxLayout()
        cur = QLabel("Current")
        new = QLabel("New")
        for lab in (cur, new):
            lab.setObjectName("PickerCaption")
        new.setAlignment(Qt.AlignmentFlag.AlignRight)
        labels.addWidget(cur)
        labels.addStretch(1)
        labels.addWidget(new)
        right.addLayout(labels)
        self.preview = _Preview()
        right.addWidget(self.preview)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("Hex"), 0, 0)
        self.hex_edit = QLineEdit()
        self.hex_edit.setAccessibleName("Hex colour")
        self.hex_edit.setPlaceholderText("#1d4ed8 or a name")
        self.hex_edit.setToolTip("A hex value (#1d4ed8, 1d4ed8, #abc) or a colour name (navy, teal …); Enter applies")
        self.hex_edit.editingFinished.connect(self._hex_entered)
        grid.addWidget(self.hex_edit, 0, 1, 1, 5)
        self.spins: dict[str, QSpinBox] = {}
        for col, (key, label) in enumerate((("r", "R"), ("g", "G"), ("b", "B"))):
            lab = QLabel(label)
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setAccessibleName({"r": "Red", "g": "Green", "b": "Blue"}[key])
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._rgb_changed)
            self.spins[key] = spin
            grid.addWidget(lab, 1, col * 2)
            grid.addWidget(spin, 1, col * 2 + 1)
        if allow_alpha:
            grid.addWidget(QLabel("Opacity"), 2, 0, 1, 2)
            self.opacity = QSpinBox()
            self.opacity.setRange(0, 100)
            self.opacity.setSuffix(" %")
            self.opacity.setAccessibleName("Opacity")
            self.opacity.setKeyboardTracking(False)
            self.opacity.valueChanged.connect(self._opacity_changed)
            grid.addWidget(self.opacity, 2, 2, 1, 2)
        else:
            self.opacity = None
        right.addLayout(grid)
        self.contrast = QLabel()
        self.contrast.setObjectName("PickerHint")
        self.contrast.setWordWrap(True)
        self.contrast.setVisible(self._show_contrast)
        right.addWidget(self.contrast)
        self.eyedropper = QPushButton("Pick from Screen")
        self.eyedropper.setToolTip("Click anywhere on the screen to take its colour (Esc cancels)")
        self.eyedropper.clicked.connect(self._pick_screen)
        from ui.toolbar_icons import make_icon

        self.eyedropper.setIcon(make_icon("eyedropper"))
        right.addWidget(self.eyedropper)
        right.addStretch(1)

        # swatches
        root.addWidget(self._section("Standard colors"))
        self._swatches: list[_Swatch] = []
        root.addWidget(self._swatch_grid(STANDARD_COLORS, columns=16))
        recent = _recent_load()
        self._recent_title = self._section("Recent colors")
        root.addWidget(self._recent_title)
        if recent:
            self._recent_grid = self._swatch_grid([("", v) for v in recent], columns=16)
            root.addWidget(self._recent_grid)
        else:
            self._recent_grid = QLabel("Colors you choose appear here.")
            self._recent_grid.setObjectName("PickerHint")
            root.addWidget(self._recent_grid)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("PickerRule")
        root.addWidget(line)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        root.addWidget(buttons)

        self.field.changed.connect(self._from_field)
        self.hue.changed.connect(self._from_field)
        self.alpha.changed.connect(self._from_field)
        self._apply_style()
        self._set_color(self._color, from_hsv=False)
        self.preview.old = QColor(self._initial)
        self.setMinimumWidth(640)
        self.hex_edit.setFocus()
        self.hex_edit.selectAll()

    # ---------------------------------------------------------------- layout helpers
    def _section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("PickerSection")
        return lab

    def _swatch_grid(self, colors, *, columns: int) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(4)
        for i, (name, value) in enumerate(colors):
            s = _Swatch(name, value)
            s.picked.connect(self._swatch_picked)
            s.chosen.connect(self._swatch_chosen)
            self._swatches.append(s)
            g.addWidget(s, i // columns, i % columns)
        g.setColumnStretch(columns, 1)
        return w

    def _apply_style(self) -> None:
        from ui.theme import current_palette

        pal = current_palette()
        self.setStyleSheet(
            f"QLabel#PickerSection {{ color: {pal.text_subtle}; font-weight: 600; margin-top: 2px; }}"
            f"QLabel#PickerCaption {{ color: {pal.text_subtle}; }}"
            f"QLabel#PickerHint {{ color: {pal.text_subtle}; }}"
            f"QFrame#PickerRule {{ color: {pal.border}; background: {pal.border}; max-height: 1px; border: none; }}"
            "QToolButton#PickerSwatch { border: none; background: transparent; }"
        )

    # ---------------------------------------------------------------- colour state
    def color(self) -> QColor:
        return QColor(self._color)

    def selected_name(self) -> str:
        return _hex(self._color, self._alpha)

    def _set_color(self, c: QColor, *, from_hsv: bool) -> None:
        if not c.isValid():
            return
        if not self._alpha:
            c = QColor(c)
            c.setAlpha(255)
        self._color = QColor(c)
        self._updating = True
        try:
            if not from_hsv:
                h, s, v, _a = c.getHsvF()
                if h >= 0:  # achromatic colours keep the hue the strip shows
                    self.hue.value = min(0.9999, h)
                    self.field.hue = self.hue.value
                self.field.sat = s
                self.field.val = v
                self.alpha.value = c.alphaF()
            self.alpha.color = QColor(c)
            for key, val in (("r", c.red()), ("g", c.green()), ("b", c.blue())):
                if self.spins[key].value() != val:
                    self.spins[key].setValue(val)
            if self.opacity is not None:
                self.opacity.setValue(int(round(c.alphaF() * 100)))
            text = _hex(c, self._alpha)
            if not self.hex_edit.hasFocus() or self.hex_edit.text().strip().lower() not in (text, text.lstrip("#")):
                self.hex_edit.setText(text)
        finally:
            self._updating = False
        self.preview.new = QColor(c)
        self.preview.update()
        self.field.update()
        self.hue.update()
        self.alpha.update()
        for s in self._swatches:
            sel = QColor(s.value).name() == c.name() and not self._alpha or (
                self._alpha and _hex(QColor(s.value), True) == _hex(c, True))
            if s.selected != sel:
                s.selected = sel
                s.update()
        if self._show_contrast:
            ratio = contrast_ratio(c, QColor("#ffffff"))
            level = "good for body text" if ratio >= 4.5 else (
                "large text only" if ratio >= 3.0 else "too faint to read easily")
            self.contrast.setText(f"Contrast on white paper: {ratio:.1f} : 1 — {level}")

    def _from_field(self) -> None:
        if self._updating:
            return
        self.field.hue = self.hue.value
        self.field.update()
        c = QColor.fromHsvF(self.hue.value, self.field.sat, self.field.val, self.alpha.value if self._alpha else 1.0)
        self._set_color(c, from_hsv=True)

    def _rgb_changed(self) -> None:
        if self._updating:
            return
        c = QColor(self.spins["r"].value(), self.spins["g"].value(), self.spins["b"].value(), self._color.alpha())
        self._set_color(c, from_hsv=False)

    def _opacity_changed(self, value: int) -> None:
        if self._updating:
            return
        c = QColor(self._color)
        c.setAlphaF(value / 100.0)
        self._set_color(c, from_hsv=False)

    def _hex_entered(self) -> None:
        c = parse_color(self.hex_edit.text())
        if c.isValid():
            if not self._alpha or len(self.hex_edit.text().strip().lstrip("#")) not in (8,):
                c.setAlpha(self._color.alpha() if self._alpha else 255)
            self._set_color(c, from_hsv=False)
        else:
            self.hex_edit.setText(_hex(self._color, self._alpha))

    def _swatch_picked(self, value: str) -> None:
        c = QColor(value)
        if self._alpha and c.alpha() == 255:
            c.setAlpha(self._color.alpha())
        self._set_color(c, from_hsv=False)

    def _swatch_chosen(self, value: str) -> None:
        self._swatch_picked(value)
        self.accept()

    # ---------------------------------------------------------------- eyedropper
    def _pick_screen(self) -> None:
        self._picker = ScreenColorPicker()
        self._picker.picked.connect(self._screen_picked)
        self._picker.cancelled.connect(lambda: setattr(self, "_picker", None))
        self._picker.start()

    def _screen_picked(self, c: QColor) -> None:
        self._picker = None
        if not c.isValid():
            return
        try:
            from ui.display_color import from_display

            c = from_display(c)
        except Exception:  # noqa: BLE001
            pass
        if self._alpha:
            c.setAlpha(self._color.alpha())
        self._set_color(c, from_hsv=False)
        self.activateWindow()

    # ---------------------------------------------------------------- result
    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.hex_edit.hasFocus():
            typed = parse_color(self.hex_edit.text())
            if typed.isValid() and typed.rgb() != self._color.rgb():
                self._hex_entered()  # first Enter applies a newly typed value, the next one accepts
                return
        super().keyPressEvent(e)

    def accept(self) -> None:
        if self.hex_edit.hasFocus():
            self._hex_entered()
        remember_color(self.selected_name())
        super().accept()


def get_color(initial, parent: QWidget | None = None, title: str = "Color", *,
              allow_alpha: bool = False, text_contrast: bool | None = None) -> QColor:
    """Drop-in for ``QColorDialog.getColor``: the chosen colour, or an invalid QColor when cancelled.

    The dialog is parented to ``parent``'s window, never to a styled colour button, so it is not
    tinted by that button's colour."""
    window = parent.window() if parent is not None else None
    dlg = ColorPickerDialog(window, initial=initial, title=title, allow_alpha=allow_alpha,
                            text_contrast=text_contrast)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.color()
    return QColor()
