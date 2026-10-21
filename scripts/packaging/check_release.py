"""Release-content gate for Monograph PDF builds (run by build_exe.ps1 and build_release.ps1).

    python scripts/packaging/check_release.py prune   <dist\\MonographPDF>
    python scripts/packaging/check_release.py check   <install-layout folder> [--release <release folder>] [--json <out>]
    python scripts/packaging/check_release.py check-source <MonographPDF_x.y.z_Source.zip> <install-layout folder>
    python scripts/packaging/check_release.py guard-frozen <installer\\release> <version> <releases folder>
    python scripts/packaging/check_release.py superseded <installer> <version> <releases folder> <dest>

prune  removes bundled parts Monograph PDF never uses (Qt's network/TLS plugins, Qt Quick/QML and
       the virtual keyboard, Qt's own PDF plugin, FFmpeg video I/O, software OpenGL; Python's own
       ssl module stays for update checks and approved problem reports) and then checks, from every remaining DLL's import table, that nothing still
       needs a removed file. Fails the build otherwise.
check  every program file (.exe .dll .pyd) in the layout must belong to a component listed in
       RELEASE_COMPONENTS below, and each component must be named in THIRD_PARTY_NOTICES.md;
       no secrets, keys, environment files, development folders or private paths may be packaged.
       No file of the predecessor PDF Editor (PDF_editor.exe, its logo or icons) may remain.
       Writes an inventory (component, files, bytes) and SHA-256 of MonographPDF.exe.

check-source  the source archive (make_source_archive.py) matches the release: every component's
       archives are present with their SHA-256, Monograph PDF's source is complete and has no
       development files, secrets or private paths, and every release file whose license requires
       corresponding source (REQUIRES_SOURCE) is covered.
superseded  release files of other versions in installer\\ are moved to build\\superseded\\<v>\\ when an
       identical copy is archived under releases\\MonographPDF_<v>\\ (otherwise the build stops).
guard-frozen  installer\\release is about to be rebuilt: if it holds another version's release (for
       example the frozen internal archive PDFEditor_0.1.5), an identical copy must exist under releases\\.

An unknown program file fails the build, so a new library cannot enter a release without being
added here and to THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Paths relative to the PyInstaller output folder (dist\MonographPDF)
PRUNE = [
    "_internal/PySide6/plugins/tls",
    "_internal/PySide6/plugins/networkinformation",
    "_internal/PySide6/plugins/generic/qtuiotouchplugin.dll",
    "_internal/PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "_internal/PySide6/plugins/imageformats/qpdf.dll",
    "_internal/PySide6/Qt6VirtualKeyboard.dll",
    "_internal/PySide6/Qt6Quick.dll",
    "_internal/PySide6/Qt6Qml.dll",
    "_internal/PySide6/Qt6QmlMeta.dll",
    "_internal/PySide6/Qt6QmlModels.dll",
    "_internal/PySide6/Qt6QmlWorkerScript.dll",
    "_internal/PySide6/Qt6Pdf.dll",
    "_internal/PySide6/Qt6Network.dll",
    "_internal/PySide6/QtNetwork.pyd",
    "_internal/PySide6/opengl32sw.dll",
    "_internal/cv2/opencv_videoio_ffmpeg*.dll",
    # Python's own _ssl.pyd and libssl-3.dll stay: update checks and approved problem reports use HTTPS
    # (core/updates/net.py, core/diagnostics/client.py). Qt's network and TLS stack is still removed.
    # PyInstaller's Qt hook copies any OpenSSL 3 DLLs it finds on PATH next to QtNetwork (which is
    # removed above). On a machine with Git for Windows on PATH these are Git's MSYS2 builds.
    "_internal/libssl-3-x64.dll",
    "_internal/libcrypto-3-x64.dll",
]

# component -> (file patterns relative to the installation folder, name in THIRD_PARTY_NOTICES.md)
RELEASE_COMPONENTS: dict[str, tuple[list[str], str]] = {
    "Monograph PDF launcher (PyInstaller bootloader)": (["MonographPDF.exe"], "PyInstaller"),
    "Monograph PDF uninstaller": (["uninstall.exe", "unins000.exe"], "Inno Setup"),
    "Monograph PDF update helper": (["MonographPDFUpdater.exe"], "Monograph PDF"),
    "Python runtime": (
        ["_internal/python3.dll", "_internal/python311.dll", "_internal/_*.pyd", "_internal/select.pyd",
         "_internal/unicodedata.pyd", "_internal/pyexpat.pyd", "_internal/libffi-8.dll"],
        "Python",
    ),
    "OpenSSL (Python hashlib and ssl)": (["_internal/libcrypto-3.dll", "_internal/libssl-3.dll"], "OpenSSL"),
    "Microsoft Visual C++ / Universal C runtime": (
        ["_internal/VCRUNTIME140*.dll", "_internal/ucrtbase.dll", "_internal/api-ms-win-*.dll",
         "_internal/PySide6/VCRUNTIME140*.dll", "_internal/PySide6/MSVCP140*.dll",
         "_internal/shiboken6/VCRUNTIME140*.dll", "_internal/shiboken6/MSVCP140*.dll",
         "_internal/numpy.libs/msvcp140-*.dll"],
        "Microsoft Visual C++",
    ),
    "Qt 6 / PySide6 / Shiboken6": (["_internal/PySide6/*", "_internal/PySide6/plugins/*/*", "_internal/shiboken6/*"], "PySide6"),
    "PyMuPDF / MuPDF": (["_internal/pymupdf/*"], "PyMuPDF"),
    "OpenCV": (["_internal/cv2/*"], "OpenCV"),
    "NumPy": (["_internal/numpy/*"], "NumPy"),
    "OpenBLAS (NumPy)": (["_internal/numpy.libs/libscipy_openblas64_*.dll"], "OpenBLAS"),
    "Pillow": (["_internal/PIL/*"], "Pillow"),
    "lxml": (["_internal/lxml/*"], "lxml"),
    "fontTools": (["_internal/fontTools/*"], "fontTools"),
    "Tesseract OCR and its libraries": (["engines/ocr/*"], "Tesseract"),
}

# Never in a release: secrets, keys, environment files, development and test material
FORBIDDEN_NAMES = [
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*.kdbx", ".git", ".gitignore",
    "pytest.ini", "conftest.py", "*.spec", "requirements*.txt", "*.log", ".pytest_cache", ".ruff_cache",
]
FORBIDDEN_DIRS = ["tests", "build", "env", "packages", "tools", "reports", ".git", "scripts"]
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
]
PRIVATE_PATH_PATTERNS = [re.compile(rb"Software[ ]testing"), re.compile(rb"(?i)[A-Z]:\\Users\\[A-Za-z0-9_.-]+\\(?:Desktop|Documents|Downloads)")]
TEXT_SUFFIXES = {".md", ".txt", ".json", ".cff", ".ini", ".cfg", ".xml", ".html"}
# Files of the predecessor product that must not ship in a Monograph PDF release
LEGACY_BRANDING = ["PDF_editor.exe", "PDF_logo.png", "pdf_editor*.png", "pdf_editor*.ico", "pdf_editor*.svg", "pdf_editor_logo*"]
MAIN_EXE = "MonographPDF.exe"


def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def component_of(rel: str) -> str | None:
    for name, (patterns, _notice) in RELEASE_COMPONENTS.items():
        for p in patterns:
            if fnmatch.fnmatch(rel, p) or (p.endswith("/*") and rel.startswith(p[:-1])):
                return name
    return None


def _pe_imports(path: Path) -> set[str]:
    import pefile  # build-time only (installed with PyInstaller)

    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        return {e.dll.decode("ascii", "replace").lower() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    except pefile.PEFormatError:
        return set()


def prune(dist: Path) -> int:
    removed: list[Path] = []
    for pattern in PRUNE:
        for target in sorted(dist.glob(pattern)):
            removed.append(target)
            if target.is_dir():
                removed.extend(p for p in target.rglob("*") if p.is_file())
                shutil.rmtree(target)
            else:
                target.unlink()
    names = {p.name.lower() for p in removed if p.suffix.lower() in (".dll", ".pyd")}
    # a name only counts as missing when no copy of it is left anywhere in the bundle (the OCR engine
    # ships its own libcrypto-3-x64.dll beside libarchive)
    names -= {p.name.lower() for p in dist.rglob("*") if p.is_file()}
    try:
        import pefile  # noqa: F401
    except ImportError:
        print("check_release: pefile is not installed; dependency check skipped", file=sys.stderr)
        return 0
    broken = []
    for binary in dist.rglob("*"):
        if binary.suffix.lower() in (".dll", ".pyd", ".exe") and binary.is_file():
            needed = _pe_imports(binary) & names
            if needed:
                broken.append(f"{_rel(binary, dist)} needs {', '.join(sorted(needed))}")
    print(f"pruned {sum(1 for p in removed if p.suffix)} files")
    if broken:
        print("A removed file is still needed:\n  " + "\n  ".join(broken), file=sys.stderr)
        return 1
    return 0


def check(layout: Path, release: Path | None, json_out: Path | None) -> int:
    problems: list[str] = []
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    inventory: dict[str, dict] = {}
    for f in sorted(p for p in layout.rglob("*") if p.is_file()):
        rel = _rel(f, layout)
        if f.suffix.lower() in (".exe", ".dll", ".pyd", ".com", ".scr", ".ocx", ".sys"):
            comp = component_of(rel)
            if comp is None:
                problems.append(f"unexpected program file (not in RELEASE_COMPONENTS): {rel}")
                continue
            entry = inventory.setdefault(comp, {"files": 0, "bytes": 0})
            entry["files"] += 1
            entry["bytes"] += f.stat().st_size
        for pruned in PRUNE:
            if fnmatch.fnmatch(rel, pruned) or rel.startswith(pruned + "/"):
                problems.append(f"file that the build removes is present: {rel}")
    for comp, (_patterns, notice) in RELEASE_COMPONENTS.items():
        if comp in inventory and notice.lower() not in notices.lower():
            problems.append(f"{comp}: '{notice}' is not named in THIRD_PARTY_NOTICES.md")

    for base in [layout] + ([release] if release else []):
        for f in base.rglob("*"):
            rel = _rel(f, base)
            parts = rel.split("/")
            if any(fnmatch.fnmatch(parts[-1], pat) for pat in FORBIDDEN_NAMES):
                problems.append(f"{base.name}: development or secret file packaged: {rel}")
            if f.is_dir() and parts[0] in FORBIDDEN_DIRS and len(parts) == 1:
                problems.append(f"{base.name}: development folder packaged: {rel}")
            if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
                data = f.read_bytes()
                for pat in SECRET_PATTERNS:
                    if pat.search(data):
                        problems.append(f"{base.name}: possible secret in {rel}")
                for pat in PRIVATE_PATH_PATTERNS:
                    if pat.search(data):
                        problems.append(f"{base.name}: private path in {rel}")

    for base in [layout] + ([release] if release else []):
        for f in base.rglob("*"):
            if any(fnmatch.fnmatch(f.name, pat) for pat in LEGACY_BRANDING):
                problems.append(f"{base.name}: old PDF Editor file packaged: {_rel(f, base)}")
    exe = layout / MAIN_EXE
    if not exe.is_file():
        problems.append(f"{MAIN_EXE} is missing")
    report = {
        "components": inventory,
        "main_exe": MAIN_EXE,
        "main_exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest().upper() if exe.is_file() else None,
        "problems": problems,
    }
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for comp, e in inventory.items():
        print(f"  {comp:48} {e['files']:4} files {e['bytes'] / 1048576:8.1f} MB")
    if problems:
        print("Release check FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print("Release check passed.")
    return 0


# Release files whose license requires the corresponding source to be distributed with the binary,
# and the source-archive components that must provide it (None: any component that covers the file).
# Independent of third_party_sources.json, so a component left out of the source archive is found.
REQUIRES_SOURCE: list[tuple[str, list[str], list[str] | None]] = [
    ("Monograph PDF (AGPL-3.0-or-later)", ["MonographPDF.exe", "uninstall.exe", "MonographPDFUpdater.exe"], ["monograph-pdf"]),
    ("pdf2docx inside MonographPDF.exe (GPL-3.0)", ["_internal/pdf2docx-*.dist-info/*"], ["pdf2docx"]),
    ("PyMuPDF / MuPDF (AGPL-3.0)", ["_internal/pymupdf/*"], ["pymupdf", "mupdf"]),
    ("Qt / PySide6 / Shiboken6 (LGPL-3.0)", ["_internal/PySide6/Qt6*.dll", "_internal/PySide6/plugins/*", "_internal/PySide6/*.pyd",
                                            "_internal/PySide6/pyside6.abi3.dll", "_internal/shiboken6/*.pyd",
                                            "_internal/shiboken6/shiboken6.abi3.dll"], None),
    ("OCR engine LGPL / GPL libraries", [f"engines/ocr/{n}" for n in (
        "libglib-*.dll", "libgio-*.dll", "libgobject-*.dll", "libgmodule-*.dll", "libpango*.dll", "libcairo-*.dll",
        "libfribidi-*.dll", "libthai-*.dll", "libdatrie-*.dll", "libgraphite2.dll", "libiconv-*.dll", "libintl-*.dll",
        "libjbig-*.dll")], None),
]


def _covered(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) or (p.endswith("/*") and rel.startswith(p[:-1])) for p in patterns)


def source_gaps(layout_files: list[str], manifest: dict, archive_ids: set[str] | None = None) -> list[str]:
    """Release files that need corresponding source but are not covered by a component that is
    (in) the source archive. ``archive_ids`` defaults to every component of the manifest."""
    comps = {c["id"]: c for c in manifest["components"]}
    present = set(comps) if archive_ids is None else archive_ids
    gaps = []
    for group, patterns, required in REQUIRES_SOURCE:
        files = [f for f in layout_files if _covered(f, patterns)]
        if not files:
            continue
        if required:
            missing = [r for r in required if r not in present]
            if missing:
                gaps.append(f"{group}: source component(s) {', '.join(missing)} missing")
            continue
        for f in files:
            if not any(_covered(f, comps[i]["covers"]) for i in present if i in comps):
                gaps.append(f"{group}: no source component covers {f}")
    return gaps


def check_source(archive: Path, layout: Path) -> int:
    """The source archive matches this release: every component's files are present with their
    recorded SHA-256, Monograph PDF's source is complete and clean, and every release file that
    needs corresponding source is covered."""
    import zipfile

    problems: list[str] = []
    layout_files = sorted(_rel(p, layout) for p in layout.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) != 1:
            return print(f"source archive has {len(tops)} top folders", file=sys.stderr) or 1
        top = tops.pop()
        record = json.loads(z.read(f"{top}/SOURCE_MANIFEST.json"))
        for comp in record["components"]:
            for f in comp["files"]:
                if comp["id"] == "monograph-pdf":
                    continue
                arc = f"{top}/{f['path']}"
                if arc not in names:
                    problems.append(f"{comp['id']}: {f['path']} missing from the archive")
                    continue
                h = hashlib.sha256()
                with z.open(arc) as fh:
                    for block in iter(lambda: fh.read(1 << 20), b""):
                        h.update(block)
                if h.hexdigest() != f["sha256"]:
                    problems.append(f"{comp['id']}: {f['path']} does not match its SHA-256")
            for rel, digest in (comp.get("binaries") or {}).items():
                # the shipped binary is the one this source belongs to
                f = layout / rel
                if f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() != digest:
                    problems.append(f"{comp['id']}: {rel} in the release is not the binary the source package belongs to")
        for need in ("monograph-pdf/LICENSE.md", "monograph-pdf/app/bootstrap.py", "monograph-pdf/installer/MonographPDF.iss",
                     "monograph-pdf/scripts/build_release.ps1", "monograph-pdf/requirements.txt",
                     "monograph-pdf/THIRD_PARTY_NOTICES.md", "monograph-pdf/resources/icons/source/Monograph_PDF_logo.png",
                     "README_SOURCE.md", "LICENSES/AGPL-3.0.txt", "LICENSES/GPL-2.0.txt", "LICENSES/GPL-3.0.txt",
                     "LICENSES/LGPL-2.1.txt", "LICENSES/LGPL-3.0.txt"):
            if f"{top}/{need}" not in names:
                problems.append(f"missing {need}")
        for n in names:
            rel = n[len(top) + 1:]
            if not rel.startswith("monograph-pdf/") or n.endswith("/"):
                continue
            parts = rel.split("/")
            if set(parts) & {"__pycache__", ".pytest_cache", ".ruff_cache", "env", ".git", "outputs", "samples"} or \
                    any(fnmatch.fnmatch(parts[-1], p) for p in ("*.pyc", ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.log", "*.exe", "*.dll")):
                problems.append(f"development or secret file in the source archive: {rel}")
            if Path(parts[-1]).suffix.lower() in TEXT_SUFFIXES | {".py", ".ps1", ".iss", ".cs", ".bat"}:
                data = z.read(n)
                for pat in SECRET_PATTERNS:
                    if pat.search(data):
                        problems.append(f"possible secret in {rel}")
                for pat in PRIVATE_PATH_PATTERNS:
                    if pat.search(data):
                        problems.append(f"private path in {rel}")
    problems += source_gaps(layout_files, record, {c["id"] for c in record["components"]})
    if problems:
        print("Source archive check FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"Source archive check passed ({len(record['components'])} components, {len(names)} entries).")
    return 0


def _release_version(release: Path) -> str | None:
    """Version named on the first line of a release folder's SHA256SUMS.txt (None if absent)."""
    sums = release / "SHA256SUMS.txt"
    if not sums.is_file():
        return None
    m = re.search(r"\b(\d+\.\d+\.\d+)\b", sums.read_text(encoding="utf-8", errors="replace").splitlines()[0] if sums.stat().st_size else "")
    return m.group(1) if m else "unknown"


