"""Mark and apply true content redaction via PyMuPDF apply_redactions()."""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from core.security.protection import is_protected as _is_protected

from core.document import PdfDocument
from core.editing.geometry import Rect


# Search terms marked with mark_text, per open document (kept in memory only, never written):
# used after applying to look for the same text in places a page redaction cannot reach.
_TERMS: "weakref.WeakKeyDictionary[PdfDocument, set[str]]" = weakref.WeakKeyDictionary()


def marked_terms(document: PdfDocument) -> set[str]:
    return set(_TERMS.get(document, set()))


@dataclass
class Residue:
    """The redacted text found outside the page content (or still on a page)."""

    where: str  # page | comment | form field | bookmark | document properties | attachment
    detail: str


@dataclass
class RedactionReport:
    destination: Path
    removed_form_fields: int = 0
    removed_annotations: int = 0
    removed_links: int = 0
    residue: list[Residue] = field(default_factory=list)


@dataclass
class RedactionMark:
    page_index: int
    rect: Rect
    text: str = ""


def mark_region(
    document: PdfDocument,
    page_index: int,
    rect: Rect,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
    text: str = "",
) -> RedactionMark:
    """Add a redaction annotation (preview) — content not yet removed until apply."""
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    r = fitz.Rect(rect.x, rect.y, rect.x1, rect.y1)
    kwargs = {"fill": fill}
    if text:
        kwargs["text"] = text
    page.add_redact_annot(r, **kwargs)
    document.invalidate_pages()
    return RedactionMark(page_index=page_index, rect=rect, text=text)


def mark_text(
    document: PdfDocument,
    page_index: int,
    query: str,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
) -> list[RedactionMark]:
    """Mark all occurrences of query on a page for redaction."""
    if not query:
        return []
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    marks: list[RedactionMark] = []
    for r in page.search_for(query) or []:
        # Inflate slightly so glyph edges are covered
        rr = fitz.Rect(r)
        rr.x0 -= 1
        rr.y0 -= 1
        rr.x1 += 1
        rr.y1 += 1
        page.add_redact_annot(rr, fill=fill)
        marks.append(
            RedactionMark(
                page_index=page_index,
                rect=Rect(float(rr.x0), float(rr.y0), float(rr.width), float(rr.height)),
                text=query,
            )
        )
    if marks:
        _TERMS.setdefault(document, set()).add(query)
        document.invalidate_pages()
    return marks


def mark_pages(
    document: PdfDocument,
    pages: list[int],
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
) -> list[RedactionMark]:
    """Mark whole pages: everything visible on them is removed when the marks are applied.

    The pages themselves stay (page numbers, bookmarks and links to them keep working); they
    become blank areas in the fill colour.
    """
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    marks: list[RedactionMark] = []
    for i in sorted(set(int(p) for p in pages)):
        if i < 0 or i >= doc.page_count:
            raise ValueError(f"Page {i + 1} does not exist (the document has {doc.page_count} pages).")
        page = doc.load_page(i)
        # The whole MediaBox in page space: wider than the visible CropBox when the page is cropped,
        # so content hidden outside the visible area is removed too
        c, m = page.cropbox, page.mediabox
        r = fitz.Rect(m.x0 - c.x0, m.y0 - c.y0, m.x1 - c.x0, m.y1 - c.y0)
        page.add_redact_annot(r, fill=fill)
        marks.append(RedactionMark(page_index=i, rect=Rect(r.x0, r.y0, r.width, r.height)))
    if marks:
        document.invalidate_pages()
    return marks


def preview_redaction_count(document: PdfDocument) -> int:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    count = 0
    for i in range(doc.page_count):
        page = doc.load_page(i)
        for annot in page.annots() or []:
            try:
                if annot.type and (
                    annot.type[0] == getattr(fitz, "PDF_ANNOT_REDACT", 12)
                    or str(annot.type[1]).lower() == "redact"
                ):
                    count += 1
            except Exception:  # noqa: BLE001
                continue
    return count


