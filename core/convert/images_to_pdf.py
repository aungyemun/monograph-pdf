"""Images → PDF (high confidence)."""

from __future__ import annotations

import io
from pathlib import Path

import fitz

# JPEG segments kept when photo metadata is removed: JFIF header (resolution), ICC colour profile,
# Adobe marker (needed to decode CMYK/YCCK correctly). Everything else in APPn/COM is metadata
# (EXIF with GPS position and camera details, XMP, IPTC, comments) and is dropped. The compressed
# picture data is copied byte for byte.
_KEEP_APP = {0xE0, 0xE2, 0xEE}
_EXIF_TO_ROTATE = {1: 0, 3: 180, 6: 90, 8: 270}


def strip_jpeg_metadata(data: bytes) -> bytes:
    """The JPEG without EXIF/XMP/IPTC/comment segments (lossless; raises ValueError if not a JPEG)."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    out = bytearray(b"\xff\xd8")
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise ValueError("corrupt JPEG marker stream")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: the rest is picture data
            out += data[i:]
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += data[i:i + 2]
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        seg = data[i:i + 2 + length]
        if len(seg) < 2 + length:
            raise ValueError("truncated JPEG segment")
        drop = (0xE0 <= marker <= 0xEF and marker not in _KEEP_APP) or marker == 0xFE
        if not drop:
            out += seg
        i += 2 + length
    raise ValueError("JPEG has no picture data")


def _exif_orientation(path: Path) -> int:
    from PIL import Image

    try:
        with Image.open(path, formats=["JPEG"]) as im:
            return int(im.getexif().get(0x0112, 1) or 1)
    except Exception:  # noqa: BLE001 — unreadable EXIF: treat as upright
        return 1


def _jpeg_page_pdf(path: Path) -> bytes | None:
    """One-page PDF of a JPEG without its metadata, or None to use the default path."""
    raw = path.read_bytes()
    if raw[:2] != b"\xff\xd8":
        return None
    orientation = _exif_orientation(path)
    if orientation not in _EXIF_TO_ROTATE:  # mirrored orientations: re-encode losslessly as PNG
        from PIL import Image, ImageOps

        with Image.open(path, formats=["JPEG"]) as im:
            dpi = im.info.get("dpi")
            upright = ImageOps.exif_transpose(im)
            buf = io.BytesIO()
            upright.save(buf, format="PNG", dpi=dpi) if dpi else upright.save(buf, format="PNG")
        src = fitz.open("png", buf.getvalue())
        try:
            return src.convert_to_pdf()
        finally:
            src.close()
    src = fitz.open("jpeg", strip_jpeg_metadata(raw))
    try:
        pdf = fitz.open("pdf", src.convert_to_pdf())
    finally:
        src.close()
    try:
        if _EXIF_TO_ROTATE[orientation]:
            pdf[0].set_rotation(_EXIF_TO_ROTATE[orientation])
        return pdf.tobytes()
    finally:
        pdf.close()


def images_to_pdf(
    image_paths: list[Path],
    destination: Path,
    *,
    page_margin_pt: float = 0.0,
    strip_metadata: bool = True,
) -> Path:
    """One page per picture, at the picture's own size and resolution.

    ``strip_metadata`` (default): photo metadata embedded in JPEG files — EXIF with GPS position,
    camera and date, XMP, IPTC, comments — is not copied into the PDF; the picture data itself
    is copied unchanged and its EXIF orientation is kept as page rotation. PNG, TIFF and other
    formats are decoded and re-encoded, so their metadata is never copied.
    """
    if not image_paths:
        raise ValueError("No images provided")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        for path in image_paths:
            path = Path(path)
            if not path.is_file():
                raise FileNotFoundError(str(path))
            if strip_metadata:
                page_pdf = _jpeg_page_pdf(path)
                if page_pdf is not None:
                    part = fitz.open("pdf", page_pdf)
                    try:
                        doc.insert_pdf(part)
                    finally:
                        part.close()
                    continue
            img = fitz.open(path.as_posix())
            try:
                # Convert image document to PDF page via insert
                rect = img[0].rect if img.page_count else None
                if rect is None:
                    # pixmap path
                    pix = fitz.Pixmap(path.as_posix())
                    w, h = pix.width, pix.height
                    page = doc.new_page(width=w + 2 * page_margin_pt, height=h + 2 * page_margin_pt)
                    page.insert_image(
                        fitz.Rect(
                            page_margin_pt,
                            page_margin_pt,
                            page_margin_pt + w,
                            page_margin_pt + h,
                        ),
                        pixmap=pix,
                    )
                else:
                    # Prefer convert via PDF insert for JPEG/PNG that open as docs
                    pdfbytes = img.convert_to_pdf()
                    imgpdf = fitz.open("pdf", pdfbytes)
                    try:
                        doc.insert_pdf(imgpdf)
                    finally:
                        imgpdf.close()
            finally:
                img.close()
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return destination
