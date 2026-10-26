"""Release source archive (MonographPDF_<version>_Source.zip): every release file whose license requires
corresponding source is covered, the manifest is complete and consistent with the MSYS2 recipes,
and the archive contains Monograph PDF's source without development files, secrets or personal data.
No network: third-party archives are replaced by small stand-ins in a temporary cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "scripts" / "packaging"
sys.path.insert(0, str(PACKAGING))
import check_release as cr  # noqa: E402
import make_source_archive as msa  # noqa: E402

sys.path.remove(str(PACKAGING))

MANIFEST = msa.load_manifest()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

# Every program file of the release that is under a copyleft license (from the built release)
COPYLEFT_RELEASE_FILES = [
    "MonographPDF.exe",
    "_internal/pdf2docx-0.5.8.dist-info/METADATA",
    "_internal/pymupdf/mupdfcpp64.dll", "_internal/pymupdf/_mupdf.pyd", "_internal/pymupdf/_extra.pyd",
    *[f"_internal/PySide6/{n}" for n in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6PrintSupport.dll", "Qt6OpenGL.dll",
                                       "Qt6Svg.dll", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtPrintSupport.pyd",
                                       "pyside6.abi3.dll")],
    *[f"_internal/PySide6/plugins/{n}" for n in ("platforms/qwindows.dll", "platforms/qdirect2d.dll", "platforms/qminimal.dll",
                                               "platforms/qoffscreen.dll", "styles/qmodernwindowsstyle.dll", "iconengines/qsvgicon.dll",
                                               "imageformats/qgif.dll", "imageformats/qico.dll", "imageformats/qjpeg.dll",
                                               "imageformats/qsvg.dll", "imageformats/qicns.dll", "imageformats/qtga.dll",
                                               "imageformats/qtiff.dll", "imageformats/qwbmp.dll", "imageformats/qwebp.dll")],
    "_internal/shiboken6/Shiboken.pyd", "_internal/shiboken6/shiboken6.abi3.dll",
    *[f"engines/ocr/{n}" for n in ("libglib-2.0-0.dll", "libgio-2.0-0.dll", "libgobject-2.0-0.dll", "libgmodule-2.0-0.dll",
                                   "libpango-1.0-0.dll", "libpangocairo-1.0-0.dll", "libpangoft2-1.0-0.dll", "libpangowin32-1.0-0.dll",
                                   "libcairo-2.dll", "libfribidi-0.dll", "libthai-0.dll", "libdatrie-1.dll", "libgraphite2.dll",
                                   "libiconv-2.dll", "libintl-8.dll", "libjbig-0.dll")],
]
PERMISSIVE_RELEASE_FILES = ["_internal/PySide6/VCRUNTIME140.dll", "engines/ocr/libpng16-16.dll", "engines/ocr/tesseract.exe",
                            "_internal/cv2/cv2.pyd", "_internal/python311.dll"]


def test_every_copyleft_release_file_is_covered_by_the_source_archive():
    files = COPYLEFT_RELEASE_FILES + PERMISSIVE_RELEASE_FILES
    assert cr.source_gaps(files, MANIFEST) == []
    # every copyleft file really is selected by REQUIRES_SOURCE (the list is not silently narrow)
    required = [f for f in files if any(cr._covered(f, pats) for _g, pats, _r in cr.REQUIRES_SOURCE)]  # noqa: SLF001
    assert sorted(required) == sorted(COPYLEFT_RELEASE_FILES)


@pytest.mark.parametrize("drop", ["ocr-jbigkit", "ocr-glib2", "qt-qtimageformats", "mupdf", "pdf2docx", "monograph-pdf"])
def test_a_missing_component_is_reported(drop):
    ids = {c["id"] for c in MANIFEST["components"]} - {drop}
    gaps = cr.source_gaps(COPYLEFT_RELEASE_FILES, MANIFEST, ids)
    assert gaps, f"dropping {drop} went unnoticed"


def test_manifest_is_complete_and_matches_the_build_recipes():
    assert MANIFEST["release"] == VERSION and MANIFEST["archive"] == f"MonographPDF_{VERSION}_Source.zip"
    names = set()
    for comp in MANIFEST["components"]:
        assert comp["license"] and comp["covers"] and comp["location"].startswith(("monograph-pdf/", "third-party/")), comp["id"]
        for f in comp["files"]:
            assert f["urls"] and all(u.startswith("https://") for u in f["urls"]), f
            assert f.get("sha256") or f.get("md5_list") or f.get("sha256_url"), f"{f['name']}: no hash to verify against"
            assert f["name"] not in names, f"duplicate {f['name']}"
            names.add(f["name"])
        if comp["id"].startswith("ocr-"):
            m = comp["msys2"]
            assert m["binary_package"].startswith("mingw-w64-x86_64-") and m["source_package"] == comp["files"][0]["name"]
            assert comp["files"][0]["name"].endswith(".src.tar.zst") and len(m["recipe_commit"]) == 40
            ver = m["binary_package"].rsplit("-", 3)[1]
            assert comp["version"].startswith(ver), (comp["id"], ver)
            assert set(comp["binaries"]) == set(comp["covers"]) and all(len(h) == 64 for h in comp["binaries"].values())
    for e in MANIFEST["exempt"]:
        assert "exception" in e["license"].lower(), e


def test_license_texts_are_shipped_and_notices_point_to_the_source_archive():
    for name in ("GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-1.1", "GCC-exception-3.1"):
        text = (ROOT / "third_party" / "licenses" / f"{name}.txt").read_text(encoding="utf-8")
        assert len(text) > 2000, name
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert f"MonographPDF_{VERSION}_Source.zip" in notices
    assert "on request" not in notices.lower()
    iss = (ROOT / "installer" / "MonographPDF.iss").read_text(encoding="utf-8-sig")
    assert 'third_party\\licenses\\*.txt"' in iss and 'DestDir: "{app}\\licenses"' in iss
    inventory = (ROOT / "licenses" / "DEPENDENCY_INVENTORY.md").read_text(encoding="utf-8")
    assert "MonographPDF_<version>_Source.zip" in inventory


def test_source_selection_leaves_out_development_and_personal_files():
    files = {p.as_posix() for p in msa.product_files()}
    assert {"app/bootstrap.py", "installer/MonographPDF.iss", "scripts/build_release.ps1", "requirements.txt", "LICENSE.md",
            "resources/icons/source/Monograph_PDF_logo.png", "resources/icons/windows/monograph_pdf.ico"} <= files
    for f in files:
        parts = f.split("/")
        assert not ({"__pycache__", ".pytest_cache", "env", "outputs"} & set(parts)), f
        assert not f.startswith(("tests/samples/", "installer/release/", "build/", "dist/", "packages/", "tools/", "runtime/",
                                 "releases/")), f
        assert not f.endswith((".pyc", ".exe", ".dll", ".zip")), f
    for personal in ("scripts/validate_real_pdfs.py", "tests/integration/test_user_real_pdfs.py",
                     "tests/integration/test_live_real_pdf_qa.py", "scripts/run_live_real_pdf_qa.py",
                     "tests/integration/test_round6_real_pdfs.py",
                     "reports/audit/MONOGRAPH_PDF_COMPREHENSIVE_QA_REPORT.md"):
        assert personal not in files
    assert not [f for f in files if f.startswith("reports/audit/qa_evidence/") or f.startswith("scripts/qa_")]
    assert "reports/audit/SECURITY_AUDIT_0.2.0.md" in files  # the published security audit stays
    assert "reports/audit/PROJECT_AUDIT.md" not in files  # internal records are not published
    assert "reports/audit/SECURITY_AUDIT_0.1.5.md" not in files
    problems = [p for rel in files if Path(rel).suffix.lower() in msa.TEXT_SUFFIXES
                for p in msa.scan_text(rel, (ROOT / rel).read_bytes())]
    assert problems == []


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


GIT_ID = ("-c", "user.name=Test", "-c", "user.email=test@example.invalid")


def _synthetic_repo(root: Path) -> tuple[Path, Path]:
    """A tiny committed project with every file the archive needs (synthetic content only)."""
    files = {
        "VERSION": b"9.9.9\n",
        "README.md": b"# Synthetic project\nline two\n",
        "LICENSE": b"official license text\n",
        "LICENSE.md": b"license summary\n",
        "docs/USER_GUIDE.md": b"guide\n",
        "tests/fixtures/sample.pdf": b"%PDF-1.7\r\n%\x00\xff binary with CRLF bytes\r\n%%EOF\r\n",
    }
    files.update({src: f"{name} text\n".encode() for name, src in msa.LICENSE_FILES.items() if src not in files})
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    _git(root, "init", "-q")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "-A")
    _git(root, *GIT_ID, "commit", "-q", "-m", "synthetic")
    manifest = root.parent / f"{root.name}-manifest.json"
    manifest.write_text(json.dumps({"release": "9.9.9", "archive": "x.zip", "exempt": [], "components": [
        {"id": "monograph-pdf", "name": "Monograph PDF", "version": "9.9.9", "license": "AGPL-3.0-or-later",
         "covers": [], "location": "monograph-pdf/", "files": []}]}), encoding="utf-8")
    cache = root.parent / "cache"
    cache.mkdir(exist_ok=True)
    return manifest, cache


def _entries(path: Path) -> dict[str, tuple[str, tuple, int, int, int]]:
    with zipfile.ZipFile(path) as z:
        return {i.filename: (hashlib.sha256(z.read(i)).hexdigest(), i.date_time, i.create_system, i.external_attr >> 16,
                             i.compress_type) for i in z.infolist()}


def test_untracked_files_in_a_checkout_never_reach_the_archive(tmp_path):
    """Only committed files are source: an untracked or merely staged file in a source folder (a private
    note, a local copy such as engines/ocr/TESSERACT_NOTICE.txt made by setup_env.ps1) is left out.
    Without .git (an unpacked source archive) every file in the source folders counts."""
    root = tmp_path / "checkout"
    for rel in ("README.md", "docs/USER_GUIDE.md", "docs/private-notes.md", "engines/ocr/TESSERACT_NOTICE.txt"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("synthetic\n", encoding="utf-8")
    unpacked = {p.as_posix() for p in msa.product_files(root)}
    assert {"README.md", "docs/USER_GUIDE.md", "docs/private-notes.md", "engines/ocr/TESSERACT_NOTICE.txt"} <= unpacked
    _git(root, "init", "-q")
    _git(root, "add", "README.md", "docs/USER_GUIDE.md")
    _git(root, *GIT_ID, "commit", "-q", "-m", "synthetic")
    _git(root, "add", "docs/private-notes.md")  # staged, never committed
    files = {p.as_posix() for p in msa.product_files(root)}
    assert files == {"README.md", "docs/USER_GUIDE.md"}


def test_archive_bytes_do_not_depend_on_the_checkout_line_endings(tmp_path):
    """Two clones of the same commit, one with core.autocrlf=true (CRLF working files) and one with
    false, give byte-identical archives: text is taken from the committed blobs (LF), the binary
    fixture keeps its CRLF bytes, and every entry has fixed metadata."""
    origin = tmp_path / "origin"
    manifest, cache = _synthetic_repo(origin)
    outs = []
    for crlf in ("true", "false"):
        clone = tmp_path / f"clone-{crlf}"
        subprocess.run(["git", "-c", f"core.autocrlf={crlf}", "clone", "-q", "-c", f"core.autocrlf={crlf}",
                        str(origin), str(clone)], check=True, capture_output=True)
        readme = (clone / "README.md").read_bytes()
        assert (b"\r\n" in readme) == (crlf == "true")  # the working copies really differ
        out = tmp_path / f"out-{crlf}" / "MonographPDF_9.9.9_Source.zip"
        assert msa.build(out, cache, offline=True, root=clone, manifest_path=manifest) == 0  # clean: no --allow-dirty
        outs.append(out)
    assert msa.sha256_of(outs[0]) == msa.sha256_of(outs[1])
    again = tmp_path / "again" / "MonographPDF_9.9.9_Source.zip"
    assert msa.build(again, cache, offline=True, root=origin, manifest_path=manifest) == 0
    assert msa.sha256_of(again) == msa.sha256_of(outs[0])
    entries = _entries(outs[0])
    names = list(entries)
    top = "MonographPDF_9.9.9_Source/"
    assert names[:names.index(top + "LICENSES/AGPL-3.0.txt")] == sorted(names[:names.index(top + "LICENSES/AGPL-3.0.txt")])
    with zipfile.ZipFile(outs[0]) as z:
        assert z.read(top + "monograph-pdf/README.md") == b"# Synthetic project\nline two\n"
        assert z.read(top + "monograph-pdf/tests/fixtures/sample.pdf") == (origin / "tests/fixtures/sample.pdf").read_bytes()
        assert z.read(top + "LICENSES/AGPL-3.0.txt") == b"official license text\n"  # the official text, unchanged
        commit_time = int(subprocess.run(["git", "-C", str(origin), "show", "-s", "--format=%ct", "HEAD"],
                                         capture_output=True, text=True, check=True).stdout)
        assert json.loads(z.read(top + "SOURCE_MANIFEST.json"))["commit"]
    t = time.gmtime(commit_time)
    stamp = (*t[:5], t.tm_sec - t.tm_sec % 2)  # ZIP time: 2-second resolution
    for name, (_, date_time, system, mode, method) in entries.items():
        assert (date_time, system, mode) == (stamp, 3, 0o100644), name
        assert method == zipfile.ZIP_DEFLATED, name


def test_uncommitted_changes_stop_the_build_unless_allowed(tmp_path):
    root = tmp_path / "checkout"
    manifest, cache = _synthetic_repo(root)
    (root / "README.md").write_bytes(b"# edited but not committed\n")
    out = tmp_path / "MonographPDF_9.9.9_Source.zip"
    assert msa.build(out, cache, offline=True, root=root, manifest_path=manifest) == 1
    assert not out.exists()
    assert msa.build(out, cache, offline=True, root=root, manifest_path=manifest, allow_dirty=True) == 0
    with zipfile.ZipFile(out) as z:  # still the committed bytes
        assert z.read("MonographPDF_9.9.9_Source/monograph-pdf/README.md") == b"# Synthetic project\nline two\n"


def test_unpacked_source_builds_are_deterministic_too(tmp_path, monkeypatch):
    """Without .git the files on disk are used; SOURCE_DATE_EPOCH (or 1980-01-01) dates every entry."""
    root = tmp_path / "unpacked"
    manifest, cache = _synthetic_repo(root)
    shutil.rmtree(root / ".git", onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")  # 2026-01-01
    a, b = tmp_path / "a" / "x.zip", tmp_path / "b" / "x.zip"
    assert msa.build(a, cache, offline=True, root=root, manifest_path=manifest) == 0
    assert msa.build(b, cache, offline=True, root=root, manifest_path=manifest) == 0
    assert msa.sha256_of(a) == msa.sha256_of(b)
    assert {e[1] for e in _entries(a).values()} == {(2026, 1, 1, 0, 0, 0)}


def test_source_selection_ships_the_repository_documents():
    """The top-level documents, and every local file README.md links to, are in the source archive."""
    files = {p.as_posix() for p in msa.product_files()}
    required = {"README.md", "LICENSE", "LICENSE.md", "CONTRIBUTING.md", "SECURITY.md", "INSTALLATION.md",
                "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "CITATION.cff", "VERSION", "requirements.txt",
                "requirements-ci.txt", "pytest.ini", ".gitattributes"}
    assert required <= files, sorted(required - files)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)|src=\"([^\"]+)\"", readme)
    local = {t for pair in targets for t in pair if t and "://" not in t and not t.startswith("mailto:")}
    assert local, "README.md links to no local files"
    missing = sorted(t for t in local if (ROOT / t).is_file() and t not in files)
    assert missing == [], missing


def _small_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """The real manifest with each third-party archive replaced by a small stand-in file."""
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = json.loads(json.dumps(MANIFEST))
    for comp in manifest["components"]:
        for f in comp["files"]:
            data = f"stand-in for {f['name']}".encode()
            (cache / f["name"]).write_bytes(data)
            f["sha256"] = hashlib.sha256(data).hexdigest()
            f.pop("md5_list", None)
            f.pop("sha256_url", None)
    path = tmp_path / "third_party_sources.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, cache


def test_built_source_archive_is_complete_portable_and_private(tmp_path):
    """The archive as built (stand-in third-party files): public documents and licenses in, internal audit
    records and local paths out, portable unique entry names, and every third-party file matching the
    SHA-256 recorded in SOURCE_MANIFEST.json."""
    manifest_path, cache = _small_manifest(tmp_path)
    out = tmp_path / f"MonographPDF_{VERSION}_Source.zip"
    assert msa.build(out, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    top = f"MonographPDF_{VERSION}_Source/"
    with zipfile.ZipFile(out) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        assert len(names) == len(set(names)), "duplicate entries"
        assert len({n.lower() for n in names}) == len(names), "entries differing only in case"
        assert not [n for n in names if "\\" in n or n.startswith("/") or ".." in n.split("/")]
        project = {n[len(top + "monograph-pdf/"):] for n in names if n.startswith(top + "monograph-pdf/")}
        for need in ("README.md", "LICENSE", "LICENSE.md", "CONTRIBUTING.md", "SECURITY.md", "INSTALLATION.md",
                     "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "CITATION.cff", "VERSION", "requirements.txt",
                     "requirements-ci.txt", "scripts/vendor_ocr.ps1", "scripts/ci/stage_ocr_engine.py",
                     "scripts/ci/ocr_engine_pins.json", "installer/MonographPDF.iss",
                     "third_party/licenses/TESSERACT_NOTICE.txt", "tests/fixtures/templates/manifest.json"):
            assert need in project, need
        audit = sorted(p for p in project if p.startswith("reports/"))
        assert audit == ["reports/audit/SECURITY_AUDIT_0.2.0.md"], audit
        assert not [p for p in project if p.startswith(("env/", "build/", "dist/", "packages/", "releases/", "tools/"))
                    or "__pycache__" in p or p.endswith((".pyc", ".exe", ".dll"))]
        problems = [p for i in infos if i.filename.startswith(top + "monograph-pdf/")
                    and Path(i.filename).suffix.lower() in msa.TEXT_SUFFIXES
                    for p in msa.scan_text(i.filename, z.read(i))]
        assert problems == []
        record = json.loads(z.read(top + "SOURCE_MANIFEST.json"))
        checked = 0
        for comp in record["components"]:
            for f in comp.get("files", []):
                member = [n for n in names if n.startswith(top + "third-party/") and n.endswith("/" + f["name"])]
                if not member:
                    continue  # the project itself is listed as a folder
                assert len(member) == 1, member
                assert hashlib.sha256(z.read(member[0])).hexdigest() == f["sha256"], f["name"]
                checked += 1
        assert checked == sum(len(c["files"]) for c in MANIFEST["components"] if c["id"] != "monograph-pdf") > 0
        readme = z.read(top + "README_SOURCE.md").decode()
        assert "vendor_ocr.ps1" in readme and "ocr_engine_pins.json" in readme and "5.4.0.20240606" in readme


def test_source_archive_is_built_and_passes_the_release_check(tmp_path):
    manifest_path, cache = _small_manifest(tmp_path)
    out = tmp_path / f"MonographPDF_{VERSION}_Source.zip"
    assert msa.build(out, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        top = f"MonographPDF_{VERSION}_Source/"
        assert all(n.startswith(top) for n in names)
        for need in ("README_SOURCE.md", "SOURCE_MANIFEST.json", "LICENSES/AGPL-3.0.txt", "LICENSES/LGPL-2.1.txt",
                     "monograph-pdf/app/bootstrap.py", "monograph-pdf/resources/icons/source/Monograph_PDF_logo.png", "third-party/ocr-engine/glib2/mingw-w64-glib2-2.80.2-2.src.tar.zst",
                     "third-party/qt/qtbase-everywhere-src-6.8.1.tar.xz",
                     "third-party/mupdf/mupdf-1.25.4-source.tar.gz"):
            assert top + need in names, need
        record = json.loads(z.read(top + "SOURCE_MANIFEST.json"))
        assert {c["id"] for c in record["components"]} == {c["id"] for c in MANIFEST["components"]}
        readme = z.read(top + "README_SOURCE.md").decode()
        assert "monograph-pdf/" in readme and "third-party/" in readme and "Monograph PDF" in readme
    layout = tmp_path / "layout"
    recorded = {rel for c in MANIFEST["components"] for rel in c.get("binaries", {})}
    for rel in COPYLEFT_RELEASE_FILES + PERMISSIVE_RELEASE_FILES:
        if rel in recorded:
            continue  # real DLL hashes are compared on Windows release builds
        (layout / rel).parent.mkdir(parents=True, exist_ok=True)
        (layout / rel).write_bytes(b"MZ")
    assert cr.check_source(out, layout) == 0


def test_source_check_rejects_tampered_or_incomplete_archives(tmp_path, capsys):
    manifest_path, cache = _small_manifest(tmp_path)
    good = tmp_path / "good.zip"
    assert msa.build(good, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    layout = tmp_path / "layout"
    recorded = {rel for c in MANIFEST["components"] for rel in c.get("binaries", {})}
    for rel in COPYLEFT_RELEASE_FILES:
        if rel not in recorded:
            (layout / rel).parent.mkdir(parents=True, exist_ok=True)
            (layout / rel).write_bytes(b"MZ")
    top = f"MonographPDF_{VERSION}_Source/"

    def rewrite(name: str, change):
        bad = tmp_path / name
        with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
            for item in src.infolist():
                data = change(item.filename, src.read(item.filename))
                if data is not None:
                    dst.writestr(item.filename, data)
        return bad

    assert cr.check_source(good, layout) == 0
    tampered = rewrite("tampered.zip", lambda n, d: b"changed" if n.endswith("jbigkit-2.1-5.src.tar.zst") else d)
    assert cr.check_source(tampered, layout) == 1
    no_qt = rewrite("noqt.zip", lambda n, d: None if "/third-party/qt/qtimageformats" in n else d)
    assert cr.check_source(no_qt, layout) == 1
    leaked = rewrite("leak.zip", lambda n, d: d)
    with zipfile.ZipFile(leaked, "a") as z:
        z.writestr(top + "monograph-pdf/.env", "TOKEN=x")
        z.writestr(top + "monograph-pdf/core/__pycache__/x.cpython-311.pyc", b"x")
    assert cr.check_source(leaked, layout) == 1
    manifest = json.loads(z_read(good, top + "SOURCE_MANIFEST.json"))
    manifest["components"] = [c for c in manifest["components"] if c["id"] != "ocr-cairo"]
    dropped = rewrite("dropped.zip", lambda n, d: json.dumps(manifest).encode() if n.endswith("SOURCE_MANIFEST.json") else d)
    cairo_only = tmp_path / "cairo-layout"
    (cairo_only / "engines" / "ocr").mkdir(parents=True)
    (cairo_only / "engines" / "ocr" / "libcairo-2.dll").write_bytes(b"MZ")
    capsys.readouterr()
    assert cr.check_source(dropped, cairo_only) == 1
    assert "no source component covers engines/ocr/libcairo-2.dll" in capsys.readouterr().err


def test_source_check_rejects_a_release_with_different_ocr_dlls(tmp_path):
    manifest_path, cache = _small_manifest(tmp_path)
    archive = tmp_path / "src.zip"
    assert msa.build(archive, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    layout = tmp_path / "layout"
    for rel in COPYLEFT_RELEASE_FILES:
        (layout / rel).parent.mkdir(parents=True, exist_ok=True)
        (layout / rel).write_bytes(b"MZ")
    # stand-in DLLs differ from the recorded MSYS2 binaries
    assert cr.check_source(archive, layout) == 1
    for comp in MANIFEST["components"]:
        for rel in comp.get("binaries", {}):
            (layout / rel).unlink()
    assert cr.check_source(archive, layout) == 0  # files absent from a layout are not compared


def z_read(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as z:
        return z.read(name)


def test_offline_build_without_cached_archives_fails(tmp_path):
    out = tmp_path / "x.zip"
    assert msa.build(out, tmp_path / "empty-cache", offline=True, allow_dirty=True) == 1
    assert not out.exists()


def test_release_scripts_publish_and_check_the_source_archive():
    build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8-sig")
    assert "make_source_archive.py" in build and "check-source $SourceZip $Payload" in build
    assert build.index("make_source_archive.py") < build.index("create_release_zip.ps1")
    zipper = (ROOT / "scripts" / "packaging" / "create_release_zip.ps1").read_text(encoding="utf-8-sig")
    assert "SHA256SUMS.txt" in zipper and "$SourceZip" in zipper and "Source.zip" in zipper


def test_make_source_archive_cli_help_runs():
    r = subprocess.run([sys.executable, str(PACKAGING / "make_source_archive.py"), "--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--offline" in r.stdout


def test_source_archive_and_checksums_use_the_new_names():
    """MonographPDF_<version>_Source.zip, SHA256SUMS lists MonographPDF.exe, installer package name."""
    assert msa.ROOT == ROOT
    zipper = (ROOT / "scripts" / "packaging" / "create_release_zip.ps1").read_text(encoding="utf-8-sig")
    assert '"{0}  MonographPDF.exe (installed program)"' in zipper
    assert "MonographPDF_${version}_Installer.zip" in zipper and "MonographPDF_${version}_Source.zip" in zipper
    assert '"Monograph PDF $version - SHA-256 checksums' in zipper
    assert "PDF_editor" not in zipper and "PDFEditor_" not in zipper
    build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8-sig")
    assert 'installer\\MonographPDF_${Version}_Source.zip' in build and 'installer\\MonographPDF_${Version}_Setup.exe' in build
    assert "guard-frozen" in build


def test_repeated_archive_generation_is_byte_identical(tmp_path):
    manifest_path, cache = _small_manifest(tmp_path)
    a = tmp_path / "a" / f"MonographPDF_{VERSION}_Source.zip"
    b = tmp_path / "b" / f"MonographPDF_{VERSION}_Source.zip"
    assert msa.build(a, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    assert msa.build(b, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 0
    assert msa.sha256_of(a) == msa.sha256_of(b)


def test_ocr_local_manifest_and_wrapper_are_excluded_from_selection(tmp_path):
    root = tmp_path / "tree"
    root.mkdir(parents=True)
    (root / "README.md").write_text("x\n", encoding="utf-8")
    ocr = root / "engines" / "ocr"
    ocr.mkdir(parents=True)
    (ocr / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (ocr / "MANIFEST.local.json").write_text('{"platform":"linux"}\n', encoding="utf-8")
    (ocr / "tesseract").write_text("#!/bin/sh\n", encoding="utf-8")
    files = {p.as_posix() for p in msa.product_files(root)}
    assert "engines/ocr/MANIFEST.json" in files
    assert "engines/ocr/MANIFEST.local.json" not in files
    assert "engines/ocr/tesseract" not in files


def test_download_http_404_tries_next_url_and_cleans_part(tmp_path, monkeypatch):
    dest = tmp_path / "pkg.src.tar.zst"
    calls: list[str] = []

    class Resp:
        def __init__(self, data: bytes):
            self._data = data

        def read(self, n: int = -1):
            if not self._data:
                return b""
            if n < 0:
                out, self._data = self._data, b""
                return out
            out, self._data = self._data[:n], self._data[n:]
            return out

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=120):  # noqa: ARG001
        url = req.get_full_url() if hasattr(req, "get_full_url") else str(req)
        calls.append(url)
        if "missing" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]
        return Resp(b"good-bytes")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    used = msa._download(
        ["https://example.test/missing/pkg.src.tar.zst", "https://example.test/mirror/pkg.src.tar.zst"],
        dest,
    )
    assert dest.read_bytes() == b"good-bytes"
    assert "mirror" in used
    assert not list(tmp_path.glob("*.part"))
    assert any("missing" in u for u in calls)


def test_download_rejects_non_https(tmp_path):
    dest = tmp_path / "x.bin"
    with pytest.raises(RuntimeError, match="no download address worked"):
        msa._download(["http://insecure.example/x.bin"], dest)
    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def test_invalid_checksum_removes_bad_cache_and_fails_build(tmp_path):
    manifest_path, cache = _small_manifest(tmp_path)
    # Corrupt one cached third-party file after pinning stand-in hashes.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    victim = next(f["name"] for c in manifest["components"] for f in c["files"])
    (cache / victim).write_bytes(b"tampered-after-pin")
    out = tmp_path / "bad.zip"
    assert msa.build(out, cache, offline=True, manifest_path=manifest_path, allow_dirty=True) == 1
    assert not out.exists()
    assert not (cache / victim).exists()  # mismatched file removed


def test_failed_zip_write_leaves_no_partial_archive(tmp_path, monkeypatch):
    manifest_path, cache = _small_manifest(tmp_path)
    out = tmp_path / "out.zip"
    real_replace = Path.replace

    def boom(self, target):  # noqa: ANN001
        if str(self).endswith(".zip.part"):
            raise OSError("simulated replace failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="simulated replace failure"):
        msa.build(out, cache, offline=True, manifest_path=manifest_path, allow_dirty=True)
    assert not out.exists()
    assert not list(tmp_path.glob("*.zip.part"))


def test_unicode_paths_round_trip_in_archive(tmp_path):
    """Japanese directory/file names and UTF-8 LF/CRLF payloads survive archive extract.

    Write fixtures with write_bytes (not write_text): on Windows, text mode would convert
    ``\\n`` to ``\\r\\n`` before git commits, which is unrelated to Unicode-path verification
    and breaks byte assertions that intentionally expect LF. The synthetic repo already sets
    ``core.autocrlf=false``, so committed bytes match what we write.
    """
    root = tmp_path / "checkout"
    manifest, cache = _synthetic_repo(root)
    lf_rel = "docs/日本語/案内.md"
    crlf_rel = "docs/日本語/改行CRLF.txt"
    name_rel = "docs/日本語ファイル名.md"
    (root / lf_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / lf_rel).write_bytes("こんにちは\n".encode("utf-8"))
    (root / crlf_rel).write_bytes("改行確認\r\n二行目\r\n".encode("utf-8"))
    (root / name_rel).write_bytes("ファイル名もUTF-8\n".encode("utf-8"))
    _git(root, "add", lf_rel, crlf_rel, name_rel)
    _git(root, *GIT_ID, "commit", "-q", "-m", "unicode")
    out = tmp_path / "u.zip"
    assert msa.build(out, cache, offline=True, root=root, manifest_path=manifest) == 0

    prefix = "MonographPDF_9.9.9_Source/monograph-pdf/"
    extract = tmp_path / "extracted"
    with zipfile.ZipFile(out) as z:
        assert z.read(prefix + lf_rel) == "こんにちは\n".encode("utf-8")
        assert z.read(prefix + crlf_rel) == "改行確認\r\n二行目\r\n".encode("utf-8")
        assert z.read(prefix + name_rel) == "ファイル名もUTF-8\n".encode("utf-8")
        # Safe extract: only product paths under the archive root (no zip-slip).
        for info in z.infolist():
            assert not info.filename.startswith("/") and ".." not in Path(info.filename).parts
        z.extractall(extract)

    got_lf = (extract / prefix / lf_rel).read_bytes()
    got_crlf = (extract / prefix / crlf_rel).read_bytes()
    got_name = (extract / prefix / name_rel).read_bytes()
    assert got_lf == "こんにちは\n".encode("utf-8")
    assert got_crlf == "改行確認\r\n二行目\r\n".encode("utf-8")
    assert got_name == "ファイル名もUTF-8\n".encode("utf-8")
    # Text decode with universal newlines still yields the same characters.
    assert got_lf.decode("utf-8").replace("\r\n", "\n") == "こんにちは\n"
    assert got_crlf.decode("utf-8").splitlines() == ["改行確認", "二行目"]


def test_msys2_ocr_pins_list_https_mirrors():
    for comp in MANIFEST["components"]:
        if not comp.get("msys2"):
            continue
        urls = comp["files"][0]["urls"]
        assert all(u.startswith("https://") for u in urls)
        assert any("repo.msys2.org" in u for u in urls)
        assert any("futureware.at" in u or "mirror.msys2.org" in u for u in urls)
