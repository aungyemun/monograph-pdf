"""Page-by-page OCR with cancel, bounded memory, and searchable layer bake."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import fitz

from core.document import PdfDocument
from core.editing.geometry import Rect
from core.ocr.engine import OcrEngine, get_ocr_engine
from core.page_info import PageContentKind, PageInfo

ProgressCb = Callable[[int, int, str], None]  # current, total, message
CancelCb = Callable[[], bool]


class OcrCancelled(Exception):
    pass


@dataclass
class OcrWord:
    text: str
    conf: float
    rect: Rect  # PDF points
    low_confidence: bool = False


@dataclass
class OcrPageResult:
    page_index: int
    words: list[OcrWord] = field(default_factory=list)
    full_text: str = ""
    mean_confidence: float = 0.0
    rotation_applied: int = 0
    skipped: bool = False
    skip_reason: str = ""
    image_dpi: int = 200


@dataclass
class OcrOptions:
    languages: str = "eng+jpn"
    dpi: int = 200
    conf_threshold: float = 60.0
    skip_native_text: bool = True
    native_text_char_threshold: int = 40
    apply_orientation: bool = True
    pages: list[int] | None = None  # None = all needing OCR
    region: Rect | None = None  # PDF coords; implies single page in pages[0]
    make_searchable: bool = True
    reconstruct_visual: bool = False  # False = preserve scan visually


@dataclass
class OcrDocumentResult:
    pages: list[OcrPageResult] = field(default_factory=list)
    output_path: Path | None = None


def page_needs_ocr(info: PageInfo, *, char_threshold: int = 40) -> bool:
    if info.content_kind == PageContentKind.IMAGE_SCANNED:
        return True
    if info.content_kind == PageContentKind.EMPTY:
        return False
    if info.char_count < char_threshold and info.has_images:
        return True
    return False


def run_ocr(
    document: PdfDocument,
    options: OcrOptions | None = None,
    *,
    engine: OcrEngine | None = None,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
    destination: Path | None = None,
) -> OcrDocumentResult:
    """
    OCR selected pages/region page-by-page. Never downloads models.
    When make_searchable and destination set, writes a new PDF with invisible text layer
    while preserving the original scan visually (unless reconstruct_visual).
    """
    options = options or OcrOptions()
    engine = engine or get_ocr_engine()
    backend = document._backend  # noqa: SLF001
    src_doc: fitz.Document = backend._doc  # noqa: SLF001

    if options.region is not None:
        if not options.pages:
            raise ValueError("OCR region requires pages=[page_index]")
        page_indices = list(options.pages[:1])
    elif options.pages is not None:
        page_indices = list(options.pages)
    else:
        infos = document.pages()
        page_indices = [
            p.index
            for p in infos
            if (not options.skip_native_text) or page_needs_ocr(p, char_threshold=options.native_text_char_threshold)
        ]

    total = max(1, len(page_indices))
    results: list[OcrPageResult] = []
    # Working copy only if baking searchable output
    out_doc: fitz.Document | None = None
    if options.make_searchable and destination is not None:
        out_doc = fitz.open(document.path)

    try:
        for i, page_index in enumerate(page_indices):
            if cancel and cancel():
                raise OcrCancelled("OCR cancelled by user")
            if progress:
                progress(i, total, f"OCR page {page_index + 1}")

            info = document.page(page_index)
            page_result = OcrPageResult(page_index=page_index, image_dpi=options.dpi)

            if options.skip_native_text and options.region is None and not page_needs_ocr(
                info, char_threshold=options.native_text_char_threshold
            ):
                page_result.skipped = True
                page_result.skip_reason = "native text present — OCR skipped"
                results.append(page_result)
                continue

            page = src_doc.load_page(page_index)
            clip = None
            if options.region is not None:
                r = options.region
                clip = fitz.Rect(r.x, r.y, r.x1, r.y1)

            pix = page.get_pixmap(dpi=options.dpi, clip=clip, alpha=False)
            # Bound memory: process one pixmap at a time (no page pixmap cache)
            import tempfile

            with tempfile.TemporaryDirectory(prefix="monographpdf_ocrpage_") as tmp:
                img_file = Path(tmp) / f"p{page_index}.png"
                pix.save(img_file.as_posix())
                del pix

                rotation = 0
                if options.apply_orientation and options.region is None:
                    try:
                        osd = engine.detect_orientation(img_file)
                        rotation = int(osd.get("rotate") or 0) % 360
                        page_result.rotation_applied = rotation
                        if rotation:
                            # Re-render rotated via pixmap rotate
                            page2 = src_doc.load_page(page_index)
                            mat = fitz.Matrix(options.dpi / 72, options.dpi / 72).prerotate(rotation)
                            pix2 = page2.get_pixmap(matrix=mat, alpha=False)
                            pix2.save(img_file.as_posix())
                            del pix2
                    except Exception:  # noqa: BLE001
                        pass

                tokens = engine.run_tsv(img_file, lang=options.languages)
                scale = 72.0 / float(options.dpi)
                words: list[OcrWord] = []
                confs: list[float] = []
                ox = options.region.x if options.region else 0.0
                oy = options.region.y if options.region else 0.0
                for tok in tokens:
                    confs.append(tok.conf)
                    pdf_rect = Rect(
                        ox + tok.left * scale,
                        oy + tok.top * scale,
                        tok.width * scale,
                        tok.height * scale,
                    )
                    words.append(
                        OcrWord(
                            text=tok.text,
                            conf=tok.conf,
                            rect=pdf_rect,
                            low_confidence=tok.conf < options.conf_threshold,
                        )
                    )
                page_result.words = words
                page_result.full_text = " ".join(w.text for w in words)
                page_result.mean_confidence = sum(confs) / len(confs) if confs else 0.0

                if out_doc is not None and options.make_searchable and words:
                    _apply_searchable_layer(
                        out_doc.load_page(page_index),
                        words,
                        reconstruct_visual=options.reconstruct_visual,
                    )

            results.append(page_result)

        if progress:
            progress(total, total, "OCR complete")

        out_path = None
        if out_doc is not None and destination is not None:
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            out_doc.save(destination.as_posix(), garbage=3, deflate=True)
            out_path = destination
        return OcrDocumentResult(pages=results, output_path=out_path)
    finally:
        if out_doc is not None:
            out_doc.close()


def _font_for_text(text: str) -> str:
    if any(ord(ch) > 0x2E80 for ch in text):
        for name in ("japan", "china-s", "korea", "cjk"):
            return name
    return "helv"


def _apply_searchable_layer(
    page: fitz.Page,
    words: list[OcrWord],
    *,
    reconstruct_visual: bool,
) -> None:
    """Insert invisible text (render mode 3) aligned to OCR boxes; keep scan pixels."""
    for w in words:
        if not w.text.strip():
            continue
        fontsize = max(4.0, w.rect.h * 0.9)
        point = fitz.Point(w.rect.x, w.rect.y1 - max(1.0, fontsize * 0.15))
        fonts = (_font_for_text(w.text), "helv")
        placed = False
        for fontname in fonts:
            try:
                page.insert_text(
                    point,
                    w.text,
                    fontsize=fontsize,
                    fontname=fontname,
                    render_mode=3,  # invisible but selectable/searchable
                )
                placed = True
                break
            except Exception:  # noqa: BLE001
                try:
                    page.insert_textbox(
                        fitz.Rect(w.rect.x, w.rect.y, w.rect.x1, w.rect.y1),
                        w.text,
                        fontsize=max(4.0, min(fontsize, w.rect.h)),
                        fontname=fontname,
                        render_mode=3,
                    )
                    placed = True
                    break
                except Exception:  # noqa: BLE001
                    continue
        if not placed:
            continue
    if reconstruct_visual:
        # Optional future path: redraw glyphs; default preserves original scan.
        pass
