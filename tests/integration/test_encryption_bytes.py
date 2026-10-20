"""Password protection checked in the written bytes, not only through the PDF library.

A protected copy must not contain any of the document's strings or stream data in readable form
(page text, properties, XMP, comments, form values, attachment contents), must use the chosen
cipher, must not carry earlier revisions of the source, and must still hold all of it once opened
with the password. Removing protection must give a truly unencrypted file.
"""

from __future__ import annotations

import re

import fitz
import pytest

from core.document import PasswordRequiredError, open_document
from core.security.ops import (
    EncryptionSettings,
    PermissionFlags,
    apply_password_protection,
    remove_password_protection,
)

TOKENS = {
    "page": b"PAGETEXT31",
    "title": b"TITLEINFO32",
    "xmp": b"XMPDATA33",
    "comment": b"COMMENT34",
    "field": b"FIELDVALUE35",
    "attachment": b"ATTACHED36",
}
OLD = b"OLDREVISION37"


def _source(path):
    d = fitz.open()
    page = d.new_page()
    # A literal (not hex) string in the content stream, so the token is findable in plain bytes.
    page.insert_text((72, 72), "x")
    xref = page.get_contents()[0]
    d.update_stream(xref, b"BT /F1 12 Tf 72 700 Td (" + TOKENS["page"] + b") Tj ET", compress=False)
    d.save(path, deflate=False)
    d.close()
    d = fitz.open(path)
    d.set_metadata({"title": TOKENS["title"].decode(), "subject": OLD.decode()})
    d.saveIncr()
    d.close()
    d = fitz.open(path)  # second revision: the old subject stays in the file's history
    d.set_metadata({"title": TOKENS["title"].decode(), "subject": "current"})
    d.set_xml_metadata(f"<x:xmpmeta xmlns:x='adobe:ns:meta/'>{TOKENS['xmp'].decode()}</x:xmpmeta>")
    page = d[0]
    page.add_text_annot((100, 100), TOKENS["comment"].decode())
    w = fitz.Widget()
    w.field_name, w.field_type = "name", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 150, 250, 170), TOKENS["field"].decode()
    page.add_widget(w)
    d.embfile_add("notes.txt", TOKENS["attachment"] + b" contents")
    d.saveIncr()
    d.close()
    return path


def _decoded_bytes(doc: fitz.Document) -> bytes:
    parts = []
    for x in range(1, doc.xref_length()):
        try:
            parts.append(doc.xref_object(x).encode("latin-1", "replace"))
            if doc.xref_is_stream(x):
                parts.append(doc.xref_stream(x) or b"")
        except Exception:  # noqa: BLE001
            continue
    return b"\n".join(parts)


def _raw_and_inflated(path) -> bytes:
    """The raw file plus every Flate stream inflated *without* decrypting: what anyone can read."""
    import zlib

    raw = path.read_bytes()
    parts = [raw]
    for m in re.finditer(rb"stream\r?\n", raw):
        chunk = raw[m.end():m.end() + 2_000_000]
        try:
            parts.append(zlib.decompressobj().decompress(chunk))
        except zlib.error:
            continue  # encrypted data is not a valid Flate stream
    return b"\n".join(parts)


@pytest.fixture
def source(tmp_path):
    src = _source(tmp_path / "in.pdf")
    raw = src.read_bytes()
    plain = _decoded_bytes(fitz.open(src))
    for name, token in TOKENS.items():
        assert token in plain, name  # the test document really contains every kind of data
    assert OLD in raw  # and an earlier revision
    return src


@pytest.mark.parametrize("algorithm,v,r", [("AES-256", 5, 6), ("AES-128", 4, 4)])
def test_protected_copy_has_no_readable_content_and_uses_the_chosen_cipher(tmp_path, source, algorithm, v, r):
    out = tmp_path / "protected.pdf"
    pdf = open_document(source)
    try:
        apply_password_protection(pdf, out, EncryptionSettings(
            user_password="open-pw", owner_password="owner-pw", algorithm=algorithm,
            permissions=PermissionFlags(print=True, copy=False, modify=False, annotate=False)))
    finally:
        pdf.close()

    readable = _raw_and_inflated(out)
    for name, token in TOKENS.items():
        assert token not in readable, f"{name} readable without the password"
    assert OLD not in readable  # no earlier revision carried over

    d = fitz.open(out)
    try:
        enc = d.xref_get_key(-1, "Encrypt")
        assert enc[0] in ("xref", "dict")
        assert d.xref_get_key(-1, "Encrypt/V") == ("int", str(v))
        assert d.xref_get_key(-1, "Encrypt/R") == ("int", str(r))
        assert d.needs_pass
        assert not d.authenticate("wrong")
    finally:
        d.close()

    with pytest.raises(PasswordRequiredError):
        open_document(out)
    d = fitz.open(out)
    try:
        assert d.authenticate("open-pw") == 2  # 2 = opened with the user (open) password
        perms = d.permissions  # what a reader opening with the open password is allowed
        assert perms & fitz.PDF_PERM_PRINT and not perms & fitz.PDF_PERM_COPY
        assert not perms & fitz.PDF_PERM_MODIFY and not perms & fitz.PDF_PERM_ANNOTATE
        plain = _decoded_bytes(d)
        for name, token in TOKENS.items():
            assert token in plain, f"{name} lost by protecting"  # kept, only encrypted
        assert OLD not in plain
    finally:
        d.close()


def test_removing_protection_gives_an_unencrypted_file(tmp_path, source):
    protected = tmp_path / "protected.pdf"
    pdf = open_document(source)
    try:
        apply_password_protection(pdf, protected, EncryptionSettings(user_password="open-pw", owner_password="owner-pw"))
    finally:
        pdf.close()
    locked = open_document(protected, password="owner-pw")
    try:
        with pytest.raises(PasswordRequiredError):
            remove_password_protection(locked, tmp_path / "nope.pdf", password="wrong")
        assert not (tmp_path / "nope.pdf").exists()
        remove_password_protection(locked, tmp_path / "open.pdf", password="owner-pw")
    finally:
        locked.close()
    d = fitz.open(tmp_path / "open.pdf")
    try:
        assert not d.needs_pass and not d.is_encrypted
        assert d.xref_get_key(-1, "Encrypt")[0] == "null"
        plain = _decoded_bytes(d)
        for name, token in TOKENS.items():
            assert token in plain, name
    finally:
        d.close()
    reopened = open_document(tmp_path / "open.pdf")
    try:
        assert reopened.metadata().encrypted is False
    finally:
        reopened.close()
