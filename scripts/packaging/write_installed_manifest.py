"""Write the list of Monograph PDF-owned relative install paths for Setup upgrade cleanup.

The manifest is shipped as ``{app}\\installed_files.txt`` (one relative path per line).
Upgrade cleanup may delete only those paths (or the legacy allowlist when no prior
manifest exists). Absolute paths, ``..``, drive roots and empty entries are rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Extra files Setup installs that are not inside dist\MonographPDF\
EXTRA_INSTALL_FILES = [
    "uninstall.exe",
    "MonographPDFUpdater.exe",
    "README.md",
    "LICENSE.md",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/USER_GUIDE.md",
    "installed_files.txt",
]

# Allowlist used when upgrading an install that has no installed_files.txt (PDF Editor <= 0.1.5)
LEGACY_OWNED_DIRS = [
    "_internal",
    "engines",
    "models",
    "docs",
    "licenses",
    "logs",
    "runtime",
    "packages",
]
LEGACY_OWNED_FILES = [
    "PDF_editor.exe",  # PDF Editor <= 0.1.5
    "MonographPDF.exe",
    "uninstall.exe",
    "MonographPDFUpdater.exe",
    "README.md",
    "LICENSE.md",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "installed_files.txt",
    "installed_files.json",
]


def is_safe_rel(path: str) -> bool:
    """Return True if *path* is a safe relative install path (POSIX separators)."""
    if not path or path.strip() != path:
        return False
    p = path.replace("\\", "/")
    if p != path.replace("\\", "/"):
        p = path.replace("\\", "/")
    p = path.replace("\\", "/")
    if not p or p.startswith("/") or p.startswith("\\"):
        return False
    if ":" in p or p.startswith("//"):
        return False
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return False
    if any(part.endswith(".lnk") and part.lower().startswith("uninstall") for part in parts):
        pass
    return True


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def collect_from_payload(payload: Path) -> list[str]:
    paths: list[str] = []
    if not payload.is_dir():
        raise SystemExit(f"payload not found: {payload}")
    for f in sorted(p for p in payload.rglob("*") if p.is_file()):
        rel = normalize_rel(f.relative_to(payload).as_posix())
        if not is_safe_rel(rel):
            raise SystemExit(f"unsafe payload path: {rel}")
        paths.append(rel)
    return paths


def collect_ocr_and_tessdata(root: Path) -> list[str]:
    paths: list[str] = []
    for folder, prefix in (
        (root / "engines" / "ocr", "engines/ocr"),
        (root / "models" / "tessdata", "models/tessdata"),
    ):
        if not folder.is_dir():
            continue
        for f in sorted(p for p in folder.rglob("*") if p.is_file()):
            if f.name == ".gitkeep":
                continue
            rel = normalize_rel(f"{prefix}/{f.relative_to(folder).as_posix()}")
            if not is_safe_rel(rel):
                raise SystemExit(f"unsafe path: {rel}")
            paths.append(rel)
    notice = root / "third_party" / "licenses" / "TESSERACT_NOTICE.txt"
    if notice.is_file():
        paths.append("engines/ocr/TESSERACT_NOTICE.txt")
    return paths


def collect_license_texts(root: Path) -> list[str]:
    paths: list[str] = []
    lic = root / "third_party" / "licenses"
    if not lic.is_dir():
        return paths
    for f in sorted(lic.glob("*.txt")):
        if f.name == "TESSERACT_NOTICE.txt":
            continue
        rel = f"licenses/{f.name}"
        if is_safe_rel(rel):
            paths.append(rel)
    return paths


def build_manifest(payload: Path, root: Path = ROOT) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for rel in collect_from_payload(payload) + collect_ocr_and_tessdata(root) + collect_license_texts(root) + EXTRA_INSTALL_FILES:
        rel = normalize_rel(rel)
        if not is_safe_rel(rel):
            raise SystemExit(f"refusing unsafe manifest entry: {rel!r}")
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    out.sort()
    return out


def write_manifest(paths: list[str], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Monograph PDF owned install paths (relative to {app})",
        "# Used by Setup during upgrades to remove obsolete application files only.",
        "# Unknown / user-created files in the install folder are never listed here.",
    ]
    lines.extend(paths)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "format": 1,
        "count": len(paths),
        "legacy_owned_dirs": LEGACY_OWNED_DIRS,
        "legacy_owned_files": LEGACY_OWNED_FILES,
        "files": paths,
    }
    dest.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--payload", type=Path, default=ROOT / "dist" / "MonographPDF")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "installer" / "installed_files.txt")
    a = ap.parse_args(argv)
    paths = build_manifest(a.payload)
    write_manifest(paths, a.out)
    print(f"Wrote {a.out} ({len(paths)} paths) and {a.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
