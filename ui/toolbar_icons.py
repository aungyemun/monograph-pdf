"""Coherent monochrome icon set (drawn in code — offline, no image assets).

Icons are drawn on a 20×20 logical grid at 2× device pixels so they stay crisp
on high-DPI screens. Ink colours come from the active theme palette; call
``refresh_registered_icons()`` after a theme switch to recolour every action
that received an icon through ``set_action_icon`` / ``apply_toolbar_icons``.
"""

from __future__ import annotations

import weakref
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_SIZE = 20
_SCALE = 2

DrawFn = Callable[[QPainter, QColor], None]
_REGISTRY: dict[str, DrawFn] = {}
_BOUND: list[tuple[weakref.ref, str]] = []


def _palette():
    try:
        from ui.theme import current_palette

        return current_palette()
    except Exception:  # noqa: BLE001
        return None


def _colors() -> tuple[QColor, QColor, QColor]:
    pal = _palette()
    if pal is None:
        return QColor("#3b4654"), QColor("#0f766e"), QColor("#b4bcc6")
    return QColor(pal.icon), QColor(pal.accent_text), QColor(pal.icon_disabled)


def _pix(draw: DrawFn, color: QColor) -> QPixmap:
    pm = QPixmap(_SIZE * _SCALE, _SIZE * _SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(_SCALE, _SCALE)
    pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p, color)
    p.end()
    pm.setDevicePixelRatio(_SCALE)
    return pm


