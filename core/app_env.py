"""Environment-variable overrides for development, testing and the installer's self-check.

Monograph PDF reads ``MONOGRAPH_PDF_<NAME>``. The ``PDFEDITOR_<NAME>`` spelling from earlier
internal builds (<= 0.1.5) is still accepted as a deprecated alias during the 0.2.x series, so older
development scripts keep working; it will be removed in a later release. Precedence:

    MONOGRAPH_PDF_<NAME>  →  PDFEDITOR_<NAME> (deprecated)  →  built-in default

This module imports nothing from the application so it can be used at the earliest start-up.
"""

from __future__ import annotations

import os

PREFIX = "MONOGRAPH_PDF_"
LEGACY_PREFIX = "PDFEDITOR_"  # deprecated alias (PDF Editor <= 0.1.5)

# Names the application reads (documented in docs/BUILD_AND_RUNTIME.md)
KNOWN = (
    "RUNTIME_DIR",
    "USER_DATA_DIR",
    "HEADLESS",
    "FORCE_DARK",
    "STARTUP_TIMING",
    "PERF_LOG",
    "DISABLE_OFFICE",
    "NO_LEGACY_MIGRATION",
    "UPDATES_DIR",
    "DIAGNOSTICS_DIR",
)


def env_name(name: str) -> str:
    return PREFIX + name


def get(name: str, default: str = "") -> str:
    """Value of ``MONOGRAPH_PDF_<name>``, else the deprecated ``PDFEDITOR_<name>``, else ``default``.

    An empty or blank value counts as unset.
    """
    for key in (PREFIX + name, LEGACY_PREFIX + name):
        value = os.environ.get(key, "")
        if value.strip():
            return value.strip()
    return default


def is_true(name: str) -> bool:
    return get(name).lower() in ("1", "true", "yes")


def profile_subdir(name: str):
    """``<MONOGRAPH_PDF_USER_DATA_DIR>/<name>`` when the user-data folder is redirected, else None.

    Only the tests, the build's and Setup's self-check, and audit harnesses redirect the user-data
    folder. Every other per-user location (diagnostics, update staging, caches, the installed
    program's runtime folder) then defaults to a folder inside it, so an isolated run can never write
    to — or consume records in — the real ``%APPDATA%`` / ``%LOCALAPPDATA%\\Monograph PDF`` folders,
    even when only this one variable is set. (Up to 0.5.1's development, problem-report records and
    update state of such runs went to the real folders unless each had its own override.)
    A location's own override (``DIAGNOSTICS_DIR`` and so on) still wins.
    """
    from pathlib import Path

    base = get("USER_DATA_DIR")
    return Path(base) / name if base else None


def set(name: str, value: str) -> None:  # noqa: A001 - mirrors os.environ semantics
    """Set ``MONOGRAPH_PDF_<name>`` for this process and its children (a stale legacy value is dropped)."""
    os.environ[PREFIX + name] = value
    os.environ.pop(LEGACY_PREFIX + name, None)
