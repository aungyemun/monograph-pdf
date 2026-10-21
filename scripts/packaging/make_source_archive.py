"""Build the release-matched source archive, e.g. ``MonographPDF_0.2.0_Source.zip``.

    python scripts/packaging/make_source_archive.py --out installer\\MonographPDF_0.2.0_Source.zip
           [--cache packages\\sources] [--offline] [--pin]

The archive contains

    MonographPDF_<version>_Source/
      README_SOURCE.md        what is where, how to build, which binaries each source covers
      SOURCE_MANIFEST.json    every component: license, release files covered, source files, SHA-256
      LICENSES/               AGPL-3.0-or-later (Monograph PDF LICENSE.md as AGPL-3.0.txt), GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-1.1,
                              GCC Runtime Library Exception
      monograph-pdf/          corresponding Monograph PDF release source (application, build, installer, documentation, release tests)
      third-party/            corresponding source of the bundled AGPL / GPL / LGPL components,
                              as published upstream (unmodified archives); for the OCR engine's
                              libraries the MSYS2 source packages (upstream archive, PKGBUILD, patches)
                              of exactly the shipped binary packages

Third-party archives are listed in ``scripts/packaging/third_party_sources.json`` with their
download addresses and SHA-256. They are downloaded once into the cache folder (build time only;
Monograph PDF itself never downloads anything) and every file is checked against its recorded hash.
``--pin`` records the hash of archives that have none yet (Qt archives are first checked against
Qt's published MD5 list). ``--offline`` fails instead of downloading.

Monograph PDF's own files are selected from the project folder: caches, virtual environments, build
output, installers, generated test files, files naming the developer's personal documents and
anything matching the release check's secret / private-path rules are left out (the build fails if
such content is found in a file that would be included).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("third_party_sources.json")

# Monograph PDF source: top-level items included (everything else in the project folder is not source)
SOURCE_TOP = [
    "app", "core", "engines", "ui", "resources", "installer", "scripts", "tests", "docs", "licenses",
    "third_party", "reports", "VERSION", "requirements.txt", "requirements-ci.txt", "pytest.ini", ".gitignore",
    "README.md", "LICENSE", "LICENSE.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "INSTALLATION.md",
    "CONTRIBUTING.md", "CITATION.cff",
]
# Never included (relative paths / name patterns)
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".git", "env", ".venv"}
EXCLUDE_PATHS = [
    "engines/ocr/*.dll", "engines/ocr/*.exe", "engines/ocr/tessdata/*", "installer/release/*", "installer/*.exe",
    "installer/*.zip", "installer/build_release_summary.txt", "tests/outputs/*", "tests/samples/*",
    # Development checks that open the developer's own documents by name (personal data)
    "scripts/validate_real_pdfs.py", "scripts/run_live_real_pdf_qa.py",
    "tests/integration/test_live_real_pdf_qa.py", "tests/integration/test_user_real_pdfs.py",
    "tests/integration/test_round6_real_pdfs.py",
    # Local release-validation material: reports, evidence and one-off QA scripts (they name the
    # developer's own documents and folders; kept on the developer's computer, see .gitignore)
    "reports/audit/qa_evidence/*", "reports/audit/MONOGRAPH_PDF_*.md", "reports/audit/FINAL_*.md",
    "reports/audit/INSTALLATION_AND_RUNTIME_AUDIT.md", "reports/audit/SOURCE_AND_ARCHITECTURE_AUDIT.md",
    "reports/audit/CONVERSION_AND_OUTPUT_FIDELITY.md", "reports/audit/PROFESSIONAL_FEATURE_GAP_ANALYSIS.md",
    "reports/audit/PROJECT_CLEANUP_INVENTORY.md", "reports/audit/MENU_AND_TOOLBAR_TEST_MATRIX.md",
    # internal development records, no longer published (only SECURITY_AUDIT_0.2.0.md is)
    "reports/audit/PROJECT_AUDIT.md", "reports/audit/SECURITY_AUDIT_0.1.5.md",
    "scripts/qa_*", "scripts/gui_driver.ps1", "scripts/office_open_check.ps1", "scripts/powerpoint_export.ps1",
]
EXCLUDE_NAMES = ["*.pyc", "*.pyo", "*.log", ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.kdbx", "Thumbs.db", "desktop.ini"]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".ps1", ".bat", ".iss", ".cs", ".cff", ".ini", ".cfg", ".toml", ".xml", ".html", ".svg"}
LICENSE_FILES = {
    "AGPL-3.0.txt": "LICENSE.md",
    "GPL-2.0.txt": "third_party/licenses/GPL-2.0.txt",
    "GPL-3.0.txt": "third_party/licenses/GPL-3.0.txt",
    "LGPL-2.1.txt": "third_party/licenses/LGPL-2.1.txt",
    "LGPL-3.0.txt": "third_party/licenses/LGPL-3.0.txt",
    "MPL-1.1.txt": "third_party/licenses/MPL-1.1.txt",
    "GCC-exception-3.1.txt": "third_party/licenses/GCC-exception-3.1.txt",
}


def _rules():
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import check_release

        return check_release
    finally:
        sys.path.pop(0)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def product_files(root: Path = ROOT) -> list[Path]:
    """Monograph PDF's own source files, relative to ``root``."""
    out: list[Path] = []
    for top in SOURCE_TOP:
        base = root / top
        items = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file()) if base.is_dir() else []
        for f in items:
            rel = f.relative_to(root)
            parts = rel.parts
            posix = rel.as_posix()
            if EXCLUDE_PARTS & set(parts):
                continue
            if any(fnmatch.fnmatch(posix, p) for p in EXCLUDE_PATHS):
                continue
            if any(fnmatch.fnmatch(f.name, p) for p in EXCLUDE_NAMES):
                continue
            out.append(rel)
    return out


