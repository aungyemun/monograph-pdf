"""Stage Linux OCR: wrap system Tesseract + download pinned tessdata_fast eng/jpn/osd.

Unlike the Windows path (byte-identical MSYS2 Tesseract DLLs), Linux uses the distribution
Tesseract binary (or a copy under engines/ocr) and the same language-data SHA-256 pins as
Windows (scripts/ci/ocr_engine_pins.json → tessdata section only).

    python scripts/ci/stage_ocr_engine_linux.py
    python scripts/ci/stage_ocr_engine_linux.py --require
    python scripts/ci/stage_ocr_engine_linux.py --verify-tessdata
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = Path(__file__).with_name("ocr_engine_pins.json")
ENGINE = ROOT / "engines" / "ocr"
TESSDATA = ROOT / "models" / "tessdata"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/{name}"
LANGS = ("eng", "jpn", "osd")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_system_tesseract() -> Path | None:
    found = shutil.which("tesseract")
    return Path(found).resolve() if found else None


LOCAL_MANIFEST = ENGINE / "MANIFEST.local.json"


def stage_wrapper(system: Path) -> None:
    """Stage Linux OCR without dirtying the tracked ``engines/ocr/MANIFEST.json``.

    Machine-local staging metadata goes to ``MANIFEST.local.json`` (gitignored via
    ``engines/ocr/*``). The committed Windows-oriented ``MANIFEST.json`` stays unchanged
    so source-archive builds see a clean working tree after OCR staging.
    """
    ENGINE.mkdir(parents=True, exist_ok=True)
    wrapper = ENGINE / "tesseract"
    # Symlink so core.ocr.paths finds engines/ocr/tesseract first
    if wrapper.is_symlink() or wrapper.exists():
        wrapper.unlink()
    wrapper.symlink_to(system)
    LOCAL_MANIFEST.write_text(
        json.dumps(
            {
                "platform": "linux",
                "tesseract": str(system),
                "note": "System Tesseract; language data SHA-256-pinned from tessdata_fast 4.1.0",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"OCR engine wrapper → {system} (local manifest {LOCAL_MANIFEST.name})")


def download_tessdata(require: bool) -> int:
    pins = json.loads(PINS.read_text(encoding="utf-8"))["tessdata"]
    TESSDATA.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        name = f"{lang}.traineddata"
        dest = TESSDATA / name
        expected = pins[name]
        if dest.is_file() and sha256(dest) == expected:
            print(f"OK {name}")
            continue
        url = TESSDATA_URL.format(name=name)
        print(f"Downloading {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 — pinned URL + SHA-256
                data = resp.read()
        except Exception as exc:  # noqa: BLE001
            print(f"download failed for {name}: {exc}", file=sys.stderr)
            if require:
                return 1
            continue
        got = hashlib.sha256(data).hexdigest()
        if got != expected:
            print(f"SHA-256 mismatch for {name}: got {got}, want {expected}", file=sys.stderr)
            if require:
                return 1
            continue
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        print(f"staged {name}")
    return 0


def verify_tessdata() -> int:
    pins = json.loads(PINS.read_text(encoding="utf-8"))["tessdata"]
    problems = []
    for name, expected in pins.items():
        path = TESSDATA / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif sha256(path) != expected:
            problems.append(f"SHA-256 differs: {name}")
    if problems:
        print("tessdata verification FAILED:")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"tessdata verified ({len(pins)} files)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require", action="store_true")
    ap.add_argument("--verify-tessdata", action="store_true")
    args = ap.parse_args()
    if args.verify_tessdata:
        return verify_tessdata()
    system = find_system_tesseract()
    if system is None:
        msg = "tesseract not found on PATH; install tesseract-ocr (and eng/jpn packs optional — we vendor tessdata)"
        print(msg, file=sys.stderr)
        return 1 if args.require else 0
    stage_wrapper(system)
    return download_tessdata(args.require)


if __name__ == "__main__":
    raise SystemExit(main())
