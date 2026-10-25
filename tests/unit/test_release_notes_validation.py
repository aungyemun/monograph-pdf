"""Release-note validation (scripts/packaging/validate_release_notes.py): notes with unresolved
template values, wrong checksums, missing results or broken links must never pass."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import validate_release_notes as vrn  # noqa: E402

V = "9.8.7"
CHANGELOG = f"# Changelog\n\n## [{V}] — 2031-02-03\n\n- x\n"


def _artifacts(tmp_path: Path) -> dict[str, str]:
    out = {}
    for i, name in enumerate(vrn.expected_artifacts(V)):
        data = f"artifact {i}".encode()
        (tmp_path / name).write_bytes(data)
        out[name] = hashlib.sha256(data).hexdigest()
    return out


def _notes(sums: dict[str, str], **override) -> str:
    parts = {
        "intro": f"Monograph PDF {V}.",
        "sums": "\n".join(f"{h}  {n}" for n, h in sums.items()),
        "tests": "Automated tests: 100 passed, 0 failed, 3 skipped (private fixtures).",
        "installer": "Installer test: 50 passed, 0 failed, 1 skipped.",
        "link": f"[CHANGELOG.md](https://github.com/aungyemun/monograph-pdf/blob/v{V}/CHANGELOG.md)",
        "date": "2031-02-03",
    }
    parts.update(override)
    return (f"{parts['intro']}\n\n## Download\n\n| File | What |\n| :--- | :--- |\n| a | b |\n\n```\n{parts['sums']}\n```\n\n"
            f"Released {parts['date']}. {parts['link']}\n\n## Verification for this release\n\n- {parts['tests']}\n"
            f"- {parts['installer']}\n\n## Known limitations\n\n- Not code-signed.\n")


@pytest.fixture
def good(tmp_path):
    sums = _artifacts(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("x", encoding="utf-8")
    return tmp_path, sums, _notes(sums)


def _check(text, tmp_path, **kw):
    return vrn.validate(text, V, artifacts=tmp_path, changelog=CHANGELOG, repo_root=tmp_path, **kw)


def test_complete_notes_pass(good):
    tmp_path, sums, text = good
    r = _check(text, tmp_path, tests=(100, 0, 3))
    assert r.ok, r.problems
    assert r.checksums == sums


@pytest.mark.parametrize("token", ["__SHA_SETUP__", "{{ sha }}", "${SHA}", "<fill in>", "TODO", "TBD", "FIXME", "0" * 64])
def test_placeholders_fail(good, token):
    tmp_path, sums, text = good
    r = _check(text.replace("(private fixtures)", f"({token})"), tmp_path)
    assert not r.ok and any("unresolved" in p for p in r.problems)


def test_published_v022_text_with_placeholders_fails(tmp_path):
    """The exact defect of the first v0.2.2 notes: template values left in the checksum block."""
    text = ("Monograph PDF 0.2.2\n\n## Download\n\n```\n__SHA_SETUP__  MonographPDF_0.2.2_Setup.exe\n"
            "__SHA_INSTALLER__  MonographPDF_0.2.2_Installer.zip\n__SHA_SOURCE__  MonographPDF_0.2.2_Source.zip\n```\n\n"
            "## Verification for this release\n\n- Automated tests on Windows 11: 1106 passed, 0 failed, 36 skipped (__SKIP_REASONS__).\n"
            "- Installer test: __INSTALLER_RESULT__.\n\n## Known limitations\n\n- x\n")
    r = vrn.validate(text, "0.2.2")
    joined = "\n".join(r.problems)
    for name in ("__SHA_SETUP__", "__SHA_INSTALLER__", "__SHA_SOURCE__", "__SKIP_REASONS__", "__INSTALLER_RESULT__"):
        assert name in joined
    assert "no SHA-256 line for MonographPDF_0.2.2_Setup.exe" in joined
    assert "missing installer test result" in joined


def test_wrong_or_missing_checksums_fail(good):
    tmp_path, sums, text = good
    setup = vrn.expected_artifacts(V)[0]
    wrong = text.replace(sums[setup], "a" * 64)
    assert any("differs from the file" in p for p in _check(wrong, tmp_path).problems)
    missing = "\n".join(line for line in text.splitlines() if not line.endswith(setup))
    assert any(f"no SHA-256 line for {setup}" in p for p in _check(missing, tmp_path).problems)
    short = text.replace(sums[setup], "abc123")
    assert any("not a SHA-256 value" in p for p in _check(short, tmp_path).problems)
    (tmp_path / setup).unlink()
    assert any("file not found" in p for p in _check(text, tmp_path).problems)


def test_other_version_names_and_tags_fail(good):
    tmp_path, sums, text = good
    r = _check(text + "\nAlso MonographPDF_9.8.6_Setup.exe and https://github.com/x/y/releases/tag/v9.8.6\n", tmp_path)
    assert any("another version" in p for p in r.problems)
    assert any("v9.8.6" in p for p in r.problems)


def test_missing_results_and_sections_fail(good):
    tmp_path, sums, text = good
    r = _check(text.replace("100 passed, 0 failed, 3 skipped", "all good"), tmp_path)
    assert any("missing test summary" in p for p in r.problems)
    r = _check(text.replace("50 passed, 0 failed", "fine"), tmp_path)
    assert any("installer test result" in p for p in r.problems)
    r = _check(text.replace("## Known limitations", "## Notes"), tmp_path)
    assert any("Known limitations" in p for p in r.problems)
    r = _check(text, tmp_path, tests=(101, 0, 3))
    assert any("differs from the recorded run" in p for p in r.problems)


def test_links_dates_and_markdown(good):
    tmp_path, sums, text = good
    assert any("relative link" in p for p in _check(text.replace(
        f"https://github.com/aungyemun/monograph-pdf/blob/v{V}/CHANGELOG.md", "CHANGELOG.md"), tmp_path).problems)
    assert any("does not exist" in p for p in _check(text.replace("CHANGELOG.md)", "NOPE.md)"), tmp_path).problems)
    assert any("differs from the CHANGELOG release date" in p for p in _check(
        text.replace("2031-02-03", "2031-02-04"), tmp_path).problems)
    unreleased = CHANGELOG.replace("2031-02-03", "Unreleased")
    r = vrn.validate(text.replace("Released 2031-02-03. ", ""), V, changelog=unreleased)
    assert any("Unreleased" in p for p in r.problems)
    assert any("code fence" in p for p in _check(text + "\n```\n", tmp_path).problems)
    assert any("column counts" in p for p in _check(text.replace("| a | b |", "| a | b | c |"), tmp_path).problems)


def test_repository_release_notes_are_valid():
    """Every Windows-style release-notes file (vX.Y.Z.md) passes (checksums are not re-hashed here).

    Platform-qualified notes (``v0.1.0-linux.md``, ``v0.1.0-macos.md``) are validated on their
    own platform CI / packaging path.
    """
    import re

    sys.path.insert(0, str(ROOT))
    win_stem = re.compile(r"^v\d+\.\d+\.\d+$")
    for notes in sorted((ROOT / "docs" / "releases").glob("v*.md")):
        if not win_stem.fullmatch(notes.stem):
            continue
        version = notes.stem[1:]
        r = vrn.validate(notes.read_text(encoding="utf-8"), version,
                         changelog=(ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), repo_root=ROOT)
        assert r.ok, (notes.name, r.problems)


def test_cli_exit_codes(good, capsys):
    tmp_path, sums, text = good
    notes = tmp_path / "notes.md"
    notes.write_text(text, encoding="utf-8")
    assert vrn.main([str(notes), "--version", V, "--artifacts", str(tmp_path)]) == 0
    notes.write_text(text.replace(sums[vrn.expected_artifacts(V)[0]], "__SHA__"), encoding="utf-8")
    assert vrn.main([str(notes), "--version", V]) == 1
    assert "FAIL" in capsys.readouterr().out
