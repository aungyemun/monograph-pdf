"""Page-by-page OCR with cancel, bounded memory, and searchable layer bake."""

from __future__ import annotations

import math
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
    rect: Rect  # display space of the page (as shown, after /Rotate), PDF points
    low_confidence: bool = False
    block: int = 0
    par: int = 0
    line: int = 0
    # Where the word's baseline starts (display space), its reading direction there (degrees,
    # counter-clockwise, 0 = left to right) and its font size in points — for the searchable layer
    baseline: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0
    size: float = 0.0


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
    region: Rect | None = None  # display space of pages[0] (as shown); implies a single page
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
        # The document as it is now (page order, rotation and comments included), not the file on disk
        # A password-protected PDF's searchable copy keeps the same protection (core/security/protection.py)
        from core.security.protection import working_copy

        out_doc = working_copy(document)

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
            # Rendering, OCR and placement all work in the page's display space (as shown, after
            # /Rotate): the picture MuPDF renders is in that space and so is ``region``. A word's pixel
            # box is mapped back through the render matrix (including a turn detected by orientation
            # analysis), so its rectangle is right on turned pages and for sideways scans.
            area = page.rect
            if options.region is not None:
                r = options.region
                area = fitz.Rect(r.x, r.y, r.x1, r.y1) & page.rect
                if area.is_empty or area.width < 2 or area.height < 2:
                    page_result.skipped = True
                    page_result.skip_reason = "the selected area is outside the page"
                    results.append(page_result)
                    continue
            zoom = options.dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, clip=area, alpha=False)
            # Bound memory: process one pixmap at a time (no page pixmap cache)
            import tempfile

            with tempfile.TemporaryDirectory(prefix="monographpdf_ocrpage_") as tmp:
                img_file = Path(tmp) / f"p{page_index}.png"
                pix.save(img_file.as_posix())
                origin = fitz.Point(pix.x, pix.y)
                del pix

                rotation = 0
                if options.apply_orientation and options.region is None:
                    try:
                        osd = engine.detect_orientation(img_file)
                        rotation = int(osd.get("rotate") or 0) % 360
                        page_result.rotation_applied = rotation
                        if rotation:
                            # Re-render turned so the text is upright for recognition. Tesseract's
                            # "Rotate: n" is the clockwise turn that makes the text upright; a positive
                            # MuPDF matrix angle turns the other way, hence -n.
                            matrix = fitz.Matrix(zoom, zoom).prerotate(-rotation)
                            pix2 = page.get_pixmap(matrix=matrix, clip=area, alpha=False)
                            pix2.save(img_file.as_posix())
                            origin = fitz.Point(pix2.x, pix2.y)
                            del pix2
                    except Exception:  # noqa: BLE001
                        pass

                tessdata = None
                if any(c not in ("eng", "jpn", "osd") for c in options.languages.split("+")):
                    from core.ocr.language_packs import tessdata_for

                    tessdata = tessdata_for(options.languages)
                tokens = engine.run_tsv(img_file, lang=options.languages, tessdata=tessdata)
                inverse = ~matrix
                words: list[OcrWord] = []
                confs: list[float] = []
                for tok in tokens:
                    confs.append(tok.conf)
                    box = fitz.Rect(tok.left + origin.x, tok.top + origin.y,
                                    tok.left + tok.width + origin.x, tok.top + tok.height + origin.y) * inverse
                    box.normalize()
                    # baseline start and direction, from the upright picture back to display space
                    start = fitz.Point(tok.left + origin.x, tok.top + tok.height * 0.82 + origin.y) * inverse
                    ahead = fitz.Point(tok.left + tok.width + origin.x, tok.top + tok.height * 0.82 + origin.y) * inverse
                    angle = math.degrees(math.atan2(-(ahead.y - start.y), ahead.x - start.x)) % 360.0
                    words.append(
                        OcrWord(
                            text=tok.text,
                            conf=tok.conf,
                            rect=Rect(box.x0, box.y0, box.width, box.height),
                            low_confidence=tok.conf < options.conf_threshold,
                            block=tok.block_num,
                            par=tok.par_num,
                            line=tok.line_num,
                            baseline=(start.x, start.y),
                            angle=angle,
                            size=max(4.0, tok.height / zoom * 0.9),
                        )
                    )
                page_result.words = words
                from core.ocr.text_export import page_text

                page_result.full_text = page_text(words)
                page_result.mean_confidence = sum(confs) / len(confs) if confs else 0.0

                if out_doc is not None and options.make_searchable and words:
                    target = out_doc.load_page(page_index)
                    if has_invisible_text(target):
                        page_result.skip_reason = "already has a searchable text layer — not added again"
                    else:
                        _apply_searchable_layer(
                            target,
                            words,
                            reconstruct_visual=options.reconstruct_visual,
                            text_turn=rotation,
                        )

            results.append(page_result)

        if progress:
            progress(total, total, "OCR complete")

        out_path = None
        if out_doc is not None and destination is not None:
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            from core.security.protection import save_copy

            save_copy(out_doc, destination)
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


def has_invisible_text(page: fitz.Page) -> bool:
    """True if the page already has invisible (OCR) text, so a second layer is not added."""
    try:
        return any(span.get("type") == 3 for span in page.get_texttrace())
    except Exception:  # noqa: BLE001
        return False


def _apply_searchable_layer(
    page: fitz.Page,
    words: list[OcrWord],
    *,
    reconstruct_visual: bool,
    text_turn: int = 0,
) -> None:
    """Insert invisible text (render mode 3) on each recognised word, keeping the scan's pixels.

    Words are in display space; each is written at its baseline in the page's own (unrotated) space,
    running in its reading direction, so selection and search match the picture on turned pages and
    on sideways scans."""
    from core.page_space import point_to_page

    for w in words:
        if not w.text.strip():
            continue
        start = point_to_page(page, *w.baseline)
        ahead = point_to_page(page, w.baseline[0] + math.cos(math.radians(w.angle)),
                              w.baseline[1] - math.sin(math.radians(w.angle)))
        angle = math.degrees(math.atan2(-(ahead.y - start.y), ahead.x - start.x)) % 360.0
        rotate = int(round(angle / 90.0)) % 4 * 90
        fontsize = w.size or max(4.0, w.rect.h * 0.9)
        for fontname in (_font_for_text(w.text), "helv"):
            try:
                page.insert_text(start, w.text, fontsize=fontsize, fontname=fontname, render_mode=3, rotate=rotate)
                break
            except Exception:  # noqa: BLE001
                continue
    _ = (reconstruct_visual, text_turn)  # reconstruct_visual: reserved; the scan is always kept
