"""Images → PDF (high confidence)."""

from __future__ import annotations

from pathlib import Path

import fitz


def images_to_pdf(
    image_paths: list[Path],
    destination: Path,
    *,
    page_margin_pt: float = 0.0,
) -> Path:
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
