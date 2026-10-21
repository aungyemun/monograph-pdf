"""After Save the window continues with the saved file: what was saved is part of the page, not
also still an overlay (it would be drawn a second time, and replaced text removed again, on the next
Save)."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def window(qtbot, tmp_path: Path):
    pytest.importorskip("PySide6")
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-save-test"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world", fontsize=12)
    page.insert_text((72, 140), "Keep me", fontsize=12)
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.open_path(src)
    yield w, src
    w.close_document(save_session=False)
    w.close()


def test_saving_twice_does_not_draw_shapes_and_pictures_twice(window, tmp_path):
    from PIL import Image

    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox

    w, src = window
    edit = w._edit  # noqa: SLF001
    shape = edit.create_shape(0, Rect(100, 300, 120, 60), "rectangle")
    shape.fill_color = "#ff0000"
    pic = tmp_path / "p.png"
    Image.new("RGB", (40, 20), (0, 0, 255)).save(pic)
    edit.add_image(ImageBox(page_index=0, rect=Rect(300, 300, 80, 40), source_path=str(pic)))
    w.save_document()
    with fitz.open(src) as d:
        fills1 = len([x for x in d[0].get_drawings() if x.get("fill")])
        images1 = len(d[0].get_images())
    assert fills1 == 1 and images1 == 1
    # the saved overlays are part of the page now
    assert not w._edit.shapes and not w._edit.images and not w._edit.objects  # noqa: SLF001
    w._edit.create_text_box(0, Rect(72, 500, 120, 30), text="Second save")  # noqa: SLF001
    w.save_document()
    with fitz.open(src) as d:
        assert len([x for x in d[0].get_drawings() if x.get("fill")]) == 1
        assert len(d[0].get_images()) == 1
        assert "Second save" in d[0].get_text()


def test_replaced_text_survives_a_second_save(window):
    from core.editing.geometry import Rect

    w, src = window
    edit = w._edit  # noqa: SLF001
    span = next(s for s in edit.extract_native_spans(0) if s.text.startswith("Hello"))
    box = edit.begin_native_edit(span, span.text)
    edit.live_set_text(box.object_id, "Goodbye world")
    edit.commit_text_edit(box.object_id, span.text, "Goodbye world")
    w.save_document()
    assert "Goodbye world" in fitz.open(src)[0].get_text()
    assert not w._edit.native_replacements  # noqa: SLF001
    w._edit.create_text_box(0, Rect(72, 500, 120, 30), text="More")  # noqa: SLF001
    w.save_document()
    text = fitz.open(src)[0].get_text()
    assert "Goodbye world" in text and "Keep me" in text and "More" in text and "Hello" not in text
