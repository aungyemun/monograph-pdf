"""Temporary files left by an interrupted save are found narrowly and never deleted (0.6.0, F-13)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from core.leftover_temps import MIN_AGE_SECONDS, find_leftovers
from core.safe_write import temporary_sibling


def _file(p: Path, data: bytes = b"partial", age: float = MIN_AGE_SECONDS + 60) -> Path:
    p.write_bytes(data)
    t = time.time() - age
    os.utime(p, (t, t))
    return p


def test_only_this_documents_own_temporary_names_are_found(tmp_path):
    doc = _file(tmp_path / "Report 2026.pdf", b"%PDF-1.7 doc", age=0)
    ours = [
        _file(tmp_path / ".Report 2026.0a1b2c3d.part"),
        _file(tmp_path / ".Report 2026.saving-deadbeef.pdf", b"%PDF-1.7\n...\n%%EOF\n"),
        _file(tmp_path / ".Report 2026.pdf.12345678.part"),
        _file(tmp_path / ".Report 2026.abcdef01.part.pdf"),
    ]
    not_ours = [
        _file(tmp_path / ".Other.0a1b2c3d.part"),  # another document's
        _file(tmp_path / "Report 2026.0a1b2c3d.part"),  # no leading dot
        _file(tmp_path / ".Report 2026.0a1b2c3.part"),  # 7 hex digits
        _file(tmp_path / ".Report 2026.part"),
        _file(tmp_path / ".Report 2026.0a1b2c3d.part.bak"),
        _file(tmp_path / "notes.txt"),
    ]
    (tmp_path / ".Report 2026.11111111.part").mkdir()  # a folder with the right name
    found = {x.path for x in find_leftovers(doc)}
    assert found == set(ours)
    assert not found & set(not_ours)
    complete = {x.path.name: x.complete_pdf for x in find_leftovers(doc)}
    assert complete[".Report 2026.saving-deadbeef.pdf"] is True
    assert complete[".Report 2026.0a1b2c3d.part"] is False


def test_recent_files_of_a_save_in_progress_are_not_listed(tmp_path):
    doc = _file(tmp_path / "a.pdf", age=0)
    _file(tmp_path / ".a.0a1b2c3d.part", age=5)  # another window may be writing it right now
    assert find_leftovers(doc) == []


def test_the_names_the_writers_use_are_recognised(tmp_path):
    doc = _file(tmp_path / "名前 ①.pdf", age=0)
    part = _file(temporary_sibling(doc))
    assert [x.path for x in find_leftovers(doc)] == [part]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_links_are_ignored(tmp_path):
    doc = _file(tmp_path / "a.pdf", age=0)
    target = _file(tmp_path / "elsewhere.bin")
    link = tmp_path / ".a.0a1b2c3d.part"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted")
    assert find_leftovers(doc) == []


def test_finding_never_deletes_or_changes_anything(tmp_path):
    doc = _file(tmp_path / "a.pdf", age=0)
    part = _file(tmp_path / ".a.0a1b2c3d.part", b"data")
    before = (part.read_bytes(), part.stat().st_mtime)
    find_leftovers(doc)
    assert (part.read_bytes(), part.stat().st_mtime) == before