def scan_text(rel: str, data: bytes) -> list[str]:
    cr = _rules()
    problems = []
    for pat in cr.SECRET_PATTERNS:
        if pat.search(data):
            problems.append(f"possible secret in {rel}")
    for pat in cr.PRIVATE_PATH_PATTERNS:
        if pat.search(data):
            problems.append(f"private path in {rel}")
    return problems


def _download(urls: list[str], dest: Path) -> str:
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MonographPDF-source-archive"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest.with_suffix(dest.suffix + ".part"), "wb") as f:
                while True:
                    block = r.read(1 << 20)
                    if not block:
                        break
                    f.write(block)
            dest.with_suffix(dest.suffix + ".part").replace(dest)
            return url
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  could not download {url}: {exc}", file=sys.stderr)
    raise RuntimeError(f"no download address worked for {dest.name}: {last}")


def _qt_md5(md5_url: str, name: str, cache: Path) -> str | None:
    listing = cache / ("md5sums-" + hashlib.sha1(md5_url.encode()).hexdigest()[:8] + ".txt")
    if not listing.exists():
        _download([md5_url], listing)
    for line in listing.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def fetch_sources(manifest: dict, cache: Path, *, offline: bool, pin: bool) -> list[str]:
    """Download (once) and verify every third-party source file. Returns problems."""
    cache.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for comp in manifest["components"]:
        for entry in comp["files"]:
            local = cache / entry["name"]
            if not local.exists():
                if offline:
                    problems.append(f"{entry['name']}: not in the cache and --offline was given")
                    continue
                print(f"  downloading {entry['name']}")
                _download(entry["urls"], local)
            digest = sha256_of(local)
            if entry.get("sha256"):
                if digest != entry["sha256"].lower():
                    problems.append(f"{entry['name']}: SHA-256 {digest} does not match the recorded {entry['sha256']}")
                continue
            if entry.get("sha256_url"):
                listing = cache / (entry["name"] + ".sha256")
                if not listing.exists() and not offline:
                    _download([entry["sha256_url"]], listing)
                published = listing.read_text(encoding="utf-8", errors="replace").split()[0].lower() if listing.exists() else ""
                if published != digest:
                    problems.append(f"{entry['name']}: SHA-256 {digest} does not match the publisher's {published or '(missing)'}")
                    continue
            if entry.get("md5_list"):
                want = _qt_md5(entry["md5_list"], entry["name"], cache)
                h = hashlib.md5()
                h.update(local.read_bytes())
                if want is None or h.hexdigest() != want:
                    problems.append(f"{entry['name']}: MD5 does not match the publisher's list ({want})")
                    continue
            if pin:
                entry["sha256"] = digest
                print(f"  pinned {entry['name']} sha256={digest}")
            else:
                problems.append(f"{entry['name']}: no SHA-256 recorded (run once with --pin)")
    return problems


