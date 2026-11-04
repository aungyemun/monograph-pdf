"""A failed PDF write never damages the file that was there before (Phase 1 reliability audit).

Error injection: every ``fitz.Document.save`` to a file writes part of a file and then fails with
"No space left on device", as a full disk or a pulled-out drive would. Before the fix, Apply Redaction,
Remove Hidden Information, Protect, Remove Password, Extract Pages, Images to PDF and copies made with
``protection.save_copy`` wrote straight onto the chosen file: the existing file was destroyed and a
truncated PDF left in its place.
"""

from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path

import fitz
import pytest


def _pdf(path: Path, pages: int = 2, text: str = "SECRET-ALPHA") -> Path:
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"page {i + 1} {text}")
    d.set_metadata({"title": "t", "author": "a"})
    d.save(path)
    d.close()
    return path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def disk_full(monkeypatch):
    """Call the returned function to make every later save to a file fail part-way."""
    real = fitz.Document.save

    def failing(self, filename, *a, **k):
        if not isinstance(filename, (str, os.PathLike)):
            return real(self, filename, *a, **k)  # in-memory copies are not disk writes
        Path(os.fspath(filename)).write_bytes(b"%PDF-1.7\n% partial\n" * 100)
        raise OSError(errno.ENOSPC, "No space left on device", os.fspath(filename))

    return lambda: monkeypatch.setattr(fitz.Document, "save", failing)


def _open(path: Path):
    from core.document import open_document

    return open_document(path)


def _writers():
    from core.convert.images_to_pdf import images_to_pdf  # noqa: F401 — imported for its presence
    from core.organize.page_ops import extract_pages
    from core.redaction import apply_redactions, mark_text
    from core.security.ops import EncryptionSettings, apply_password_protection
    from core.security.protection import save_copy, working_copy
    from core.security.sanitize import SanitizeOptions, remove_hidden

    def redact(doc, dest):
        mark_text(doc, 0, "SECRET-ALPHA")
        apply_redactions(doc, dest)

    return {
        "apply redaction": redact,
        "remove hidden information": lambda doc, dest: remove_hidden(doc, dest, SanitizeOptions.everything()),
        "protect with a password": lambda doc, dest: apply_password_protection(
            doc, dest, EncryptionSettings(user_password="u", owner_password="o")),
        "extract pages": lambda doc, dest: extract_pages(doc, [0], dest),
        "save_copy (exports)": lambda doc, dest: save_copy(working_copy(doc), dest),
        "backend save_as": lambda doc, dest: doc.save_as(dest),
    }


@pytest.mark.parametrize("name", list(_writers()))
def test_a_failed_write_keeps_the_existing_file(tmp_path, disk_full, name):
    src = _pdf(tmp_path / "src.pdf")
    dest = _pdf(tmp_path / "existing.pdf", pages=5, text="keep me")
    before = _sha(dest)
    doc = _open(src)
    disk_full()
    try:
        with pytest.raises(OSError):
            _writers()[name](doc, dest)
    finally:
        doc.close()
    assert _sha(dest) == before, f"{name}: the existing file was damaged by the failed write"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.pdf", "src.pdf"], "temporary file left behind"


@pytest.mark.parametrize("name", list(_writers()))
def test_a_failed_write_leaves_no_new_file(tmp_path, disk_full, name):
    src = _pdf(tmp_path / "src.pdf")
    dest = tmp_path / "new.pdf"
    doc = _open(src)
    disk_full()
    try:
        with pytest.raises(OSError):
            _writers()[name](doc, dest)
    finally:
        doc.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src.pdf"], "partial or temporary file left behind"


def test_images_to_pdf_failed_write_keeps_the_existing_file(tmp_path, disk_full):
    from PIL import Image

    from core.convert.images_to_pdf import images_to_pdf

    img = tmp_path / "a.png"
    Image.new("RGB", (40, 30), (200, 10, 10)).save(img)
    dest = _pdf(tmp_path / "existing.pdf")
    before = _sha(dest)
    disk_full()
    with pytest.raises(OSError):
        images_to_pdf([img], dest)
    assert _sha(dest) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.png", "existing.pdf"]


@pytest.mark.parametrize("name", list(_writers()))
def test_a_successful_write_replaces_the_existing_file(tmp_path, name):
    src = _pdf(tmp_path / "src.pdf")
    dest = _pdf(tmp_path / "existing.pdf", pages=5, text="old content")
    doc = _open(src)
    try:
        _writers()[name](doc, dest)
    finally:
        doc.close()
    with fitz.open(dest) as d:
        if d.needs_pass:
            assert d.authenticate("o")
        assert d.page_count in (1, 2)  # the new content (one page for extract pages)
        assert "old content" not in d[0].get_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.pdf", "src.pdf"]


@pytest.mark.parametrize("name", [*_writers(), "save as (bake)"])
def test_a_read_only_destination_is_refused_on_every_platform(tmp_path, name):
    """Phase 1.1 finding F-10: on Linux and macOS ``os.replace`` replaces a read-only file (only the
    folder's permissions count), so writing through a temporary file silently replaced read-only PDFs
    that writing in place had refused. Checked through the file's mode, so it also holds for root."""
    import stat

    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_via_backend

    src = _pdf(tmp_path / "src.pdf")
    dest = _pdf(tmp_path / "existing.pdf", pages=5, text="keep me")
    before = _sha(dest)
    os.chmod(dest, stat.S_IREAD)
    doc = _open(src)
    try:
        with pytest.raises(PermissionError):
            if name == "save as (bake)":
                bake_via_backend(EditableDocument(doc), dest)
            else:
                _writers()[name](doc, dest)
    finally:
        doc.close()
        os.chmod(dest, stat.S_IREAD | stat.S_IWRITE)
    assert _sha(dest) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.pdf", "src.pdf"]
