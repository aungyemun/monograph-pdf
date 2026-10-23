"""Smooth dragging: a move repaints only where the moved box was and is (no trails left behind),
text layout and pictures are cached, and bundled fonts are registered with Qt once."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-drag-perf"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 900)
    w.show()
    src = tmp_path / "page.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Drag test page", fontsize=14)
    doc.save(str(src))
    doc.close()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _move(w, obj, steps, qtbot):
    """Press on ``obj``, then held-button moves; returns the repaint region of every move."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point

    inner = w._canvas._canvas  # noqa: SLF001
    regions = []
    real_update = inner.update

    def spy(*args):
        if args:
            regions.append(args[0])
        return real_update(*args)

    inner.update = spy
    left = Qt.MouseButton.LeftButton

    def send(kind, pos, buttons, button):
        p = QPointF(pos)
        QApplication.sendEvent(inner, QMouseEvent(kind, p, inner.mapToGlobal(p), button, buttons,
                                                  Qt.KeyboardModifier.NoModifier))

    c = inner.pdf_to_widget(obj.page_index, Point(obj.rect.cx, obj.rect.cy))
    send(QEvent.Type.MouseButtonPress, c, left, left)
    frames = []
    for dx, dy in steps:
        before = inner.pdf_rect_to_widget(obj.page_index, obj.rect)
        regions.clear()
        send(QEvent.Type.MouseMove, QPoint(c.x() + dx, c.y() + dy), left, Qt.MouseButton.NoButton)
        after = inner.pdf_rect_to_widget(obj.page_index, obj.rect)
        frames.append((before, after, list(regions)))
    send(QEvent.Type.MouseButtonRelease, QPoint(c.x() + steps[-1][0], c.y() + steps[-1][1]),
         Qt.MouseButton.NoButton, left)
    inner.update = real_update
    qtbot.wait(10)
    return frames


@pytest.mark.parametrize("kind", ["text", "image", "shape"])
def test_each_move_repaints_the_old_and_the_new_place(win, qtbot, kind, tmp_path):
    from PySide6.QtGui import QColor, QImage, QRegion

    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox

    edit = win._edit  # noqa: SLF001
    if kind == "text":
        obj = edit.create_text_box(0, Rect(100, 300, 160, 40), text="Moving box")
    elif kind == "image":
        png = tmp_path / "pic.png"
        img = QImage(40, 30, QImage.Format.Format_RGB32)
        img.fill(QColor("#2563eb"))
        assert img.save(str(png))
        obj = ImageBox(page_index=0, rect=Rect(100, 300, 120, 90), source_path=str(png))
        edit.add_image(obj)
    else:
        obj = edit.create_shape(0, Rect(100, 300, 120, 80), "rectangle")
    edit.select([obj.object_id])
    frames = _move(win, obj, [(4, 0), (30, 12), (31, 13), (-50, 60), (120, -40)], qtbot)
    assert frames
    for before, after, regions in frames:
        assert regions, "a move must repaint something"
        region = QRegion()
        for r in regions:
            region = region.united(r if isinstance(r, QRegion) else QRegion(r))
        # both the place it left (no trail) and the place it moved to, with the handles
        for rect in (before, after):
            grown = rect.adjusted(-6, -6, 6, 6)
            assert region.intersected(QRegion(grown)) == QRegion(grown), (rect, region.boundingRect())
        # but not the whole page
        page = win._canvas._canvas._layouts[0]  # noqa: SLF001
        assert region.boundingRect().width() * region.boundingRect().height() < page.width() * page.height() / 2 \
            or edit.guides


def test_snap_guides_are_repainted_when_they_appear_and_vanish(win, qtbot):
    from PySide6.QtGui import QRegion

    from core.editing.geometry import Rect

    edit = win._edit  # noqa: SLF001
    edit.create_text_box(0, Rect(100, 200, 160, 40), text="anchor")
    moving = edit.create_text_box(0, Rect(300, 400, 160, 40), text="moving")
    edit.select([moving.object_id])
    inner = win._canvas._canvas  # noqa: SLF001
    seen_guides = []
    frames = _move(win, moving, [(-150, 3), (-199, 5), (-120, 60)], qtbot)
    for _b, _a, regions in frames:
        seen_guides.append(bool(edit.guides))
    rects = inner._live_dirty_rects([moving.object_id])  # noqa: SLF001
    region = QRegion()
    for r in rects:
        region = region.united(QRegion(r))
    for g in edit.guides:  # any guide shown now lies inside what the next move repaints
        layout = inner._layouts[0]  # noqa: SLF001
        sx, sy = inner._scale(0)  # noqa: SLF001
        if g.orientation == "v":
            x = layout.left() + int(g.position * sx)
            assert region.contains(QRegion(x, layout.top() + 5, 1, 1).boundingRect().topLeft())
        else:
            y = layout.top() + int(g.position * sy)
            assert region.contains(QRegion(layout.left() + 5, y, 1, 1).boundingRect().topLeft())