def _overlaps(r: fitz.Rect, areas: list[fitz.Rect]) -> bool:
    return any(not (fitz.Rect(r) & a).is_empty for a in areas)


def _remove_covered_objects(page: fitz.Page) -> tuple[int, int, int]:
    """Form fields, annotations and links under a redaction area are removed with it.

    MuPDF's apply_redactions() removes page content only: a form field over a marked area
    would keep showing (and storing) its value, a comment its text, a link its target.
    Returns (form fields, annotations, links) removed.
    """
    redact = getattr(fitz, "PDF_ANNOT_REDACT", 12)
    areas = [fitz.Rect(a.rect) for a in page.annots(types=[redact])]
    if not areas:
        return 0, 0, 0
    widgets = [w.xref for w in page.widgets() if _overlaps(w.rect, areas)]
    for xref in widgets:
        for w in page.widgets():
            if w.xref == xref:
                page.delete_widget(w)
                break
    others = [a.xref for a in page.annots() if a.type[0] != redact and _overlaps(a.rect, areas)]
    for xref in others:
        annot = page.load_annot(xref)
        if annot is not None:
            page.delete_annot(annot)
    links = [ln for ln in page.get_links() if _overlaps(ln.get("from", fitz.Rect()), areas)]
    for ln in links:
        page.delete_link(ln)
    return len(widgets), len(others), len(links)


def _contains(text: object, term: str) -> bool:
    return isinstance(text, str) and term.casefold() in text.casefold()


def find_residue(doc: fitz.Document, terms: set[str] | list[str]) -> list[Residue]:
    """Where the terms still occur: page text, comments, form values, bookmarks, properties, attachments."""
    out: list[Residue] = []
    for term in sorted({t for t in terms if t}):
        for page in doc:
            if page.search_for(term):
                out.append(Residue("page", f"page {page.number + 1}: “{term}”"))
            for a in page.annots() or []:
                info = a.info or {}
                if any(_contains(info.get(k), term) for k in ("content", "title", "subject")):
                    out.append(Residue("comment", f"{a.type[1]} comment on page {page.number + 1}"))
            for w in page.widgets() or []:
                if _contains(w.field_value, term) or _contains(w.field_name, term):
                    out.append(Residue("form field", f"field “{w.field_name}” on page {page.number + 1}"))
        for _lvl, title, pno, *_ in doc.get_toc(simple=False) or []:
            if _contains(title, term):
                out.append(Residue("bookmark", f"bookmark “{title}”"))
        meta = {k: v for k, v in (doc.metadata or {}).items() if _contains(v, term)}
        if meta:
            out.append(Residue("document properties", ", ".join(sorted(meta))))
        try:
            if _contains(doc.get_xml_metadata(), term):
                out.append(Residue("document properties", "XMP metadata"))
        except Exception:  # noqa: BLE001
            pass
        for name in doc.embfile_names():
            if _attachment_label_has(doc, name, term):
                out.append(Residue("attachment", f"attachment “{name}”"))
    # Attachments are listed, never read (security policy), so their content cannot be checked:
    # every attachment not already named above is listed for the user to review.
    if terms:
        named = {r.detail for r in out if r.where == "attachment"}
        for name in doc.embfile_names():
            if f"attachment “{name}”" not in named:
                out.append(Residue(UNCHECKED_ATTACHMENT, f"attachment “{name}” (content not checked)"))
    return out


UNCHECKED_ATTACHMENT = "attachment (not checked)"


def _attachment_label_has(doc: fitz.Document, name: str, term: str) -> bool:
    """The term in an attachment's name or description (its content is never read)."""
    if _contains(name, term):
        return True
    try:
        info = doc.embfile_info(name) or {}
    except Exception:  # noqa: BLE001
        return False
    return any(_contains(info.get(k), term) for k in ("filename", "ufilename", "desc", "description"))


