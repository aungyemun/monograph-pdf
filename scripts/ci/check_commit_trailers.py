"""Reject AI-assistant attribution in commit messages; human Co-authored-by trailers are allowed.

    python scripts/ci/check_commit_trailers.py --message-file .git/COMMIT_EDITMSG   # commit-msg hook
    python scripts/ci/check_commit_trailers.py --range origin/main..HEAD          # CI: new commits only

Only commits in the given range are checked: history published before this check stays as it is.
Use as a local hook with ``scripts/ci/commit-msg`` (see the file header). Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Matched against the Co-authored-by name/email only. Assistants are listed by their identities
# (``devin-ai``, not ``devin``), so most human names pass; a human co-author whose name matches
# (for example "Claude") can be committed with MONOGRAPH_ALLOW_AI_TRAILER=1 in the local hook.
AI_IDENTITY = re.compile(
    r"claude|anthropic|cursor|copilot|openai|chatgpt|codex|gemini|google-labs-jules|devin-ai"
    r"|aider|codeium|windsurf|tabnine|codewhisperer|amazon[ -]?q\b",
    re.IGNORECASE,
)
CO_AUTHOR = re.compile(r"^\s*co-authored-by:\s*(?P<who>.+)$", re.IGNORECASE)
# A footer line such as "🤖 Generated with [Claude Code](...)", not a mention inside a sentence.
FOOTER = re.compile(r"^\W*generated with \[?(claude code|cursor)", re.IGNORECASE)


def problems(message: str) -> list[str]:
    """Lines of ``message`` that attribute the commit to an AI assistant (comments ignored)."""
    found = []
    for line in message.splitlines():
        if line.startswith("#"):
            continue
        m = CO_AUTHOR.match(line)
        if (m and AI_IDENTITY.search(m.group("who"))) or FOOTER.match(line):
            found.append(line.strip())
    return found


def commits_in(rev_range: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01", rev_range],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    result = []
    for record in out.split("\x01"):
        record = record.strip("\n")
        if record:
            sha, _, body = record.partition("\x00")
            result.append((sha, body))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message-file", type=Path, help="commit message file (commit-msg hook)")
    group.add_argument("--range", dest="rev_range", help="git revision range, e.g. origin/main..HEAD")
    args = parser.parse_args(argv)

    failures: list[tuple[str, list[str]]] = []
    if args.message_file:
        bad = problems(args.message_file.read_text(encoding="utf-8"))
        if bad:
            failures.append(("this commit", bad))
    else:
        for sha, body in commits_in(args.rev_range):
            bad = problems(body)
            if bad:
                failures.append((sha[:12], bad))

    if not failures:
        return 0
    print("AI assistant attribution is not allowed in commit messages:", file=sys.stderr)
    for where, lines in failures:
        for line in lines:
            print(f"  {where}: {line}", file=sys.stderr)
    print("Remove these lines (git commit --amend, or git rebase for older commits).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
