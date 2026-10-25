"""Project-local OCR engine and language-data paths (never network at runtime)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.paths import BUNDLE_ROOT, ENGINES_DIR, MODELS_DIR, ROOT


def ocr_engine_dir() -> Path:
    """Prefer install-root sidecar; fall back to frozen bundle extract."""
    for base in (ENGINES_DIR, BUNDLE_ROOT / "engines", ROOT / "engines"):
        candidate = base / "ocr"
        if _has_tesseract(candidate):
            return candidate
    return ENGINES_DIR / "ocr"


def _has_tesseract(folder: Path) -> bool:
    return any(p.is_file() for p in _exe_candidates(folder))


def _exe_candidates(folder: Path) -> list[Path]:
    names = ("tesseract.exe",) if sys.platform.startswith("win") else ("tesseract", "tesseract.exe")
    out: list[Path] = []
    for name in names:
        out.append(folder / name)
        out.append(folder / "bin" / name)
    return out


def tesseract_exe() -> Path | None:
    """Bundled / project-local engine only (never PATH).

    On macOS the development layout may place a wrapper at ``engines/ocr/tesseract`` that
    runs ``tools/ocr-env/bin/tesseract`` (still under the project root).
    """
    for base in (ocr_engine_dir(), BUNDLE_ROOT / "engines" / "ocr", ROOT / "engines" / "ocr"):
        for candidate in _exe_candidates(base):
            if candidate.is_file() and os.access(candidate, os.X_OK if not sys.platform.startswith("win") else os.F_OK):
                return candidate
    if not sys.platform.startswith("win"):
        # Project-local micromamba env staged by scripts/vendor_ocr_macos.sh
        for cand in (
            ROOT / "tools" / "ocr-env" / "bin" / "tesseract",
            ROOT / "tools" / "tesseract" / "prefix" / "bin" / "tesseract",
        ):
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    return None


def tessdata_dir() -> Path:
    """Bundled traineddata for eng / jpn / osd (never downloaded at runtime)."""
    for candidate in (
        MODELS_DIR / "tessdata",
        BUNDLE_ROOT / "models" / "tessdata",
        ROOT / "models" / "tessdata",
        ocr_engine_dir() / "tessdata",
    ):
        if candidate.is_dir() and any(candidate.glob("*.traineddata")):
            return candidate
    return MODELS_DIR / "tessdata"


def required_languages() -> tuple[str, ...]:
    return ("eng", "jpn", "osd")


def language_files_present(langs: tuple[str, ...] | None = None) -> dict[str, bool]:
    langs = langs or required_languages()
    data = tessdata_dir()
    return {lang: (data / f"{lang}.traineddata").is_file() for lang in langs}


def ocr_ready() -> tuple[bool, str]:
    exe = tesseract_exe()
    if exe is None:
        return False, "The OCR engine (engines/ocr) was not found."
    present = language_files_present()
    missing = [k for k, ok in present.items() if not ok]
    if missing:
        return False, f"OCR language data is missing: {', '.join(missing)}."
    return True, f"{exe} + tessdata OK"
