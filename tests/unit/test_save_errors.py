"""Plain-language save errors and the atomic byte-for-byte copy (0.5.1)."""

from __future__ import annotations

import errno
import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.save_errors import explain_save_error
from core.security.protection import copy_file_exactly


def _err(cls, err=None, winerror=None):
    e = cls(err or 0, "x")
    if winerror is not None:
        e.winerror = winerror
    return e


def test_disk_full(tmp_path):
    msg, hint = explain_save_error(OSError(errno.ENOSPC, "No space left on device"), tmp_path / "a.pdf")
    assert "not enough free space" in msg and "“a.pdf”" in msg


def test_in_use_and_read_only_and_permission(tmp_path, monkeypatch):
    dest = tmp_path / "B.pdf"
    dest.write_bytes(b"%PDF-1.7\n")
    msg, hint = explain_save_error(_err(PermissionError, winerror=32), dest)
    assert "in use by another program" in msg and "not changed" in hint
    monkeypatch.setattr("core.save_errors._read_only", lambda p: True)
    msg, _ = explain_save_error(_err(PermissionError, winerror=5), dest)
    assert "read-only" in msg
    monkeypatch.setattr("core.save_errors.os.access", lambda *a: False)
    msg, _ = explain_save_error(_err(PermissionError, winerror=5), tmp_path / "new.pdf")
    assert "permission to save files" in msg


def test_messages_never_name_internal_temporary_files(tmp_path):
    e = PermissionError(13, "Access is denied")
    e.filename, e.filename2 = str(tmp_path / ".B.24e39fad.part"), str(tmp_path / "B.pdf")
    (tmp_path / "B.pdf").write_bytes(b"x")
    msg, hint = explain_save_error(e, tmp_path / "B.pdf")
    assert ".part" not in msg + hint and "Access is denied" not in msg


def test_missing_folder(tmp_path):
    msg, _ = explain_save_error(FileNotFoundError(2, "nope"), tmp_path / "gone" / "a.pdf")
    assert "does not exist" in msg


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_copy_file_exactly_replaces_atomically(tmp_path):
    src, dst = tmp_path / "src.pdf", tmp_path / "dst.pdf"
    src.write_bytes(b"%PDF-source")
    dst.write_bytes(b"%PDF-old")
    copy_file_exactly(SimpleNamespace(path=src), dst)
    assert dst.read_bytes() == b"%PDF-source"
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".part"]


@pytest.mark.parametrize("existing", [True, False])
def test_copy_file_exactly_failure_keeps_or_removes(tmp_path, monkeypatch, existing):
    src, dst = tmp_path / "src.pdf", tmp_path / "dst.pdf"
    src.write_bytes(b"%PDF-source" * 100)
    if existing:
        dst.write_bytes(b"%PDF-old")
        before = _sha(dst)

    def partial(a, b, *x, **k):
        Path(b).write_bytes(Path(a).read_bytes()[:10])
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(shutil, "copyfile", partial)
    with pytest.raises(OSError):
        copy_file_exactly(SimpleNamespace(path=src), dst)
    if existing:
        assert _sha(dst) == before  # 0.5.0 left a 10-byte, unreadable file here
    else:
        assert not dst.exists()
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".part"]
