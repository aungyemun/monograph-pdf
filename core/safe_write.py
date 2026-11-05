"""Write a PDF so that a failed write never damages an existing file (Phase 1 reliability audit).

Before this, several commands (Apply Redaction, Remove Hidden Information, Protect, Remove Password,
Extract Pages, Images to PDF, copies made through ``protection.save_copy``) wrote straight onto the chosen
file. When writing failed part-way — disk full, a removable drive pulled out, a network share gone —
the file that was there before was already overwritten and a truncated PDF was left in its place.

``save_pdf_atomic`` writes a temporary file in the destination's folder, flushes it to the disk, and
only then replaces the destination in one step (``replace_file``: ``os.replace``, keeping the replaced
file's attributes and permissions). If anything fails, the temporary file
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


# --- replacing a file while keeping its attributes and permissions (0.6.0, audit finding F-11) ----
#
# ``os.replace`` swaps in the new file as it is: on Windows the replaced file's Hidden / System /
# Archive attributes and any explicit access-control entries were lost (the new file inherits the
# folder's permissions), on Linux and macOS its permission bits. ``replace_file`` keeps them:
#
# * Windows: ``ReplaceFileW`` (the API Windows provides for exactly this), only when both files are
#   in the same folder (same volume). It keeps the replaced file's attributes, security descriptor
#   (ACL), creation time and alternate data streams. Errors keep the safety of ``os.replace``: when
#   the replaced file cannot be removed (in use) nothing has changed and ``PermissionError`` is
#   raised, as before; in the documented state where the old file is already gone but the new one
#   could not take its name, the new file is moved into place with ``os.replace`` (nothing is lost).
#   Where ReplaceFileW is not supported (some network file systems) ``os.replace`` is used as before.
# * Linux / macOS: the replaced file's permission bits are copied to the new file before the rename.
#   Ownership, extended attributes and POSIX ACLs are not copied (that needs privileges or is
#   file-system specific); the new file belongs to the user saving it, as before.
#
# Never used to *weaken* anything: read-only destinations are refused before (``refuse_read_only``),
# and only the replaced file's own attributes are carried over.

_ERROR_UNABLE_TO_REMOVE_REPLACED = 1175
_ERROR_UNABLE_TO_MOVE_REPLACEMENT = 1176
_ERROR_UNABLE_TO_MOVE_REPLACEMENT_2 = 1177
_NOT_SUPPORTED = {1, 50, 87, 120}  # invalid function, not supported, invalid parameter, not implemented
_IN_USE = {5, 32, 33}  # access denied, sharing violation, lock violation


def _replace_file_w(replaced: str, replacement: str) -> int:
    """Call ``ReplaceFileW``; 0 on success, else the Windows error code (tests replace this)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = k32.ReplaceFileW
    fn.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                   wintypes.LPVOID, wintypes.LPVOID]
    fn.restype = wintypes.BOOL
    if fn(replaced, replacement, None, 0, None, None):
        return 0
    return ctypes.get_last_error() or 1


def _in_use_error(destination: Path, code: int) -> PermissionError:
    exc = PermissionError(errno.EACCES, "The file is in use by another program", str(destination))
    try:
        exc.winerror = 32 if code in (_ERROR_UNABLE_TO_REMOVE_REPLACED, 32, 33) else code  # read by save_errors
    except AttributeError:  # pragma: no cover — platforms without the attribute
        pass
    return exc


def replace_file(replacement: Path | str, destination: Path | str) -> None:
    """Move ``replacement`` onto ``destination`` like ``os.replace``, keeping the replaced file's
    attributes and permissions where the platform allows it (see above)."""
    replacement, destination = Path(replacement), Path(destination)
    if not destination.exists():
        os.replace(replacement, destination)
        return
    same_folder = os.path.normcase(os.path.abspath(replacement.parent)) == \
        os.path.normcase(os.path.abspath(destination.parent))
    if os.name == "nt":
        if not same_folder:
            os.replace(replacement, destination)
            return
        code = _replace_file_w(str(destination), str(replacement))
        if code == 0:
            return
        if code == _ERROR_UNABLE_TO_MOVE_REPLACEMENT and not destination.exists() and replacement.exists():
            # the old file is gone, the new one kept its temporary name: give it the real name
            os.replace(replacement, destination)
            return
        if code in _NOT_SUPPORTED:
            os.replace(replacement, destination)
            return
        if code in _IN_USE or code == _ERROR_UNABLE_TO_REMOVE_REPLACED:
            raise _in_use_error(destination, code)
        import ctypes

        raise ctypes.WinError(code)
    try:
        mode = os.stat(destination).st_mode
        os.chmod(replacement, mode & 0o7777)
    except OSError:
        pass  # keep the default permissions rather than fail the save
    os.replace(replacement, destination)


def save_pdf_atomic(doc, destination: Path | str, **save_kwargs) -> Path:
    """``doc.save(destination, **save_kwargs)`` without ever leaving a damaged or partial file."""
    destination = Path(destination)
    refuse_read_only(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = temporary_sibling(destination)
    try:
        doc.save(part.as_posix(), **save_kwargs)
        flush_to_disk(part)
        replace_file(part, destination)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return destination
