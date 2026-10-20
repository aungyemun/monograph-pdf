"""Protect ▸ Remove Hidden Information (core.security.sanitize).

Results are checked in the written file itself: every object and every decompressed stream is
searched for the removed content, so nothing survives as an unreferenced leftover either.
"""

from __future__ import annotations

import hashlib

import fitz
import pytest

from core.document import DocumentError, open_document
from core.security.sanitize import SanitizeOptions, remove_hidden, scan_hidden

XMP = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>XMPCREATOR77</dc:creator>'
       '</rdf:Description></rdf:RDF></x:xmpmeta>')


def _all_bytes(path) -> bytes:
    """Every object and decompressed stream of the file, plus the raw file."""
    d = fitz.open(path)
    parts = [open(path, "rb").read()]
    for x in range(1, d.xref_length()):
        try:
            parts.append(d.xref_object(x).encode("latin-1", "replace"))
            if d.xref_is_stream(x):
                parts.append(d.xref_stream(x) or b"")
        except Exception:  # noqa: BLE001
            continue
    d.close()
    return b"\n".join(parts)


def _make(path):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), "Visible body text")
    p.insert_text((72, 120), "OCRLAYER55", render_mode=3)
    p.add_text_annot((100, 200), "NOTETEXT33")
    p.add_highlight_annot(fitz.Rect(72, 60, 200, 76))
    p.add_file_annot((150, 200), b"ATTACHPAYLOAD11", "a.txt")
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 300, 200, 320), "uri": "https://linkhost.example/x"})
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "fieldname"
    w.rect = fitz.Rect(72, 400, 200, 420)
    w.field_value = "FIELDVALUE22"
    p.add_widget(w)
    d.new_page().insert_text((72, 72), "Second page")
    d.embfile_add("emb.txt", b"EMBEDDEDDATA44")
    d.set_metadata({"author": "AUTHORNAME66", "title": "Report"})
    d.set_xml_metadata(XMP)
    d.set_toc([[1, "BOOKMARK88", 1]])
    js = d.get_new_xref()
    d.update_object(js, "<</S/JavaScript/JS(app.alert('SCRIPT99'))>>")
    d.xref_set_key(d.pdf_catalog(), "OpenAction", f"{js} 0 R")
    d.xref_set_key(d[1].xref, "PieceInfo", "<</App<</Private(PRIVATE12)>>>>")
    d.save(path)
    d.close()
    return path


def test_scan_counts_each_kind(tmp_path):
    doc = open_document(_make(tmp_path / "in.pdf"))
    info = scan_hidden(doc)
    assert info.metadata_fields >= 2 and info.xmp_metadata
    assert info.attachments == 2  # embedded file + file-attachment comment
    assert info.javascript >= 1
    assert info.comments == 2 and info.form_fields == 1 and info.links == 1
    assert info.bookmarks == 1 and info.private_data == 1 and info.hidden_text_pages == 1
    doc.close()


def test_default_removal_keeps_what_readers_use(tmp_path):
    src = _make(tmp_path / "in.pdf")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    doc = open_document(src)
    report = remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    a = report.after
    assert (a.metadata_fields, a.xmp_metadata, a.attachments, a.javascript, a.private_data) == (0, False, 0, 0, 0)
    assert (a.comments, a.form_fields, a.links, a.bookmarks, a.hidden_text_pages) == (2, 1, 1, 1, 1)
    data = _all_bytes(tmp_path / "out.pdf")
    for gone in (b"AUTHORNAME66", b"XMPCREATOR77", b"EMBEDDEDDATA44", b"ATTACHPAYLOAD11", b"SCRIPT99", b"PRIVATE12"):
        assert gone not in data, gone
    for kept in (b"NOTETEXT33", b"FIELDVALUE22", b"BOOKMARK88"):
        assert kept in data, kept
    assert hashlib.sha256(src.read_bytes()).hexdigest() == digest  # the original is never changed


