"""Build provenance records: which commit, which tools, which outputs (docs/RELEASE_PROVENANCE.md).

    python scripts/packaging/provenance.py write --out build/installer/MonographPDF_X.Y.Z_provenance.json
           --version X.Y.Z [--signing none] --artifact FILE [--artifact FILE ...]
    python scripts/packaging/provenance.py verify --record <record.json> [--dir <folder with the files>]
           [--require-published]

``write`` refuses a build from a working tree with uncommitted changes to tracked files (the record
would not describe a commit). ``verify`` checks the files' SHA-256 against the record, that the
commit exists in this clone, and — with ``--require-published`` — that the commit is part of the
official history: reachable from ``origin/main`` or tagged ``v<version>``. No network is used;
fetch the official repository first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _tool_versions() -> dict:
    out = {"python": platform.python_version(), "os": f"{platform.system()} {platform.release()} ({platform.machine()})"}
    try:
        from importlib.metadata import version

        out["pyinstaller"] = version("pyinstaller")
    except Exception:  # noqa: BLE001
        pass
    return out


def write(out: Path, version: str, artifacts: list[Path], signing: str, root: Path = ROOT) -> dict:
    commit = _git("rev-parse", "HEAD", root=root)
    if _git("status", "--porcelain", "--untracked-files=no", root=root):
        raise SystemExit("provenance: the working tree has uncommitted changes; a release is built from a commit")
    record = {
        "schema": 1,
        "product": "Monograph PDF",
        "version": version,
        "repository": "https://github.com/aungyemun/monograph-pdf",
        "commit": commit,
        "commit_time": datetime.fromtimestamp(int(_git("show", "-s", "--format=%ct", commit, root=root)),
                                              timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tree": _git("rev-parse", f"{commit}^{{tree}}", root=root),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "maintainer workstation (scripts/build_release.ps1)",
        "tools": _tool_versions(),
        "signing": signing,
        "artifacts": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in artifacts},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} (commit {commit[:12]}, {len(artifacts)} artifacts)")
    return record


def verify(record_path: Path, folder: Path | None, require_published: bool, root: Path = ROOT) -> list[str]:
    rec = json.loads(record_path.read_text(encoding="utf-8"))
    problems = []
    commit = str(rec.get("commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        problems.append("record has no valid commit")
    elif subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
                        capture_output=True).returncode != 0:
        problems.append(f"commit {commit[:12]} is not in this clone (fetch the official repository)")
    elif rec.get("tree") and _git("rev-parse", f"{commit}^{{tree}}", root=root, check=False) != rec["tree"]:
        problems.append("the commit's tree differs from the record")
    if require_published and not problems:
        on_main = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "origin/main"],
                                 capture_output=True).returncode == 0
        tag = _git("rev-parse", f"refs/tags/v{rec.get('version')}^{{commit}}", root=root, check=False)
        if not on_main and tag != commit:
            problems.append(f"commit {commit[:12]} is neither on origin/main nor tagged v{rec.get('version')}")
    if folder is not None:
        for name, meta in (rec.get("artifacts") or {}).items():
            path = folder / name
            if not path.is_file():
                continue
            if sha256(path) != meta.get("sha256"):
                problems.append(f"{name}: SHA-256 differs from the provenance record")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--out", type=Path, required=True)
    w.add_argument("--version", required=True)
    w.add_argument("--signing", default="none")
    w.add_argument("--artifact", type=Path, action="append", default=[])
    v = sub.add_parser("verify")
    v.add_argument("--record", type=Path, required=True)
    v.add_argument("--dir", type=Path)
    v.add_argument("--require-published", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "write":
        missing = [p for p in a.artifact if not p.is_file()]
        if missing:
            print(f"provenance: missing {', '.join(map(str, missing))}", file=sys.stderr)
            return 1
        write(a.out, a.version, a.artifact, a.signing)
        return 0
    problems = verify(a.record, a.dir, a.require_published)
    print("Provenance " + ("FAILED:\n  " + "\n  ".join(problems) if problems else "verified"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