def _tree_hashes(folder: Path) -> dict[str, str]:
    out = {}
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        out[_rel(f, folder)] = h.hexdigest()
    return out


def guard_frozen(release: Path, version: str, archive_root: Path) -> int:
    """installer\\release may be rebuilt only if it is empty, holds this version, or holds a release
    that is kept byte for byte under ``archive_root/<name>/release``."""
    found = _release_version(release)
    if found is None or found == version:
        print(f"installer release folder: {'empty' if found is None else 'version ' + found} - may be rebuilt")
        return 0
    current = _tree_hashes(release)
    for copy in sorted(archive_root.glob("*/release")) if archive_root.is_dir() else []:
        if _tree_hashes(copy) == current:
            print(f"installer release folder holds {found}; an identical copy is kept in {copy}")
            return 0
    print(f"installer release folder holds release {found}, which is not archived under {archive_root}.\n"
          f"Copy it unchanged to {archive_root}\\<Product>_{found}\\release first; it is never overwritten.", file=sys.stderr)
    return 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def superseded(installer: Path, version: str, archive_root: Path, dest: Path) -> int:
    """Release files of *other* versions left in ``installer`` (MonographPDF_<v>_Setup.exe /
    _Installer.zip / _Source.zip) are moved to ``dest/<v>/`` - only if a byte-identical copy is kept
    under ``archive_root/MonographPDF_<v>/``. Otherwise nothing is moved and the build stops, so an
    unarchived release is never lost and the new release set never mixes versions. Nothing is deleted."""
    pattern = re.compile(r"^MonographPDF_(\d+\.\d+\.\d+)_(Setup\.exe|Installer\.zip|Source\.zip)$")
    others = sorted(p for p in installer.glob("MonographPDF_*") if p.is_file()
                    and (m := pattern.match(p.name)) and m.group(1) != version)
    missing = []
    for f in others:
        kept = archive_root / f"MonographPDF_{pattern.match(f.name).group(1)}" / f.name
        if not kept.is_file() or _sha256(kept) != _sha256(f):
            missing.append(f"{f.name} (no identical copy at {kept})")
    if missing:
        print("Release files of an earlier version are in the installer folder but not archived:\n  "
              + "\n  ".join(missing) + f"\nCopy them unchanged to {archive_root / 'MonographPDF_<version>'} first.",
              file=sys.stderr)
        return 1
    for f in others:
        target = dest / pattern.match(f.name).group(1) / f.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.stem}.{int(f.stat().st_mtime)}{target.suffix}")
        shutil.move(str(f), str(target))
        print(f"moved archived earlier release file {f.name} -> {target}")
    if not others:
        print("installer folder: no release files of other versions")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[0] == "guard-frozen":
        return guard_frozen(Path(argv[1]), argv[2], Path(argv[3]))
    if len(argv) >= 5 and argv[0] == "superseded":
        return superseded(Path(argv[1]), argv[2], Path(argv[3]), Path(argv[4]))
    if len(argv) >= 3 and argv[0] == "check-source":
        return check_source(Path(argv[1]), Path(argv[2]))
    if len(argv) >= 2 and argv[0] == "prune":
        return prune(Path(argv[1]))
    if len(argv) >= 2 and argv[0] == "check":
        release = json_out = None
        if "--release" in argv:
            release = Path(argv[argv.index("--release") + 1])
        if "--json" in argv:
            json_out = Path(argv[argv.index("--json") + 1])
        return check(Path(argv[1]), release, json_out)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
