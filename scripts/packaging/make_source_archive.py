"""Build the release-matched source archive, e.g. ``MonographPDF_0.2.0_Source.zip``.

    python scripts/packaging/make_source_archive.py --out installer\\MonographPDF_0.2.0_Source.zip
           [--cache packages\\sources] [--offline] [--pin]

The archive contains

    MonographPDF_<version>_Source/
      README_SOURCE.md        what is where, how to build, which binaries each source covers
      SOURCE_MANIFEST.json    every component: license, release files covered, source files, SHA-256
      LICENSES/               AGPL-3.0 (the official text, from LICENSE), GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-1.1,
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

Monograph PDF's own files: in a git checkout, the files committed in ``HEAD`` with their committed
bytes (untracked files, uncommitted edits and the checkout's line-ending conversion never reach the
archive; uncommitted changes to selected files stop the build unless ``--allow-dirty``); in an unpacked
source archive, the files on disk. Caches, virtual environments, build output, installers, generated
test files, files naming the developer's personal documents and anything matching the release check's
secret / private-path rules are left out (the build fails if such content is found in a file that would
be included).

The archive is deterministic: entries in a fixed order, every entry dated with the commit time (or
``SOURCE_DATE_EPOCH``, else 1980-01-01), Unix rw-r--r-- attributes, Deflate level 9 for project files
and stored third-party archives. The same commit and the same third-party archives give the same ZIP
bytes with the same Python version (its zlib).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("third_party_sources.json")

# Monograph PDF source: top-level items included (everything else in the project folder is not source)
SOURCE_TOP = [
    "app", "core", "engines", "ui", "resources", "installer", "scripts", "tests", "docs", "licenses",
    "third_party", "reports", "VERSION", "requirements.txt", "requirements-ci.txt", "pytest.ini", ".gitignore", ".gitattributes",
    "README.md", "LICENSE", "LICENSE.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "INSTALLATION.md",
    "LINUX.md",
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
    "AGPL-3.0.txt": "LICENSE",
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


class ProjectSource:
    """Monograph PDF's own files and their bytes.

    In a git checkout the archive is made from the committed tree (``HEAD``): only committed files are
    source, and their bytes are the git blobs, so the archive does not depend on the checkout's
    line-ending settings (core.autocrlf), on untracked files lying in a source folder (a local copy, a
    private note) or on uncommitted edits. Without ``.git`` (an unpacked source archive) the files on
    disk are used as they are."""

    def __init__(self, root: Path):
        self.root = root
        self.git = (root / ".git").exists()
        self.commit: str | None = None
        self.epoch: int | None = None
        self._tree: dict[str, str] = {}
        if self.git:
            self.commit = self._git("rev-parse", "HEAD").decode().strip()
            self.epoch = int(self._git("show", "-s", "--format=%ct", "HEAD").decode().strip())
            for rec in self._git("ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0"):
                if not rec:
                    continue
                meta, path = rec.split(b"\t", 1)
                mode, kind, sha = meta.decode().split()
                if kind == "blob" and mode in ("100644", "100755"):
                    self._tree[path.decode("utf-8", "surrogateescape")] = sha

    def _git(self, *args: str, data: bytes | None = None) -> bytes:
        try:
            out = subprocess.run(["git", "-C", str(self.root), *args], input=data, capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"{self.root} is a git checkout but git {args[0]} failed: {exc}") from exc
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])} failed in {self.root}: {out.stderr.decode(errors='replace').strip()}")
        return out.stdout

    def candidates(self) -> list[str]:
        if self.git:
            return sorted(self._tree)
        found = set()
        for top in SOURCE_TOP:
            base = self.root / top
            items = [base] if base.is_file() else base.rglob("*") if base.is_dir() else []
            found.update(p.relative_to(self.root).as_posix() for p in items if p.is_file())
        return sorted(found)

    def read(self, rel: str) -> bytes:
        if self.git:
            if rel not in self._tree:
                raise FileNotFoundError(f"{rel} is not committed in {self.commit}")
            return self._git("cat-file", "blob", self._tree[rel])
        return (self.root / rel).read_bytes()

    def read_many(self, rels: list[str]) -> dict[str, bytes]:
        """Bytes of many files; one ``git cat-file --batch`` call in a checkout."""
        if not self.git:
            return {r: self.read(r) for r in rels}
        missing = [r for r in rels if r not in self._tree]
        if missing:
            raise FileNotFoundError(f"not committed in {self.commit}: {', '.join(missing)}")
        raw = self._git("cat-file", "--batch", data="".join(self._tree[r] + "\n" for r in rels).encode())
        out, pos = {}, 0
        for r in rels:
            nl = raw.index(b"\n", pos)
            sha, kind, size = raw[pos:nl].decode().split()
            if sha != self._tree[r] or kind != "blob":
                raise RuntimeError(f"unexpected git cat-file reply for {r}")
            start = nl + 1
            out[r] = raw[start:start + int(size)]
            pos = start + int(size) + 1
        return out

    def uncommitted(self, rels: list[str]) -> list[str]:
        """Selected files whose working copy differs from HEAD in content (line endings excepted)."""
        if not self.git:
            return []
        changed = set(self._git("diff", "--name-only", "-z", "HEAD", "--").decode("utf-8", "surrogateescape").split("\0"))
        return sorted(set(rels) & changed)


def _selected(rel: str) -> bool:
    if not any(rel == top or rel.startswith(top + "/") for top in SOURCE_TOP):
        return False
    if EXCLUDE_PARTS & set(rel.split("/")):
        return False
    if any(fnmatch.fnmatch(rel, p) for p in EXCLUDE_PATHS):
        return False
    return not any(fnmatch.fnmatch(rel.rsplit("/", 1)[-1], p) for p in EXCLUDE_NAMES)


def product_files(root: Path = ROOT) -> list[Path]:
    """Monograph PDF's own source files, relative to ``root``, sorted (in a git checkout: committed files)."""
    return [Path(rel) for rel in ProjectSource(root).candidates() if _selected(rel)]


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
        "Text files are stored exactly as committed in the repository (the repository keeps them with LF line endings); binary files are byte-identical.",
        "",
        "Not included: build tools (Python, PyInstaller, Inno Setup, compilers), development caches, and local personal-document validation utilities that embed private or machine-local paths (development-only; not part of corresponding-source coverage).",
        "",
    ]
    return "\n".join(lines)


