"""Scroll button (auto-scroll) for the page view, as in web browsers and Acrobat.

* **Middle mouse button** — press the wheel button on a page: a round scroll marker appears where
  you pressed. Move the pointer above or below it and the pages scroll that way, faster the further
  the pointer is from the marker (sideways too, when the page is wider than the window).
  - *Click* the middle button (press and release without moving): scrolling continues until any
    click, the wheel, or Esc.
  - *Hold* the middle button and move: scrolling stops when the button is released.
* **View ▸ Automatic Scrolling** (Ctrl+Shift+H) — the pages move down at a steady reading speed;
  ↓ / ↑ make it faster / slower (↑ past zero scrolls back up), Esc or a click stops it. It stops by
  itself at the end of the document.

Only the view moves: nothing in the document changes.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget

DEAD_ZONE = 10  # px around the marker where nothing moves
TICK_MS = 15
CLICK_MS = 350  # a middle press released sooner than this without moving = "click" (toggle) mode
CLICK_SLOP = 6
READ_SPEEDS = (15, 25, 40, 60, 90, 135, 200, 300, 450, 700)  # px/s for automatic scrolling
DEFAULT_READ_STEP = 2


def _speed(distance: float) -> float:
    """Pixels per second for a pointer ``distance`` px beyond the dead zone (signed)."""
    d = abs(distance) - DEAD_ZONE
    if d <= 0:
        return 0.0
    v = 4.0 * d + 0.06 * d * d  # gentle near the marker, quick further away
    return math.copysign(min(v, 9000.0), distance)


def _marker_pixmap(size: int, dpr: float, *, up: bool, down: bool, left: bool = False,
                   right: bool = False, round_badge: bool = True) -> QPixmap:
    """The scroll marker: a white disc with a dark ring, arrowheads and a centre dot."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ink = QColor("#1f2328")
    c = size / 2.0
    if round_badge:
        p.setPen(QPen(ink, 1.4))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QPointF(c, c), c - 1.5, c - 1.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ink)
    p.drawEllipse(QPointF(c, c), size * 0.075, size * 0.075)
    a = size * 0.16  # arrowhead half-width
    off_near, off_far = size * 0.17, size * 0.36

    def tri(points):
        path = QPainterPath()
        path.moveTo(*points[0])
        for pt in points[1:]:
            path.lineTo(*pt)
        path.closeSubpath()
        p.drawPath(path)

    if up:
        tri([(c, c - off_far), (c - a, c - off_near), (c + a, c - off_near)])
    if down:
        tri([(c, c + off_far), (c - a, c + off_near), (c + a, c + off_near)])
    if left:
        tri([(c - off_far, c), (c - off_near, c - a), (c - off_near, c + a)])
    if right:
        tri([(c + off_far, c), (c + off_near, c - a), (c + off_near, c + a)])
    p.end()
    return pm


class _Marker(QWidget):
    """The round marker shown where scrolling started (does not take mouse input)."""

    SIZE = 30

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.horizontal = False
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        pm = _marker_pixmap(self.SIZE, self.devicePixelRatioF(), up=True, down=True,
                            left=self.horizontal, right=self.horizontal)
        p.drawPixmap(0, 0, pm)
        p.end()


