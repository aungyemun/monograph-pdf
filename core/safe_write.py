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
#   In every case the replaced file's permission list is compared afterwards and written back if it
#   changed (ReplaceFileW does not keep a protected list on every Windows version; see below).
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


# ReplaceFileW does not keep the permissions on every Windows version: on Windows Server 2022 a file
# whose permission list is protected (inheritance switched off) gained the folder's inherited entries
# after the replacement, i.e. it became more widely accessible (Windows CI, 2026-11-09). So the
# replaced file's permission list (DACL, with its protected / inherited state) is read before the
# swap, compared afterwards and written back if Windows changed it.
_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_UNPROTECTED_DACL_SECURITY_INFORMATION = 0x20000000
_SDDL_REVISION_1 = 1


def _advapi():
    import ctypes
    from ctypes import wintypes

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD,
                                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    adv.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                                              ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    adv.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    adv.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    adv.SetNamedSecurityInfoW.restype = wintypes.DWORD
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    k32.LocalFree.restype = ctypes.c_void_p
    return ctypes, wintypes, adv, k32


def _read_dacl_sddl(path: Path) -> str | None:
    """The file's permission list as SDDL (``D:P(...)...``, flags included); None if unreadable."""
    try:
        ctypes, wintypes, adv, k32 = _advapi()
        sd = ctypes.c_void_p()
        if adv.GetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
                                     None, None, None, None, ctypes.byref(sd)) != 0:
            return None
        try:
            text = wintypes.LPWSTR()
            if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    sd, _SDDL_REVISION_1, _DACL_SECURITY_INFORMATION, ctypes.byref(text), None):
                return None
            try:
                return text.value
            finally:
                k32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        finally:
            k32.LocalFree(sd)
    except (OSError, AttributeError):
        return None


def _write_dacl_sddl(path: Path, sddl: str) -> bool:
    """Apply a permission list read by ``_read_dacl_sddl``: its explicit entries and whether
    inheritance is switched off (inherited entries are recomputed from the folder by Windows)."""
    try:
        ctypes, wintypes, adv, k32 = _advapi()
        sd = ctypes.c_void_p()
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, _SDDL_REVISION_1,
                                                                        ctypes.byref(sd), None):
            return False
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            dacl = ctypes.c_void_p()
            if not adv.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(dacl),
                                                 ctypes.byref(defaulted)) or not present:
                return False
            flags = sddl[2:sddl.find("(")] if "(" in sddl else sddl[2:]
            info = _DACL_SECURITY_INFORMATION | (_PROTECTED_DACL_SECURITY_INFORMATION if "P" in flags
                                                 else _UNPROTECTED_DACL_SECURITY_INFORMATION)
            return adv.SetNamedSecurityInfoW(str(path), _SE_FILE_OBJECT, info, None, None, dacl, None) == 0
        finally:
            k32.LocalFree(sd)
    except (OSError, AttributeError):
        return False


def _restore_dacl(path: Path, before: str | None) -> None:
    """Write the replaced file's permission list back if the replacement changed it (best effort:
    the new content is already in place, so a failure here does not fail the save)."""
    if before is None:
        return
    if _read_dacl_sddl(path) != before:
        _write_dacl_sddl(path, before)


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
        dacl = _read_dacl_sddl(destination)
        if not same_folder:
            os.replace(replacement, destination)
            _restore_dacl(destination, dacl)
            return
        code = _replace_file_w(str(destination), str(replacement))
        if code == 0:
            _restore_dacl(destination, dacl)
            return
        if code == _ERROR_UNABLE_TO_MOVE_REPLACEMENT and not destination.exists() and replacement.exists():
            # the old file is gone, the new one kept its temporary name: give it the real name
            os.replace(replacement, destination)
            _restore_dacl(destination, dacl)
            return
        if code in _NOT_SUPPORTED:
            os.replace(replacement, destination)
            _restore_dacl(destination, dacl)
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