def test_text_layout_is_cached_but_follows_changes():
    from core.editing.geometry import Rect
    from core.editing.text_box import TextBox
    from core.editing.text_layout import layout_text_box

    box = TextBox(page_index=0, rect=Rect(10, 10, 120, 40), text="Hello world")
    first = layout_text_box(box)
    box.rect = Rect(300, 500, 120, 40)  # moved only
    assert layout_text_box(box) is first
    box.text = "Hello world, longer text that wraps onto another line"
    assert layout_text_box(box) is not first
    box.rect = Rect(300, 500, 400, 40)  # wider: wraps differently
    again = layout_text_box(box)
    assert len(again.lines) <= len(layout_text_box(TextBox(page_index=0, rect=Rect(0, 0, 120, 40),
                                                           text=box.text)).lines)


def test_bundled_fonts_are_registered_with_qt_once(qtbot, monkeypatch):
    from PySide6.QtGui import QFontDatabase

    from core.editing import font_resolver

    calls = []
    monkeypatch.setattr(font_resolver, "_QT_REGISTERED", set())
    monkeypatch.setattr(QFontDatabase, "addApplicationFont", staticmethod(lambda path: calls.append(path) or 1))
    for _ in range(5):
        font_resolver._register_bundled_with_qt()  # noqa: SLF001
    files = set(font_resolver._bundled_family_map().values())  # noqa: SLF001  (several names per file)
    assert sorted(calls) == sorted(files)  # each file once, however often text is painted


def test_pictures_are_decoded_once(win, tmp_path, monkeypatch):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage

    png = tmp_path / "big.png"
    img = QImage(3000, 2000, QImage.Format.Format_RGB32)
    img.fill(QColor("#10b981"))
    assert img.save(str(png))
    inner = win._canvas._canvas  # noqa: SLF001
    a = inner._image_pixmap(str(png), QSize(300, 200))  # noqa: SLF001
    b = inner._image_pixmap(str(png), QSize(300, 200))  # noqa: SLF001
    assert a is b and a.width() <= 2048
    assert inner._image_pixmap(str(tmp_path / "missing.png"), QSize(10, 10)) is None  # noqa: SLF001


def test_moved_objects_stay_on_the_page(win):
    """Past the page edge a picture would be cut off on screen, in other PDF apps and on paper."""
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox

    edit = win._edit  # noqa: SLF001
    page = edit.pdf.page(0)
    img = ImageBox(page_index=0, rect=Rect(400, 300, 150, 100), source_path="")
    edit.add_image(img)
    edit.live_translate([img.object_id], 300, 0, snap=False, notify=False)
    assert img.rect.x1 == pytest.approx(page.display_width_pt) and img.rect.y == 300
    edit.live_translate([img.object_id], -900, -900, snap=False, notify=False)
    assert (img.rect.x, img.rect.y) == (0, 0)
    # several objects keep their arrangement: the move stops when the first one reaches the edge
    box = edit.create_text_box(0, Rect(100, 500, 100, 30), text="x")
    img.rect = Rect(300, 500, 150, 100)
    edit.live_translate([img.object_id, box.object_id], 500, 0, snap=False, notify=False)
    assert img.rect.x1 == pytest.approx(page.display_width_pt) and box.rect.x == pytest.approx(100 + (img.rect.x - 300))
    # arrow-key nudges stop at the edge as well
    box.rect = Rect(page.display_width_pt - 101, 500, 100, 30)
    edit.select([box.object_id])
    edit.nudge_selection(10, 0)
    assert box.rect.x1 == pytest.approx(page.display_width_pt)
