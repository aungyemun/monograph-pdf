"""Commit-message check: AI-assistant attribution is rejected, human co-authors are kept."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import check_commit_trailers as ct  # noqa: E402

sys.path.remove(str(ROOT / "scripts" / "ci"))


@pytest.mark.parametrize(
    "line",
    [
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
        "Co-authored-by: Cursor <cursoragent@cursor.com>",
        "co-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>",
        "Co-authored-by: devin-ai-integration[bot] <158243242+devin-ai-integration[bot]@users.noreply.github.com>",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ],
)
def test_ai_attribution_rejected(line):
    assert ct.problems(f"Fix saving\n\nBody.\n\n{line}\n") == [line]


@pytest.mark.parametrize(
    "message",
    [
        "Fix saving\n\nCo-authored-by: Jane Doe <jane@example.com>\n",
        "Fix saving\n\nCo-authored-by: Devin Smith <devin@example.org>\n",
        "Fix cursor position after paste\n\nThe text cursor moved to the end.\n",
        "Fix saving\n# Co-authored-by: Claude <noreply@anthropic.com>\n",
        "CI check\n\n- rejects \"Generated with Claude Code\" footer lines\n",
    ],
)
def test_human_and_plain_messages_pass(message):
    assert ct.problems(message) == []


def test_message_file_exit_codes(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("Fix\n\nCo-authored-by: Jane Doe <jane@example.com>\n", encoding="utf-8")
    assert ct.main(["--message-file", str(msg)]) == 0
    msg.write_text("Fix\n\nCo-authored-by: Cursor <cursoragent@cursor.com>\n", encoding="utf-8")
    assert ct.main(["--message-file", str(msg)]) == 1


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True,
                          text=True, check=True).stdout.strip()


def test_range_checks_only_new_commits(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "old", "-m",
         "Co-authored-by: Cursor <cursoragent@cursor.com>")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "new", "-m",
         "Co-authored-by: Jane Doe <jane@example.com>")
    monkeypatch.chdir(repo)
    assert ct.main(["--range", f"{base}..HEAD"]) == 0
    _git(repo, "commit", "-q", "--allow-empty", "-m", "newer", "-m",
         "Co-Authored-By: Claude <noreply@anthropic.com>")
    assert ct.main(["--range", f"{base}..HEAD"]) == 1
