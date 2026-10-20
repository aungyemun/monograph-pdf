"""Accepted dependency inventory — record once; do not duplicate equivalents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptedDependency:
    name: str
    purpose: str
    license: str
    redistributable: bool
    windows_support: str
    offline_ok: bool
    notes: str


# Scaffolding summary only. The authoritative shipped inventory is
# licenses/DEPENDENCY_INVENTORY.md and THIRD_PARTY_NOTICES.md (kept in sync with the release).
ACCEPTED_DEPENDENCIES: tuple[AcceptedDependency, ...] = (
    AcceptedDependency(
        name="Python 3.11.x",
        purpose="Application language (source-compatible with 3.11/3.12; runtime bundled in release)",
        license="PSF",
        redistributable=True,
        windows_support="official",
        offline_ok=True,
        notes="Release builds use Python 3.11.9; developers may use 3.11 or 3.12.",
    ),
    AcceptedDependency(
        name="PySide6",
        purpose="Desktop UI (Qt for Python)",
        license="LGPL-3.0",
        redistributable=True,
        windows_support="official wheels",
        offline_ok=True,
        notes="Dynamic link; ship LGPL notices under licenses/.",
    ),
    AcceptedDependency(
        name="PyMuPDF (MuPDF)",
        purpose="PDF render/core operations",
        license="AGPL-3.0 (PyMuPDF default) / MuPDF dual",
        redistributable=True,
        windows_support="official wheels",
        offline_ok=True,
        notes="Confirm distribution terms before commercial release; see licenses/DEPENDENCY_INVENTORY.md.",
    ),
    AcceptedDependency(
        name="qpdf",
        purpose="Structural/security PDF operations",
        license="Apache-2.0",
        redistributable=True,
        windows_support="vendored binary under engines/qpdf",
        offline_ok=True,
        notes="Not required for scaffolding UI; bundled in later stage.",
    ),
    AcceptedDependency(
        name="Tesseract OCR",
        purpose="Offline OCR",
        license="Apache-2.0",
        redistributable=True,
        windows_support="vendored under engines/ocr",
        offline_ok=True,
        notes="Language data under models/; no online OCR.",
    ),
    AcceptedDependency(
        name="packaging",
        purpose="Version parsing helpers",
        license="Apache-2.0 OR BSD-2-Clause",
        redistributable=True,
        windows_support="pure Python wheel",
        offline_ok=True,
        notes="Lightweight; used by tooling.",
    ),
    AcceptedDependency(
        name="pytest / pytest-qt",
        purpose="Unit and UI tests (dev only)",
        license="MIT",
        redistributable=False,
        windows_support="wheels",
        offline_ok=True,
        notes="Not shipped in end-user runtime.",
    ),
    AcceptedDependency(
        name="PyInstaller",
        purpose="Produce MonographPDF.exe and offline bundles",
        license="GPL-2.0-or-later WITH Bootloader exception",
        redistributable=True,
        windows_support="official",
        offline_ok=True,
        notes="Dev/build tool; bootloader exception allows app distribution.",
    ),
)


def list_accepted() -> list[AcceptedDependency]:
    return list(ACCEPTED_DEPENDENCIES)
