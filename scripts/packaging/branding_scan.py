"""Branding scan: find every remaining reference to the predecessor product PDF Editor and classify it.

    python scripts/packaging/branding_scan.py [--layout <built app folder>] [--json <out>] [--show <class>]

Searched patterns: PDF Editor, PDF_editor(.exe), PDFEditor_, PDF_logo.png, pdf_editor.ico, and the old
%APPDATA% / %LOCALAPPDATA% / Program Files paths. Every match is classified as

  EXPECTED-HISTORICAL               release history (CHANGELOG entries <= 0.1.5, the 0.1.5 audit,
                                    statements that Monograph PDF succeeds PDF Editor)
  EXPECTED-MIGRATION-COMPATIBILITY  code, installer, tests and documentation that recognise, upgrade,
                                    migrate or clean up PDF Editor installations and data, deprecated
                                    PDFEDITOR_* aliases, PDF private keys kept for file compatibility
  INCORRECT-STALE-BRANDING          anything else: the old name used as the active product identity

Exit code 1 when an INCORRECT-STALE-BRANDING match exists. With --layout, the files of a built
application (text files, and file names) are scanned too: there every match is stale unless it is
in the release history (CHANGELOG.md, README / notices statements) — the program must not contain the
old identity.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PATTERN = re.compile(
    r"PDF Editor|PDF_editor|PDFEditor_|(?<![A-Za-z_])PDF_logo\.png|pdf_editor\.ico"
    r"|%APPDATA%\\\\?PDF Editor|%LOCALAPPDATA%\\\\?PDF Editor|Program Files\\\\?PDF Editor"
)
SCAN_TOP = ["app", "core", "engines", "ui", "resources", "installer", "scripts", "tests", "docs", "licenses",
            "third_party", "reports"]
SCAN_FILES = ["README.md", "INSTALLATION.md", "LICENSE.md", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CHANGELOG.md",
              "CITATION.cff", "requirements.txt", "pytest.ini", ".gitignore", "VERSION"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "env", "build", "dist", "release", "outputs", "samples", ".git"}
TEXT = {".py", ".ps1", ".bat", ".iss", ".cs", ".md", ".txt", ".json", ".cff", ".qss", ".ini", ".cfg", ""}

HISTORICAL_FILES = {"reports/audit/SECURITY_AUDIT_0.1.5.md"}
# Files whose purpose is recognising / migrating / cleaning up PDF Editor or testing that
MIGRATION_FILES = {
    "core/legacy_migration.py", "core/app_env.py", "tests/unit/test_monograph_migration.py",
    "scripts/packaging/branding_scan.py", "scripts/packaging/write_installed_manifest.py",
    "tests/unit/test_installed_manifest.py",
    # Setup's active identity comes from #define AppName / AppExe (pinned by tests); every literal
    # PDF Editor name in the script detects, upgrades or cleans up the predecessor
    "installer/MonographPDF.iss",
}
# Build outputs that are regenerated (never committed)
SKIP_FILES = {"installer/build_release_summary.txt"}
# Words that mark a line as describing the predecessor, its history or the migration from it
CONTEXT = re.compile(
    r"(?i)successor|succeeds|formerly|previously|predecessor|renamed|new name|final (?:PDF Editor )?release|"
    r"legacy|upgrad|migrat|<= ?0\.1\.5|≤ ?0\.1\.5|0\.1\.5|old |earlier|deprecated|alias|left by|stale|"
    r"recognis|recogniz|replac|kept from|compatib|still read|was your default|coming from|instead of|existing PDF Editor"
)
# Code identifiers that exist only for the predecessor
LEGACY_IDENT = re.compile(r"Legacy|LEGACY_|legacy_|IsLegacy|PDFEditorAlign|PDFEditorVAlign|PDFEDITOR_|releases[\\/]PDFEditor_0\.1\.5")


def _files(root: Path) -> list[Path]:
    out = [root / f for f in SCAN_FILES if (root / f).is_file()]
    for top in SCAN_TOP:
        base = root / top
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            rel = f.relative_to(root)
            if f.is_file() and not (SKIP_PARTS & set(rel.parts)) and f.suffix.lower() in TEXT:
                out.append(f)
    return sorted(out)


def _changelog_history_start(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.startswith("## [0.1.5]"):
            return i
    return len(lines)


def classify(rel: str, line: str, lineno: int, history_from: int, previous: str = "") -> str:
    if rel in HISTORICAL_FILES or (rel == "CHANGELOG.md" and lineno >= history_from):
        return "EXPECTED-HISTORICAL"
    if rel in MIGRATION_FILES or LEGACY_IDENT.search(line):
        return "EXPECTED-MIGRATION-COMPATIBILITY"
    if rel.startswith("tests/") and re.search(r"(?i)legacy|0\.1\.5|PDF_editor|PDFEditor|PDF_logo|pdf_editor", line):
        return "EXPECTED-MIGRATION-COMPATIBILITY"  # tests asserting the old names are recognised / absent
    if rel == "scripts/test_installer.ps1":
        return "EXPECTED-MIGRATION-COMPATIBILITY"  # installs the frozen PDF Editor 0.1.5 to test the upgrade
    if "Monograph" in line or "monograph" in line:
        # the line relates the two names (detection, upgrade, cleanup or history)
        return "EXPECTED-HISTORICAL" if re.search(r"(?i)successor|succeeds|formerly|previously|final|renamed|new name", line) \
            else "EXPECTED-MIGRATION-COMPATIBILITY"
    if CONTEXT.search(line) or "unregistered" in line:
        if re.search(r"(?i)successor|succeeds|formerly|previously|final (?:PDF Editor )?release|renamed|new name", line):
            return "EXPECTED-HISTORICAL"
        return "EXPECTED-MIGRATION-COMPATIBILITY"
    if previous and (CONTEXT.search(previous) or LEGACY_IDENT.search(previous)):
        return "EXPECTED-MIGRATION-COMPATIBILITY"  # explained by the line before (comment or heading)
    return "INCORRECT-STALE-BRANDING"


def scan(root: Path = ROOT, layout: Path | None = None) -> list[dict]:
    hits: list[dict] = []
    for f in _files(root):
        rel = f.relative_to(root).as_posix()
        if rel in SKIP_FILES:
            continue
        try:
            lines = f.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        history_from = _changelog_history_start(lines) if rel == "CHANGELOG.md" else 0
        for i, line in enumerate(lines):
            for m in PATTERN.finditer(line):
                hits.append({"file": rel, "line": i + 1, "match": m.group(0),
                             "class": classify(rel, line, i, history_from, lines[i - 1] if i else ""),
                             "text": line.strip()[:200]})
    if layout is not None:
        for f in sorted(layout.rglob("*")):
            rel = "layout/" + f.relative_to(layout).as_posix()
            if PATTERN.search(f.name) or re.search(r"(?i)^pdf_editor", f.name):
                hits.append({"file": rel, "line": 0, "match": f.name, "class": "INCORRECT-STALE-BRANDING", "text": "file name"})
            if f.is_file() and f.suffix.lower() in {".md", ".txt", ".json", ".cff"} and f.stat().st_size < 5_000_000:
                lines = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                history_from = _changelog_history_start(lines) if f.name == "CHANGELOG.md" else 0
                for i, line in enumerate(lines):
                    for m in PATTERN.finditer(line):
                        cls = classify(f.name if f.name in ("CHANGELOG.md",) else rel, line, i, history_from,
                                       lines[i - 1] if i else "")
                        if f.name not in ("CHANGELOG.md", "README.md", "THIRD_PARTY_NOTICES.md", "LICENSE.md",
                                          "INSTALLATION.md", "USER_GUIDE.md", "SECURITY.md", "DEPENDENCY_INVENTORY.md",
                                          "CITATION.cff"):
                            cls = "INCORRECT-STALE-BRANDING"
                        hits.append({"file": rel, "line": i + 1, "match": m.group(0), "class": cls, "text": line.strip()[:200]})
    return hits


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layout", type=Path, help="built application folder (e.g. dist\\MonographPDF)")
    ap.add_argument("--json", type=Path, help="write all matches as JSON")
    ap.add_argument("--show", default="INCORRECT-STALE-BRANDING", help="class to list in full (or 'all')")
    a = ap.parse_args(argv)
    hits = scan(ROOT, a.layout)
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["class"]] = counts.get(h["class"], 0) + 1
    files: dict[str, set] = {}
    for h in hits:
        files.setdefault(h["class"], set()).add(h["file"])
    for cls in ("EXPECTED-HISTORICAL", "EXPECTED-MIGRATION-COMPATIBILITY", "INCORRECT-STALE-BRANDING"):
        print(f"{cls:34} {counts.get(cls, 0):5} matches in {len(files.get(cls, ())):3} files")
    for h in hits:
        if a.show == "all" or h["class"] == a.show:
            print(f"  [{h['class']}] {h['file']}:{h['line']}: {h['text']}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"counts": counts, "matches": hits}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if counts.get("INCORRECT-STALE-BRANDING") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
