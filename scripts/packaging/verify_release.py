"""Verify a complete release set before publishing — or a downloaded, already published one.

    python scripts/packaging/verify_release.py --dir installer [--version X.Y.Z]
        [--notes docs/releases/vX.Y.Z.md] [--tests P,F,S] [--layout dist/MonographPDF]

Checks, each reported as PASS / FAIL:
  artifacts     exactly MonographPDF_<v>_Setup.exe, _Installer.zip and _Source.zip; their SHA-256
  sums          SHA256SUMS.txt inside the Installer ZIP matches Setup.exe and the Source ZIP
  zip-names     Installer ZIP entry names are portable ('/' separators, no absolute or '..' paths)
  notices       Installer ZIP carries LICENSE, THIRD_PARTY_NOTICES, license texts, OCR and font notices
  versions      the release's own source (inside the Source ZIP): VERSION, CITATION.cff,
                THIRD_PARTY_NOTICES.md, third_party_sources.json, the dependency inventory and a dated
                CHANGELOG entry name this version; the Installer ZIP's CITATION and CHANGELOG too
  privacy       no private paths or secrets in any text file of both ZIPs (check_release.py patterns);
                none of the source-archive exclusions (personal-document tests, local QA material)
  ocr           (with --layout) the OCR engine and eng/jpn/osd language data are present
  update-trust  (with --layout) the bundled update and reporting configuration is the repository's
                own (a test build's synthetic keys, mock endpoints or test CA can never be released)
  --allow-unreleased  (build_release.ps1) a development build may carry an Unreleased CHANGELOG entry;
                publishing always needs a dated entry and --notes
  notes         (with --notes) validate_release_notes.py, with checksums verified against the files and
                links / dates checked against the release's own source

Nothing is published or changed; the exit code is 1 when any check fails.
"""

from __future__ import annotations

import argparse
import fnmatch
import tempfile
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import check_release as cr  # noqa: E402
import make_source_archive as msa  # noqa: E402
import validate_release_notes as vrn  # noqa: E402

INSTALLER_ZIP_REQUIRED = [
    "Setup.exe", "SHA256SUMS.txt", "LICENSE.md", "THIRD_PARTY_NOTICES.md", "README.md", "INSTALLATION.md",
    "SECURITY.md", "CITATION.cff", "CHANGELOG.md", "docs/USER_GUIDE.md", "runtime/ocr/TESSERACT_NOTICE.txt",
    "runtime/fonts/OFL.txt", "licenses/GPL-2.0.txt", "licenses/GPL-3.0.txt", "licenses/LGPL-2.1.txt",
    "licenses/LGPL-3.0.txt", "licenses/MPL-1.1.txt", "licenses/GCC-exception-3.1.txt",
]
OCR_REQUIRED = ["engines/ocr/tesseract.exe", "models/tessdata/eng.traineddata", "models/tessdata/jpn.traineddata",
                "models/tessdata/osd.traineddata"]
TEXT = {".md", ".txt", ".json", ".cff", ".py", ".ps1", ".bat", ".iss", ".cs", ".ini", ".cfg", ".toml", ".xml", ".html"}


class Report:
    def __init__(self) -> None:
        self.failed = False

    def check(self, name: str, problems: list[str], ok_detail: str = "") -> None:
        if problems:
            self.failed = True
            for p in problems:
                print(f"FAIL  {name}: {p}")
        else:
            print(f"PASS  {name}" + (f" — {ok_detail}" if ok_detail else ""))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def version_problems(version: str, root: Path) -> list[str]:
    p = []

    def need(rel: str, pattern: str) -> None:
        f = root / rel
        if not f.is_file():
            p.append(f"{rel} missing")
        elif not re.search(pattern, f.read_text(encoding="utf-8-sig")):
            p.append(f"{rel} does not name version {version}")

    v = re.escape(version)
    if (root / "VERSION").read_text(encoding="utf-8").strip() != version:
        p.append(f"VERSION is {(root / 'VERSION').read_text(encoding='utf-8').strip()!r}, not {version}")
    need("CITATION.cff", rf'(?m)^version: "{v}"')
    need("THIRD_PARTY_NOTICES.md", rf"\| Monograph PDF \| {v} \|")
    need("licenses/DEPENDENCY_INVENTORY.md", rf"Monograph PDF {v}\)")
    need("CHANGELOG.md", rf"(?m)^## \[{v}\] — ")
    src = json.loads((root / "scripts/packaging/third_party_sources.json").read_text(encoding="utf-8"))
    if src.get("release") != version or src.get("archive") != f"MonographPDF_{version}_Source.zip":
        p.append("scripts/packaging/third_party_sources.json names another release")
    return p


TRUST_FILES = ["resources/update/update_config.json", "resources/diagnostics/reporting.json"]


def trust_problems(layout: Path, root: Path) -> list[str]:
    """The update/reporting configuration inside the built app must equal the release's source."""
    problems = []
    bundled = layout / "_internal"
    for rel in TRUST_FILES:
        shipped, source = bundled / rel, root / rel
        if not shipped.is_file():
            problems.append(f"{rel} is missing from the application")
        elif not source.is_file() or shipped.read_bytes() != source.read_bytes():
            problems.append(f"{rel} differs from the repository's (test configuration in a release build?)")
    for folder in ("resources/update", "resources/diagnostics"):
        extra = sorted(p.name for p in (bundled / folder).glob("*") if (folder + "/" + p.name) not in TRUST_FILES) \
            if (bundled / folder).is_dir() else []
        if extra:
            problems.append(f"unexpected files in {folder}: {', '.join(extra)}")
    return problems


