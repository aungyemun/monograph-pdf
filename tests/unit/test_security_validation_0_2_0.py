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


def _blank_pdf(path: Path) -> None:
    import fitz

    d = fitz.open()
    d.new_page(width=200, height=200)
    d.save(path)
    d.close()


def test_saving_a_placed_picture_uses_only_the_safe_decoders(tmp_path, monkeypatch):
    """The save step opens a placed picture (with opacity / crop / rotation) with the safe formats only."""
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_into_document

    pdf_path = tmp_path / "base.pdf"
    _blank_pdf(pdf_path)
    png = tmp_path / "pic.png"
    Image.new("RGB", (8, 8), "red").save(png)

    opened = []
    real_open = Image.open

    def spy(*args, **kwargs):
        opened.append(kwargs.get("formats"))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", spy)
    pdf = open_document(pdf_path)
    model = EditableDocument(pdf)
    model.add_image(ImageBox(page_index=0, rect=Rect(10, 10, 60, 60), source_path=str(png), opacity=0.5))
    out = tmp_path / "out.pdf"
    bake_into_document(model, out)
    pdf.close()
    assert out.is_file()
    assert opened and all(f == SAFE_IMAGE_FORMATS for f in opened), opened


def test_saving_a_renamed_psd_picture_does_not_decode_it(tmp_path):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_into_document

    pdf_path = tmp_path / "base.pdf"
    _blank_pdf(pdf_path)
    fake = tmp_path / "evil.png"
    fake.write_bytes(b"8BPS\x00\x01" + bytes(64))  # a PSD header carrying a picture extension
    pdf = open_document(pdf_path)
    model = EditableDocument(pdf)
    model.add_image(ImageBox(page_index=0, rect=Rect(10, 10, 60, 60), source_path=str(fake), opacity=0.5))
    out = tmp_path / "out.pdf"
    bake_into_document(model, out)  # must finish without decoding the PSD and without crashing
    pdf.close()
    assert out.is_file()
