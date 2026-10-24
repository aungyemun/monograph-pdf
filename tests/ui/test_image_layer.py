"""Picture placement: in front of the page, or behind its text (the text shows through), on screen and in the saved PDF."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


def _doc_with_text(path, *, white_background: bool = False):
    d = fitz.open()
    page = d.new_page(width=400, height=300)
    if white_background:  # many PDFs paint the whole page white first
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    page.insert_text((40, 120), "WWWWWWWWWWWWWW", fontsize=36, color=(0, 0, 0))
    d.save(path.as_posix())
    d.close()


def _blue_png(path):
    from PIL import Image

    Image.new("RGB", (200, 100), (40, 90, 220)).save(path)


def _dark_share(page, rect, *, dark=60) -> float:
    pix = page.get_pixmap(clip=rect, dpi=72)
    n = pix.width * pix.height
    s = pix.samples
    blackish = sum(1 for i in range(0, len(s), pix.n) if max(s[i], s[i + 1], s[i + 2]) < dark)
    return blackish / max(1, n)


def test_layer_round_trips_and_copies():
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox

    b = ImageBox(page_index=0, rect=Rect(0, 0, 10, 10), source_path="x.png", layer="behind")
    assert ImageBox.from_dict(b.to_dict()).layer == "behind"
    assert b.copy().layer == "behind"
    assert ImageBox.from_dict({**b.to_dict(), "layer": "weird"}).layer == "front"
    old = b.to_dict()
    old.pop("layer")
    assert ImageBox.from_dict(old).layer == "front"  # sessions saved before 0.5.0


@pytest.mark.parametrize("white_background", [False, True])
def test_saved_pdf_front_covers_text_behind_shows_text(tmp_path, white_background):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox
    from engines.bake_edits import bake_into_document

    src = tmp_path / "in.pdf"
    _doc_with_text(src, white_background=white_background)
    pic = tmp_path / "b.png"
    _blue_png(pic)
    results = {}
    for layer in ("front", "behind"):
        doc = open_document(src)
        edit = EditableDocument(doc)
        edit.add_image(ImageBox(page_index=0, rect=Rect(30, 60, 280, 140), source_path=str(pic), layer=layer))
        out = tmp_path / f"{layer}.pdf"
        bake_into_document(edit, out)
        doc.close()
        with fitz.open(out) as d:
            page = d[0]
            area = fitz.Rect(50, 92, 290, 128)
            results[layer] = _dark_share(page, area)
            assert "WWWW" in page.get_text()  # the text stays text either way
            if layer == "behind":
                blue = page.get_pixmap(clip=fitz.Rect(100, 160, 140, 170), dpi=72)
                r, g, b = blue.samples[0:3]
                assert b > 180 and r < 90  # the picture is there, in its own colour
    assert results["front"] < 0.02, results  # the picture hides the text
    assert results["behind"] > 0.15, results  # the text shows through the picture


def test_canvas_and_menu(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor

    from core import user_prefs
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-image-layer"])
    src = tmp_path / "in.pdf"
    _doc_with_text(src)
    pic = tmp_path / "b.png"
    _blue_png(pic)
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    assert win.open_path(src)
    edit = win._edit  # noqa: SLF001
    box = ImageBox(page_index=0, rect=Rect(30, 60, 280, 140), source_path=str(pic))
    edit.add_image(box)
    edit.selection = [box.object_id]
    win._sync_selection_actions()  # noqa: SLF001
    assert win.act_image_front.isEnabled() and win.act_image_front.isChecked()
    canvas = win._canvas._canvas  # noqa: SLF001
    qtbot.waitUntil(lambda: len(canvas._cache) > 0, timeout=3000)  # noqa: SLF001

    def text_pixels_dark() -> float:
        canvas.update()
        img = canvas.grab().toImage()
        k = img.devicePixelRatio() or 1.0  # HiDPI displays: the picture has more pixels than the widget
        wr = canvas.pdf_rect_to_widget(0, Rect(50, 92, 240, 36))
        dark = total = 0
        for x in range(wr.left(), wr.right(), 3):
            for y in range(wr.top(), wr.bottom(), 3):
                c = QColor(img.pixel(int(x * k), int(y * k)))
                total += 1
                dark += max(c.red(), c.green(), c.blue()) < 60
        return dark / max(1, total)

    canvas.update()
    qtbot.wait(50)
    assert text_pixels_dark() < 0.02
    win.act_image_behind.trigger()
    assert box.layer == "behind" and win.act_image_behind.isChecked()
    assert text_pixels_dark() > 0.15
    edit.undo()
    assert box.layer == "front"
    win.close_document(save_session=False)
    win.close()


def test_a_stretched_picture_is_saved_stretched_as_on_screen(tmp_path):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox
    from engines.bake_edits import bake_into_document

    src = tmp_path / "in.pdf"
    d = fitz.open()
    d.new_page(width=400, height=300)
    d.save(src.as_posix())
    d.close()
    pic = tmp_path / "b.png"
    _blue_png(pic)  # 2:1
    doc = open_document(src)
    edit = EditableDocument(doc)
    edit.add_image(ImageBox(page_index=0, rect=Rect(20, 20, 360, 60), source_path=str(pic), lock_aspect=False))
    out = tmp_path / "o.pdf"
    bake_into_document(edit, out)
    doc.close()
    with fitz.open(out) as d2:
        info = d2[0].get_image_info()
        assert info
        x0, y0, x1, y1 = info[0]["bbox"]
        assert (x1 - x0) == pytest.approx(360, abs=1) and (y1 - y0) == pytest.approx(60, abs=1)
