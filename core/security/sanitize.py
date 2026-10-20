"""Find and remove hidden information: metadata, attachments, scripts, comments and more.

``scan_hidden`` reports what a document carries besides its visible page content;
``remove_hidden`` writes a cleaned copy (the open document and its file are never changed) and
re-scans the copy so the report states what is actually left. Everything works offline on an
in-memory copy. Attachment *contents* are never read: attachments are counted and deleted by name.

Password-protected files are refused: cleaning would have to write them unencrypted, which must be
an explicit choice (Protect ▸ Unlock first, then protect the cleaned copy again).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import fitz

from core.document import DocumentError, PdfDocument

_COMMENT_SKIP = {fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_REDACT}


@dataclass
class HiddenInfo:
    metadata_fields: int = 0
    xmp_metadata: bool = False
    attachments: int = 0
    javascript: int = 0
    comments: int = 0
    form_fields: int = 0
    links: int = 0
    bookmarks: int = 0
    thumbnails: int = 0
    private_data: int = 0
    hidden_text_pages: int = 0
    redaction_marks: int = 0

    def total(self) -> int:
        return sum(int(getattr(self, f.name)) for f in fields(self) if f.name != "redaction_marks")


@dataclass
class SanitizeOptions:
    """What to remove. Defaults remove what is never needed to read the document."""

    metadata: bool = True
    attachments: bool = True
    javascript: bool = True
    thumbnails: bool = True
    private_data: bool = True
    comments: bool = False
    form_fields: bool = False
    links: bool = False
    bookmarks: bool = False
    hidden_text: bool = False

    @classmethod
    def everything(cls) -> "SanitizeOptions":
        return cls(**{f.name: True for f in fields(cls)})


@dataclass
class SanitizeReport:
    destination: Path
    before: HiddenInfo
    after: HiddenInfo
    notes: list[str] = field(default_factory=list)


def _raw(document: PdfDocument | fitz.Document) -> fitz.Document:
    return document if isinstance(document, fitz.Document) else document._backend._doc  # noqa: SLF001


def _is_js(doc: fitz.Document, xref: int, key: str) -> bool:
    try:
        kind, value = doc.xref_get_key(xref, key)
    except Exception:  # noqa: BLE001
        return False
    return kind == "name" and value == "/JavaScript"


def _inline_js_action(doc: fitz.Document, xref: int) -> bool:
    """True when the object's own /A action (written inline) is JavaScript, or chains to JavaScript
    through /Next. A JavaScript action stored as its own object is found by the object scan."""
    return _is_js(doc, xref, "A/S") or _is_js(doc, xref, "A/Next/S")


def _outline_items(doc: fitz.Document) -> list[int]:
    """Every bookmark (outline item) object, depth first; safe against loops in damaged files."""
    def ref(xref: int, key: str) -> int:
        kind, value = doc.xref_get_key(xref, key)
        return int(value.split()[0]) if kind == "xref" else 0

    items: list[int] = []
    seen: set[int] = set()
    root = ref(doc.pdf_catalog(), "Outlines")
    stack = [ref(root, "First")] if root else []
    while stack:
        xref = stack.pop()
        if not xref or xref in seen or len(seen) > 100_000:
            continue
        seen.add(xref)
        items.append(xref)
        stack.append(ref(xref, "Next"))
        stack.append(ref(xref, "First"))
    return items


def _open_action_runs_something(doc: fitz.Document) -> bool:
    """True when the document's open action does more than show a page: JavaScript, launching a
    program, opening a web address, submitting a form, … A plain destination ("open at page N",
    an array or /GoTo) is not hidden information and is kept."""
    cat = doc.pdf_catalog()
    kind, value = doc.xref_get_key(cat, "OpenAction")
    if kind == "null":
        return False
    if kind == "array":
        return False
    if kind == "xref":
        try:
            target = doc.xref_object(int(value.split()[0])).strip()
        except Exception:  # noqa: BLE001
            return True
        if target.startswith("["):
            return False
    s_kind, s_value = doc.xref_get_key(cat, "OpenAction/S")
    return not (s_kind == "name" and s_value == "/GoTo")


def _js_objects(doc: fitz.Document) -> int:
    n = 0
    for xref in range(1, doc.xref_length()):
        try:
            if _is_js(doc, xref, "S"):
                n += 1
        except Exception:  # noqa: BLE001
            continue
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
        n += 1
    if _open_action_runs_something(doc):
        indirect_js = doc.xref_get_key(cat, "OpenAction")[0] == "xref" and _is_js(doc, cat, "OpenAction/S")
        if not indirect_js:  # a JavaScript action stored as its own object is counted above
            n += 1
    if doc.xref_get_key(cat, "AA")[0] != "null":
        n += 1
    # actions written inline in pages, annotations and fields (not their own object)
    for page in doc:
        if doc.xref_get_key(page.xref, "AA")[0] != "null":
            n += 1
        for annot in list(page.annots()) + list(page.widgets() or []):
            if _inline_js_action(doc, annot.xref):
                n += 1
            if doc.xref_get_key(annot.xref, "AA")[0] != "null":
                n += 1
    # bookmarks that run JavaScript when clicked
    n += sum(1 for item in _outline_items(doc) if _inline_js_action(doc, item))
    return n


def _invisible_spans(page: fitz.Page) -> list[dict]:
    try:
        return [sp for sp in page.get_texttrace() if sp.get("type") == 3 and sp.get("chars")]
    except Exception:  # noqa: BLE001
        return []


def _visible_text(page: fitz.Page) -> str:
    try:
        return "".join(chr(c[0]) for sp in page.get_texttrace() if sp.get("type") != 3 for c in sp["chars"])
    except Exception:  # noqa: BLE001
        return ""


def _hidden_text_pages(doc: fitz.Document) -> int:
    """Pages with invisible text (rendering mode 3) — typically a recognised (OCR) text layer."""
    return sum(1 for page in doc if _invisible_spans(page))


def _remove_invisible_text(doc: fitz.Document) -> tuple[int, list[str]]:
    """Delete invisible text glyphs, page by page, and prove the visible text is unchanged.

    Each invisible span is covered by a thin removal box along its middle; MuPDF then deletes the
    glyphs inside (no fill, images and drawings untouched). Pages that already carry redaction
    marks are skipped so those marks are never applied by accident. Raises ``_VisibleTextTouched``
    when a page's visible text would change."""
    cleaned = 0
    notes: list[str] = []
    for page in doc:
        spans = _invisible_spans(page)
        if not spans:
            continue
        if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in page.annots()):
            notes.append(f"Page {page.number + 1}: invisible text kept because the page has redaction marks.")
            continue
        before = _visible_text(page)
        for sp in spans:
            r = fitz.Rect(sp["bbox"])
            h = r.height
            r = fitz.Rect(r.x0 + 0.2, r.y0 + h * 0.4, r.x1 - 0.2, r.y1 - h * 0.4)
            if r.is_empty:
                continue
            page.add_redact_annot(r, fill=False)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE
        )
        if _visible_text(page) != before:
            raise _VisibleTextTouched(page.number)
        cleaned += 1
    return cleaned, notes


