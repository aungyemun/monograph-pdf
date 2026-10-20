"""Images → PDF: photo metadata (EXIF/GPS, XMP, comments) is not copied; pictures stay
pixel-identical and upright for every EXIF orientation."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageOps

from core.convert.images_to_pdf import images_to_pdf, strip_jpeg_metadata

GPS = {1: "N", 2: (35.0, 41.0, 0.0), 3: "E", 4: (139.0, 41.0, 0.0)}


def _photo(path: Path, orientation: int, *, icc: bytes | None = None, comment: bytes | None = None) -> Path:
    im = Image.new("RGB", (240, 120), (255, 255, 255))
    for x in range(60):  # red band on the left of the stored pixels, blue square top-right
        for y in range(120):
            im.putpixel((x, y), (255, 0, 0))
    for x in range(200, 240):
        for y in range(0, 40):
            im.putpixel((x, y), (0, 0, 255))
    ex = Image.Exif()
    ex[0x0112] = orientation
    ex[0x010F] = "PhoneMakerXYZ"
    ex[0x8825] = GPS
    kw = {"exif": ex.tobytes(), "dpi": (72, 72), "quality": 95}
    if icc:
        kw["icc_profile"] = icc
    if comment:
        kw["comment"] = comment
    im.save(path, **kw)
    return path


def _all_bytes(path: Path) -> bytes:
    with fitz.open(path) as d:
        parts = [path.read_bytes()]
        for x in range(1, d.xref_length()):
            if d.xref_is_stream(x):
                parts.append(d.xref_stream_raw(x) or b"")
        return b"".join(parts)


def _colour_at(pix: fitz.Pixmap, fx: float, fy: float) -> str:
    r, g, b = pix.pixel(int(fx * (pix.width - 1)), int(fy * (pix.height - 1)))[:3]
    return "red" if r > 200 and g < 80 and b < 80 else "blue" if b > 200 and r < 80 else "white" if min(r, g, b) > 200 else "?"


@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_every_exif_orientation_is_upright_and_metadata_is_gone(tmp_path, orientation):
    src = _photo(tmp_path / f"o{orientation}.jpg", orientation, comment=b"SECRETCOMMENT")
    out = images_to_pdf([src], tmp_path / "out.pdf")
    with Image.open(src) as im:
        ref = ImageOps.exif_transpose(im).convert("RGB")
    buf = io.BytesIO()
    ref.save(buf, format="PNG")
    ref_pix = fitz.Pixmap(buf.getvalue())
    with fitz.open(out) as d:
        page = d[0]
        assert (round(page.rect.width), round(page.rect.height)) == ref.size  # 72 dpi: 1 px = 1 pt
        pix = page.get_pixmap(dpi=72, alpha=False)
        for fx, fy in ((0.05, 0.5), (0.5, 0.05), (0.95, 0.5), (0.5, 0.95), (0.9, 0.1), (0.1, 0.9)):
            assert _colour_at(pix, fx, fy) == _colour_at(ref_pix, fx, fy), (orientation, fx, fy)
    blob = _all_bytes(out)
    for secret in (b"PhoneMakerXYZ", b"SECRETCOMMENT", b"Exif\x00\x00"):
        assert secret not in blob, (orientation, secret)


def test_picture_data_is_copied_unchanged(tmp_path):
    src = _photo(tmp_path / "p.jpg", 6)
    out = images_to_pdf([src], tmp_path / "out.pdf")
    expected = strip_jpeg_metadata(src.read_bytes())
    with fitz.open(out) as d:
        xref = d[0].get_images()[0][0]
        assert d.xref_stream_raw(xref) == expected  # DCT data byte for byte, no re-encoding
        assert d[0].rotation == 90


def test_icc_profile_is_kept(tmp_path):
    from PIL import ImageCms

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = _photo(tmp_path / "icc.jpg", 1, icc=icc)
    stripped = strip_jpeg_metadata(src.read_bytes())
    with Image.open(io.BytesIO(stripped)) as im:
        assert im.info.get("icc_profile") == icc
        assert not im.getexif()


def test_opt_out_keeps_the_previous_behaviour(tmp_path):
    src = _photo(tmp_path / "p.jpg", 1)
    out = images_to_pdf([src], tmp_path / "out.pdf", strip_metadata=False)
    assert b"PhoneMakerXYZ" in _all_bytes(out)


def test_non_jpeg_and_mixed_inputs_keep_order_and_size(tmp_path):
    png = tmp_path / "a.png"
    Image.new("RGB", (100, 50), (0, 128, 0)).save(png, dpi=(72, 72))
    jpg = _photo(tmp_path / "b.jpg", 8)
    out = images_to_pdf([png, jpg, png], tmp_path / "out.pdf")
    with fitz.open(out) as d:
        assert d.page_count == 3
        assert [(round(p.rect.width), round(p.rect.height)) for p in d] == [(100, 50), (120, 240), (100, 50)]


def test_broken_jpeg_is_refused_cleanly(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\xff\xd8\xff\xe1\x00\x10Exif")  # truncated
    with pytest.raises(Exception):
        images_to_pdf([bad], tmp_path / "out.pdf")
    assert not (tmp_path / "out.pdf").exists()