def scan_zip(path: Path, *, source: bool) -> list[str]:
    problems = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            parts = name.split("/", 2)
            if source and len(parts) == 3 and parts[1] == "monograph-pdf":
                if any(fnmatch.fnmatch(parts[2], pat) for pat in msa.EXCLUDE_PATHS):
                    problems.append(f"{path.name}: {parts[2]} should not be published (source-archive exclusion)")
            if Path(name).suffix.lower() not in TEXT or info.file_size > 20_000_000:
                continue
            data = z.read(info)
            for pat in cr.PRIVATE_PATH_PATTERNS:
                if pat.search(data):
                    problems.append(f"{path.name}: private path in {name}")
            for pat in cr.SECRET_PATTERNS:
                if pat.search(data):
                    problems.append(f"{path.name}: possible secret in {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, required=True, help="folder with the three release files")
    ap.add_argument("--version", default=(ROOT / "VERSION").read_text(encoding="utf-8").strip())
    ap.add_argument("--notes", type=Path)
    ap.add_argument("--tests")
    ap.add_argument("--layout", type=Path)
    ap.add_argument("--allow-unreleased", action="store_true",
                    help="build check of a development version: accept a CHANGELOG entry marked Unreleased")
    a = ap.parse_args(argv)
    v, rep = a.version, Report()
    names = vrn.expected_artifacts(v)
    setup, inst, src = (a.dir / n for n in names)

    missing = [n for n in names if not (a.dir / n).is_file()]
    others = sorted(p.name for p in a.dir.glob("MonographPDF_*") if p.is_file() and p.name not in names
                    and re.match(r"MonographPDF_\d", p.name) and not p.name.endswith(".part"))
    detail = ", ".join(f"{n} {sha256(a.dir / n)}" for n in names if (a.dir / n).is_file())
    rep.check("artifacts", [f"missing {n}" for n in missing] + [f"file of another release here: {o}" for o in others], detail)
    if missing:
        return 1

    with zipfile.ZipFile(inst) as z:
        entries = z.namelist()
        # orig_filename: the name as stored (on Windows zipfile already turns '\\' into '/')
        raw = [i.orig_filename for i in z.infolist()]
        bad = [e for e in raw if "\\" in e or e.startswith("/") or ".." in e.replace("\\", "/").split("/")]
        rep.check("zip-names", [f"non-portable entry name {e!r}" for e in bad], f"{len(entries)} entries")
        norm = {e.replace("\\", "/") for e in entries}
        rep.check("notices", [f"Installer ZIP lacks {r}" for r in INSTALLER_ZIP_REQUIRED if r not in norm])
        sums_name = next((e for e in entries if e.replace("\\", "/") == "SHA256SUMS.txt"), None)
        sums = z.read(sums_name).decode("utf-8-sig") if sums_name else ""
        inner_setup = next((e for e in entries if e.replace("\\", "/") == "Setup.exe"), None)
        inner_setup_hash = hashlib.sha256(z.read(inner_setup)).hexdigest() if inner_setup else ""
        zipped_docs = {e.replace("\\", "/"): z.read(e).decode("utf-8-sig", "replace") for e in entries
                       if e.replace("\\", "/") in ("CHANGELOG.md", "CITATION.cff", "README.md")}
    listed = {m.group(2).strip(): m.group(1).lower() for m in re.finditer(r"(?m)^([0-9A-Fa-f]{64})\s+(.+?)\s*$", sums)}
    problems = []
    if listed.get("Setup.exe") != sha256(setup):
        problems.append("SHA256SUMS.txt: Setup.exe differs from the published Setup.exe")
    if inner_setup_hash != sha256(setup):
        problems.append("the Setup.exe inside the Installer ZIP differs from the published Setup.exe")
    if listed.get(src.name) != sha256(src):
        problems.append(f"SHA256SUMS.txt: {src.name} differs from the published file")
    rep.check("sums", problems)

    tmp = tempfile.TemporaryDirectory(prefix="monograph_verify_")
    release_root = Path(tmp.name)
    with zipfile.ZipFile(src) as z:
        top = f"MonographPDF_{v}_Source/monograph-pdf/"
        members = [m for m in z.namelist() if m.startswith(top) and not m.endswith("/")]
        for m in members:
            dest = release_root / m[len(top):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(m))
    vp = version_problems(v, release_root) if members else [f"{src.name} has no {top} folder"]
    if not re.search(rf'(?m)^version: "{re.escape(v)}"', zipped_docs.get("CITATION.cff", "")):
        vp.append("CITATION.cff inside the Installer ZIP names another version")
    dated = r"(?:\d{4}-\d\d-\d\d|Unreleased)" if a.allow_unreleased else r"\d{4}-\d\d-\d\d"
    if not re.search(rf"(?m)^## \[{re.escape(v)}\] — {dated}", zipped_docs.get("CHANGELOG.md", "")):
        vp.append("CHANGELOG.md inside the Installer ZIP has no dated entry for this version")
    rep.check("versions", vp)

    rep.check("privacy", scan_zip(inst, source=False) + scan_zip(src, source=True))

    if a.layout is not None:
        rep.check("ocr", [f"missing {r}" for r in OCR_REQUIRED if not (a.layout / r).is_file()])
        rep.check("update-trust", trust_problems(a.layout, release_root))

    if a.notes is not None:
        changelog = (release_root / "CHANGELOG.md").read_text(encoding="utf-8")
        tests = tuple(int(x) for x in a.tests.split(",")) if a.tests else None
        r = vrn.validate(a.notes.read_text(encoding="utf-8"), v, artifacts=a.dir, changelog=changelog,
                         repo_root=release_root, tests=tests)
        rep.check("notes", r.problems, f"{len(r.checksums)} checksums match the files")
    else:
        print("NOT VERIFIED  notes: no --notes given (required before publishing)")

    tmp.cleanup()
    print("RESULT: " + ("FAIL" if rep.failed else "PASS"))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