def make_icon(name: str) -> QIcon:
    draw = _REGISTRY.get(name)
    if draw is None:
        return QIcon()
    ink, accent, disabled = _colors()
    icon = QIcon()
    normal = _pix(draw, ink)
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(normal, QIcon.Mode.Active, QIcon.State.Off)
    on = _pix(draw, accent)
    icon.addPixmap(on, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(on, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(_pix(draw, disabled), QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(_pix(draw, disabled), QIcon.Mode.Disabled, QIcon.State.On)
    return icon


def icon_names() -> list[str]:
    return sorted(_REGISTRY)


def set_action_icon(target, name: str) -> None:
    """Assign icon ``name`` to a QAction / QToolButton and remember it for theme refresh."""
    if name not in _REGISTRY or target is None:
        return
    target.setIcon(make_icon(name))
    try:
        _BOUND.append((weakref.ref(target), name))
    except TypeError:
        pass


def refresh_registered_icons() -> None:
    alive: list[tuple[weakref.ref, str]] = []
    for ref, name in _BOUND:
        obj = ref()
        if obj is None:
            continue
        try:
            obj.setIcon(make_icon(name))
            alive.append((ref, name))
        except RuntimeError:  # deleted C++ object
            continue
    _BOUND[:] = alive


def icon(name: str):
    def deco(fn: DrawFn) -> DrawFn:
        _REGISTRY[name] = fn
        return fn

    return deco


def _poly(p: QPainter, pts, *, close: bool = True, fill: QColor | None = None) -> None:
    poly = QPolygonF([QPointF(x, y) for x, y in pts])
    if fill is not None:
        p.setBrush(fill)
    if close:
        p.drawPolygon(poly)
    else:
        p.drawPolyline(poly)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _soft(c: QColor, alpha: int = 70) -> QColor:
    return QColor(c.red(), c.green(), c.blue(), alpha)


def _doc(p: QPainter, x: float = 4.5, y: float = 2.5, w: float = 11, h: float = 15) -> None:
    fold = 3.5
    _poly(p, [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)])
    _poly(p, [(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], close=False)


# ------------------------------------------------------------------ file


@icon("open")
def _open(p, c):
    _poly(p, [(2.5, 5), (7.5, 5), (9, 6.5), (16.5, 6.5), (16.5, 15.5), (2.5, 15.5)])
    p.drawLine(QPointF(2.5, 9), QPointF(16.5, 9))


@icon("save")
def _save(p, c):
    _poly(p, [(3.5, 3), (13.5, 3), (16.5, 6), (16.5, 17), (3.5, 17)])
    p.drawRect(QRectF(6.5, 3, 6, 4))
    p.drawRoundedRect(QRectF(6, 11, 8, 6), 1, 1)


@icon("save_as")
def _save_as(p, c):
    _poly(p, [(3, 3), (12, 3), (14.5, 5.5), (14.5, 9)], close=False)
    p.drawLine(QPointF(3, 3), QPointF(3, 16.5))
    p.drawLine(QPointF(3, 16.5), QPointF(9, 16.5))
    p.drawRect(QRectF(6, 3, 5, 3.5))
    p.drawLine(QPointF(11, 17), QPointF(17.5, 10.5))
    p.drawLine(QPointF(16, 9), QPointF(18.5, 11.5))


@icon("print")
def _print(p, c):
    p.drawRect(QRectF(6, 2.5, 8, 4.5))
    p.drawRoundedRect(QRectF(2.5, 7, 15, 7), 1.5, 1.5)
    p.drawRect(QRectF(6, 11.5, 8, 6))
    p.drawPoint(QPointF(14.5, 9.5))


@icon("close")
def _close(p, c):
    p.drawLine(QPointF(5, 5), QPointF(15, 15))
    p.drawLine(QPointF(15, 5), QPointF(5, 15))


@icon("info")
def _info(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    p.drawLine(QPointF(10, 9), QPointF(10, 14))
    p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPoint(QPointF(10, 6.3))


@icon("help")
def _help(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    path = QPainterPath(QPointF(7.5, 8))
    path.cubicTo(QPointF(7.5, 5), QPointF(12.5, 5), QPointF(12.5, 8))
    path.cubicTo(QPointF(12.5, 10), QPointF(10, 10), QPointF(10, 12))
    p.drawPath(path)
    p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPoint(QPointF(10, 14.6))


@icon("keyboard")
def _keyboard(p, c):
    p.drawRoundedRect(QRectF(2, 5, 16, 10), 2, 2)
    for x in (5, 8, 11, 14):
        p.drawPoint(QPointF(x, 8))
    for x in (6.5, 9.5, 12.5):
        p.drawPoint(QPointF(x, 10.5))
    p.drawLine(QPointF(7, 12.8), QPointF(13, 12.8))


@icon("recent")
def _recent(p, c):
    p.drawEllipse(QRectF(3, 3, 14, 14))
    p.drawLine(QPointF(10, 6), QPointF(10, 10))
    p.drawLine(QPointF(10, 10), QPointF(13, 12))


@icon("exit")
def _exit(p, c):
    _poly(p, [(11, 4), (4, 4), (4, 16), (11, 16)], close=False)
    p.drawLine(QPointF(8, 10), QPointF(17, 10))
    _poly(p, [(14, 7), (17, 10), (14, 13)], close=False)


# ------------------------------------------------------------------ edit


@icon("undo")
def _undo(p, c):
    path = QPainterPath(QPointF(5, 8))
    path.lineTo(QPointF(12, 8))
    path.cubicTo(QPointF(17, 8), QPointF(17, 16), QPointF(12, 16))
    path.lineTo(QPointF(8, 16))
    p.drawPath(path)
    _poly(p, [(8, 5), (5, 8), (8, 11)], close=False)


@icon("redo")
def _redo(p, c):
    path = QPainterPath(QPointF(15, 8))
    path.lineTo(QPointF(8, 8))
    path.cubicTo(QPointF(3, 8), QPointF(3, 16), QPointF(8, 16))
    path.lineTo(QPointF(12, 16))
    p.drawPath(path)
    _poly(p, [(12, 5), (15, 8), (12, 11)], close=False)


@icon("cut")
def _cut(p, c):
    p.drawEllipse(QRectF(3, 12, 4.5, 4.5))
    p.drawEllipse(QRectF(12.5, 12, 4.5, 4.5))
    p.drawLine(QPointF(6.5, 12.5), QPointF(14, 3))
    p.drawLine(QPointF(13.5, 12.5), QPointF(6, 3))


@icon("copy")
def _copy(p, c):
    p.drawRoundedRect(QRectF(7, 6.5, 9.5, 11), 1.5, 1.5)
    _poly(p, [(13, 6.5), (13, 3), (3.5, 3), (3.5, 14), (7, 14)], close=False)


@icon("paste")
def _paste(p, c):
    _poly(p, [(7, 4), (4, 4), (4, 17), (16, 17), (16, 4), (13, 4)], close=False)
    p.drawRoundedRect(QRectF(7, 2.5, 6, 3), 1, 1)
    p.drawLine(QPointF(7, 10), QPointF(13, 10))
    p.drawLine(QPointF(7, 13), QPointF(11, 13))


@icon("delete")
def _delete(p, c):
    p.drawLine(QPointF(3.5, 5.5), QPointF(16.5, 5.5))
    _poly(p, [(8, 5.5), (8, 3), (12, 3), (12, 5.5)], close=False)
    _poly(p, [(5, 5.5), (6, 17), (14, 17), (15, 5.5)], close=False)
    p.drawLine(QPointF(8.5, 8.5), QPointF(8.5, 14))
    p.drawLine(QPointF(11.5, 8.5), QPointF(11.5, 14))


@icon("duplicate")
def _duplicate(p, c):
    p.drawRoundedRect(QRectF(3, 3, 10, 10), 1.5, 1.5)
    p.drawRoundedRect(QRectF(7, 7, 10, 10), 1.5, 1.5)
    p.drawLine(QPointF(12, 10), QPointF(12, 14))
    p.drawLine(QPointF(10, 12), QPointF(14, 12))


@icon("select_all")
def _select_all(p, c):
    pen = QPen(c, 1.4, Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    p.drawRect(QRectF(3, 3, 14, 14))
    p.setPen(QPen(c, 1.5))
    p.setBrush(_soft(c))
    p.drawRect(QRectF(6.5, 6.5, 7, 7))


@icon("find")
def _find(p, c):
    p.drawEllipse(QRectF(3, 3, 10.5, 10.5))
    p.drawLine(QPointF(11.8, 11.8), QPointF(17, 17))


@icon("style_copy")
def _style_copy(p, c):
    p.drawRoundedRect(QRectF(3, 3, 11, 5), 1.5, 1.5)
    _poly(p, [(14, 5.5), (16.5, 5.5), (16.5, 10.5), (10, 10.5), (10, 12.5)], close=False)
    p.drawRoundedRect(QRectF(8.8, 12.5, 2.4, 5), 1, 1)


# ------------------------------------------------------------------ tools


@icon("select")
def _select(p, c):
    _poly(p, [(5, 3), (5, 16), (8.6, 12.8), (11, 17.5), (13, 16.6), (10.7, 12), (15, 12)], fill=_soft(c, 255))


@icon("hand")
def _hand(p, c):
    path = QPainterPath(QPointF(6, 11))
    path.lineTo(QPointF(6, 5))
    path.moveTo(QPointF(8.7, 10))
    path.lineTo(QPointF(8.7, 3.5))
    path.moveTo(QPointF(11.4, 10))
    path.lineTo(QPointF(11.4, 4))
    path.moveTo(QPointF(14, 10.5))
    path.lineTo(QPointF(14, 6))
    p.drawPath(path)
    outline = QPainterPath(QPointF(6, 10))
    outline.lineTo(QPointF(3.8, 8.6))
    outline.cubicTo(QPointF(2.5, 9.5), QPointF(3, 11), QPointF(4.5, 12.5))
    outline.cubicTo(QPointF(7, 16), QPointF(8, 17.5), QPointF(11, 17.5))
    outline.cubicTo(QPointF(14, 17.5), QPointF(14, 14), QPointF(14, 10.5))
    p.drawPath(outline)


@icon("text")
def _text(p, c):
    p.drawLine(QPointF(4.5, 4), QPointF(15.5, 4))
    p.drawLine(QPointF(10, 4), QPointF(10, 16.5))
    p.drawLine(QPointF(7.5, 16.5), QPointF(12.5, 16.5))
    p.drawLine(QPointF(4.5, 4), QPointF(4.5, 5.8))
    p.drawLine(QPointF(15.5, 4), QPointF(15.5, 5.8))


@icon("edit_text")
def _edit_text(p, c):
    p.drawLine(QPointF(3, 4), QPointF(11, 4))
    p.drawLine(QPointF(7, 4), QPointF(7, 13))
    p.drawLine(QPointF(10, 17), QPointF(17, 10))
    p.drawLine(QPointF(15.5, 8.5), QPointF(18.5, 11.5))
    p.drawLine(QPointF(10, 17), QPointF(9.5, 18.5))


@icon("image")
def _image(p, c):
    p.drawRoundedRect(QRectF(2.5, 3.5, 15, 13), 2, 2)
    p.drawEllipse(QRectF(5.5, 6.5, 3, 3))
    _poly(p, [(3, 15), (8.5, 10.5), (11.5, 13), (14, 10.5), (17.5, 14)], close=False)


@icon("highlight")
def _highlight(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_soft(c, 80))
    p.drawRect(QRectF(2.5, 13.5, 15, 4))
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    _poly(p, [(5.5, 12.5), (12.5, 3), (16, 5.5), (9, 15)])
    p.drawLine(QPointF(5.5, 12.5), QPointF(4.5, 15.5))
    p.drawLine(QPointF(4.5, 15.5), QPointF(9, 15))


@icon("eraser")
def _eraser(p, c):
    # Angled eraser block (parallelogram) with a darker tip
    p.setBrush(_soft(c, 50))
    _poly(p, [(4, 13), (12, 4), (16, 7.5), (8, 16.5)], fill=_soft(c, 50))
    p.setBrush(c)
    _poly(p, [(12, 4), (16, 7.5), (14.5, 9), (10.5, 5.5)], fill=c)
    p.setBrush(Qt.BrushStyle.NoBrush)


@icon("underline")
def _underline(p, c):
    path = QPainterPath(QPointF(6, 3.5))
    path.lineTo(QPointF(6, 9.5))
    path.cubicTo(QPointF(6, 14), QPointF(14, 14), QPointF(14, 9.5))
    path.lineTo(QPointF(14, 3.5))
    p.drawPath(path)
    p.drawLine(QPointF(4, 17), QPointF(16, 17))


@icon("strikeout")
def _strikeout(p, c):
    path = QPainterPath(QPointF(14, 5.5))
    path.cubicTo(QPointF(13, 3), QPointF(6, 3), QPointF(6.2, 6.5))
    path.cubicTo(QPointF(6.4, 9), QPointF(13.8, 9), QPointF(14, 12.8))
    path.cubicTo(QPointF(14, 16.8), QPointF(7, 17), QPointF(6, 14.5))
    p.drawPath(path)
    p.drawLine(QPointF(3, 10), QPointF(17, 10))


@icon("comment")
def _comment(p, c):
    path = QPainterPath(QPointF(4, 3.5))
    path.lineTo(QPointF(16, 3.5))
    path.quadTo(QPointF(17.5, 3.5), QPointF(17.5, 5))
    path.lineTo(QPointF(17.5, 12))
    path.quadTo(QPointF(17.5, 13.5), QPointF(16, 13.5))
    path.lineTo(QPointF(9, 13.5))
    path.lineTo(QPointF(5.5, 17))
    path.lineTo(QPointF(5.5, 13.5))
    path.lineTo(QPointF(4, 13.5))
    path.quadTo(QPointF(2.5, 13.5), QPointF(2.5, 12))
    path.lineTo(QPointF(2.5, 5))
    path.quadTo(QPointF(2.5, 3.5), QPointF(4, 3.5))
    p.drawPath(path)
    p.drawLine(QPointF(6, 7.3), QPointF(14, 7.3))
    p.drawLine(QPointF(6, 10), QPointF(11, 10))


@icon("callout")
def _callout(p, c):
    p.drawRoundedRect(QRectF(7, 3, 10.5, 8), 1.5, 1.5)
    p.drawLine(QPointF(9, 11), QPointF(3, 17))
    p.drawLine(QPointF(9.5, 6), QPointF(15, 6))
    p.drawLine(QPointF(9.5, 8.5), QPointF(13, 8.5))


@icon("stamp")
def _stamp(p, c):
    path = QPainterPath(QPointF(8, 9))
    path.cubicTo(QPointF(5.5, 7), QPointF(6.5, 2.5), QPointF(10, 2.5))
    path.cubicTo(QPointF(13.5, 2.5), QPointF(14.5, 7), QPointF(12, 9))
    p.drawPath(path)
    p.drawRoundedRect(QRectF(3, 9, 14, 4.5), 1.5, 1.5)
    p.drawLine(QPointF(3.5, 17), QPointF(16.5, 17))


@icon("shapes")
def _shapes(p, c):
    p.drawRect(QRectF(2.5, 8.5, 8.5, 8.5))
    p.drawEllipse(QRectF(8.5, 2.5, 9, 9))


@icon("rect")
def _rect(p, c):
    p.drawRoundedRect(QRectF(3, 4.5, 14, 11), 1, 1)


@icon("ellipse")
def _ellipse(p, c):
    p.drawEllipse(QRectF(2.5, 4.5, 15, 11))


@icon("circle")
def _circle(p, c):
    p.drawEllipse(QRectF(3.5, 3.5, 13, 13))


@icon("line")
def _line(p, c):
    p.drawLine(QPointF(4, 16), QPointF(16, 4))


@icon("arrow")
def _arrow(p, c):
    p.drawLine(QPointF(4, 16), QPointF(15.5, 4.5))
    _poly(p, [(9, 4.5), (15.5, 4.5), (15.5, 11)], close=False)


@icon("freehand")
def _freehand(p, c):
    path = QPainterPath(QPointF(3, 14))
    path.cubicTo(QPointF(5, 6), QPointF(8, 6), QPointF(9, 11))
    path.cubicTo(QPointF(10, 16), QPointF(13, 15), QPointF(14, 9))
    path.cubicTo(QPointF(14.5, 6), QPointF(16, 5), QPointF(17.5, 6))
    p.drawPath(path)


@icon("color")
def _color(p, c):
    p.drawLine(QPointF(6, 13), QPointF(10, 3))
    p.drawLine(QPointF(10, 3), QPointF(14, 13))
    p.drawLine(QPointF(7.4, 9.5), QPointF(12.6, 9.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ef4444"))
    p.drawRoundedRect(QRectF(3, 15, 14, 3), 1, 1)


# ------------------------------------------------------------------ text formatting


@icon("bold")
def _bold(p, c):
    f = QFont("Segoe UI")
    f.setPixelSize(15)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 20, 20), int(Qt.AlignmentFlag.AlignCenter), "B")


@icon("italic")
def _italic(p, c):
    p.drawLine(QPointF(9, 4), QPointF(15, 4))
    p.drawLine(QPointF(5, 16), QPointF(11, 16))
    p.drawLine(QPointF(12, 4), QPointF(8, 16))


@icon("underline_fmt")
def _underline_fmt(p, c):
    _underline(p, c)


@icon("align_left")
def _al(p, c):
    for y, w in ((5, 14), (8.5, 9), (12, 14), (15.5, 9)):
        p.drawLine(QPointF(3, y), QPointF(3 + w, y))


def _letters(p: QPainter, text: str, size: float) -> None:
    f = QFont("Segoe UI")
    f.setPixelSize(int(size))
    f.setWeight(QFont.Weight.Bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.3)
    p.setFont(f)
    p.drawText(QRectF(-2, 0, 24, 20), int(Qt.AlignmentFlag.AlignCenter), text)


@icon("case_upper")
def _cu(p, c):
    _letters(p, "AB", 13)


@icon("case_lower")
def _cl(p, c):
    _letters(p, "ab", 14.5)


@icon("wrap_text")
def _wrap(p, c):
    # two full lines, the last one turns back under itself with an arrowhead
    p.drawLine(QPointF(3, 5), QPointF(17, 5))
    path = QPainterPath(QPointF(3, 10))
    path.lineTo(QPointF(14, 10))
    path.cubicTo(QPointF(18.5, 10), QPointF(18.5, 15.5), QPointF(14, 15.5))
    path.lineTo(QPointF(10, 15.5))
    p.drawPath(path)
    _poly(p, ((10.5, 13), (8, 15.5), (10.5, 18)), close=False)
    p.drawLine(QPointF(3, 15.5), QPointF(6, 15.5))


@icon("align_center")
def _ac(p, c):
    for y, w in ((5, 14), (8.5, 9), (12, 14), (15.5, 9)):
        p.drawLine(QPointF(10 - w / 2, y), QPointF(10 + w / 2, y))


@icon("align_justify")
def _aj(p, c):
    for y, w in ((5, 14), (8.5, 14), (12, 14), (15.5, 8)):
        p.drawLine(QPointF(3, y), QPointF(3 + w, y))


@icon("align_right")
def _ar(p, c):
    for y, w in ((5, 14), (8.5, 9), (12, 14), (15.5, 9)):
        p.drawLine(QPointF(17 - w, y), QPointF(17, y))


def _valign(p, top: float) -> None:
    """Box edges (faint) with two text lines placed at ``top``."""
    pen = p.pen()
    faint = QPen(pen)
    faint.setWidthF(1.0)
    col = QColor(faint.color())
    col.setAlphaF(0.45)
    faint.setColor(col)
    p.setPen(faint)
    p.drawLine(QPointF(2, 2.5), QPointF(18, 2.5))
    p.drawLine(QPointF(2, 17.5), QPointF(18, 17.5))
    p.setPen(pen)
    p.drawLine(QPointF(5, top), QPointF(15, top))
    p.drawLine(QPointF(6.5, top + 3.5), QPointF(13.5, top + 3.5))


@icon("valign_top")
def _vt(p, c):
    _valign(p, 6)


@icon("valign_middle")
def _vm(p, c):
    _valign(p, 8.25)


@icon("valign_bottom")
def _vb(p, c):
    _valign(p, 10.5)


@icon("font_smaller")
def _fsm(p, c):
    f = QFont("Segoe UI")
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(1, 4, 12, 14), int(Qt.AlignmentFlag.AlignCenter), "A")
    p.drawLine(QPointF(13, 8), QPointF(18, 8))


@icon("font_larger")
def _flg(p, c):
    f = QFont("Segoe UI")
    f.setPixelSize(14)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 3, 13, 16), int(Qt.AlignmentFlag.AlignCenter), "A")
    p.drawLine(QPointF(13, 7), QPointF(18, 7))
    p.drawLine(QPointF(15.5, 4.5), QPointF(15.5, 9.5))


# ------------------------------------------------------------------ arrange / align objects


@icon("bring_forward")
def _bf(p, c):
    p.drawRect(QRectF(3, 7, 9, 9))
    p.setBrush(_soft(c, 255))
    p.drawRect(QRectF(8, 3, 9, 9))
    p.setBrush(Qt.BrushStyle.NoBrush)


@icon("send_backward")
def _sb(p, c):
    p.setBrush(_soft(c, 255))
    p.drawRect(QRectF(3, 7, 9, 9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(8, 3, 9, 9))


@icon("obj_align_left")
def _oal(p, c):
    p.drawLine(QPointF(3, 2.5), QPointF(3, 17.5))
    p.drawRect(QRectF(5.5, 5, 11, 3.5))
    p.drawRect(QRectF(5.5, 11.5, 7, 3.5))


@icon("obj_align_center")
def _oac(p, c):
    p.drawLine(QPointF(10, 2.5), QPointF(10, 17.5))
    p.drawRect(QRectF(4, 5, 12, 3.5))
    p.drawRect(QRectF(6.5, 11.5, 7, 3.5))


@icon("distribute")
def _dist(p, c):
    p.drawLine(QPointF(3, 3), QPointF(3, 17))
    p.drawLine(QPointF(17, 3), QPointF(17, 17))
    p.drawRect(QRectF(7.5, 6, 5, 8))


# ------------------------------------------------------------------ view


@icon("zoom_in")
def _zoom_in(p, c):
    _find(p, c)
    p.drawLine(QPointF(5.7, 8.25), QPointF(10.8, 8.25))
    p.drawLine(QPointF(8.25, 5.7), QPointF(8.25, 10.8))


@icon("zoom_out")
def _zoom_out(p, c):
    _find(p, c)
    p.drawLine(QPointF(5.7, 8.25), QPointF(10.8, 8.25))


@icon("fit_width")
def _fit_width(p, c):
    p.drawRoundedRect(QRectF(5, 3, 10, 14), 1, 1)
    p.drawLine(QPointF(1.5, 10), QPointF(5, 10))
    p.drawLine(QPointF(15, 10), QPointF(18.5, 10))
    _poly(p, [(3, 8.3), (1.5, 10), (3, 11.7)], close=False)
    _poly(p, [(17, 8.3), (18.5, 10), (17, 11.7)], close=False)


@icon("fit_page")
def _fit_page(p, c):
    p.drawRoundedRect(QRectF(5.5, 4.5, 9, 11), 1, 1)
    for (x0, y0, x1, y1) in ((2.5, 5, 2.5, 2.5), (2.5, 2.5, 5, 2.5), (17.5, 5, 17.5, 2.5), (17.5, 2.5, 15, 2.5),
                             (2.5, 15, 2.5, 17.5), (2.5, 17.5, 5, 17.5), (17.5, 15, 17.5, 17.5), (17.5, 17.5, 15, 17.5)):
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


@icon("actual_size")
def _actual(p, c):
    p.drawRoundedRect(QRectF(2.5, 4, 15, 12), 1.5, 1.5)
    f = QFont("Segoe UI")
    f.setPixelSize(7)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(2.5, 4, 15, 12), int(Qt.AlignmentFlag.AlignCenter), "1:1")


@icon("prev")
def _prev(p, c):
    _poly(p, [(12.5, 4.5), (7, 10), (12.5, 15.5)], close=False)


@icon("next")
def _next(p, c):
    _poly(p, [(7.5, 4.5), (13, 10), (7.5, 15.5)], close=False)


@icon("first")
def _first(p, c):
    _poly(p, [(14, 4.5), (8.5, 10), (14, 15.5)], close=False)
    p.drawLine(QPointF(5.5, 4.5), QPointF(5.5, 15.5))


@icon("last")
def _last(p, c):
    _poly(p, [(6, 4.5), (11.5, 10), (6, 15.5)], close=False)
    p.drawLine(QPointF(14.5, 4.5), QPointF(14.5, 15.5))


@icon("goto")
def _goto(p, c):
    _doc(p, 3, 2.5, 10, 14)
    p.drawLine(QPointF(10, 13), QPointF(18, 13))
    _poly(p, [(15, 10), (18, 13), (15, 16)], close=False)


@icon("panel_left")
def _panel_left(p, c):
    p.drawRoundedRect(QRectF(2.5, 3.5, 15, 13), 2, 2)
    p.drawLine(QPointF(7.5, 3.5), QPointF(7.5, 16.5))


@icon("panel_right")
def _panel_right(p, c):
    p.drawRoundedRect(QRectF(2.5, 3.5, 15, 13), 2, 2)
    p.drawLine(QPointF(12.5, 3.5), QPointF(12.5, 16.5))


@icon("fullscreen")
def _fullscreen(p, c):
    for pts in (((3, 7), (3, 3), (7, 3)), ((13, 3), (17, 3), (17, 7)), ((17, 13), (17, 17), (13, 17)), ((7, 17), (3, 17), (3, 13))):
        _poly(p, pts, close=False)


@icon("theme")
def _theme(p, c):
    p.drawEllipse(QRectF(3, 3, 14, 14))
    path = QPainterPath(QPointF(10, 3))
    path.arcTo(QRectF(3, 3, 14, 14), 90, 180)
    path.closeSubpath()
    p.setBrush(c)
    p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush)


@icon("fields")
def _fields(p, c):
    p.drawRoundedRect(QRectF(2.5, 6, 15, 8), 1.5, 1.5)
    p.drawLine(QPointF(5.5, 8.5), QPointF(5.5, 11.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_soft(c, 60))
    p.drawRect(QRectF(3.5, 7, 13, 6))


# ------------------------------------------------------------------ pages / organize


@icon("pages")
def _pages(p, c):
    p.drawRoundedRect(QRectF(3.5, 2.5, 9, 12), 1, 1)
    _poly(p, [(14.5, 5), (16.5, 5), (16.5, 17.5), (7, 17.5), (7, 16.5)], close=False)


@icon("bookmarks")
def _bookmarks(p, c):
    _poly(p, [(5.5, 2.5), (14.5, 2.5), (14.5, 17.5), (10, 13.5), (5.5, 17.5)])


@icon("search")
def _search(p, c):
    _find(p, c)


@icon("attachments")
def _attach(p, c):
    path = QPainterPath(QPointF(13.5, 6.5))
    path.lineTo(QPointF(7.5, 12.5))
    path.cubicTo(QPointF(6, 14), QPointF(8.5, 16.5), QPointF(10, 15))
    path.lineTo(QPointF(16, 9))
    path.cubicTo(QPointF(19, 6), QPointF(14, 1), QPointF(11, 4))
    path.lineTo(QPointF(4.5, 10.5))
    path.cubicTo(QPointF(1, 14), QPointF(6.5, 19.5), QPointF(10, 16))
    p.drawPath(path)


@icon("rotate_cw")
def _rot_cw(p, c):
    p.drawArc(QRectF(3.5, 4, 12, 12), 100 * 16, -280 * 16)
    _poly(p, [(12.5, 1.5), (15.5, 4.8), (12, 7)], close=False)


@icon("rotate_ccw")
def _rot_ccw(p, c):
    p.drawArc(QRectF(4.5, 4, 12, 12), 80 * 16, 280 * 16)
    _poly(p, [(7.5, 1.5), (4.5, 4.8), (8, 7)], close=False)


@icon("page_add")
def _page_add(p, c):
    _doc(p, 3.5, 2.5, 10, 14)
    p.drawLine(QPointF(15, 12), QPointF(15, 18))
    p.drawLine(QPointF(12, 15), QPointF(18, 15))


@icon("page_insert")
def _page_insert(p, c):
    _doc(p, 6.5, 2.5, 10, 14)
    p.drawLine(QPointF(1.5, 10), QPointF(9.5, 10))
    _poly(p, [(6.5, 7), (9.5, 10), (6.5, 13)], close=False)


@icon("page_delete")
def _page_delete(p, c):
    _doc(p, 3.5, 2.5, 10, 14)
    p.drawLine(QPointF(12.5, 12.5), QPointF(17.5, 17.5))
    p.drawLine(QPointF(17.5, 12.5), QPointF(12.5, 17.5))


@icon("page_duplicate")
def _page_dup(p, c):
    p.drawRoundedRect(QRectF(3, 2.5, 9, 11.5), 1, 1)
    p.drawRoundedRect(QRectF(7.5, 6, 9, 11.5), 1, 1)


@icon("page_replace")
def _page_replace(p, c):
    p.drawRoundedRect(QRectF(5.5, 3, 9, 14), 1, 1)
    p.drawArc(QRectF(1.5, 6, 8, 8), 90 * 16, 180 * 16)
    _poly(p, [(4, 12.5), (5.5, 14), (4, 15.5)], close=False)


@icon("crop")
def _crop(p, c):
    _poly(p, [(5.5, 2), (5.5, 14.5), (18, 14.5)], close=False)
    _poly(p, [(2, 5.5), (14.5, 5.5), (14.5, 18)], close=False)


@icon("extract")
def _extract(p, c):
    _doc(p, 3, 2.5, 10, 14)
    p.drawLine(QPointF(9, 12), QPointF(18, 12))
    _poly(p, [(15, 9), (18, 12), (15, 15)], close=False)


@icon("merge")
def _merge(p, c):
    p.drawRoundedRect(QRectF(2.5, 3, 6, 8), 1, 1)
    p.drawRoundedRect(QRectF(11.5, 3, 6, 8), 1, 1)
    _poly(p, [(5.5, 11), (5.5, 13), (10, 15.5), (14.5, 13), (14.5, 11)], close=False)
    p.drawLine(QPointF(10, 15.5), QPointF(10, 18))


@icon("split")
def _split(p, c):
    p.drawRoundedRect(QRectF(7, 2, 6, 7), 1, 1)
    _poly(p, [(10, 9), (10, 11), (5, 13.5), (5, 15)], close=False)
    _poly(p, [(10, 11), (15, 13.5), (15, 15)], close=False)
    p.drawRoundedRect(QRectF(2.5, 15, 5, 3), 1, 1)
    p.drawRoundedRect(QRectF(12.5, 15, 5, 3), 1, 1)


@icon("page_size")
def _page_size(p, c):
    p.drawRoundedRect(QRectF(5, 5, 10, 13), 1, 1)
    p.drawLine(QPointF(5, 2.5), QPointF(15, 2.5))
    p.drawLine(QPointF(2.5, 5), QPointF(2.5, 18))


# ------------------------------------------------------------------ convert / export / ocr


@icon("convert")
def _convert(p, c):
    p.drawLine(QPointF(3, 7), QPointF(15, 7))
    _poly(p, [(12, 4), (15.5, 7), (12, 10)], close=False)
    p.drawLine(QPointF(17, 13), QPointF(5, 13))
    _poly(p, [(8, 10), (4.5, 13), (8, 16)], close=False)


@icon("export")
def _export(p, c):
    _poly(p, [(7, 7), (4, 7), (4, 17), (16, 17), (16, 7), (13, 7)], close=False)
    p.drawLine(QPointF(10, 2.5), QPointF(10, 12))
    _poly(p, [(7, 5.5), (10, 2.5), (13, 5.5)], close=False)


@icon("import_images")
def _import_images(p, c):
    p.drawRoundedRect(QRectF(2.5, 5.5, 11, 9), 1.5, 1.5)
    _poly(p, [(3, 13.5), (6.5, 10), (9, 12), (13, 8.5)], close=False)
    _poly(p, [(15.5, 4), (17.5, 4), (17.5, 17), (6, 17), (6, 15)], close=False)


@icon("text_file")
def _text_file(p, c):
    _doc(p)
    for y in (8, 10.5, 13):
        p.drawLine(QPointF(7, y), QPointF(13, y))


@icon("ocr")
def _ocr(p, c):
    for pts in (((2.5, 6), (2.5, 2.5), (6, 2.5)), ((14, 2.5), (17.5, 2.5), (17.5, 6)),
                ((17.5, 14), (17.5, 17.5), (14, 17.5)), ((6, 17.5), (2.5, 17.5), (2.5, 14))):
        _poly(p, pts, close=False)
    f = QFont("Segoe UI")
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(2, 3, 16, 14), int(Qt.AlignmentFlag.AlignCenter), "Aa")


@icon("magic")
def _magic(p, c):
    p.drawLine(QPointF(3, 17), QPointF(12, 8))
    p.drawLine(QPointF(14, 2.5), QPointF(14, 6.5))
    p.drawLine(QPointF(12, 4.5), QPointF(16, 4.5))
    p.drawLine(QPointF(16.5, 9), QPointF(16.5, 11.5))
    p.drawLine(QPointF(15.25, 10.25), QPointF(17.75, 10.25))


@icon("optimize")
def _optimize(p, c):
    _poly(p, [(4, 7), (10, 2.5), (16, 7)], close=False)
    _poly(p, [(4, 13), (10, 17.5), (16, 13)], close=False)
    p.drawLine(QPointF(10, 2.5), QPointF(10, 8))
    p.drawLine(QPointF(10, 12), QPointF(10, 17.5))
    p.drawLine(QPointF(4, 10), QPointF(16, 10))


@icon("watermark")
def _watermark(p, c):
    path = QPainterPath(QPointF(10, 2.5))
    path.cubicTo(QPointF(14, 8), QPointF(16, 10), QPointF(16, 12.5))
    path.cubicTo(QPointF(16, 16), QPointF(13, 17.5), QPointF(10, 17.5))
    path.cubicTo(QPointF(7, 17.5), QPointF(4, 16), QPointF(4, 12.5))
    path.cubicTo(QPointF(4, 10), QPointF(6, 8), QPointF(10, 2.5))
    p.drawPath(path)


@icon("header_footer")
def _header_footer(p, c):
    p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 1, 1)
    p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(6.5, 5.3), QPointF(13.5, 5.3))
    p.drawLine(QPointF(6.5, 14.7), QPointF(10, 14.7))


