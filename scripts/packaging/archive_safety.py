"""Path-safety helpers for source-archive and build-time extraction."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def assert_safe_member(name: str) -> str:
    """Reject absolute paths, drive letters, backslashes and ``..`` traversal."""
    if not name or name.endswith("/") or name.endswith("\\"):
        # directory markers are allowed only if their path parts are safe
        trimmed = name.rstrip("/\\")
        if not trimmed:
            raise ValueError("empty archive member name")
        assert_safe_member(trimmed)
        return name
    if "\\" in name:
        raise ValueError(f"unsafe archive member (backslash): {name!r}")
    if name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"unsafe archive member (absolute): {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or pure.anchor:
        raise ValueError(f"unsafe archive member (absolute): {name!r}")
    if ".." in pure.parts:
        raise ValueError(f"unsafe archive member (parent segment): {name!r}")
    if any(p.startswith(":") or (len(p) >= 2 and p[1] == ":") for p in pure.parts):
        raise ValueError(f"unsafe archive member (drive): {name!r}")
    return name


def _contained(dest: Path, target: Path) -> bool:
    try:
        target.relative_to(dest)
        return True
    except ValueError:
        return False


def safe_extract_zip(archive: Path, dest: Path) -> list[Path]:
    """Extract a ZIP into ``dest``, refusing path-traversal members."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = assert_safe_member(info.filename)
            target = (dest / name).resolve()
            if not _contained(dest, target):
                raise ValueError(f"unsafe archive member escapes destination: {name!r}")
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            written.append(target)
    return written


def safe_extract_tar(archive: Path, dest: Path) -> list[Path]:
    """Extract a tar/tar.gz into ``dest``, refusing path-traversal members."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            name = assert_safe_member(member.name)
            target = (dest / name).resolve()
            if not _contained(dest, target):
                raise ValueError(f"unsafe archive member escapes destination: {name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"refusing non-regular archive member: {name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise ValueError(f"cannot read archive member: {name!r}")
            with src, open(target, "wb") as out:
                out.write(src.read())
            written.append(target)
    return written