REDACTED = "[redacted]"


def scrub_residue(doc: fitz.Document, terms: set[str] | list[str]) -> int:
    """Remove the terms outside the page content. Returns the number of places changed.

    Comment texts, bookmark titles and document properties get the term replaced by
    "[redacted]"; form fields containing it are cleared; XMP metadata containing it is deleted;
    attachments whose name or description contains it are removed. Attachment content is never
    read (security policy), so other attachments are left for the user to review. Page content is not touched here — that is what applying the redaction marks does.
    """
    import re

    changed = 0
    for term in {t for t in terms if t}:
        pat = re.compile(re.escape(term), re.IGNORECASE)
        for page in doc:
            for a in list(page.annots() or []):
                info = dict(a.info or {})
                new = {k: pat.sub(REDACTED, info.get(k) or "") for k in ("content", "title", "subject")}
                if any(new[k] != (info.get(k) or "") for k in new):
                    a.set_info(**new)
                    a.update()
                    changed += 1
            for w in list(page.widgets() or []):
                if _contains(w.field_value, term):
                    w.field_value = ""
                    w.update()
                    changed += 1
        toc = doc.get_toc(simple=False) or []
        if any(_contains(row[1], term) for row in toc):
            changed += sum(1 for row in toc if _contains(row[1], term))
            doc.set_toc([[row[0], pat.sub(REDACTED, row[1]), *row[2:]] for row in toc])
        meta = dict(doc.metadata or {})
        if any(_contains(v, term) for v in meta.values()):
            changed += 1
            doc.set_metadata({k: pat.sub(REDACTED, v) if isinstance(v, str) else v for k, v in meta.items()
                              if k not in ("format", "encryption")})
        try:
            if _contains(doc.get_xml_metadata(), term):
                doc.del_xml_metadata()
                changed += 1
        except Exception:  # noqa: BLE001
            pass
        for name in list(doc.embfile_names()):
            if _attachment_label_has(doc, name, term):
                doc.embfile_del(name)
                changed += 1
    return changed


def apply_redactions_report(document: PdfDocument, destination: Path) -> RedactionReport:
    """Apply every redaction mark, write ``destination`` and report what else still holds the text.

    Besides the page content under each mark (text, image pixels, vector graphics), form fields,
    annotations and links overlapping a mark are removed. Text marked with mark_text is then
    searched for in the written file — comments elsewhere, form values, bookmarks, document
    properties and attachments are listed in ``residue`` (nothing there is changed silently; see
    scrub_residue).
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    report = RedactionReport(destination=destination)
    for i in range(src.page_count):
        page = src.load_page(i)
        f, a, ln = _remove_covered_objects(page)
        report.removed_form_fields += f
        report.removed_annotations += a
        report.removed_links += ln
        try:
            page.apply_redactions()
        except Exception:  # noqa: BLE001
            page.apply_redactions(images=2, graphics=2, text=0)

    document.invalidate_pages()
    src.save(
        destination.as_posix(),
        garbage=4,
        deflate=True,
        encryption=fitz.PDF_ENCRYPT_KEEP if _is_protected(src) else fitz.PDF_ENCRYPT_NONE,
        incremental=False,
    )
    terms = marked_terms(document)
    if terms:
        with fitz.open(destination) as out:
            if out.needs_pass:
                report.residue = find_residue(src, terms)
            else:
                report.residue = find_residue(out, terms)
    return report


def apply_redactions(
    document: PdfDocument,
    destination: Path,
    *,
    images: int | bool = True,
    graphics: int | bool = True,
    text: int | bool = True,
) -> Path:
    """
    Apply true content redaction and write destination.
    Uses page.apply_redactions() so underlying text/images are removed — not covered by rectangles;
    form fields, annotations and links under a mark are removed too (see apply_redactions_report).
    """
    return apply_redactions_report(document, destination).destination
