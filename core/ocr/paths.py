"""Project-local OCR engine and language-data paths (never network at runtime)."""

from __future__ import annotations

from pathlib import Path

from app.paths import BUNDLE_ROOT, ENGINES_DIR, MODELS_DIR


def ocr_engine_dir() -> Path:
    """Prefer install-root sidecar; fall back to frozen bundle extract."""
    for base in (ENGINES_DIR, BUNDLE_ROOT / "engines"):
        candidate = base / "ocr"
        if (candidate / "tesseract.exe").is_file() or (candidate / "bin" / "tesseract.exe").is_file():
            return candidate
    return ENGINES_DIR / "ocr"


def tesseract_exe() -> Path | None:
    for candidate in (
        ocr_engine_dir() / "tesseract.exe",
        ocr_engine_dir() / "bin" / "tesseract.exe",
        BUNDLE_ROOT / "engines" / "ocr" / "tesseract.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def tessdata_dir() -> Path:
    """Bundled traineddata for eng / jpn / osd (never downloaded at runtime)."""
    for candidate in (
        MODELS_DIR / "tessdata",
        BUNDLE_ROOT / "models" / "tessdata",
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
        return False, "The OCR engine (engines\\ocr) was not found."
    present = language_files_present()
    missing = [k for k, ok in present.items() if not ok]
    if missing:
        return False, f"OCR language data is missing: {', '.join(missing)}."
    return True, f"{exe} + tessdata OK"