def test_everything_removes_all_kinds_but_keeps_visible_text(tmp_path):
    doc = open_document(_make(tmp_path / "in.pdf"))
    report = remove_hidden(doc, tmp_path / "out.pdf", SanitizeOptions.everything())
    doc.close()
    assert report.after.total() == 0
    data = _all_bytes(tmp_path / "out.pdf")
    for gone in (b"NOTETEXT33", b"FIELDVALUE22", b"BOOKMARK88", b"linkhost", b"OCRLAYER55"):
        assert gone not in data, gone
    out = fitz.open(tmp_path / "out.pdf")
    assert out.page_count == 2
    assert out[0].get_text().strip() == "Visible body text"
    assert "Second page" in out[1].get_text()
    out.close()
    assert any("OCR" in n for n in report.notes)


def test_invisible_text_over_visible_text_is_kept(tmp_path):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), "SAMEPLACE visible")
    p.insert_text((72, 72), "SAMEPLACE hidden", render_mode=3)
    d.save(tmp_path / "in.pdf")
    d.close()
    doc = open_document(tmp_path / "in.pdf")
    report = remove_hidden(doc, tmp_path / "out.pdf", SanitizeOptions(hidden_text=True))
    doc.close()
    out = fitz.open(tmp_path / "out.pdf")
    assert "SAMEPLACE visible" in out[0].get_text()
    out.close()
    assert report.after.hidden_text_pages == 1
    assert any("kept" in n for n in report.notes)


def test_pending_redaction_marks_are_reported_not_applied(tmp_path):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), "MARKEDWORD stays")
    p.add_redact_annot(fitz.Rect(70, 60, 160, 76))
    d.save(tmp_path / "in.pdf")
    d.close()
    doc = open_document(tmp_path / "in.pdf")
    report = remove_hidden(doc, tmp_path / "out.pdf", SanitizeOptions.everything())
    doc.close()
    assert report.after.redaction_marks == 1
    assert any("Apply Redactions" in n for n in report.notes)
    out = fitz.open(tmp_path / "out.pdf")
    assert "MARKEDWORD" in out[0].get_text()
    out.close()


@pytest.mark.parametrize("user_pw", ["u", ""])
def test_protected_files_are_refused(tmp_path, user_pw):
    d = fitz.open()
    d.new_page().insert_text((72, 72), "x")
    path = tmp_path / "enc.pdf"
    d.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user_pw, owner_pw="owner", permissions=0)
    d.close()
    doc = open_document(path, password=user_pw or None)
    with pytest.raises(DocumentError, match="password"):
        remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    assert not (tmp_path / "out.pdf").exists()


# ------------------------------------------------------------------ audit 0.2.3: actions, history, leftovers


def _plain(path, pages=2):
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"Page {i + 1} body")
    d.save(path)
    d.close()
    return path


@pytest.mark.parametrize("action", [
    "<</S/URI/URI(https://TRACKER66.example/open)>>",
    "<</S/Launch/F(TRACKER66.exe)>>",
    "<</S/SubmitForm/F<</FS/URL/F(https://TRACKER66.example/submit)>>>>",
    "<</S/JavaScript/JS(app.launchURL('https://TRACKER66.example'))>>",
])
def test_open_actions_of_any_kind_are_found_and_removed(tmp_path, action):
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    d.xref_set_key(d.pdf_catalog(), "OpenAction", action)
    d.saveIncr()
    d.close()
    doc = open_document(src)
    assert scan_hidden(doc).javascript >= 1
    report = remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    assert report.after.javascript == 0
    assert b"TRACKER66" not in _all_bytes(tmp_path / "out.pdf")


def test_open_at_page_destination_is_not_hidden_information(tmp_path):
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    d.xref_set_key(d.pdf_catalog(), "OpenAction", f"[{d[1].xref} 0 R /Fit]")
    d.saveIncr()
    d.close()
    doc = open_document(src)
    assert scan_hidden(doc).javascript == 0
    remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    out = fitz.open(tmp_path / "out.pdf")
    assert out.xref_get_key(out.pdf_catalog(), "OpenAction")[0] == "array"  # kept
    out.close()


