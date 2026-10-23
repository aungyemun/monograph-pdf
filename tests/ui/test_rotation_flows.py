"""Page rotation in every direction keeps pictures and text boxes on the page, and undo / redo
stay correct across an inserted blank page (the flow behind a real report)."""

from __future__ import annotations

import os
from types import SimpleNamespace

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")


def _inside(r, w, h, shown_w=None, shown_h=None):
    sw = r.w if shown_w is None else shown_w
    sh = r.h if shown_h is None else shown_h
    return (r.cx - sw / 2 >= -0.01 and r.cx + sw / 2 <= w + 0.01
            and r.cy - sh / 2 >= -0.01 and r.cy + sh / 2 <= h + 0.01)


@pytest.mark.parametrize("degrees", [90, 180, 270])
def test_turned_page_keeps_boxes_and_pictures_on_it(degrees):
    from core.editing.geometry import Rect
    from core.organize.rotate_command import turn_overlays

    w, h = 595.0, 842.0
    # a wide text box across the top and a wide picture at the right edge of a portrait page
    box = SimpleNamespace(page_index=0, rect=Rect(20, 30, 560, 40))
    img = SimpleNamespace(page_index=0, rect=Rect(400, 700, 190, 80), rotation=0.0)
    edit = SimpleNamespace(objects={"b": box}, images={"i": img}, shapes={}, fields={}, tables={},
                           _native_replacements={})
    turn_overlays(edit, 0, w, h, degrees)
    nw, nh = (h, w) if degrees in (90, 270) else (w, h)
    assert _inside(box.rect, nw, nh)
    quarter = round(img.rotation / 90) % 2 == 1
    assert _inside(img.rect, nw, nh, img.rect.h if quarter else img.rect.w, img.rect.w if quarter else img.rect.h)
    assert img.rotation == degrees % 360


def test_rotating_back_restores_the_original_place():
    from core.editing.geometry import Rect
    from core.organize.rotate_command import turn_overlays

    img = SimpleNamespace(page_index=0, rect=Rect(470, 90, 110, 110), rotation=0.0)
    edit = SimpleNamespace(objects={}, images={"i": img}, shapes={}, fields={}, tables={}, _native_replacements={})
    turn_overlays(edit, 0, 595, 842, 270)  # counterclockwise
    turn_overlays(edit, 0, 842, 595, 90)  # clockwise again
    assert img.rect.as_tuple() == pytest.approx((470, 90, 110, 110)) and img.rotation == 0


def test_insert_blank_then_rotate_counterclockwise_with_undo_and_redo(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from core import user_prefs
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    errors = []
    for name in ("warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: errors.append(a) or QMessageBox.StandardButton.Ok))
    create_application(["monograph-pdf-rotation-flows"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(w, "report_error", lambda *a, **k: errors.append(a))
    src = tmp_path / "two.pdf"
    d = fitz.open()
    for n in range(2):
        d.new_page(width=595, height=842).insert_text((72, 100), f"Page {n + 1}", fontsize=20)
    d.save(src)
    d.close()
    assert w.open_path(src)
    img = ImageBox(page_index=0, rect=Rect(470, 90, 110, 110), source_path="")
    w._edit.add_image(img)  # noqa: SLF001

    def rot():
        doc = w._document._backend._doc  # noqa: SLF001
        return [doc.load_page(i).rotation for i in range(doc.page_count)]

    def image():
        return w._edit.images[img.object_id]  # noqa: SLF001  (undo of a page change re-creates objects)

    w._canvas.go_to_page(0)  # noqa: SLF001
    w._insert_blank_page()  # noqa: SLF001
    w._left.thumbs.setCurrentRow(0)  # noqa: SLF001
    w.act_rotate_ccw.trigger()
    assert rot() == [270, 0, 0] and image().rotation == 270
    w._left.thumbs.clearSelection()  # noqa: SLF001
    w._left.thumbs.item(2).setSelected(True)  # noqa: SLF001
    w.act_rotate_ccw.trigger()
    assert rot() == [270, 0, 270]
    turned = image().rect.as_tuple()
    for _ in range(3):
        w._undo()  # noqa: SLF001
    assert rot() == [0, 0] and image().rect.as_tuple() == pytest.approx((470, 90, 110, 110))
    for _ in range(3):
        w._redo()  # noqa: SLF001
    assert rot() == [270, 0, 270] and image().rect.as_tuple() == pytest.approx(turned)
    assert errors == []
    w._edit.dirty = False  # noqa: SLF001
    w.close_document(save_session=False)
    w.close()
