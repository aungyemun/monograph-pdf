"""Resolve Windows known folders without hard-coding usernames."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_downloads_dir() -> Path:
    """
    Return the current user's Downloads folder.

    Uses SHGetKnownFolderPath(FOLDERID_Downloads) on Windows; falls back to
    ~/Downloads on other platforms or when the API is unavailable.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
            fid = GUID(
                0x374DE290,
                0x123F,
                0x4565,
                (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
            )
            SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
            SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                wintypes.HANDLE,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            path_ptr = ctypes.c_wchar_p()
            hr = SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(path_ptr))
            if hr == 0 and path_ptr.value:
                return Path(path_ptr.value)
        except Exception:  # noqa: BLE001
            pass
        # USERPROFILE\Downloads fallback (still no hard-coded username)
        profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        if profile:
            candidate = Path(profile) / "Downloads"
            if candidate.is_dir():
                return candidate
    return Path.home() / "Downloads"
