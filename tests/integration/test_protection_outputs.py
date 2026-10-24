"""Password-protected, digitally signed and watermarked PDFs in every output (core/security/protection.py)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.document import PasswordRequiredError, open_document

USER, OWNER = "user-pw", "owner-pw"


def _protected(path: Path, *, perms: int = fitz.PDF_PERM_PRINT, user: str = USER, owner: str = OWNER,
               pages: int = 2) -> Path:
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 100), f"Confidential page {i + 1}", fontsize=18)
    d.set_toc([[1, "Start", 1]])
    d.set_metadata({"title": "Secret title", "author": "A. Author"})
    d.save(path.as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user, owner_pw=owner, permissions=perms)
    d.close()
    return path


def _assert_still_protected(path: Path) -> None:
    with fitz.open(path.as_posix()) as d:
        assert d.needs_pass, f"{path.name} was written without its open password"
        assert d.authenticate(USER) and "256" in (d.metadata or {}).get("encryption", "")
        assert int(d.permissions) & fitz.PDF_PERM_PRINT and not int(d.permissions) & fitz.PDF_PERM_COPY


def test_permissions_follow_the_password_used(tmp_path):
    from core.security.protection import allowed, unlock_with_owner_password

    src = _protected(tmp_path / "p.pdf")
    doc = open_document(src, password=USER)
    try:
        assert allowed(doc, "print") and not allowed(doc, "copy") and not allowed(doc, "edit")
        assert not allowed(doc, "owner")
        assert not unlock_with_owner_password(doc, USER)  # the open password is not the permissions password
        assert not unlock_with_owner_password(doc, "wrong")
        assert not allowed(doc, "copy")
        assert unlock_with_owner_password(doc, OWNER)
        assert allowed(doc, "copy") and allowed(doc, "edit") and allowed(doc, "owner")
    finally:
        doc.close()
    owner_doc = open_document(src, password=OWNER)
    try:
        assert allowed(owner_doc, "copy")  # opened with the permissions password
    finally:
        owner_doc.close()


def test_unprotected_pdf_allows_everything(tmp_path):
    from core.security.protection import allowed, protection_info

    p = tmp_path / "plain.pdf"
    d = fitz.open()
    d.new_page()
    d.save(p.as_posix())
    d.close()
    doc = open_document(p)
    try:
        assert all(allowed(doc, k) for k in ("copy", "print", "edit", "assemble", "owner"))
        assert not protection_info(doc).protected and protection_info(doc).summary_lines() == []
    finally:
        doc.close()


@pytest.mark.parametrize("writer", ["copy", "metadata", "flatten", "watermark", "extract"])
def test_copies_of_a_protected_pdf_stay_protected(tmp_path, writer):
    from core.convert.copy_pdf import copy_pdf_preserving_metadata
    from core.convert.flatten_export import export_flattened_pdf
    from core.convert.page_marks import WatermarkSpec, apply_page_marks
    from core.organize.page_ops import extract_pages
    from core.security.ops import remove_metadata

    src = _protected(tmp_path / "p.pdf")
    out = tmp_path / f"{writer}.pdf"
    doc = open_document(src, password=USER)
    try:
        {
            "copy": lambda: copy_pdf_preserving_metadata(doc, out),
            "metadata": lambda: remove_metadata(doc, out),
            "flatten": lambda: export_flattened_pdf(doc, out),
            "watermark": lambda: apply_page_marks(doc, out, watermark=WatermarkSpec(text="DRAFT")),
            "extract": lambda: extract_pages(doc, [1], out),
        }[writer]()
    finally:
        doc.close()
    _assert_still_protected(out)
    with fitz.open(out.as_posix()) as d:
        d.authenticate(USER)
        if writer == "copy":
            assert d.get_toc() == [[1, "Start", 1]]  # bookmarks were lost before
            assert d.metadata["title"] == "Secret title"
        if writer == "metadata":
            assert not d.metadata.get("title") and not d.metadata.get("author")
        if writer == "extract":
            assert d.page_count == 1 and "page 2" in d[0].get_text()


def test_a_permissions_only_pdf_keeps_its_restrictions(tmp_path):
    from core.convert.copy_pdf import copy_pdf_preserving_metadata
    from core.security.protection import allowed

    src = _protected(tmp_path / "o.pdf", user="")
    doc = open_document(src)  # opens without a password
    try:
        assert not allowed(doc, "copy")
        copy_pdf_preserving_metadata(doc, tmp_path / "c.pdf")
    finally:
        doc.close()
    with fitz.open((tmp_path / "c.pdf").as_posix()) as d:
        assert not d.needs_pass
        assert (d.metadata or {}).get("encryption") and not int(d.permissions) & fitz.PDF_PERM_COPY


def test_compress_source_keeps_protection(tmp_path):
    from core.convert.compress import _source_bytes

    src = _protected(tmp_path / "p.pdf")
    doc = open_document(src, password=USER)
    try:
        data = _source_bytes(doc)
    finally:
        doc.close()
    with fitz.open("pdf", data) as d:
        assert d.needs_pass


def test_removing_restrictions_needs_the_permissions_password(tmp_path):
    from core.security.ops import remove_password_protection

    src = _protected(tmp_path / "p.pdf")
    doc = open_document(src, password=USER)
    try:
        with pytest.raises(PasswordRequiredError, match="permissions password"):
            remove_password_protection(doc, tmp_path / "x.pdf", password=USER)
        remove_password_protection(doc, tmp_path / "ok.pdf", password=OWNER)
    finally:
        doc.close()
    with fitz.open((tmp_path / "ok.pdf").as_posix()) as d:
        assert not d.needs_pass and not (d.metadata or {}).get("encryption")
    # nothing restricted: the open password may remove the protection
    free = _protected(tmp_path / "free.pdf", perms=-1)
    doc = open_document(free, password=USER)
    try:
        remove_password_protection(doc, tmp_path / "free_out.pdf", password=USER)
    finally:
        doc.close()


def _signed_like(path: Path, *, signed: bool) -> Path:
    d = fitz.open()
    page = d.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    w.field_name = "Sig1"
    w.rect = fitz.Rect(72, 700, 250, 750)
    page.add_widget(w)
    if signed:
        sig = d.get_new_xref()
        d.update_object(sig, "<</Type/Sig/Filter/Adobe.PPKLite/ByteRange[0 0 0 0]/Contents<00>>>")
        wx = next(page.widgets()).xref
        d.xref_set_key(wx, "V", f"{sig} 0 R")
    d.save(path.as_posix())
    d.close()
    return path


def test_only_signed_signature_fields_count(tmp_path):
    from core.security.protection import signed_signature_count

    with fitz.open(_signed_like(tmp_path / "empty.pdf", signed=False).as_posix()) as d:
        assert signed_signature_count(d) == 0
    with fitz.open(_signed_like(tmp_path / "signed.pdf", signed=True).as_posix()) as d:
        assert signed_signature_count(d) == 1


def test_export_can_leave_out_removable_marks_only(tmp_path):
    from core.convert.page_marks import WatermarkSpec, apply_page_marks, count_marks, lock_page_marks
    from core.security.protection import export_source_without_marks, protection_info

    plain = tmp_path / "a.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 100), "Body text", fontsize=14)
    d.save(plain.as_posix())
    d.close()
    marked = tmp_path / "m.pdf"
    doc = open_document(plain)
    try:
        apply_page_marks(doc, marked, watermark=WatermarkSpec(text="DRAFT"))
    finally:
        doc.close()
    doc = open_document(marked)
    try:
        assert protection_info(doc).marks
        clean = export_source_without_marks(doc, {"Watermark"})
        assert not any(count_marks(clean).values())
        assert "DRAFT" not in clean[0].get_text() and "Body text" in clean[0].get_text()
        clean.close()
        # a locked watermark is part of the page: it stays
        locked = fitz.open(marked.as_posix())
        lock_page_marks(locked)
        assert not any(count_marks(locked).values())
        locked.close()
    finally:
        doc.close()


def test_merge_refuses_a_restricted_source_without_the_permissions_password(tmp_path):
    from core.organize.merge import MergeJob, combine_to_pdf

    src = _protected(tmp_path / "p.pdf")
    job = MergeJob()
    s = job.add_path(src, password=USER)
    assert s.restricted and s.open_error and "Password" in s.open_error
    job2 = MergeJob()
    s2 = job2.add_path(src, password=OWNER)
    assert not s2.restricted and not s2.open_error and s2.encrypted
    combine_to_pdf(job2, tmp_path / "merged.pdf")
    assert fitz.open((tmp_path / "merged.pdf").as_posix()).page_count == 2


def test_batch_skips_a_pdf_whose_permissions_forbid_copying(tmp_path):
    from core.convert.batch import BatchItem, BatchOptions, BatchRunner

    src = _protected(tmp_path / "p.pdf")
    item = BatchItem(source=src)
    BatchRunner([item], BatchOptions(format_key="txt", output_dir=tmp_path / "out", password=lambda p: USER)).run()
    assert item.status == "failed" and "permissions" in item.message
    ok = BatchItem(source=src)
    BatchRunner([ok], BatchOptions(format_key="txt", output_dir=tmp_path / "out2", password=lambda p: OWNER)).run()
    assert ok.status == "done", ok.message
