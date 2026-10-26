"""Path-safety checks for source-archive extraction helpers."""

from __future__ import annotations

import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import archive_safety as safety  # noqa: E402

sys.path.remove(str(ROOT / "scripts" / "packaging"))


@pytest.mark.parametrize(
    "name",
    ["../evil", "/abs/path", "a/../../b", "C:/windows", "dir\\file", ""],
)
def test_unsafe_member_names_rejected(name):
    with pytest.raises(ValueError):
        safety.assert_safe_member(name)


def test_safe_zip_extract_and_traversal_blocked(tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("pkg/readme.txt", "ok")
        z.writestr("pkg/日本語.txt", "こんにちは")
    dest = tmp_path / "out"
    written = safety.safe_extract_zip(good, dest)
    assert (dest / "pkg" / "readme.txt").read_text(encoding="utf-8") == "ok"
    assert (dest / "pkg" / "日本語.txt").read_text(encoding="utf-8") == "こんにちは"
    assert len(written) == 2

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escape.txt", "nope")
    with pytest.raises(ValueError, match="unsafe"):
        safety.safe_extract_zip(evil, dest)


def test_safe_tar_extract_and_traversal_blocked(tmp_path):
    good = tmp_path / "good.tar.gz"
    with tarfile.open(good, "w:gz") as tf:
        data = b"payload"
        info = tarfile.TarInfo("nested/file.bin")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    written = safety.safe_extract_tar(good, dest)
    assert (dest / "nested" / "file.bin").read_bytes() == b"payload"
    assert written

    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as tf:
        info = tarfile.TarInfo("../escape.bin")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe"):
        safety.safe_extract_tar(evil, dest)