# Deterministic ZIP entries: the same source gives the same archive bytes (same Python / zlib).
ZIP_EPOCH_DEFAULT = 315532800  # 1980-01-01 00:00:00 UTC, the earliest ZIP date
COMPRESS_LEVEL = 9


def _zinfo(name: str, epoch: int, compress: int) -> zipfile.ZipInfo:
    """Fixed metadata for every entry: timestamp, Unix creator, regular file rw-r--r--, method."""
    t = time.gmtime(max(epoch, ZIP_EPOCH_DEFAULT))
    # ZIP (DOS) time has a 2-second resolution: round down so the stored time is exactly this one
    zi = zipfile.ZipInfo(name, date_time=(*t[:5], t.tm_sec - t.tm_sec % 2))
    zi.create_system = 3
    zi.create_version = 20
    zi.extract_version = 20
    zi.external_attr = 0o100644 << 16
    zi.compress_type = compress
    return zi


def build(out: Path, cache: Path, *, offline: bool = False, pin: bool = False, root: Path = ROOT,
          manifest_path: Path = MANIFEST, allow_dirty: bool = False) -> int:
    source = ProjectSource(root)
    manifest = load_manifest(manifest_path)
    version = source.read("VERSION").decode("utf-8").strip()
    if manifest["release"] != version:
        print(f"third_party_sources.json is for {manifest['release']}, VERSION is {version}", file=sys.stderr)
        return 1
    problems = fetch_sources(manifest, cache, offline=offline, pin=pin)
    if pin:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files = [p.as_posix() for p in product_files(root)]
    license_srcs = sorted(set(LICENSE_FILES.values()))
    dirty = source.uncommitted(files + license_srcs)
    if dirty and not allow_dirty:
        problems.append("uncommitted changes (the archive is made from the committed files; commit them or use "
                        "--allow-dirty for a development build): " + ", ".join(dirty))
    data = source.read_many(sorted(set(files) | set(license_srcs)))
    for rel in files:
        if Path(rel).suffix.lower() in TEXT_SUFFIXES:
            problems += scan_text(rel, data[rel])
    if problems:
        print("Source archive FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    # Timestamp of every entry: the commit time in a checkout; otherwise SOURCE_DATE_EPOCH or 1980-01-01.
    epoch = source.epoch if source.epoch is not None else int(os.environ.get("SOURCE_DATE_EPOCH", ZIP_EPOCH_DEFAULT))
    top = f"MonographPDF_{version}_Source"
    record = {"release": version, "archive": out.name, "components": [], "exempt": manifest["exempt"]}
    if source.commit:
        record["commit"] = source.commit
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w") as z:
        def put(name: str, payload: bytes) -> None:
            z.writestr(_zinfo(name, epoch, zipfile.ZIP_DEFLATED), payload, compresslevel=COMPRESS_LEVEL)

        for rel in files:
            put(f"{top}/monograph-pdf/{rel}", data[rel])
        for name in sorted(LICENSE_FILES):
            put(f"{top}/LICENSES/{name}", data[LICENSE_FILES[name]])
        for comp in manifest["components"]:
            entry = {k: comp[k] for k in ("id", "name", "version", "license", "covers", "location") if k in comp}
            entry["files"] = []
            if comp["id"] == "monograph-pdf":
                entry["files"] = [{"name": "monograph-pdf/", "count": len(files)}]
            for f in comp["files"]:
                arc = f"{top}/{comp['location']}{f['name']}"
                # upstream archives are already compressed: store them as they are
                with open(cache / f["name"], "rb") as src, z.open(_zinfo(arc, epoch, zipfile.ZIP_STORED), "w") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                entry["files"].append({"name": f["name"], "path": arc[len(top) + 1:], "sha256": f["sha256"], "source": f["urls"][0]})
            for key in ("msys2", "binaries"):
                if comp.get(key):
                    entry[key] = comp[key]
            if comp.get("notes"):
                entry["notes"] = comp["notes"]
            record["components"].append(entry)
        put(f"{top}/SOURCE_MANIFEST.json", (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        put(f"{top}/README_SOURCE.md", _readme(manifest, version).encode("utf-8"))
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
    ap.add_argument("--allow-dirty", action="store_true",
                    help="development only: build although selected files have uncommitted changes "
                         "(the archive still contains the committed versions)")
    a = ap.parse_args(argv)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    out = a.out or ROOT / "installer" / f"MonographPDF_{version}_Source.zip"
    return build(out, a.cache, offline=a.offline, pin=a.pin, allow_dirty=a.allow_dirty)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