@icon("capabilities")
def _caps(p, c):
    for y in (4.5, 10, 15.5):
        p.drawLine(QPointF(8, y), QPointF(17, y))
    _poly(p, [(2.5, 4.5), (3.8, 5.8), (6, 3)], close=False)
    _poly(p, [(2.5, 10), (3.8, 11.3), (6, 8.5)], close=False)
    p.drawLine(QPointF(3, 14), QPointF(5.5, 16.5))
    p.drawLine(QPointF(5.5, 14), QPointF(3, 16.5))


# ------------------------------------------------------------------ forms / tables


@icon("form")
def _form(p, c):
    p.drawRoundedRect(QRectF(3, 2.5, 14, 15), 1.5, 1.5)
    p.drawRect(QRectF(6, 6, 2.5, 2.5))
    p.drawLine(QPointF(10.5, 7.2), QPointF(14.5, 7.2))
    p.drawRect(QRectF(6, 11.5, 2.5, 2.5))
    p.drawLine(QPointF(10.5, 12.7), QPointF(14.5, 12.7))


@icon("checkbox")
def _checkbox(p, c):
    p.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)
    _poly(p, [(6.5, 10), (9, 12.5), (13.5, 7.5)], close=False)


@icon("radio")
def _radio(p, c):
    p.drawEllipse(QRectF(3.5, 3.5, 13, 13))
    p.setBrush(c)
    p.drawEllipse(QRectF(7.5, 7.5, 5, 5))
    p.setBrush(Qt.BrushStyle.NoBrush)