def test_document_and_page_automatic_actions_are_counted_and_removed(tmp_path):
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    d.xref_set_key(d.pdf_catalog(), "AA", "<</WC<</S/URI/URI(https://AACAT77.example)>>>>")
    d.xref_set_key(d[0].xref, "AA", "<</O<</S/Launch/F(AAPAGE77.exe)>>>>")
    d.saveIncr()
    d.close()
    doc = open_document(src)
    assert scan_hidden(doc).javascript == 2
    remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    data = _all_bytes(tmp_path / "out.pdf")
    assert b"AACAT77" not in data and b"AAPAGE77" not in data


def test_earlier_revisions_and_unreferenced_objects_do_not_survive(tmp_path):
    """Values replaced by an incremental save stay in the file's history; the cleaned copy is a
    fresh, fully rewritten file without that history or orphaned objects."""
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    d.set_metadata({"author": "placeholder"})  # creates the Info dictionary
    info = int(d.xref_get_key(-1, "Info")[1].split()[0])
    d.xref_set_key(info, "Author", "(OLDAUTHOR55)")  # literal string: visible in the raw file
    d.saveIncr()
    d.close()  # a second session appends a new revision (in one session MuPDF rewrites the last one)
    d = fitz.open(src)
    d.xref_set_key(info, "Author", "(NEWAUTHOR55)")
    orphan = d.get_new_xref()
    d.update_object(orphan, "<</Secret(ORPHAN55)>>")
    d.saveIncr()
    d.close()
    assert b"OLDAUTHOR55" in src.read_bytes() and b"ORPHAN55" in src.read_bytes()
    doc = open_document(src)
    remove_hidden(doc, tmp_path / "kept.pdf", SanitizeOptions(metadata=False))
    remove_hidden(doc, tmp_path / "clean.pdf")
    doc.close()
    kept = _all_bytes(tmp_path / "kept.pdf")
    assert b"NEWAUTHOR55" in kept  # current properties kept when not chosen
    assert b"OLDAUTHOR55" not in kept and b"ORPHAN55" not in kept  # history and leftovers gone anyway
    clean = _all_bytes(tmp_path / "clean.pdf")
    assert b"NEWAUTHOR55" not in clean and b"OLDAUTHOR55" not in clean


def test_page_thumbnails_are_counted_and_removed(tmp_path):
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    thumb = d.get_new_xref()
    d.update_object(thumb, "<</Type/XObject/Subtype/Image/Width 1/Height 1/ColorSpace/DeviceGray/BitsPerComponent 8>>")
    d.update_stream(thumb, b"THUMB88")
    d.xref_set_key(d[0].xref, "Thumb", f"{thumb} 0 R")
    d.saveIncr()
    d.close()
    doc = open_document(src)
    assert scan_hidden(doc).thumbnails == 1
    report = remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    assert report.after.thumbnails == 0
    assert b"THUMB88" not in _all_bytes(tmp_path / "out.pdf")


def test_cleaned_copy_is_a_valid_pdf_and_the_report_matches_it(tmp_path):
    doc = open_document(_make(tmp_path / "in.pdf"))
    report = remove_hidden(doc, tmp_path / "out.pdf", SanitizeOptions.everything())
    doc.close()
    out = fitz.open(tmp_path / "out.pdf")
    try:
        assert not out.is_repaired and out.page_count == 2
        for page in out:
            page.get_pixmap(dpi=30)
        independent = scan_hidden(out)
    finally:
        out.close()
    assert independent == report.after  # the reported result is a scan of the written file


