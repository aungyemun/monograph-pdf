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
