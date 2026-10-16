"""Make PDF Editable — non-destructive analysis before any OCR/conversion."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.document import PdfDocument
from core.forms.detect import detect_field_candidates
from core.forms.fields import FieldType
from core.ocr.pipeline import page_needs_ocr
from core.page_info import PageContentKind
from core.tables.detect import detect_tables


@dataclass
class PageAnalysis:
    page_index: int
    kind: str
    has_native_text: bool
    char_count: int
    image_count: int
    needs_ocr: bool
    form_widget_count: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class EditableAnalysis:
    path: str
    page_count: int
    pages: list[PageAnalysis]
    native_text_pages: int
    scanned_pages: int
    mixed_pages: int
    empty_pages: int
    pages_needing_ocr: list[int]
    acroform_fields: int
    field_candidates: int
    table_candidates: int
    has_images: bool
    summary_lines: list[str]
    destructive_warning: str = (
        "No conversion has been applied. Review this summary before OCR or flatten."
    )


def analyze_for_editable(document: PdfDocument) -> EditableAnalysis:
    """
    Inspect document structure without modifying it.
    Does not OCR; only reports where OCR would be required.
    """
    pages_info = document.pages()
    meta = document.metadata()
    backend_doc = document._backend._doc  # noqa: SLF001

    # Existing AcroForm widgets
    acro_count = 0
    widgets_per_page: dict[int, int] = {}
    try:
        for i in range(document.page_count):
            page = backend_doc.load_page(i)
            n = len(list(page.widgets() or []))
            widgets_per_page[i] = n
            acro_count += n
    except Exception:  # noqa: BLE001
        pass

    # Candidates — detection is read-only
    try:
        candidates = detect_field_candidates(backend_doc)
    except Exception:  # noqa: BLE001
        candidates = []
    try:
        tables = detect_tables(backend_doc)
    except Exception:  # noqa: BLE001
        tables = []

    page_rows: list[PageAnalysis] = []
    need_ocr: list[int] = []
    native = scanned = mixed = empty = 0
    has_images = False

    for info in pages_info:
        needs = page_needs_ocr(info)
        if needs:
            need_ocr.append(info.index)
        if info.content_kind == PageContentKind.TEXT:
            native += 1
        elif info.content_kind == PageContentKind.IMAGE_SCANNED:
            scanned += 1
        elif info.content_kind == PageContentKind.MIXED:
            mixed += 1
        else:
            empty += 1
        if info.has_images:
            has_images = True
        notes: list[str] = []
        if needs:
            notes.append("OCR recommended (image/scanned or little extractable text)")
        elif info.has_text:
            notes.append("Native text present — OCR not required")
        if widgets_per_page.get(info.index, 0):
            notes.append(f"{widgets_per_page[info.index]} form widget(s)")
        page_rows.append(
            PageAnalysis(
                page_index=info.index,
                kind=info.content_kind.value,
                has_native_text=info.has_text,
                char_count=info.char_count,
                image_count=info.image_count,
                needs_ocr=needs,
                form_widget_count=widgets_per_page.get(info.index, 0),
                notes=notes,
            )
        )

    sig_note = ""
    if any(getattr(c, "field_type", None) == FieldType.SIGNATURE for c in []):
        sig_note = ""

    summary = [
        f"File: {document.name}",
        f"Pages: {document.page_count}",
        f"Pages with selectable text: {native}",
        f"Scanned (image-only) pages: {scanned}",
        f"Pages with both: {mixed}",
        f"Empty pages: {empty}",
        f"Pages that need text recognition (OCR): {len(need_ocr)}"
        + (f" — page {', '.join(str(p + 1) for p in need_ocr[:20])}" if need_ocr else ""),
        f"Fillable form fields: {acro_count}",
        f"Boxes and lines that could become fields: {len(candidates)}",
        f"Tables found: {len(tables)}",
        f"Password-protected: {'yes' if meta.encrypted else 'no'}",
        "Pages that already have selectable text are left as they are.",
    ]
    if sig_note:
        summary.append(sig_note)

    return EditableAnalysis(
        path=str(document.path),
        page_count=document.page_count,
        pages=page_rows,
        native_text_pages=native,
        scanned_pages=scanned,
        mixed_pages=mixed,
        empty_pages=empty,
        pages_needing_ocr=need_ocr,
        acroform_fields=acro_count,
        field_candidates=len(candidates),
        table_candidates=len(tables),
        has_images=has_images,
        summary_lines=summary,
    )