class _VisibleTextTouched(Exception):
    pass


def scan_hidden(document: PdfDocument | fitz.Document) -> HiddenInfo:
    doc = _raw(document)
    info = HiddenInfo()
    meta = doc.metadata or {}
    info.metadata_fields = sum(
        1 for k, v in meta.items() if v and k not in ("format", "encryption")
    )
    try:
        info.xmp_metadata = bool((doc.get_xml_metadata() or "").strip())
    except Exception:  # noqa: BLE001
        info.xmp_metadata = False
    try:
        info.attachments = int(doc.embfile_count())
    except Exception:  # noqa: BLE001
        info.attachments = 0
    info.javascript = _js_objects(doc)
    try:
        info.bookmarks = len(doc.get_toc(simple=True) or [])
    except Exception:  # noqa: BLE001
        info.bookmarks = 0
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "PieceInfo")[0] != "null":
        info.private_data += 1
    for page in doc:
        for annot in page.annots():
            t = annot.type[0]
            if t == fitz.PDF_ANNOT_FILE_ATTACHMENT:
                info.attachments += 1
            elif t == fitz.PDF_ANNOT_REDACT:
                info.redaction_marks += 1
            elif t not in _COMMENT_SKIP:
                info.comments += 1
        info.form_fields += sum(1 for _ in (page.widgets() or []))
        info.links += len(page.get_links())
        if doc.xref_get_key(page.xref, "Thumb")[0] != "null":
            info.thumbnails += 1
        if doc.xref_get_key(page.xref, "PieceInfo")[0] != "null":
            info.private_data += 1
    info.hidden_text_pages = _hidden_text_pages(doc)
    return info


