"""Undo support for any PDF annotation: capture, remove, re-insert and restore in place.

MuPDF keeps an annotation's objects (its dictionary, appearance streams and pop-up) in the file when the
annotation is removed from the page's /Annots array; they are dropped only when the file is saved with
garbage collection. So an annotation is undone by taking it out of /Annots and redone by putting the
same objects back at the same position, and a change (text, colour, opacity, position) is undone by
writing back the objects' earlier text and stream bytes. This works for every annotation type the
application creates or imports, with the same identity (xref and /NM) throughout.
"""

from __future__ import annotations

import re
from typing import Any

import fitz

from core.document import PdfDocument

_REF = re.compile(r"(\d+)\s+0\s+R")


def _doc(document: PdfDocument) -> fitz.Document:
    return document._backend._doc  # noqa: SLF001


def _page(document: PdfDocument, page_index: int) -> fitz.Page:
    doc = _doc(document)
    if not 0 <= page_index < doc.page_count:
        raise IndexError(f"page out of range: {page_index}")
    return doc.load_page(page_index)


def annots_refs(doc: fitz.Document, page_xref: int) -> list[int]:
    """xrefs listed in a page's /Annots array (direct or indirect array)."""
    kind, value = doc.xref_get_key(page_xref, "Annots")
    if kind == "xref":
        value = doc.xref_object(int(value.split()[0]))
    elif kind != "array":
        return []
    return [int(m) for m in _REF.findall(value)]


def _set_annots(doc: fitz.Document, page_xref: int, refs: list[int]) -> None:
    array = "[" + " ".join(f"{r} 0 R" for r in refs) + "]"
    kind, value = doc.xref_get_key(page_xref, "Annots")
    if kind == "xref":
        doc.update_object(int(value.split()[0]), array)
    else:
        doc.xref_set_key(page_xref, "Annots", array)


def _appearance_xrefs(doc: fitz.Document, xref: int) -> list[int]:
    kind, value = doc.xref_get_key(xref, "AP")
    if kind == "xref":
        value = doc.xref_object(int(value.split()[0]))
    if kind == "null" or not value:
        return []
    return sorted({int(m) for m in _REF.findall(value)})


def capture(document: PdfDocument, page_index: int, xref: int) -> dict[str, Any]:
    """Everything needed to put an annotation back exactly: its objects (dictionary, pop-up,
    appearance streams with their bytes) and its position in the page's /Annots."""
    doc = _doc(document)
    page = _page(document, page_index)
    objects: dict[int, str] = {}
    streams: dict[int, bytes] = {}
    members = [int(xref)]
    popup = 0
    kind, value = doc.xref_get_key(int(xref), "Popup")
    if kind == "xref":
        popup = int(value.split()[0])
        members.append(popup)
    for x in members + _appearance_xrefs(doc, int(xref)):
        objects[x] = doc.xref_object(x, compressed=False)
        if doc.xref_is_stream(x):
            streams[x] = doc.xref_stream(x) or b""  # decoded; written back re-encoded
    refs = annots_refs(doc, page.xref)
    return {
        "page_index": page_index,
        "xref": int(xref),
        "popup": popup,
        "objects": objects,
        "streams": streams,
        "positions": {x: refs.index(x) for x in members if x in refs},
    }


def is_on_page(document: PdfDocument, page_index: int, xref: int) -> bool:
    page = _page(document, page_index)
    return int(xref) in annots_refs(_doc(document), page.xref)


def remove(document: PdfDocument, page_index: int, xref: int) -> dict[str, Any]:
    """Take an annotation (and its pop-up) off the page; returns the capture for ``reinsert``."""
    snap = capture(document, page_index, xref)
    doc = _doc(document)
    page = _page(document, page_index)
    members = {snap["xref"], snap["popup"]} - {0}
    _set_annots(doc, page.xref, [r for r in annots_refs(doc, page.xref) if r not in members])
    document.invalidate_pages()
    return snap


def restore_objects(document: PdfDocument, snap: dict[str, Any]) -> None:
    """Write back the captured object dictionaries and stream bytes (undo of a change)."""
    doc = _doc(document)
    for x, text in snap["objects"].items():
        doc.update_object(int(x), text)
    for x, data in snap["streams"].items():
        doc.update_stream(int(x), data)  # sets /Filter and /Length to match
    document.invalidate_pages()


def reinsert(document: PdfDocument, snap: dict[str, Any]) -> int:
    """Put a removed annotation back with the same objects at the same position. Returns its xref."""
    restore_objects(document, snap)
    doc = _doc(document)
    page = _page(document, int(snap["page_index"]))
    refs = annots_refs(doc, page.xref)
    for x, pos in sorted(snap["positions"].items(), key=lambda kv: kv[1]):
        if x not in refs:
            refs.insert(min(pos, len(refs)), int(x))
    for x in (snap["xref"], snap["popup"]):
        if x and x not in refs:
            refs.append(int(x))
    _set_annots(doc, page.xref, refs)
    document.invalidate_pages()
    return int(snap["xref"])


def find_live(document: PdfDocument, page_index: int, xref: int) -> tuple[fitz.Page, fitz.Annot] | None:
    """(page, annotation) — keep the page referenced while using the annotation (PyMuPDF holds the
    page only weakly)."""
    page = _page(document, page_index)
    for annot in page.annots() or []:
        if int(annot.xref) == int(xref):
            return page, annot
    return None
