"""PDF pages → PNG / JPEG / TIFF (high confidence)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import PdfDocument
from core.safe_paths import safe_child

SUPPORTED_IMAGE_FORMATS = ("png", "jpeg", "jpg", "tiff", "tif")


def pdf_pages_to_images(
    document: PdfDocument,
    output_dir: Path,
    *,
    pages: list[int] | None = None,
    fmt: str = "png",
    dpi: int = 150,
    jpeg_quality: int = 85,
    name_prefix: str = "page",
) -> list[Path]:
    fmt = fmt.lower().lstrip(".")
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt == "tif":
        fmt = "tiff"
    if fmt not in ("png", "jpeg", "tiff"):
        raise ValueError(f"Unsupported image format: {fmt} (supported: png, jpeg, tiff)")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = document._backend  # noqa: SLF001
    doc: fitz.Document = backend._doc  # noqa: SLF001
    indices = list(range(doc.page_count)) if pages is None else list(pages)
    written: list[Path] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for i in indices:
        if i < 0 or i >= doc.page_count:
            raise IndexError(f"page out of range: {i}")
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        # Never replaces a file already in the folder (``name (2).png`` instead)
        out = safe_child(output_dir, f"{name_prefix}_{i + 1:04d}.{('jpg' if fmt == 'jpeg' else fmt)}")
        if fmt == "png":
            pix.save(out.as_posix())
        elif fmt == "jpeg":
            # MuPDF jpg path
            pix.save(out.as_posix(), jpg_quality=max(1, min(100, jpeg_quality)))
        else:
            # TIFF via Pillow for broad codec support
            from PIL import Image
            import io

            png = pix.tobytes("png")
            im = Image.open(io.BytesIO(png))
            im.save(out.as_posix(), format="TIFF")
        written.append(out)
    return written
