"""A PDF with only a permissions (owner) password opens without a password. Monograph PDF must report
its restrictions truthfully and keep them (and the owner password) when saving — it used to show
"every action allowed" and silently save an unprotected file."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

OWNER = "owner-secret"


@pytest.fixture
def restricted(tmp_path) -> Path:
    src = tmp_path / "restricted.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Original text", fontsize=12)
    doc.save(src, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=OWNER, user_pw="",
             permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY)
    doc.close()
    return src


def _check_still_restricted(path: Path, *, text: str) -> None:
    with fitz.open(path) as out:
        assert not out.needs_pass, "must still open without a password"
        assert out.metadata.get("encryption"), "protection was removed on save"
        assert not out.permissions & fitz.PDF_PERM_COPY and out.permissions & fitz.PDF_PERM_PRINT
        assert text in out[0].get_text()
        assert out.authenticate(OWNER) == 4, "the owner password must be kept"


def test_restrictions_are_reported(restricted):
    from core.document import open_document
    from core.security import inspect_permissions

    document = open_document(restricted)
    try:
        meta = document.metadata()
        assert meta.encrypted
        assert meta.permissions["print"] and not meta.permissions["copy"] and not meta.permissions["edit"]
        flags = inspect_permissions(document)
        assert flags.print and not flags.copy and not flags.modify and not flags.annotate
    finally:
        document.close()


def test_unprotected_pdf_still_allows_everything(tmp_path):
    from core.document import open_document

    src = tmp_path / "plain.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(src)
    doc.close()
    document = open_document(src)
    try:
        meta = document.metadata()
        assert not meta.encrypted and all(meta.permissions.values())
    finally:
        document.close()


def test_save_with_edits_keeps_owner_password_and_restrictions(restricted, tmp_path):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Rect
    from engines.bake_edits import bake_via_backend

    document = open_document(restricted)
    try:
        edit = EditableDocument(document)
        edit.create_text_box(0, Rect(72, 200, 160, 30), text="Added words")
        out = tmp_path / "saved.pdf"
        bake_via_backend(edit, out)
    finally:
        document.close()
    _check_still_restricted(out, text="Added words")


def test_page_undo_snapshot_keeps_the_protection(restricted, tmp_path):
    from core.document import open_document
    from engines.mupdf_backend import restore_bytes, snapshot_bytes

    document = open_document(restricted)
    try:
        backend = document._backend  # noqa: SLF001
        restore_bytes(backend, snapshot_bytes(backend))
        out = tmp_path / "after_undo.pdf"
        backend.save_as(out)
    finally:
        document.close()
    _check_still_restricted(out, text="Original text")
