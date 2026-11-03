"""Stage a self-contained Tesseract into a macOS .app (Contents/Resources/engines/ocr).

The development layout (scripts/vendor_ocr_macos.sh) leaves ``engines/ocr/tesseract`` as a
shell wrapper that runs ``tools/ocr-env/bin/tesseract``. ``tools/`` is never bundled, so the
wrapper cannot be shipped. This copies the real Mach-O binary to ``<dest>/bin/tesseract`` and
the transitive closure of its non-system dylibs to ``<dest>/lib`` — the binary already carries
``LC_RPATH @loader_path/../lib``, so no install names need rewriting.

Files are copied from the extracted conda *package*, not from the installed environment: on install
conda patches the environment's own path into some libraries (OpenSSL, curl, krb5, libxml2, …),
which would ship the builder's home folder and make the binaries differ per machine. The package
bytes carry conda-forge's neutral placeholder prefix and equal the published package exactly.

Licensing: every conda package that owns a staged file has its license files copied to
``<dest>/licenses/<package>/`` and is listed (name, version, build, license, package URL) in
``<dest>/THIRD_PARTY_OCR.json``. Copyleft components (e.g. lzo GPL-2.0-or-later, libiconv
LGPL-2.1) are marked so their corresponding source can be provided with a release.

Usage: python scripts/packaging/stage_ocr_macos.py <ocr-env prefix> <dest engines/ocr dir>
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
COPYLEFT = ("GPL", "LGPL", "MPL")
TESSERACT_NOTICE = """Tesseract OCR
Copyright Google LLC and contributors
License: Apache License 2.0 (licenses/tesseract/)
https://github.com/tesseract-ocr/tesseract

The macOS build of Monograph PDF includes a conda-forge build of Tesseract under
engines/ocr/bin with the libraries it needs under engines/ocr/lib. Each library's
license is in engines/ocr/licenses/<package>/ and THIRD_PARTY_OCR.json lists
package versions, licenses and download URLs; THIRD_PARTY_OCR_SOURCES.json records
each package's provenance (published package, feedstock commit, upstream sources
and SHA-256 of every bundled file). Language data (eng, jpn, osd) under
models/tessdata comes from tessdata_fast and keeps its upstream licensing.

lzo (GPL-2.0-or-later) and libiconv (LGPL-2.1) are copyleft. Their complete
corresponding source (upstream release archive, conda-forge recipe, patches and build
scripts) is published with every Monograph PDF for macOS release, in the folder
MonographPDF_<version>_macOS_OCR_Corresponding_Source next to the .dmg.
"""


def linked_libraries(binary: Path) -> list[str]:
    out = subprocess.run(["otool", "-L", str(binary)], check=True, capture_output=True, text=True).stdout
    names = []
    for line in out.splitlines()[1:]:
        m = re.match(r"\s+(\S+) \(", line)
        if m:
            names.append(m.group(1))
    return names


def resolve(ref: str, lib_dir: Path) -> Path | None:
    """Map an install name to a file in the env's lib dir (``None`` for system libraries)."""
    if ref.startswith(SYSTEM_PREFIXES):
        return None
    if ref.startswith(("@rpath/", "@loader_path/", "@executable_path/")):
        name = ref.split("/", 1)[1].rsplit("/", 1)[-1]
    else:
        name = Path(ref).name
    path = lib_dir / name
    if not path.exists():
        raise FileNotFoundError(f"{ref} not found in {lib_dir}")
    return path


def dylib_closure(binary: Path, lib_dir: Path) -> list[str]:
    seen: dict[str, Path] = {}
    queue = [binary]
    while queue:
        current = queue.pop()
        for ref in linked_libraries(current):
            path = resolve(ref, lib_dir)
            if path is None:
                continue
            if path.name not in seen and path.resolve() != current.resolve():
                seen[path.name] = path
                queue.append(path.resolve())
    return sorted(seen)


