"""Version-resource metadata of Monograph PDF's own Windows binaries (required for code signing).

    python scripts/packaging/check_metadata.py --version X.Y.Z FILE...

Every file must carry ProductName "Monograph PDF" and ProductVersion X.Y.Z (the same value in every
binary of a build), and a FileVersion that starts with X.Y.Z. Reads the PE resources with ``pefile``
(a build dependency of PyInstaller); nothing is executed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PRODUCT_NAME = "Monograph PDF"


def version_strings(path: Path) -> dict[str, str]:
    import pefile

    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    out: dict[str, str] = {}
    for info in getattr(pe, "FileInfo", None) or []:
        for entry in info:
            for table in getattr(entry, "StringTable", []) or []:
                for k, v in table.entries.items():
                    out[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace").strip()
    pe.close()
    return out


def problems_for(path: Path, version: str) -> list[str]:
    try:
        s = version_strings(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{path.name}: version resource unreadable ({type(exc).__name__})"]
    out = []
    if s.get("ProductName") != PRODUCT_NAME:
        out.append(f"{path.name}: ProductName is {s.get('ProductName')!r}, expected {PRODUCT_NAME!r}")
    if s.get("ProductVersion") != version:
        out.append(f"{path.name}: ProductVersion is {s.get('ProductVersion')!r}, expected {version!r}")
    if not str(s.get("FileVersion", "")).startswith(version):
        out.append(f"{path.name}: FileVersion {s.get('FileVersion')!r} does not start with {version}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True)
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    problems = [p for f in a.files for p in problems_for(f, a.version)]
    for f in a.files:
        print(f"  {f.name}: checked")
    if problems:
        print("Metadata check FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"Metadata check passed: {len(a.files)} files carry {PRODUCT_NAME} {a.version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