@icon("dropdown")
def _dropdown(p, c):
    p.drawRoundedRect(QRectF(2.5, 6, 15, 8), 1.5, 1.5)
    _poly(p, [(12, 9), (13.75, 11), (15.5, 9)], close=False)


@icon("table")
def _table(p, c):
    p.drawRoundedRect(QRectF(2.5, 3.5, 15, 13), 1.5, 1.5)
    p.drawLine(QPointF(2.5, 8), QPointF(17.5, 8))
    p.drawLine(QPointF(2.5, 12.3), QPointF(17.5, 12.3))
    p.drawLine(QPointF(8, 3.5), QPointF(8, 16.5))


@icon("detect")
def _detect(p, c):
    pen = QPen(c, 1.4, Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    p.drawRect(QRectF(2.5, 2.5, 11, 11))
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawEllipse(QRectF(8.5, 8.5, 6.5, 6.5))
    p.drawLine(QPointF(14, 14), QPointF(17.5, 17.5))


# ------------------------------------------------------------------ protect / sign


@icon("lock")
def _lock(p, c):
    p.drawRoundedRect(QRectF(4, 9, 12, 8.5), 1.5, 1.5)
    path = QPainterPath(QPointF(6.5, 9))
    path.lineTo(QPointF(6.5, 6.5))
    path.cubicTo(QPointF(6.5, 2), QPointF(13.5, 2), QPointF(13.5, 6.5))
    path.lineTo(QPointF(13.5, 9))
    p.drawPath(path)
    p.drawLine(QPointF(10, 12), QPointF(10, 14.5))


@icon("unlock")
def _unlock(p, c):
    p.drawRoundedRect(QRectF(4, 9, 12, 8.5), 1.5, 1.5)
    path = QPainterPath(QPointF(6.5, 9))
    path.lineTo(QPointF(6.5, 6.5))
    path.cubicTo(QPointF(6.5, 2), QPointF(13.5, 2), QPointF(13.5, 5))
    p.drawPath(path)
    p.drawLine(QPointF(10, 12), QPointF(10, 14.5))


@icon("shield")
def _shield(p, c):
    path = QPainterPath(QPointF(10, 2.5))
    path.lineTo(QPointF(16, 5))
    path.lineTo(QPointF(16, 9.5))
    path.cubicTo(QPointF(16, 13.5), QPointF(13, 16.2), QPointF(10, 17.5))
    path.cubicTo(QPointF(7, 16.2), QPointF(4, 13.5), QPointF(4, 9.5))
    path.lineTo(QPointF(4, 5))
    path.closeSubpath()
    p.drawPath(path)


@icon("metadata")
def _metadata(p, c):
    _doc(p)
    p.drawLine(QPointF(7, 9), QPointF(13, 9))
    p.drawLine(QPointF(7, 12), QPointF(11, 12))
    p.drawLine(QPointF(7, 6), QPointF(9, 6))


@icon("redact")
def _redact(p, c):
    p.drawLine(QPointF(3, 5), QPointF(17, 5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(3, 8.5, 14, 4), 1, 1)
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(3, 16), QPointF(12, 16))


@icon("redact_apply")
def _redact_apply(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(2.5, 4, 10, 3.5), 1, 1)
    p.drawRoundedRect(QRectF(2.5, 10, 7, 3.5), 1, 1)
    p.setPen(QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    _poly(p, [(11.5, 13.5), (14, 16), (18, 11)], close=False)


@icon("sign")
def _sign(p, c):
    path = QPainterPath(QPointF(2.5, 13))
    path.cubicTo(QPointF(4, 6), QPointF(7, 4), QPointF(7, 9))
    path.cubicTo(QPointF(7, 14), QPointF(5, 15), QPointF(6.5, 11.5))
    path.cubicTo(QPointF(8, 8.5), QPointF(10, 12.5), QPointF(11.5, 11))
    path.cubicTo(QPointF(13, 9.5), QPointF(14, 12.5), QPointF(17.5, 11.5))
    p.drawPath(path)
    p.drawLine(QPointF(2.5, 16.5), QPointF(17.5, 16.5))


@icon("sign_image")
def _sign_image(p, c):
    p.drawRoundedRect(QRectF(2.5, 4, 15, 12), 1.5, 1.5)
    path = QPainterPath(QPointF(5, 12))
    path.cubicTo(QPointF(6, 7), QPointF(8, 7), QPointF(8.5, 10))
    path.cubicTo(QPointF(9, 13), QPointF(12, 8), QPointF(15, 10))
    p.drawPath(path)


@icon("sign_draw")
def _sign_draw(p, c):
    p.drawLine(QPointF(4, 16), QPointF(14, 6))
    p.drawLine(QPointF(12.5, 4.5), QPointF(15.5, 7.5))
    p.drawLine(QPointF(14, 3), QPointF(17, 6))
    p.drawLine(QPointF(4, 16), QPointF(3, 17.5))
    p.drawLine(QPointF(9, 17.5), QPointF(17, 17.5))


# ------------------------------------------------------------------ public helpers


# ------------------------------------------------------------------ additional commands


def _plus(p: QPainter, cx: float, cy: float, r: float = 2.5) -> None:
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))


