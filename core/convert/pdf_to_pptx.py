"""PDF → PPTX (best-effort: page images as slides)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

from core.convert.pdf_to_images import pdf_pages_to_images
from core.document import PdfDocument

FIDELITY_NOTICE = (
    "Best-effort: each PDF page is placed as a full-slide image. "
    "Text is not editable as native PowerPoint shapes."
)


def pdf_to_pptx(
    document: PdfDocument,
    destination: Path,
    *,
    pages: list[int] | None = None,
    dpi: int = 120,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    # Prefer blank layout
    blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]

    with tempfile.TemporaryDirectory(prefix="monographpdf_pptx_") as tmp:
        images = pdf_pages_to_images(
            document,
            Path(tmp),
            pages=pages,
            fmt="png",
            dpi=dpi,
            name_prefix="slide",
        )
        from PIL import Image

        for img_path in images:
            with Image.open(img_path) as im:
                w_px, h_px = im.size
            slide_w = int(w_px / dpi * 914400)
            slide_h = int(h_px / dpi * 914400)
            prs.slide_width = slide_w
            prs.slide_height = slide_h
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(
                str(img_path), Emu(0), Emu(0), width=Emu(slide_w), height=Emu(slide_h)
            )
        try:
            prs.core_properties.comments = FIDELITY_NOTICE
        except Exception:  # noqa: BLE001
            pass
        prs.save(destination.as_posix())
    return destination