def _owners(prefix: Path) -> dict[str, dict]:
    """Map ``bin/…`` / ``lib/…`` paths to the conda-meta record of the package that installed them."""
    owners: dict[str, dict] = {}
    for meta in sorted((prefix / "conda-meta").glob("*.json")):
        record = json.loads(meta.read_text(encoding="utf-8"))
        for rel in record.get("files", ()):
            owners[rel] = record
    return owners


def write_licenses(prefix: Path, dest: Path, staged: list[str]) -> list[dict]:
    """Copy the license files of every package owning a staged file; return the inventory."""
    owners = _owners(prefix)
    packages: dict[str, dict] = {}
    for rel in staged:
        record = owners.get(rel)
        if record is None:
            raise LookupError(f"{rel} is not owned by any conda package in {prefix}")
        packages[record["name"]] = record
    inventory = []
    for name, record in sorted(packages.items()):
        src = Path(record.get("extracted_package_dir", "")) / "info" / "licenses"
        files = sorted(p for p in src.rglob("*") if p.is_file()) if src.is_dir() else []
        if not files:
            raise FileNotFoundError(f"no license files for {name} (expected under {src})")
        out = dest / "licenses" / name
        for f in files:
            target = out / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
        license_id = record.get("license", "")
        inventory.append({
            "name": name, "version": record["version"], "build": record.get("build", ""),
            "license": license_id, "url": record.get("url", ""),
            "copyleft": any(tag in license_id for tag in COPYLEFT),
            "license_files": [str(t.relative_to(dest)) for t in sorted(out.rglob("*")) if t.is_file()],
        })
    (dest / "THIRD_PARTY_OCR.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    (dest / "TESSERACT_NOTICE.txt").write_text(TESSERACT_NOTICE, encoding="utf-8")
    return inventory


def package_file(prefix: Path, rel: str, owners: dict[str, dict]) -> Path:
    """The unpatched file for ``rel`` (``bin/…`` / ``lib/…``) inside its extracted conda package."""
    target = (prefix / rel).resolve().relative_to(prefix.resolve()).as_posix()
    record = owners.get(target) or owners.get(rel)
    if record is None:
        raise LookupError(f"{rel} is not owned by any conda package in {prefix}")
    path = (Path(record["extracted_package_dir"]) / target).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing — the conda package cache was cleaned; re-run vendor_ocr_macos.sh")
    return path


def stage(prefix: Path, dest: Path) -> list[str]:
    src_bin = prefix / "bin" / "tesseract"
    lib_dir = prefix / "lib"
    if not src_bin.is_file():
        raise FileNotFoundError(f"{src_bin} missing — run scripts/vendor_ocr_macos.sh")
    names = dylib_closure(src_bin, lib_dir)
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "bin").mkdir(parents=True)
    (dest / "lib").mkdir()
    owners = _owners(prefix)
    shutil.copy2(package_file(prefix, "bin/tesseract", owners), dest / "bin" / "tesseract")
    for name in names:
        # Copy the real file under the referenced name (no symlinks inside the signed bundle).
        shutil.copy2(package_file(prefix, f"lib/{name}", owners), dest / "lib" / name)
    write_licenses(prefix, dest, ["bin/tesseract"] + [f"lib/{n}" for n in names])
    # Conda package files can be group-writable; an app bundle ships 755 code and 644 data.
    for path in dest.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o755 if path.parent.name in ("bin", "lib") else 0o644)
    return names


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    prefix, dest = Path(argv[0]), Path(argv[1])
    names = stage(prefix, dest)
    inventory = json.loads((dest / "THIRD_PARTY_OCR.json").read_text(encoding="utf-8"))
    copyleft = [f"{p['name']} ({p['license']})" for p in inventory if p["copyleft"]]
    print(f"Staged tesseract + {len(names)} dylib(s) from {len(inventory)} package(s) into {dest}")
    if copyleft:
        print("Copyleft components (ship corresponding source with releases): " + ", ".join(copyleft))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