def _minus(p: QPainter, cx: float, cy: float, r: float = 2.5) -> None:
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))


@icon("obj_align_right")
def _oar(p, c):
    p.drawLine(QPointF(17, 2.5), QPointF(17, 17.5))
    p.drawRect(QRectF(3.5, 5, 11, 3.5))
    p.drawRect(QRectF(7.5, 11.5, 7, 3.5))


@icon("obj_align_top")
def _oat(p, c):
    p.drawLine(QPointF(2.5, 3), QPointF(17.5, 3))
    p.drawRect(QRectF(5, 5.5, 3.5, 11))
    p.drawRect(QRectF(11.5, 5.5, 3.5, 7))


@icon("obj_align_middle")
def _oam(p, c):
    p.drawLine(QPointF(2.5, 10), QPointF(17.5, 10))
    p.drawRect(QRectF(5, 4, 3.5, 12))
    p.drawRect(QRectF(11.5, 6.5, 3.5, 7))


@icon("obj_align_bottom")
def _oab(p, c):
    p.drawLine(QPointF(2.5, 17), QPointF(17.5, 17))
    p.drawRect(QRectF(5, 3.5, 3.5, 11))
    p.drawRect(QRectF(11.5, 7.5, 3.5, 7))


@icon("distribute_v")
def _distv(p, c):
    p.drawLine(QPointF(3, 3), QPointF(17, 3))
    p.drawLine(QPointF(3, 17), QPointF(17, 17))
    p.drawRect(QRectF(6, 7.5, 8, 5))


