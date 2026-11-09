"""scripts/audit/privacy_scan.py: finds secrets and personal text without ever printing them."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("privacy_scan", ROOT / "scripts" / "audit" / "privacy_scan.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

# assembled at run time so this test file itself contains no secret-shaped or personal string
FAKE_TOKEN = "ghp" + "_" + "Q" * 36
PERSONAL = "Example-Private-" + "Marker-7731"


def _patterns(tmp: Path) -> Path:
    p = tmp / "patterns.txt"
    p.write_text("# comment\n\n" + PERSONAL + "\n", encoding="utf-8")
    return p


def test_files_and_zips_are_scanned_and_nothing_secret_is_printed(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text(f"token={FAKE_TOKEN}\nwritten by {PERSONAL.lower()}\n", encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "data" / "b.zip", "w") as z:
        z.writestr("inner/readme.md", f"contact: someone@private-mail.example, ok: a@example.org {PERSONAL}")
    out = tmp_path / "report.json"
    code = ps.main(["--path", str(tmp_path / "data"), "--patterns", str(_patterns(tmp_path)), "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 1
    assert "github_token" in printed and "personal_pattern" in printed
    assert FAKE_TOKEN not in printed and PERSONAL.lower() not in printed.lower()
    assert "someone@private-mail.example" not in printed and "so...@private-mail.example" in printed
    assert "example.org" not in printed
    report = out.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in report and PERSONAL not in report  # no --show-context: never the value
    assert '"pattern_line": 1' in report
    assert "b.zip!inner/readme.md" in report


def test_clean_input_exits_zero(tmp_path, capsys):
    (tmp_path / "ok.md").write_text("Contact: maintainer@users.noreply.github.com\n", encoding="utf-8")
    assert ps.main(["--path", str(tmp_path / "ok.md"), "--patterns", str(tmp_path / "missing.txt")]) == 0
    assert "findings: none" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_history_attribution_and_publication_state(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@users.noreply.github.com",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    git("init", "-q")
    (repo / "f.txt").write_text(f"{PERSONAL}\n", encoding="utf-8")
    git("add", "f.txt")
    git("commit", "-q", "-m", "add\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    (repo / "f.txt").write_text("clean\n", encoding="utf-8")  # removed later: still in history
    git("commit", "-qam", "clean")
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "private-patterns.txt").write_text(PERSONAL + "\n", encoding="utf-8")
    code = ps.main(["--git", str(repo)])  # default patterns file of the first repository
    printed = capsys.readouterr().out
    assert code == 1
    assert "personal patterns loaded: 1" in printed
    assert "blobs flagged 1 (already in a remote branch or tag: 0)" in printed
    assert "commits with AI attribution: 1" in printed
    assert "f.txt" in printed and PERSONAL not in printed
