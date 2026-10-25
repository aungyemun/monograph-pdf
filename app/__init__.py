"""Monograph PDF application package."""

from __future__ import annotations

from core.versioning import get_version


def read_version() -> str:
    """Return the authoritative product version for the host platform (Option B)."""
    return get_version()


__version__ = read_version()