@icon("find_next")
def _find_next(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 9, 9))
    p.drawLine(QPointF(10, 10), QPointF(12.5, 12.5))
    _poly(p, [(13.5, 11), (17, 14.5), (13.5, 18)], close=False)


@icon("find_prev")
def _find_prev(p, c):
    p.drawEllipse(QRectF(8.5, 2.5, 9, 9))
    p.drawLine(QPointF(10, 10), QPointF(7.5, 12.5))
    _poly(p, [(6.5, 11), (3, 14.5), (6.5, 18)], close=False)


@icon("deselect")
def _deselect(p, c):
    pen = QPen(c, 1.4, Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    p.drawRect(QRectF(2.5, 2.5, 15, 15))
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(7, 7), QPointF(13, 13))
    p.drawLine(QPointF(13, 7), QPointF(7, 13))


@icon("folder")
def _folder(p, c):
    _poly(p, [(2.5, 5), (7.5, 5), (9, 6.5), (17.5, 6.5), (17.5, 16), (2.5, 16)])
    p.drawLine(QPointF(2.5, 9), QPointF(17.5, 9))


@icon("clear_list")
def _clear_list(p, c):
    for y in (5, 9, 13):
        p.drawLine(QPointF(3, y), QPointF(10, y))
    p.drawLine(QPointF(12, 11), QPointF(17, 16))
    p.drawLine(QPointF(17, 11), QPointF(12, 16))


@icon("background")
def _background(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_soft(c, 90))
    p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 1, 1)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 1, 1)
    p.drawLine(QPointF(7, 7), QPointF(13, 7))
    p.drawLine(QPointF(7, 10.5), QPointF(13, 10.5))


@icon("page_design_remove")
def _pd_remove(p, c):
    p.drawRoundedRect(QRectF(3, 2.5, 10, 13), 1, 1)
    p.drawLine(QPointF(5.5, 5.3), QPointF(10.5, 5.3))
    p.drawLine(QPointF(5.5, 12.7), QPointF(8.5, 12.7))
    p.drawLine(QPointF(12.5, 12.5), QPointF(17.5, 17.5))
    p.drawLine(QPointF(17.5, 12.5), QPointF(12.5, 17.5))