class AutoScroller(QObject):
    """Auto-scrolling for one scroll area (see module doc)."""

    started = Signal(str)  # mode: "hold", "click", "read"
    stopped = Signal()
    speedChanged = Signal(int)  # automatic scrolling: px/s (negative = up)

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._marker = _Marker(area.viewport())
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._mode = ""  # "" (off), "hold", "click", "read"
        self._origin = QPoint()
        self._press_time = 0.0
        self._acc = [0.0, 0.0]
        self._read_step = DEFAULT_READ_STEP
        self._read_dir = 1
        self._cursor_key: tuple | None = None
        self._cursors: dict = {}
        self._filtering = False
        self._eat_release = None  # button whose release is swallowed after a click that stopped scrolling

    # ------------------------------------------------------------------ state
    @property
    def active(self) -> bool:
        return bool(self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def read_speed(self) -> int:
        return self._read_dir * READ_SPEEDS[self._read_step]

    def origin(self) -> QPoint:
        return QPoint(self._origin)

    def marker(self) -> QWidget:
        return self._marker

    # ------------------------------------------------------------------ start / stop
    def begin_middle(self, viewport_pos: QPoint) -> None:
        """Middle button pressed at ``viewport_pos``: start in "hold" mode (a quick release turns it
        into "click" mode, see :meth:`middle_released`)."""
        if self._mode:
            self.stop()
            return
        self._begin("hold", viewport_pos)
        self._press_time = time.monotonic()

    def middle_released(self, viewport_pos: QPoint) -> None:
        if self._mode != "hold":
            return
        quick = (time.monotonic() - self._press_time) * 1000 < CLICK_MS
        still = (viewport_pos - self._origin).manhattanLength() <= CLICK_SLOP
        if quick and still:
            self._mode = "click"  # keep scrolling until the next click / Esc
            self.started.emit("click")
        else:
            self.stop()

    def start_reading(self) -> None:
        """Automatic scrolling at a steady speed (View ▸ Automatic Scrolling)."""
        if self._mode == "read":
            self.stop()
            return
        if self._mode:
            self.stop()
        vp = self._area.viewport()
        self._read_dir = 1
        self._begin("read", QPoint(vp.width() // 2, vp.height() // 2), show_marker=False)
        self.speedChanged.emit(self.read_speed)

    def change_reading_speed(self, faster: bool) -> None:
        """↓ = faster downwards, ↑ = slower (and, below the slowest, back upwards)."""
        signed = self._read_dir * (self._read_step + 1)
        signed += 1 if faster else -1
        if signed == 0:
            signed = 1 if faster else -1
        signed = max(-len(READ_SPEEDS), min(len(READ_SPEEDS), signed))
        self._read_dir = 1 if signed > 0 else -1
        self._read_step = abs(signed) - 1
        self.speedChanged.emit(self.read_speed)

    def _begin(self, mode: str, pos: QPoint, *, show_marker: bool = True) -> None:
        self._mode = mode
        self._origin = QPoint(pos)
        self._acc = [0.0, 0.0]
        if show_marker:
            hb = self._area.horizontalScrollBar()
            self._marker.horizontal = hb.maximum() > hb.minimum()
            self._marker.move(pos.x() - _Marker.SIZE // 2, pos.y() - _Marker.SIZE // 2)
            self._marker.show()
            self._marker.raise_()
            self._marker.update()
        self._set_cursor((0, 0) if show_marker else None)
        app = QApplication.instance()
        if app is not None and not self._filtering:
            app.installEventFilter(self)
            self._filtering = True
        self._clock.start()
        self._timer.start()
        self.started.emit(mode)

    def stop(self, *, eat_release_of=None) -> None:
        if not self._mode:
            return
        self._mode = ""
        self._timer.stop()
        self._marker.hide()
        self._set_cursor(None)
        self._eat_release = eat_release_of
        if eat_release_of is None:
            self._remove_filter()
        self.stopped.emit()

    def _remove_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and self._filtering:
            app.removeEventFilter(self)
            self._filtering = False

    # ------------------------------------------------------------------ cursor
    def _set_cursor(self, key: tuple | None) -> None:
        if key == self._cursor_key:
            return
        app = QApplication.instance()
        if app is None:
            return
        if self._cursor_key is not None:
            QApplication.restoreOverrideCursor()
        self._cursor_key = key
        if key is None:
            return
        if key not in self._cursors:
            dx, dy = key
            neutral = dx == 0 and dy == 0
            hb = self._area.horizontalScrollBar()
            wide = hb.maximum() > hb.minimum()
            dpr = self._area.devicePixelRatioF() if hasattr(self._area, "devicePixelRatioF") else 1.0
            pm = _marker_pixmap(
                24, dpr,
                up=dy < 0 or (neutral), down=dy > 0 or neutral,
                left=dx < 0 or (neutral and wide), right=dx > 0 or (neutral and wide),
                round_badge=neutral,
            )
            self._cursors[key] = QCursor(pm, 12, 12)
        QApplication.setOverrideCursor(self._cursors[key])

    # ------------------------------------------------------------------ scrolling
    def _offset(self) -> QPoint:
        vp = self._area.viewport()
        return vp.mapFromGlobal(QCursor.pos()) - self._origin

    def _tick(self) -> None:
        if not self._mode:
            return
        dt = max(0.001, min(0.1, self._clock.restart() / 1000.0))
        hb, vb = self._area.horizontalScrollBar(), self._area.verticalScrollBar()
        if self._mode == "read":
            vx, vy = 0.0, float(self.read_speed)
        else:
            off = self._offset()
            vy = _speed(off.y())
            vx = _speed(off.x()) if hb.maximum() > hb.minimum() else 0.0
            self._set_cursor((int(math.copysign(1, vx)) if vx else 0, int(math.copysign(1, vy)) if vy else 0))
        for i, (bar, v) in enumerate(((hb, vx), (vb, vy))):
            if not v:
                self._acc[i] = 0.0
                continue
            self._acc[i] += v * dt
            step = int(self._acc[i])
            if step:
                self._acc[i] -= step
                bar.setValue(bar.value() + step)
        if self._mode == "read":
            at_end = (vy > 0 and vb.value() >= vb.maximum()) or (vy < 0 and vb.value() <= vb.minimum())
            if at_end:
                self.stop()

    # ------------------------------------------------------------------ events while active
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if self._eat_release is not None and not self._mode:
            if et == QEvent.Type.MouseButtonRelease and event.button() == self._eat_release:
                self._eat_release = None
                self._remove_filter()
                return True
            if et == QEvent.Type.MouseMove:
                return True
            return False
        if not self._mode:
            return False
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton:
            if self._mode == "hold":
                vp = self._area.viewport()
                self.middle_released(vp.mapFromGlobal(event.globalPosition().toPoint()))
            return self._mode != "read"
        if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            # Any click ends auto-scrolling and is not passed on (it must not edit the page)
            self.stop(eat_release_of=event.button())
            return True
        if et == QEvent.Type.Wheel:
            self.stop()
            return False
        if et == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.stop()
                return True
            if self._mode == "read" and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.change_reading_speed(key == Qt.Key.Key_Down)
                return True
            if self._mode == "read" and key == Qt.Key.Key_Space:
                self.stop()
                return True
            if key not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                self.stop()
            return False
        if et in (QEvent.Type.WindowDeactivate, QEvent.Type.ApplicationDeactivate):
            self.stop()
        return False


def marker_rect(scroller: AutoScroller) -> QRectF:
    """Tests: geometry of the marker in viewport coordinates."""
    m = scroller.marker()
    return QRectF(m.geometry())
