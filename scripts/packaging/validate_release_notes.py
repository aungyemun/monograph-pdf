"""Validate release notes before they are published (and in CI).

    python scripts/packaging/validate_release_notes.py NOTES.md --version 0.2.2
        [--artifacts DIR]        files named in the notes; their SHA-256 must match the notes
        [--changelog CHANGELOG.md] release date in the notes must match the changelog entry
        [--repo-root DIR]        links to blob/<tag>/<path> must name files that exist
        [--tests P,F,S]          the test summary must state exactly these numbers

Fails (exit 1) with one line per problem when the notes contain an unresolved template value
(``__NAME__``, ``{{name}}``, ``${name}``, ``<fill in>``, TODO/TBD/FIXME), a missing or malformed
SHA-256 line for an expected artifact, a checksum that differs from the file, an artifact name or
tag of another version, a missing test or installer summary, a relative or broken repository link,
an inconsistent release date, or broken Markdown structure (unclosed code fence, ragged table).
Placeholder-like values are never accepted as evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PRODUCT_FILE = "MonographPDF"
ARTIFACT_SUFFIXES = ("_Setup.exe", "_Installer.zip", "_Source.zip")
REQUIRED_SECTIONS = ("Download", "Verification", "Known limitations")
REPO = "aungyemun/monograph-pdf"

PLACEHOLDER_PATTERNS = [
    (re.compile(r"__[A-Z0-9][A-Z0-9_]*__"), "template variable"),
    (re.compile(r"\{\{[^}]*\}\}"), "template variable"),
    (re.compile(r"\$\{[^}]*\}"), "template variable"),
    (re.compile(r"<\s*(?:fill[^>]*|todo[^>]*|tbd|placeholder[^>]*|insert[^>]*)>", re.I), "placeholder"),
    (re.compile(r"\b(?:TODO|TBD|FIXME|XXX)\b"), "unfinished marker"),
    (re.compile(r"\b(?:0{64}|[fF]{64})\b"), "dummy checksum"),
]
SHA_LINE = re.compile(r"^\s*([0-9A-Fa-f]{64})\s+\*?(\S+)\s*$")
HEXISH_LINE = re.compile(r"^\s*(\S+)\s+\*?(" + PRODUCT_FILE + r"_\S+)\s*$")
TEST_SUMMARY = re.compile(r"(\d+)\s+passed,\s*(\d+)\s+failed,\s*(\d+)\s+skipped", re.I)
INSTALLER_SUMMARY = re.compile(r"installer[^\n]*?(\d+)\s+passed,\s*(\d+)\s+failed", re.I)
ARTIFACT_NAME = re.compile(PRODUCT_FILE + r"_(\d+\.\d+\.\d+)_[A-Za-z]+\.(?:exe|zip)")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")


@dataclass
class Result:
    problems: list[str] = field(default_factory=list)
    checksums: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def expected_artifacts(version: str) -> list[str]:
    return [f"{PRODUCT_FILE}_{version}{s}" for s in ARTIFACT_SUFFIXES]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _sections(text: str) -> set[str]:
    return {m.group(1).strip().lower() for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}


def _changelog_date(changelog: str, version: str) -> str | None:
    m = re.search(rf"^## \[{re.escape(version)}\] — (\S+)\s*$", changelog, re.M)
    return m.group(1) if m else None


def _markdown_problems(text: str) -> list[str]:
    problems = []
    if text.count("```") % 2:
        problems.append("Markdown: unclosed ``` code fence")
    lines = text.splitlines()
    in_code = False
    table: list[tuple[int, int]] = []

    def flush() -> None:
        if table and len({n for _l, n in table}) > 1:
            problems.append(f"Markdown: table starting on line {table[0][0]} has rows with different column counts")
        table.clear()

    for no, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            table.append((no, s.count("|") - s.count("\\|")))
        else:
            flush()
        if re.match(r"^#{1,6}[^#\s]", line):
            problems.append(f"Markdown: line {no}: heading needs a space after '#'")
    flush()
    return problems


def validate(text: str, version: str, *, artifacts: Path | None = None, changelog: str | None = None,
             repo_root: Path | None = None, tests: tuple[int, int, int] | None = None) -> Result:
    r = Result()
    p = r.problems
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        p.append(f"version {version!r} is not x.y.z")
    for no, line in enumerate(text.splitlines(), 1):
        for pat, kind in PLACEHOLDER_PATTERNS:
            for m in pat.finditer(line):
                p.append(f"line {no}: unresolved {kind}: {m.group(0)!r}")
    if version not in text:
        p.append(f"the notes never mention version {version}")
    sections = _sections(text)
    for wanted in REQUIRED_SECTIONS:
        if not any(s.startswith(wanted.lower()) for s in sections):
            p.append(f"missing section '## {wanted}'")

    # checksums
    for line in text.splitlines():
        m = SHA_LINE.match(line)
        if m:
            r.checksums[m.group(2)] = m.group(1).lower()
        else:
            h = HEXISH_LINE.match(line)
            if h and not re.fullmatch(r"[0-9A-Fa-f]{64}", h.group(1)):
                p.append(f"checksum for {h.group(2)} is not a SHA-256 value: {h.group(1)!r}")
    for name in expected_artifacts(version):
        if name not in r.checksums:
            p.append(f"no SHA-256 line for {name}")
    for name in r.checksums:
        if name not in expected_artifacts(version):
            p.append(f"checksum for unexpected file {name}")
    if artifacts is not None:
        for name, digest in r.checksums.items():
            f = artifacts / name
            if not f.is_file():
                p.append(f"{name}: file not found in {artifacts}")
            elif _sha256(f) != digest:
                p.append(f"{name}: SHA-256 in the notes ({digest}) differs from the file ({_sha256(f)})")

    # artifact names and tags of other versions
    for m in ARTIFACT_NAME.finditer(text):
        if m.group(1) != version:
            p.append(f"artifact name of another version: {m.group(0)}")
    for m in re.finditer(r"/(?:tree|blob|releases/tag)/v(\d+\.\d+\.\d+)", text):
        if m.group(1) != version:
            p.append(f"link to another version's tag: v{m.group(1)}")

    # results
    ts = next((m for line in text.splitlines() if "installer" not in line.lower()
               for m in [TEST_SUMMARY.search(line)] if m), None)
    if not ts:
        p.append("missing test summary ('N passed, N failed, N skipped')")
    elif tests is not None and tuple(int(x) for x in ts.groups()) != tests:
        p.append(f"test summary {ts.group(0)!r} differs from the recorded run {tests}")
    if not INSTALLER_SUMMARY.search(text):
        p.append("missing installer test result ('Installer test … N passed, N failed')")

    # links
    for m in LINK.finditer(text):
        target = m.group(2)
        if target.startswith("#"):
            continue
        if not re.match(r"https?://", target):
            p.append(f"relative link does not work in release notes: {target}")
            continue
        bm = re.match(rf"https://github\.com/{re.escape(REPO)}/blob/[^/]+/(.+?)(?:#.*)?$", target)
        if bm and repo_root is not None and not (repo_root / bm.group(1)).exists():
            p.append(f"link to a file that does not exist: {bm.group(1)}")

    # dates
    if changelog is not None:
        when = _changelog_date(changelog, version)
        if when is None:
            p.append(f"CHANGELOG has no '## [{version}] — <date>' entry")
        else:
            for d in set(DATE.findall(text)):
                if d != when:
                    p.append(f"date {d} differs from the CHANGELOG release date {when}")
            if when.lower() == "unreleased":
                p.append(f"CHANGELOG still marks {version} as Unreleased")

    p.extend(_markdown_problems(text))
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("notes", type=Path)
    ap.add_argument("--version", required=True)
    ap.add_argument("--artifacts", type=Path)
    ap.add_argument("--changelog", type=Path)
    ap.add_argument("--repo-root", type=Path)
    ap.add_argument("--tests", help="passed,failed,skipped of the recorded run")
    a = ap.parse_args(argv)
    tests = tuple(int(x) for x in a.tests.split(",")) if a.tests else None
    text = a.notes.read_text(encoding="utf-8")
    changelog = a.changelog.read_text(encoding="utf-8") if a.changelog else None
    r = validate(text, a.version, artifacts=a.artifacts, changelog=changelog, repo_root=a.repo_root, tests=tests)
    for problem in r.problems:
        print(f"FAIL  {problem}")
    if r.ok:
        print(f"PASS  {a.notes} — {len(r.checksums)} checksums" + (" verified against the files" if a.artifacts else ""))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