def test_bookmark_scripts_are_counted_and_removed_but_bookmarks_kept(tmp_path):
    """JavaScript written inline in a bookmark's action (or chained through /Next) is not its own
    object, so the object scan alone missed it; the bookmarks themselves are kept by default."""
    src = _plain(tmp_path / "in.pdf")
    d = fitz.open(src)
    d.set_toc([[1, "Intro", 1], [2, "Detail", 2], [1, "Web", 1]])
    items = []
    x = int(d.xref_get_key(int(d.xref_get_key(d.pdf_catalog(), "Outlines")[1].split()[0]), "First")[1].split()[0])
    while x:  # Intro, Web (top level); Detail is the child of Intro
        items.append(x)
        k, v = d.xref_get_key(x, "Next")
        x = int(v.split()[0]) if k == "xref" else 0
    child = int(d.xref_get_key(items[0], "First")[1].split()[0])
    d.xref_set_key(child, "A", "<</S/JavaScript/JS(app.alert('BMJS91'))>>")
    d.xref_set_key(items[0], "A", f"<</S/GoTo/D[{d[0].xref} 0 R/Fit]/Next<</S/JavaScript/JS(app.alert('BMNEXT92'))>>>>")
    d.xref_set_key(items[1], "A", "<</S/URI/URI(https://example.org/manual)>>")  # a web-link bookmark
    d.saveIncr()
    d.close()
    doc = open_document(src)
    assert scan_hidden(doc).javascript == 2
    report = remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    assert report.after.javascript == 0
    data = _all_bytes(tmp_path / "out.pdf")
    assert b"BMJS91" not in data and b"BMNEXT92" not in data
    out = fitz.open(tmp_path / "out.pdf")
    assert [t[1] for t in out.get_toc()] == ["Intro", "Detail", "Web"]  # bookmarks not chosen: kept
    assert b"https://example.org/manual" in data  # web-link bookmark kept
    out.close()


def test_page_and_image_xmp_metadata_are_removed_with_document_properties(tmp_path):
    src = _plain(tmp_path / "in.pdf", pages=1)
    d = fitz.open(src)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), 0)
    d[0].insert_image(fitz.Rect(100, 100, 140, 140), pixmap=pix)
    d.saveIncr()
    d.close()
    d = fitz.open(src)
    img = d[0].get_images()[0][0]
    for owner, token in ((d[0].xref, b"PAGEXMP93"), (img, b"IMGXMP94")):
        m = d.get_new_xref()
        d.update_object(m, "<</Type/Metadata/Subtype/XML>>")
        d.update_stream(m, b"<x:xmpmeta>" + token + b"</x:xmpmeta>")
        d.xref_set_key(owner, "Metadata", f"{m} 0 R")
    d.saveIncr()
    d.close()
    doc = open_document(src)
    remove_hidden(doc, tmp_path / "kept.pdf", SanitizeOptions(metadata=False))
    remove_hidden(doc, tmp_path / "out.pdf")
    doc.close()
    kept = _all_bytes(tmp_path / "kept.pdf")
    assert b"PAGEXMP93" in kept and b"IMGXMP94" in kept  # not chosen: kept
    data = _all_bytes(tmp_path / "out.pdf")
    assert b"PAGEXMP93" not in data and b"IMGXMP94" not in data
    assert fitz.open(tmp_path / "out.pdf")[0].get_images()  # the picture itself stays


def test_xfa_form_data_goes_with_form_fields_only(tmp_path):
    src = _plain(tmp_path / "in.pdf", pages=1)
    d = fitz.open(src)
    xfa = d.get_new_xref()
    d.update_object(xfa, "<<>>")
    d.update_stream(xfa, b"<xdp:xdp><xfa:datasets><name>XFADATA95</name></xfa:datasets></xdp:xdp>")
    d.xref_set_key(d.pdf_catalog(), "AcroForm", f"<</Fields[]/XFA {xfa} 0 R>>")
    d.saveIncr()
    d.close()
    doc = open_document(src)
    remove_hidden(doc, tmp_path / "default.pdf")
    remove_hidden(doc, tmp_path / "fields.pdf", SanitizeOptions(form_fields=True))
    doc.close()
    assert b"XFADATA95" in _all_bytes(tmp_path / "default.pdf")  # forms not chosen: kept
    assert b"XFADATA95" not in _all_bytes(tmp_path / "fields.pdf")