@icon("date_field")
def _date_field(p, c):
    p.drawRoundedRect(QRectF(3, 4, 14, 13), 1.5, 1.5)
    p.drawLine(QPointF(3, 8), QPointF(17, 8))
    p.drawLine(QPointF(7, 2.5), QPointF(7, 5.5))
    p.drawLine(QPointF(13, 2.5), QPointF(13, 5.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for x in (6, 10, 14):
        p.drawRect(QRectF(x - 1, 10.5, 2, 2))
    p.drawRect(QRectF(5, 13.5, 2, 2))


@icon("select_fields")
def _select_fields(p, c):
    p.drawRoundedRect(QRectF(2.5, 4, 11, 6), 1, 1)
    _poly(p, [(10, 9), (10, 18), (12.5, 15.5), (14.5, 19), (16, 18.2), (14, 14.8), (17.5, 14.5)])


@icon("accept")
def _accept(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    _poly(p, [(6.5, 10.5), (9, 13), (14, 7.5)], close=False)


@icon("reject")
def _reject(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    p.drawLine(QPointF(7.3, 7.3), QPointF(12.7, 12.7))
    p.drawLine(QPointF(12.7, 7.3), QPointF(7.3, 12.7))


def _grid(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2.5, 3.5, 11, 10), 1, 1)
    p.drawLine(QPointF(2.5, 8.5), QPointF(13.5, 8.5))
    p.drawLine(QPointF(8, 3.5), QPointF(8, 13.5))


@icon("row_add")
def _row_add(p, c):
    _grid(p)
    _plus(p, 15, 15.5)


@icon("row_delete")
def _row_del(p, c):
    _grid(p)
    _minus(p, 15, 15.5)


@icon("col_add")
def _col_add(p, c):
    _grid(p)
    p.drawLine(QPointF(16.5, 4), QPointF(16.5, 9))
    p.drawLine(QPointF(14, 6.5), QPointF(19, 6.5))


@icon("col_delete")
def _col_del(p, c):
    _grid(p)
    p.drawLine(QPointF(14, 6.5), QPointF(19, 6.5))


@icon("pages_to_doc")
def _pages_to_doc(p, c):
    p.drawRoundedRect(QRectF(2.5, 3, 7, 9), 1, 1)
    p.drawRoundedRect(QRectF(11, 8, 7, 9.5), 1, 1)
    p.drawLine(QPointF(6, 14.5), QPointF(9.5, 14.5))
    _poly(p, [(8, 12.8), (9.7, 14.5), (8, 16.2)], close=False)


@icon("pages_move")
def _pages_move(p, c):
    pen = QPen(c, 1.4, Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    p.drawRoundedRect(QRectF(2.5, 3, 7, 9), 1, 1)
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawRoundedRect(QRectF(11, 8, 7, 9.5), 1, 1)
    p.drawLine(QPointF(6, 14.5), QPointF(9.5, 14.5))
    _poly(p, [(8, 12.8), (9.7, 14.5), (8, 16.2)], close=False)


@icon("pages_reorder")
def _pages_reorder(p, c):
    """A page with an up and a down arrow beside it: move pages within the document."""
    _doc(p, 2.5, 2.5, 10, 15)
    p.drawLine(QPointF(16, 3.5), QPointF(16, 16.5))
    _poly(p, [(13.5, 6), (16, 3.5), (18.5, 6)], close=False)
    _poly(p, [(13.5, 14), (16, 16.5), (18.5, 14)], close=False)


@icon("redact_pages")
def _redact_pages(p, c):
    p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 1, 1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRect(QRectF(6.5, 5, 7, 10))


@icon("count")
def _count(p, c):
    p.drawRoundedRect(QRectF(2.5, 4, 15, 12), 2, 2)
    f = QFont()
    f.setPixelSize(8)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(2.5, 4, 15, 12), Qt.AlignmentFlag.AlignCenter, "123")


@icon("about")
def _about(p, c):
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    p.drawLine(QPointF(10, 9), QPointF(10, 14))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QRectF(9.1, 5.4, 1.8, 1.8))


@icon("bookmark_add")
def _bookmark_add(p, c):
    _poly(p, [(4, 2.5), (11.5, 2.5), (11.5, 16.5), (7.75, 13), (4, 16.5)])
    _plus(p, 15.5, 6)


@icon("rename")
def _rename(p, c):
    p.drawRoundedRect(QRectF(2.5, 6, 15, 8), 1.5, 1.5)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 16.5))
    p.drawLine(QPointF(10.5, 3.5), QPointF(13.5, 3.5))
    p.drawLine(QPointF(10.5, 16.5), QPointF(13.5, 16.5))


@icon("move_up")
def _move_up(p, c):
    p.drawLine(QPointF(10, 16.5), QPointF(10, 4))
    _poly(p, [(5.5, 8.5), (10, 4), (14.5, 8.5)], close=False)


@icon("move_down")
def _move_down(p, c):
    p.drawLine(QPointF(10, 3.5), QPointF(10, 16))
    _poly(p, [(5.5, 11.5), (10, 16), (14.5, 11.5)], close=False)


@icon("bookmark_target")
def _bookmark_target(p, c):
    _poly(p, [(3, 2.5), (9.5, 2.5), (9.5, 14.5), (6.25, 11.5), (3, 14.5)])
    p.drawRoundedRect(QRectF(11.5, 7, 6, 8), 1, 1)
    p.drawLine(QPointF(9.5, 11), QPointF(11.5, 11))


@icon("sanitize")
def _sanitize(p, c):
    _doc(p, 3.5, 2.5, 10, 13.5)
    p.drawLine(QPointF(6, 6.5), QPointF(11, 6.5))
    p.drawLine(QPointF(6, 9.5), QPointF(9, 9.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for x, y, r in ((15.5, 13, 1.6), (13, 16.5, 1.3), (17, 17, 1.1)):
        p.drawEllipse(QPointF(x, y), r, r)


@icon("snapshot")
def _snapshot(p, c):
    pen = QPen(c, 1.4, Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 2])
    p.setPen(pen)
    p.drawRect(QRectF(2.5, 2.5, 11, 9))
    p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawRoundedRect(QRectF(8, 9.5, 9.5, 8), 1, 1)
    p.drawRect(QRectF(10.5, 8, 4, 1.5))


@icon("default_app")
def _default_app(p, c):
    _doc(p, 3.5, 2.5, 10, 13.5)
    p.drawEllipse(QRectF(10.5, 10.5, 7.5, 7.5))
    _poly(p, [(12.3, 14.3), (13.8, 15.8), (16.3, 12.8)], close=False)


@icon("numbering")
def _numbering(p, c):
    p.drawRoundedRect(QRectF(4, 2.5, 12, 15), 1, 1)
    f = QFont()
    f.setPixelSize(6)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(4, 11, 12, 6), Qt.AlignmentFlag.AlignCenter, "001")



def icon_open() -> QIcon:
    return make_icon("open")


def icon_save() -> QIcon:
    return make_icon("save")


def icon_undo() -> QIcon:
    return make_icon("undo")


def icon_redo() -> QIcon:
    return make_icon("redo")


def icon_select() -> QIcon:
    return make_icon("select")


def icon_text() -> QIcon:
    return make_icon("text")


def icon_image() -> QIcon:
    return make_icon("image")


def icon_highlight() -> QIcon:
    return make_icon("highlight")


def icon_zoom_in() -> QIcon:
    return make_icon("zoom_in")


def icon_zoom_out() -> QIcon:
    return make_icon("zoom_out")


def icon_fit_width() -> QIcon:
    return make_icon("fit_width")


def icon_prev() -> QIcon:
    return make_icon("prev")


def icon_next() -> QIcon:
    return make_icon("next")


def icon_pages() -> QIcon:
    return make_icon("pages")


def icon_bookmarks() -> QIcon:
    return make_icon("bookmarks")


def icon_search() -> QIcon:
    return make_icon("search")


def apply_toolbar_icons(actions: dict) -> None:
    """Map icon names → actions (``{"open": act_open, ...}``); recoloured on theme change."""
    for key, act in actions.items():
        if act is not None:
            set_action_icon(act, key)


@icon("updates")
def _updates(p, c):
    # downward arrow into a tray: download and install a newer version
    p.drawLine(QPointF(10, 2.5), QPointF(10, 12))
    _poly(p, [(6.5, 8.5), (10, 12), (13.5, 8.5)], close=False)
    _poly(p, [(3, 12.5), (3, 16.5), (17, 16.5), (17, 12.5)], close=False)


@icon("settings")
def _settings(p, c):
    # three sliders
    for y, knob in ((5, 7), (10, 13), (15, 9)):
        p.drawLine(QPointF(3, y), QPointF(17, y))
        p.setBrush(c)
        p.drawEllipse(QRectF(knob - 1.8, y - 1.8, 3.6, 3.6))
        p.setBrush(Qt.BrushStyle.NoBrush)


