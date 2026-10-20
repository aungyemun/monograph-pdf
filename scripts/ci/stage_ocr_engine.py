"""Stage the OCR engine for CI only when it is byte-identical to the engine Monograph PDF ships.

    python scripts/ci/stage_ocr_engine.py --write-pins          (maintainer: record the shipped engine)
    python scripts/ci/stage_ocr_engine.py --from "C:/Program Files/Tesseract-OCR"   (CI)

The release bundles Tesseract (engines/ocr) and tessdata_fast eng/jpn/osd (models/tessdata); neither
is in the repository. In CI, Tesseract is installed from the approved Chocolatey package of the same
version and the language data is downloaded from the tessdata_fast repository. Every file is
checked against the SHA-256 recorded from the shipped copy (scripts/ci/ocr_engine_pins.json); only
if *all* files match are they placed where the application looks for them. Otherwise nothing is
staged, the OCR tests skip, and the category report shows OCR as NOT VERIFIED — a different or
tampered engine is never tested in place of the real one.

Exit code is 0 in both cases (the decision is reported, not hidden); 2 for usage errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = Path(__file__).with_name("ocr_engine_pins.json")
ENGINE = ROOT / "engines" / "ocr"
TESSDATA = ROOT / "models" / "tessdata"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{name}"
LANGS = ("eng", "jpn", "osd")
SKIP = {"MANIFEST.json"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_pins() -> int:
    exe = ENGINE / "tesseract.exe"
    if not exe.is_file():
        print(f"no shipped engine at {exe}", file=sys.stderr)
        return 2
    engine = {p.name: sha256(p) for p in sorted(ENGINE.iterdir()) if p.is_file() and p.name not in SKIP}
    tessdata = {}
    for lang in LANGS:
        f = TESSDATA / f"{lang}.traineddata"
        if not f.is_file():
            print(f"missing {f}", file=sys.stderr)
            return 2
        tessdata[f.name] = sha256(f)
    PINS.write_text(json.dumps({"tesseract_version": "5.4.0.20240606", "engine": engine, "tessdata": tessdata},
                               indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PINS.relative_to(ROOT)}: {len(engine)} engine files, {len(tessdata)} language files")
    return 0


def summary(line: str) -> None:
    print(line)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def stage(source: Path) -> int:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ocr_stage_") as tmp:
        work = Path(tmp)
        (work / "engine").mkdir()
        (work / "tessdata").mkdir()
        for name, expected in pins["engine"].items():
            src = source / name
            if name == "TESSERACT_NOTICE.txt":
                # written by the release tooling, not part of the upstream install
                (work / "engine" / name).write_text("Tesseract OCR (Apache-2.0), staged for CI tests.\n", encoding="utf-8")
                continue
            if not src.is_file():
                problems.append(f"{name}: not in the installed engine")
            elif sha256(src) != expected:
                problems.append(f"{name}: SHA-256 differs from the shipped engine")
            else:
                shutil.copy2(src, work / "engine" / name)
        for name, expected in pins["tessdata"].items():
            dest = work / "tessdata" / name
            try:
                with urllib.request.urlopen(TESSDATA_URL.format(name=name), timeout=120) as r, dest.open("wb") as fh:
                    shutil.copyfileobj(r, fh)
            except OSError as exc:
                problems.append(f"{name}: download failed ({exc})")
                continue
            if sha256(dest) != expected:
                problems.append(f"{name}: SHA-256 differs from the shipped language data")
        if problems:
            summary("OCR engine **not staged** — OCR tests will be SKIPPED and reported NOT VERIFIED:")
            for p in problems:
                summary(f"- {p}")
            return 0
        ENGINE.mkdir(parents=True, exist_ok=True)
        TESSDATA.mkdir(parents=True, exist_ok=True)
        for f in (work / "engine").iterdir():
            shutil.copy2(f, ENGINE / f.name)
        for f in (work / "tessdata").iterdir():
            shutil.copy2(f, TESSDATA / f.name)
    summary(f"OCR engine staged: Tesseract {pins['tesseract_version']}, {len(pins['engine'])} files and "
            f"{', '.join(LANGS)} language data, all SHA-256 identical to the shipped copy.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write-pins", action="store_true")
    g.add_argument("--from", dest="source", type=Path, help="folder of the installed Tesseract")
    a = ap.parse_args(argv)
    if a.write_pins:
        return write_pins()
    if not a.source.is_dir():
        summary(f"OCR engine not staged: {a.source} does not exist — OCR tests will be NOT VERIFIED.")
        return 0
    return stage(a.source)


if __name__ == "__main__":
    sys.exit(main())
