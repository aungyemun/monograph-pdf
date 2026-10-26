"""Image flip H/V (FEATURE-02)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from core.editing.geometry import Rect
from core.editing.image_box import ImageBox, export_image_box


def test_flip_horizontal_swaps_left_and_right(tmp_path: Path):
    pic = tmp_path / "src.png"
    im = Image.new("RGB", (40, 20), (255, 255, 255))
    for y in range(20):
        im.putpixel((0, y), (255, 0, 0))
        im.putpixel((39, y), (0, 0, 255))
    im.save(pic)

    box = ImageBox(page_index=0, rect=Rect(0, 0, 40, 20), source_path=str(pic), flip_h=True)
    out = tmp_path / "out.png"
    export_image_box(box, out)
    flipped = Image.open(out)
    assert flipped.getpixel((0, 10))[:3] == (0, 0, 255)
    assert flipped.getpixel((39, 10))[:3] == (255, 0, 0)


def test_flip_vertical_swaps_top_and_bottom(tmp_path: Path):
    pic = tmp_path / "src.png"
    im = Image.new("RGB", (20, 40), (255, 255, 255))
    for x in range(20):
        im.putpixel((x, 0), (255, 0, 0))
        im.putpixel((x, 39), (0, 255, 0))
    im.save(pic)

    box = ImageBox(page_index=0, rect=Rect(0, 0, 20, 40), source_path=str(pic), flip_v=True)
    out = tmp_path / "out.png"
    export_image_box(box, out)
    flipped = Image.open(out)
    assert flipped.getpixel((10, 0))[:3] == (0, 255, 0)
    assert flipped.getpixel((10, 39))[:3] == (255, 0, 0)
