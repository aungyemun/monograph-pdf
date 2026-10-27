"""Lightweight engine availability probes (no network)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.paths import ENGINES_DIR, ROOT


@dataclass(frozen=True)
class EngineStatus:
    name: str
    available: bool
    detail: str


def probe_pymupdf() -> EngineStatus:
    try:
        import fitz  # PyMuPDF

        return EngineStatus("PyMuPDF", True, f"version={fitz.version[0]}")
    except Exception as exc:  # noqa: BLE001 — probe must never crash bootstrap
        return EngineStatus("PyMuPDF", False, str(exc))


def probe_pyside6() -> EngineStatus:
    try:
        import PySide6

        return EngineStatus("PySide6", True, f"version={PySide6.__version__}")
    except Exception as exc:  # noqa: BLE001
        return EngineStatus("PySide6", False, str(exc))


def probe_qpdf() -> EngineStatus:
    import sys

    names = ("qpdf.exe",) if sys.platform.startswith("win") else ("qpdf", "qpdf.exe")
    for name in names:
        candidate = ENGINES_DIR / "qpdf" / "bin" / name
        if candidate.is_file():
            try:
                detail = str(candidate.relative_to(ROOT))
            except ValueError:
                detail = str(candidate)
            return EngineStatus("qpdf", True, detail)
    return EngineStatus("qpdf", False, "optional structural toolkit not present")


def probe_tesseract() -> EngineStatus:
    try:
        from core.ocr.paths import ocr_ready

        ok, detail = ocr_ready()
        return EngineStatus("Tesseract", ok, detail)
    except Exception as exc:  # noqa: BLE001
        return EngineStatus("Tesseract", False, str(exc))


def probe_all() -> list[EngineStatus]:
    return [
        probe_pyside6(),
        probe_pymupdf(),
        probe_qpdf(),
        probe_tesseract(),
    ]
