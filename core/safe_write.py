"""Write a PDF so that a failed write never damages an existing file (Phase 1 reliability audit).

Before this, several commands (Apply Redaction, Remove Hidden Information, Protect, Remove Password,
Extract Pages, Images to PDF, copies made through ``protection.save_copy``) wrote straight onto the chosen
file. When writing failed part-way — disk full, a removable drive pulled out, a network share gone —
the file that was there before was already overwritten and a truncated PDF was left in its place.

``save_pdf_atomic`` writes a temporary file in the destination's folder, flushes it to the disk, and
only then replaces the destination in one step (``os.replace``). If anything fails, the temporary file
is removed and the destination is exactly as it was (or still absent).
"""

from __future__ import annotations

import errno
import os
import uuid
from pathlib import Path


def flush_to_disk(path: Path) -> None:
    """Ask the operating system to write ``path``'s data to the disk (not only to its cache) before it
    is swapped in. This narrows, but does not close, the window in which a power cut could leave an
    empty or partial file: the rename itself is not flushed (no folder fsync; on Windows ``os.replace``
    does not use MOVEFILE_WRITE_THROUGH), and drive caches may still hold data."""
    try:
        with open(path, "rb+") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass  # best effort: some file systems (network shares) do not support it


def temporary_sibling(destination: Path) -> Path:
    """A unique temporary name in the same folder (``os.replace`` is atomic only within one volume)."""
    destination = Path(destination)
    return destination.with_name(f".{destination.stem}.{uuid.uuid4().hex[:8]}.part")


def refuse_read_only(destination: Path) -> None:
    """Raise ``PermissionError`` when ``destination`` exists and is marked read-only.

    Writing in place used to fail on a read-only file by itself. Swapping a new file in with
    ``os.replace`` does not on Linux and macOS (only the folder's permissions are checked there), so a
    read-only file would be replaced without a word; the check keeps the old behaviour everywhere."""
    from core.save_errors import _read_only

    if destination.exists() and _read_only(destination):
        raise PermissionError(errno.EACCES, "The file is read-only", str(destination))


def save_pdf_atomic(doc, destination: Path | str, **save_kwargs) -> Path:
    """``doc.save(destination, **save_kwargs)`` without ever leaving a damaged or partial file."""
    destination = Path(destination)
    refuse_read_only(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = temporary_sibling(destination)
    try:
        doc.save(part.as_posix(), **save_kwargs)
        flush_to_disk(part)
        os.replace(part, destination)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return destination
