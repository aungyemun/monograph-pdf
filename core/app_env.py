"""Environment-variable overrides for development, testing and the installer's self-check.

Monograph PDF reads ``MONOGRAPH_PDF_<NAME>``. The ``PDFEDITOR_<NAME>`` spelling of PDF Editor
(final release 0.1.5) is still accepted as a deprecated alias during the 0.2.x series, so older
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
    "DISABLE_OFFICE",
    "NO_LEGACY_MIGRATION",
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


def set(name: str, value: str) -> None:  # noqa: A001 - mirrors os.environ semantics
    """Set ``MONOGRAPH_PDF_<name>`` for this process and its children (a stale legacy value is dropped)."""
    os.environ[PREFIX + name] = value
    os.environ.pop(LEGACY_PREFIX + name, None)
