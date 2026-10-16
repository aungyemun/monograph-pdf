"""Monograph PDF application package."""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    """Resolve repo root, or PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def read_version() -> str:
    """Return the authoritative product version from VERSION."""
    version_path = _project_root() / "VERSION"
    return version_path.read_text(encoding="utf-8").strip()


__version__ = read_version()