def _readme(manifest: dict, version: str) -> str:
    lines = [
        f"# Monograph PDF {version} — source archive",
        "",
        f"This archive is the corresponding source for the Monograph PDF {version} binary release",
        f"(`MonographPDF_{version}_Setup.exe` / `MonographPDF_{version}_Installer.zip`). It is published together with the release.",
        "",
        "| Folder | Contents |",
        "| :--- | :--- |",
        "| `monograph-pdf/` | Corresponding Monograph PDF release source (AGPL-3.0-or-later): application, build scripts (`scripts/`), installer script (`installer/`), release tests, documentation |",
        "| `third-party/` | Unmodified upstream source archives of the bundled AGPL / GPL / LGPL components; for the OCR engine's libraries the MSYS2 source packages (`*.src.tar.zst`: upstream archive, PKGBUILD and patches) of exactly the shipped binary packages |",
        "| `LICENSES/` | License texts: AGPL-3.0, GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-1.1, GCC Runtime Library Exception |",
        "| `SOURCE_MANIFEST.json` | For every component: license, the release files it covers, the source files with SHA-256 and their download address |",
        "",
        "## Components and the binaries they cover",
        "",
        "| Component | Version | License | Release files | Source in this archive |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for c in manifest["components"]:
        src = c["location"] + (", ".join(f["name"] for f in c["files"]) if c["files"] else "")
        if c.get("msys2"):
            src += f" (source of MSYS2 binary package `{c['msys2']['binary_package']}`, DLLs byte-identical)"
        lines.append(f"| {c['name']} | {c['version']} | {c['license']} | {', '.join('`' + p + '`' for p in c['covers'])} | {src} |")
    lines += [
        "",
        "Not requiring source distribution:",
        "",
    ]
    for e in manifest["exempt"]:
        lines.append(f"- {e['component']} ({e['license']}): {e['reason']} Files: {', '.join('`' + p + '`' for p in e['covers'])}.")
    lines += [
        "- The remaining bundled components not listed as requiring corresponding-source distribution use permissive licenses or applicable runtime/bootloader exceptions (see `monograph-pdf/THIRD_PARTY_NOTICES.md`).",
        "",
        "## Building Monograph PDF from this source",
        "",
        "On Windows 10/11 with Python 3.11, in `monograph-pdf/`:",
        "",
        "1. `powershell -ExecutionPolicy Bypass -File scripts\\setup_env.ps1` — creates `env\\` with the pinned packages of `requirements.txt`.",
        "2. Install Tesseract 5.4.0.20240606 (`choco install tesseract --version 5.4.0.20240606`), then `powershell -ExecutionPolicy Bypass -File scripts\\vendor_ocr.ps1` — places the OCR engine and the eng / jpn / osd language data in `engines\\ocr` and `models\\tessdata`, only if every file matches the SHA-256 pinned in `scripts/ci/ocr_engine_pins.json`.",
        "3. Install Inno Setup 6 into `tools\\inno` (or system-wide).",
        "4. `installer\\build_release.bat` — tests, `MonographPDF.exe`, self-check, `uninstall.exe`, `Setup.exe`, this source archive.",
        "",
        "The third-party archives build with their own instructions (PyMuPDF builds MuPDF from `mupdf-*-source.tar.gz`; Qt and PySide6 with CMake; the OCR libraries with the MSYS2 MINGW64 toolchain: unpack a `.src.tar.zst` and run `makepkg-mingw` in its folder).",
        "",
        "Not included: build tools (Python, PyInstaller, Inno Setup, compilers), development caches, and local personal-document validation utilities that embed private or machine-local paths (development-only; not part of corresponding-source coverage).",
        "",
    ]
    return "\n".join(lines)


def build(out: Path, cache: Path, *, offline: bool = False, pin: bool = False, root: Path = ROOT,
          manifest_path: Path = MANIFEST) -> int:
    manifest = load_manifest(manifest_path)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if manifest["release"] != version:
        print(f"third_party_sources.json is for {manifest['release']}, VERSION is {version}", file=sys.stderr)
        return 1
    problems = fetch_sources(manifest, cache, offline=offline, pin=pin)
    if pin:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files = product_files(root)
    for rel in files:
        if rel.suffix.lower() in TEXT_SUFFIXES:
            problems += scan_text(rel.as_posix(), (root / rel).read_bytes())
    if problems:
        print("Source archive FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    top = f"MonographPDF_{version}_Source"
    record = {"release": version, "archive": out.name, "components": [], "exempt": manifest["exempt"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.write(root / rel, f"{top}/monograph-pdf/{rel.as_posix()}")
        for name, src in LICENSE_FILES.items():
            z.write(root / src, f"{top}/LICENSES/{name}")
        for comp in manifest["components"]:
            entry = {k: comp[k] for k in ("id", "name", "version", "license", "covers", "location") if k in comp}
            entry["files"] = []
            if comp["id"] == "monograph-pdf":
                entry["files"] = [{"name": "monograph-pdf/", "count": len(files)}]
            for f in comp["files"]:
                arc = f"{top}/{comp['location']}{f['name']}"
                # upstream archives are already compressed: store them as they are
                z.write(cache / f["name"], arc, compress_type=zipfile.ZIP_STORED)
                entry["files"].append({"name": f["name"], "path": arc[len(top) + 1:], "sha256": f["sha256"], "source": f["urls"][0]})
            for key in ("msys2", "binaries"):
                if comp.get(key):
                    entry[key] = comp[key]
            if comp.get("notes"):
                entry["notes"] = comp["notes"]
            record["components"].append(entry)
        z.writestr(f"{top}/SOURCE_MANIFEST.json", json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        z.writestr(f"{top}/README_SOURCE.md", _readme(manifest, version))
    tmp.replace(out)
    size = out.stat().st_size
    print(f"Wrote {out} ({size / 1048576:.1f} MB, {len(files)} Monograph PDF files, "
          f"{sum(len(c['files']) for c in manifest['components'])} third-party archives)")
    print(f"sha256 {sha256_of(out).upper()}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--cache", type=Path, default=ROOT / "packages" / "sources")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--pin", action="store_true")
    a = ap.parse_args(argv)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    out = a.out or ROOT / "installer" / f"MonographPDF_{version}_Source.zip"
    return build(out, a.cache, offline=a.offline, pin=a.pin)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
