"""Install the repository's Git hook templates into this clone's .git/hooks (local only).

    python scripts/git-hooks/install_hooks.py [--force]

Copies ``scripts/git-hooks/pre-push`` to ``.git/hooks/pre-push`` with LF line endings and no BOM
(Git for Windows runs hooks with its own sh). An existing different hook is kept unless --force
is given; it is then saved as ``pre-push.bak`` first. Creates an empty
``.git/info/private-patterns.txt`` with instructions if it does not exist yet. Nothing is pushed or
committed: hooks and that file live only in your clone.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATTERNS_HELP = """# Private patterns: one fixed string per line, matched case-insensitively.
# Lines starting with # are ignored. This file is local to this clone; it is never committed.
# Add text that must never be pushed or published, for example your private e-mail address,
# your Windows user folder (C:\\Users\\<name>), your computer's name, the folder that holds your
# signing key, or the number or title of a private document you test with.
"""


def git_dir() -> Path:
    out = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install the pre-push privacy guard into this clone.")
    ap.add_argument("--force", action="store_true", help="replace a different existing hook (kept as pre-push.bak)")
    a = ap.parse_args(argv)
    gd = git_dir()
    src = (HERE / "pre-push").read_bytes().replace(b"\r\n", b"\n")
    if src.startswith(b"\xef\xbb\xbf"):
        src = src[3:]
    dst = gd / "hooks" / "pre-push"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.read_bytes() != src:
        if not a.force:
            print(f"{dst} exists and differs; not replaced (use --force to replace it, a backup is kept)")
            return 1
        dst.with_name("pre-push.bak").write_bytes(dst.read_bytes())
    dst.write_bytes(src)
    if os.name != "nt":
        dst.chmod(0o755)
    print(f"installed {dst}")
    pats = gd / "info" / "private-patterns.txt"
    if not pats.exists():
        pats.parent.mkdir(parents=True, exist_ok=True)
        pats.write_text(PATTERNS_HELP, encoding="utf-8", newline="\n")
        print(f"created {pats} - add your private patterns to it")
    else:
        print(f"kept {pats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
