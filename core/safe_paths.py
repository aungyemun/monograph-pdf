"""Safe names and paths for files Monograph PDF writes and programs it starts.

* :func:`safe_child` turns a generated name (from a bookmark title, a document name or a
  PDF-supplied image type) into a file directly inside the folder the user chose: no folder
  parts, no ``..``, no characters or names Windows reserves, and never an existing file
  (``name (2).pdf`` is used instead, so nothing the user already has is replaced).
* :func:`windows_tool` gives the full path of a Windows program (``explorer.exe``,
  ``rundll32.exe``, ``powershell.exe`` …) so that a same-named program in the current folder,
  for example a downloaded ``explorer.exe`` next to a PDF, is never started instead.
"""

from __future__ import annotations

import ntpath
import os
import re
from pathlib import Path

_WINDOWS = os.name == "nt"

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class UnsafePathError(ValueError):
    """A generated file name would leave the chosen folder or is not a valid file name."""


def safe_name(name: str, *, fallback: str = "file") -> str:
    """A single, valid Windows file name made from ``name`` (folder parts are rejected)."""
    raw = str(name or "")
    if "/" in raw or "\\" in raw or raw.strip() in {".", ".."} or ".." in Path(raw).parts:
        raise UnsafePathError(f"Not a plain file name: {raw!r}")
    cleaned = _BAD_CHARS.sub("_", raw).strip().rstrip(". ")
    if not cleaned:
        cleaned = fallback
    stem, dot, ext = cleaned.partition(".")
    if stem.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:180]


def unique_path(path: Path) -> Path:
    """``path`` when nothing exists there yet, else ``name (2).ext``, ``name (3).ext`` …"""
    path = Path(path)
    if not path.exists():
        return path
    for n in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(path)


def safe_child(folder: Path, name: str, *, overwrite: bool = False) -> Path:
    """A path for ``name`` directly inside ``folder`` (see the module notes)."""
    folder = Path(folder)
    target = folder / safe_name(name)
    try:
        inside = target.resolve().parent == folder.resolve()
    except OSError:
        inside = False
    if not inside:
        raise UnsafePathError(f"{name!r} would be written outside {folder}")
    return target if overwrite else unique_path(target)


def windows_tool(name: str) -> str:
    """Full path of a program in the Windows system folder (``name`` itself elsewhere)."""
    if not _WINDOWS:
        return name
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    folders = {
        "explorer.exe": root,
        "powershell.exe": ntpath.join(root, "System32", "WindowsPowerShell", "v1.0"),
    }
    return ntpath.join(folders.get(name.lower(), ntpath.join(root, "System32")), name)
