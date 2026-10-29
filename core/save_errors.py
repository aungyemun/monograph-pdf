"""Plain-language explanations for a save that failed because of the file system.

Every save path writes to a temporary file beside the destination and swaps it in (or writes a new
file and removes it again on failure), so when one of these errors is reported the existing file has
not been changed. 0.5.0 showed Windows' own text plus a generic hint, for example
"[WinError 5] Access is denied: '…\\.B.24e39fad.part' -> '…\\B.pdf' — Pick a writable folder", which
named an internal temporary file and pointed users at the wrong cause.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

# Windows error codes (winerror) that mean "someone else has the file open"
_IN_USE = {32, 33}  # ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION
_ACCESS_DENIED = 5
_DISK_FULL = {39, 112}  # ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL


def _read_only(path: Path) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_READONLY", 1)) or not (st.st_mode & stat.S_IWRITE)


def explain_save_error(exc: BaseException, destination: Path) -> tuple[str, str]:
    """``(message, hint)`` for a failed save to ``destination``."""
    dest = Path(destination)
    name = f"“{dest.name}”"
    winerror = getattr(exc, "winerror", None)
    err = getattr(exc, "errno", None)
    unchanged = " The existing file was not changed." if dest.exists() else ""
    if err == errno.ENOSPC or winerror in _DISK_FULL:
        return (f"There is not enough free space on the drive to save {name}.",
                "Free some space or choose another drive." + unchanged)
    if isinstance(exc, FileNotFoundError) and not dest.parent.exists():
        return (f"The folder “{dest.parent}” does not exist (any more).", "Choose another folder.")
    if isinstance(exc, PermissionError) or winerror in _IN_USE or winerror == _ACCESS_DENIED:
        if dest.exists() and _read_only(dest):
            return (f"{name} is read-only, so it was not replaced.",
                    "Choose another name or folder, or clear the file's read-only attribute in Windows "
                    "(Properties) first." + unchanged)
        if dest.exists():
            return (f"{name} is in use by another program, so it could not be replaced.",
                    "Close the program that has it open (for example a PDF viewer, a cloud-sync or backup "
                    "tool or a virus scan), then try again, or choose another name." + unchanged)
        if not os.access(dest.parent, os.W_OK):
            return (f"You do not have permission to save files in “{dest.parent}”.",
                    "Choose another folder, for example Documents.")
        return (f"Windows did not allow {name} to be written.",
                "Choose another folder, for example Documents.")
    return (str(exc).strip() or f"{name} could not be saved.", "Choose another name or folder." + unchanged)
