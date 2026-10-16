"""Hardening added during the 0.2.0 security audit."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from core.editing.geometry import Rect
from core.editing.image_box import SAFE_IMAGE_FORMATS, ImageBox, export_image_box

ROOT = Path(__file__).resolve().parents[2]


def _box(path: Path) -> ImageBox:
    return ImageBox(page_index=0, rect=Rect(0, 0, 10, 10), source_path=str(path))


def test_placed_picture_export_reads_everyday_formats(tmp_path):
    src = tmp_path / "pic.png"
    Image.new("RGB", (8, 8), "red").save(src)
    out = export_image_box(_box(src), tmp_path / "out.png")
    assert out.is_file()


@pytest.mark.parametrize("name,header", [("evil.psd", b"8BPS\x00\x01" + bytes(26)), ("evil.jp2", b"\x00\x00\x00\x0cjP  \r\n\x87\n" + bytes(32))])
def test_placed_picture_export_refuses_rare_decoders(tmp_path, name, header):
    src = tmp_path / name
    src.write_bytes(header)
    with pytest.raises(UnidentifiedImageError):
        export_image_box(_box(src), tmp_path / "out.png")


def test_safe_formats_exclude_rare_readers():
    assert "PSD" not in SAFE_IMAGE_FORMATS and "JPEG2000" not in SAFE_IMAGE_FORMATS and "FITS" not in SAFE_IMAGE_FORMATS


def test_printer_name_with_a_quote_is_not_passed_to_rundll32():
    text = (ROOT / "ui" / "print_dialog.py").read_text(encoding="utf-8")
    guard = text.index("""if '"' in info.printerName():""")
    assert guard < text.index("proc.setNativeArguments(")
