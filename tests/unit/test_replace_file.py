"""Replacing a file keeps its attributes and permissions (0.6.0, audit finding F-11).

Before 0.6.0 every save swapped the new file in with ``os.replace``: on Windows the replaced file's
Hidden attribute and explicit access-control entries were lost, on Linux/macOS its permission bits.
Synthetic files in a temporary folder only.
"""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from core import safe_write
from core.safe_write import replace_file

WIN = sys.platform == "win32"


def _write(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


@pytest.mark.skipif(WIN, reason="POSIX permission bits")
def test_posix_permission_bits_are_kept(tmp_path):
    dest = _write(tmp_path / "doc.pdf", b"old")
    os.chmod(dest, 0o640)
    new = _write(tmp_path / ".doc.1234abcd.part", b"new")
    os.chmod(new, 0o666)
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()
    assert stat.S_IMODE(dest.stat().st_mode) == 0o640


def test_new_destination_is_a_plain_move(tmp_path):
    new = _write(tmp_path / "x.part", b"data")
    replace_file(new, tmp_path / "out.pdf")
    assert (tmp_path / "out.pdf").read_bytes() == b"data" and not new.exists()


def test_unicode_paths(tmp_path):
    folder = tmp_path / "テスト 資料 ①"
    folder.mkdir()
    dest = _write(folder / "報告書 – é.pdf", b"old")
    new = _write(folder / ".報告書 – é.abcd1234.part", b"new")
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()


# -- Windows ------------------------------------------------------------------------------------

def _attrs(p: Path) -> int:
    return os.stat(p).st_file_attributes  # type: ignore[attr-defined]


def _set_hidden(p: Path) -> None:
    import ctypes

    FILE_ATTRIBUTE_HIDDEN = 0x2
    assert ctypes.windll.kernel32.SetFileAttributesW(str(p), _attrs(p) | FILE_ATTRIBUTE_HIDDEN)


def _icacls(p: Path) -> str:
    out = subprocess.run(["icacls", str(p)], capture_output=True, text=True, check=True).stdout
    return "\n".join(line.strip() for line in out.splitlines()[:-2])  # drop the summary line


USERS_SID = "*S-1-5-32-545"  # BUILTIN\Users, by SID so it works in every display language


@pytest.mark.skipif(not WIN, reason="Windows attributes")
def test_windows_hidden_attribute_is_kept(tmp_path):
    dest = _write(tmp_path / "hidden.pdf", b"old")
    _set_hidden(dest)
    new = _write(tmp_path / ".hidden.abcd1234.part", b"new")
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()
    assert _attrs(dest) & stat.FILE_ATTRIBUTE_HIDDEN


@pytest.mark.skipif(not WIN, reason="Windows ACL")
def test_windows_explicit_acl_entry_is_kept_and_nothing_is_added(tmp_path):
    dest = _write(tmp_path / "acl.pdf", b"old")
    subprocess.run(["icacls", str(dest), "/grant", f"{USERS_SID}:(R)"], capture_output=True, check=True)
    before = _icacls(dest)
    assert "(R)" in before
    new = _write(tmp_path / ".acl.abcd1234.part", b"new")
    replace_file(new, dest)
    assert dest.read_bytes() == b"new"
    assert _icacls(dest).replace(str(dest), "") == before.replace(str(dest), "")  # same entries, no more


@pytest.mark.skipif(not WIN, reason="Windows ACL")
def test_windows_inherited_permissions_stay_inherited(tmp_path):
    dest = _write(tmp_path / "inh.pdf", b"old")
    before = _icacls(dest)
    new = _write(tmp_path / ".inh.abcd1234.part", b"new")
    replace_file(new, dest)
    assert _icacls(dest).replace(str(dest), "") == before.replace(str(dest), "")


@pytest.mark.skipif(not WIN, reason="Windows file sharing")
def test_windows_file_open_in_another_program_is_not_replaced(tmp_path):
    dest = _write(tmp_path / "open.pdf", b"old")
    new = _write(tmp_path / ".open.abcd1234.part", b"new")
    with open(dest, "rb"):  # Python opens without FILE_SHARE_DELETE, like many viewers
        with pytest.raises(PermissionError) as info:
            replace_file(new, dest)
    assert getattr(info.value, "winerror", None) in (5, 32, 33)
    assert dest.read_bytes() == b"old" and new.read_bytes() == b"new"


@pytest.mark.skipif(not WIN, reason="ReplaceFileW error handling")
def test_windows_state_old_file_gone_new_file_unmoved_is_recovered(tmp_path, monkeypatch):
    dest = _write(tmp_path / "rec.pdf", b"old")
    new = _write(tmp_path / ".rec.abcd1234.part", b"new")

    def half_done(replaced, replacement):
        os.remove(replaced)  # what Windows documents for ERROR_UNABLE_TO_MOVE_REPLACEMENT without backup
        return safe_write._ERROR_UNABLE_TO_MOVE_REPLACEMENT

    monkeypatch.setattr(safe_write, "_replace_file_w", half_done)
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()


@pytest.mark.skipif(not WIN, reason="ReplaceFileW error handling")
@pytest.mark.parametrize("code, outcome", [
    (1175, "in_use"),  # ERROR_UNABLE_TO_REMOVE_REPLACED: nothing changed
    (32, "in_use"),
    (50, "fallback"),  # not supported by the file system: plain os.replace, as before 0.6.0
    (1392, "error"),  # anything else: an error, nothing is moved
])
def test_windows_replacefile_errors(tmp_path, monkeypatch, code, outcome):
    dest = _write(tmp_path / "e.pdf", b"old")
    new = _write(tmp_path / ".e.abcd1234.part", b"new")
    monkeypatch.setattr(safe_write, "_replace_file_w", lambda a, b: code)
    if outcome == "fallback":
        replace_file(new, dest)
        assert dest.read_bytes() == b"new"
        return
    with pytest.raises(PermissionError if outcome == "in_use" else OSError):
        replace_file(new, dest)
    assert dest.read_bytes() == b"old" and new.read_bytes() == b"new"


@pytest.mark.skipif(not WIN, reason="Windows attributes")
def test_windows_replacement_from_another_folder_uses_os_replace(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(safe_write, "_replace_file_w", lambda a, b: called.append(1) or 0)
    (tmp_path / "a").mkdir()
    dest = _write(tmp_path / "doc.pdf", b"old")
    new = _write(tmp_path / "a" / "x.tmp", b"new")
    replace_file(new, dest)
    assert not called and dest.read_bytes() == b"new"


@pytest.mark.skipif(not WIN, reason="Windows attributes")
def test_save_writers_keep_the_hidden_attribute(tmp_path):
    import fitz

    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_via_backend

    src = tmp_path / "src.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "content")
    d.save(src)
    d.close()
    for name, write in (
        ("save_as", lambda doc, dest: doc.save_as(dest)),
        ("bake", lambda doc, dest: bake_via_backend(EditableDocument(doc), dest)),
    ):
        dest = _write(tmp_path / f"{name}.pdf", b"%PDF-1.4 old")
        _set_hidden(dest)
        doc = open_document(src)
        try:
            write(doc, dest)
        finally:
            doc.close()
        assert _attrs(dest) & stat.FILE_ATTRIBUTE_HIDDEN, name
        assert dest.read_bytes().startswith(b"%PDF") and b"old" not in dest.read_bytes()[:20]


def test_read_only_is_still_refused_first(tmp_path):
    import fitz

    from core.safe_write import save_pdf_atomic

    dest = _write(tmp_path / "ro.pdf", b"old")
    os.chmod(dest, stat.S_IREAD)
    try:
        d = fitz.open()
        d.new_page()
        with pytest.raises(PermissionError) as info:
            save_pdf_atomic(d, dest)
        assert info.value.errno == errno.EACCES
        assert dest.read_bytes() == b"old"
    finally:
        os.chmod(dest, stat.S_IREAD | stat.S_IWRITE)


# ReplaceFileW does not keep a protected permission list on every Windows version (Windows Server 2022
# CI, 2026-11-09: the file gained the folder's inherited entries). These tests swap in a file that
# lost its permissions (plain os.replace) and check that replace_file writes the list back.

def _replace_losing_permissions(replaced, replacement):
    os.replace(replacement, replaced)  # the new file keeps its own, folder-inherited permissions
    return 0


@pytest.mark.skipif(not WIN, reason="Windows ACL")
def test_windows_protected_permissions_are_restored_when_windows_drops_them(tmp_path, monkeypatch):
    dest = _write(tmp_path / "prot.pdf", b"old")
    # inheritance off, the inherited entries copied as explicit ones, one entry removed: a restricted file
    subprocess.run(["icacls", str(dest), "/inheritance:d"], capture_output=True, check=True)
    subprocess.run(["icacls", str(dest), "/remove:g", USERS_SID], capture_output=True, check=True)
    before = _icacls(dest)
    assert "(I)" not in before
    monkeypatch.setattr(safe_write, "_replace_file_w", _replace_losing_permissions)
    new = _write(tmp_path / ".prot.abcd1234.part", b"new")
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()
    assert _icacls(dest).replace(str(dest), "") == before.replace(str(dest), "")
    assert safe_write._read_dacl_sddl(dest).startswith("D:P")


@pytest.mark.skipif(not WIN, reason="Windows ACL")
def test_windows_explicit_entry_is_restored_when_windows_drops_it(tmp_path, monkeypatch):
    dest = _write(tmp_path / "expl.pdf", b"old")
    subprocess.run(["icacls", str(dest), "/grant", f"{USERS_SID}:(R)"], capture_output=True, check=True)
    before = _icacls(dest)
    monkeypatch.setattr(safe_write, "_replace_file_w", _replace_losing_permissions)
    new = _write(tmp_path / ".expl.abcd1234.part", b"new")
    replace_file(new, dest)
    assert _icacls(dest).replace(str(dest), "") == before.replace(str(dest), "")


@pytest.mark.skipif(not WIN, reason="Windows ACL")
def test_windows_unreadable_permissions_never_fail_the_save(tmp_path, monkeypatch):
    dest = _write(tmp_path / "u.pdf", b"old")
    monkeypatch.setattr(safe_write, "_read_dacl_sddl", lambda p: None)
    new = _write(tmp_path / ".u.abcd1234.part", b"new")
    replace_file(new, dest)
    assert dest.read_bytes() == b"new" and not new.exists()