# --- 0.3.0 tools ---------------------------------------------------------------------------------

@icon("squiggly")
def _squiggly(p, c):
    # "S" over a wavy line
    path = QPainterPath(QPointF(13.5, 4.5))
    path.cubicTo(QPointF(12.5, 2.5), QPointF(6.5, 2.5), QPointF(6.8, 5.5))
    path.cubicTo(QPointF(7, 7.5), QPointF(13.2, 7.5), QPointF(13.3, 10.3))
    path.cubicTo(QPointF(13.3, 13.3), QPointF(7.2, 13.4), QPointF(6.3, 11.2))
    p.drawPath(path)
    wave = QPainterPath(QPointF(2.5, 16.5))
    x = 2.5
    up = True
    while x < 17:
        wave.quadTo(QPointF(x + 1.25, 14.6 if up else 18.4), QPointF(x + 2.5, 16.5))
        x += 2.5
        up = not up
    p.drawPath(wave)


@icon("area_ocr")
def _area_ocr(p, c):
    # dashed selection rectangle around "Aa"
    pen = p.pen()
    dashed = QPen(pen)
    dashed.setStyle(Qt.PenStyle.DashLine)
    dashed.setDashPattern([2.0, 1.6])
    p.setPen(dashed)
    p.drawRect(QRectF(2.5, 4, 15, 12))
    p.setPen(pen)
    f = QFont("Segoe UI")
    f.setPixelSize(8)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(2.5, 4, 15, 12), int(Qt.AlignmentFlag.AlignCenter), "Aa")


@icon("searchable")
def _searchable(p, c):
    # page with text lines and a magnifier
    _poly(p, [(3, 2.5), (11.5, 2.5), (14.5, 5.5), (14.5, 9)], close=False)
    _poly(p, [(3, 2.5), (3, 17.5), (9, 17.5)], close=False)
    for y in (7, 10, 13):
        p.drawLine(QPointF(5.5, y), QPointF(9.5 if y > 7 else 11, y))
    p.drawEllipse(QRectF(10, 10, 5.5, 5.5))
    p.drawLine(QPointF(14.6, 14.6), QPointF(17.5, 17.5))


@icon("batch")
def _batch(p, c):
    # a stack of pages (back pages show only their edges) and an arrow
    _poly(p, [(2.5, 11), (2.5, 2.5), (9.5, 2.5)], close=False)
    _poly(p, [(5, 13.5), (5, 5), (12, 5)], close=False)
    p.drawRect(QRectF(7.5, 7.5, 7, 9))
    p.drawLine(QPointF(9.5, 11), QPointF(12.5, 11))
    p.drawLine(QPointF(9.5, 13.5), QPointF(12.5, 13.5))
    _poly(p, [(16, 9.5), (18, 12), (16, 14.5)], close=False)


@icon("comments_panel")
def _comments_panel(p, c):
    # two overlapping speech bubbles
    p.drawRoundedRect(QRectF(2.5, 3, 10, 7), 1.5, 1.5)
    _poly(p, [(5, 10), (5, 12.5), (7.5, 10)], close=False)
    p.drawRoundedRect(QRectF(8, 8.5, 9.5, 6.5), 1.5, 1.5)
    _poly(p, [(14.5, 15), (14.5, 17.5), (12, 15)], close=False)


@icon("text_extract")
def _text_extract(p, c):
    # scanned page -> text lines
    p.drawRect(QRectF(2.5, 3, 7, 9))
    p.drawLine(QPointF(4, 6), QPointF(8, 6))
    p.drawLine(QPointF(4, 8.5), QPointF(8, 8.5))
    p.drawLine(QPointF(10.5, 10), QPointF(13, 12.5))
    _poly(p, [(10.6, 12.6), (13, 12.5), (12.9, 10.1)], close=False)
    for y in (14, 16.5):
        p.drawLine(QPointF(11.5, y), QPointF(17.5, y))


@icon("language")
def _language(p, c):
    # globe
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    p.drawEllipse(QRectF(6.5, 2.5, 7, 15))
    p.drawLine(QPointF(2.5, 10), QPointF(17.5, 10))
    p.drawLine(QPointF(4, 6), QPointF(16, 6))
    p.drawLine(QPointF(4, 14), QPointF(16, 14))


@icon("stamp_custom")
def _stamp_custom(p, c):
    # stamp with a plus
    p.drawRoundedRect(QRectF(2.5, 11, 15, 4), 1, 1)
    p.drawLine(QPointF(4, 17.5), QPointF(16, 17.5))
    _poly(p, [(7.5, 11), (8.5, 7), (11.5, 7), (12.5, 11)], close=False)
    p.drawEllipse(QRectF(7.5, 2, 5, 5))


def _small_letter(p: QPainter, text: str, rect: QRectF, size: float = 6.5) -> None:
    f = QFont("Segoe UI")
    f.setPixelSize(max(1, round(size)))
    f.setBold(True)
    p.setFont(f)
    p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


def _doc_to_doc(p: QPainter, left: str, right: str) -> None:
    """Page with a letter -> arrow -> page with a letter (conversion icons)."""
    p.drawRect(QRectF(2, 4, 6.5, 9))
    p.drawRect(QRectF(11.5, 7, 6.5, 9))
    _small_letter(p, left, QRectF(2, 4, 6.5, 9))
    _small_letter(p, right, QRectF(11.5, 7, 6.5, 9))
    p.drawLine(QPointF(6, 16.5), QPointF(9.5, 16.5))
    _poly(p, [(8, 15), (9.5, 16.5), (8, 18)], close=False)


@icon("pdf_to_pptx")
def _pdf_to_pptx(p, c):
    _doc_to_doc(p, "A", "P")


@icon("pptx_to_pdf")
def _pptx_to_pdf(p, c):
    _doc_to_doc(p, "P", "A")


@icon("pdf_to_word")
def _pdf_to_word(p, c):
    _doc_to_doc(p, "A", "W")


@icon("word_to_pdf")
def _word_to_pdf(p, c):
    _doc_to_doc(p, "W", "A")


@icon("save_copy")
def _save_copy(p, c):
    # two stacked disks
    _poly(p, [(2.5, 12), (2.5, 2.5), (10, 2.5)], close=False)
    _poly(p, [(5.5, 5.5), (14, 5.5), (17, 8.5), (17, 17.5), (5.5, 17.5)])
    p.drawRect(QRectF(8, 5.5, 5.5, 3.5))
    p.drawRoundedRect(QRectF(8, 12.5, 6.5, 5), 1, 1)


@icon("target_size")
def _target_size(p, c):
    # a target with a centre dot
    p.drawEllipse(QRectF(2.5, 2.5, 15, 15))
    p.drawEllipse(QRectF(6, 6, 8, 8))
    p.setBrush(c)
    p.drawEllipse(QRectF(8.8, 8.8, 2.4, 2.4))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _bars(p: QPainter, c: QColor, filled: int) -> None:
    for i in range(3):
        h = 4 + i * 4.5
        r = QRectF(3 + i * 5.5, 17 - h, 3.5, h)
        if i < filled:
            p.setBrush(c)
        p.drawRect(r)
        p.setBrush(Qt.BrushStyle.NoBrush)


@icon("quality_high")
def _quality_high(p, c):
    _bars(p, c, 3)


@icon("quality_balanced")
def _quality_balanced(p, c):
    _bars(p, c, 2)


@icon("quality_smallest")
def _quality_smallest(p, c):
    _bars(p, c, 1)


@icon("preview")
def _preview(p, c):
    # an eye
    path = QPainterPath(QPointF(2, 10))
    path.quadTo(QPointF(10, 2), QPointF(18, 10))
    path.quadTo(QPointF(10, 18), QPointF(2, 10))
    p.drawPath(path)
    p.drawEllipse(QRectF(7.5, 7.5, 5, 5))