def _strip_inline_js(doc: fitz.Document) -> None:
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
        doc.xref_set_key(cat, "Names/JavaScript", "null")
    if _open_action_runs_something(doc):
        doc.xref_set_key(cat, "OpenAction", "null")
    if doc.xref_get_key(cat, "AA")[0] != "null":
        doc.xref_set_key(cat, "AA", "null")
    for page in doc:
        if doc.xref_get_key(page.xref, "AA")[0] != "null":
            doc.xref_set_key(page.xref, "AA", "null")
        for annot in list(page.annots()) + list(page.widgets() or []):
            if _inline_js_action(doc, annot.xref):
                doc.xref_set_key(annot.xref, "A", "null")
            if doc.xref_get_key(annot.xref, "AA")[0] != "null":
                doc.xref_set_key(annot.xref, "AA", "null")
    for item in _outline_items(doc):  # the bookmark stays; only its script goes
        if _inline_js_action(doc, item):
            doc.xref_set_key(item, "A", "null")


def remove_hidden(
    document: PdfDocument,
    destination: Path,
    options: SanitizeOptions | None = None,
) -> SanitizeReport:
    """Write a copy of ``document`` without the chosen kinds of hidden information."""
    options = options or SanitizeOptions()
    src = _raw(document)
    if src.needs_pass or src.is_encrypted or (src.metadata or {}).get("encryption"):
        raise DocumentError(
            "This PDF is password-protected. Unlock it first (Protect ▸ Unlock PDF), remove the "
            "hidden information from the unlocked copy, then protect the result again."
        )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = scan_hidden(src)
    notes: list[str] = []
    try:
        _write_clean(src, destination, options, notes)
    except _VisibleTextTouched as exc:
        notes.clear()
        notes.append(
            f"Invisible text was kept: on page {exc.args[0] + 1} it overlaps visible text and could not "
            "be removed without changing what the page shows."
        )
        options = SanitizeOptions(**{**options.__dict__, "hidden_text": False})
        _write_clean(src, destination, options, notes)
    check = fitz.open(destination.as_posix())
    try:
        after = scan_hidden(check)
    finally:
        check.close()
    if before.redaction_marks:
        notes.append(
            f"{before.redaction_marks} redaction mark(s) were left as they are — marked content is "
            "only removed by Protect ▸ Apply Redactions."
        )
    if options.hidden_text and before.hidden_text_pages:
        notes.append("Invisible text was removed, so recognised (OCR) text on scanned pages can no longer be searched.")
    return SanitizeReport(destination=destination, before=before, after=after, notes=notes)


def _write_clean(src: fitz.Document, destination: Path, options: SanitizeOptions, notes: list[str]) -> None:
    doc = fitz.open("pdf", src.tobytes(garbage=3, deflate=True))
    try:
        if options.hidden_text:
            _cleaned, page_notes = _remove_invisible_text(doc)
            notes.extend(page_notes)
        for page in doc:
            # File-attachment comments, other comments, fields and links go one page at a time.
            for annot in list(page.annots()):
                t = annot.type[0]
                if (t == fitz.PDF_ANNOT_FILE_ATTACHMENT and options.attachments) or (
                    options.comments and t not in _COMMENT_SKIP and t != fitz.PDF_ANNOT_FILE_ATTACHMENT
                ):
                    page.delete_annot(annot)
            if options.form_fields:
                for widget in list(page.widgets() or []):
                    page.delete_widget(widget)
            if options.thumbnails and doc.xref_get_key(page.xref, "Thumb")[0] != "null":
                doc.xref_set_key(page.xref, "Thumb", "null")
            if options.private_data and doc.xref_get_key(page.xref, "PieceInfo")[0] != "null":
                doc.xref_set_key(page.xref, "PieceInfo", "null")
        if options.private_data:
            cat = doc.pdf_catalog()
            if doc.xref_get_key(cat, "PieceInfo")[0] != "null":
                doc.xref_set_key(cat, "PieceInfo", "null")
        if options.form_fields:
            cat = doc.pdf_catalog()
            if doc.xref_get_key(cat, "AcroForm")[0] != "null":
                doc.xref_set_key(cat, "AcroForm", "null")
        if options.javascript:
            _strip_inline_js(doc)
        if options.bookmarks:
            doc.set_toc([])
        doc.scrub(
            attached_files=False,
            clean_pages=False,
            embedded_files=options.attachments,
            hidden_text=False,
            javascript=options.javascript,
            metadata=options.metadata,
            redactions=False,
            remove_links=options.links,
            reset_fields=False,
            reset_responses=False,  # replies are comments: deleted above (and this call fails without replies in PyMuPDF 1.25)
            thumbnails=False,
            xml_metadata=options.metadata,
        )
        doc.save(destination.as_posix(), garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()
