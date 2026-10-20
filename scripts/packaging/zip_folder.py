"""Write a ZIP of a folder with portable entry names (used for MonographPDF_x.y.z_Installer.zip).

    python scripts/packaging/zip_folder.py <folder> <out.zip> [--exclude PATTERN ...]

Entry names use '/' as the ZIP format requires (Windows PowerShell 5.1's Compress-Archive writes
'\\', which other unzip tools turn into odd file names), are sorted, and carry a fixed timestamp so
the same files always give the same archive.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path

FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def zip_folder(folder: Path, out: Path, exclude: list[str] | None = None) -> list[str]:
    exclude = exclude or []
    # sort by the stored name itself: Path ordering is case-insensitive on Windows only
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    names = []
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            rel = f.relative_to(folder).as_posix()
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f.name, pat) for pat in exclude):
                continue
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with f.open("rb") as src, z.open(info, "w") as dst:
                while block := src.read(1 << 20):
                    dst.write(block)
            names.append(rel)
    tmp.replace(out)
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--exclude", action="append", default=[])
    a = ap.parse_args(argv)
    if not a.folder.is_dir():
        print(f"not a folder: {a.folder}", file=sys.stderr)
        return 1
    names = zip_folder(a.folder, a.out, a.exclude)
    print(f"{a.out}: {len(names)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
