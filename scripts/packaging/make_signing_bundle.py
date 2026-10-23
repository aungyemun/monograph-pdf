"""Copy the reviewed update-signing tools, as committed, into a small stand-alone folder.

    python scripts/packaging/make_signing_bundle.py --out <new folder> [--commit HEAD]

The folder holds only what ``update_manifest.py`` (keygen, selftest, export-pkcs8, make, verify)
needs, taken with ``git show <commit>:<path>`` (never from uncommitted files), plus:

* ``core/__init__.py`` replaced by an empty package marker: the application's own one imports the
  PDF engine, which signing does not need (the only difference from the repository);
* ``requirements-signing.txt``: exact versions and SHA-256 hashes of the optional ``cryptography``
  wheels (Windows x64, CPython 3.11) for the PKCS#8 key file and the second Ed25519 implementation;
* ``BUNDLE_MANIFEST.json``: commit, file list and SHA-256 of every file.

No key, no application binary and nothing from outside the listed files is included. Nothing is
contacted on the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FILES = [
    "LICENSE.md",
    "VERSION",
    "resources/update/update_config.json",
    "core/app_env.py",
    "core/product_meta.py",
    "core/safe_paths.py",
    "core/versioning.py",
    "core/updates/__init__.py",
    "core/updates/authenticode.py",
    "core/updates/config.py",
    "core/updates/ed25519.py",
    "core/updates/install_target.py",
    "core/updates/manager.py",
    "core/updates/manifest.py",
    "core/updates/net.py",
    "core/updates/semver.py",
    "core/updates/staging.py",
    "core/updates/state.py",
    "scripts/packaging/signing_key.py",
    "scripts/packaging/update_manifest.py",
    "scripts/packaging/update_selftest.py",
]

CORE_INIT = '"""Monograph PDF core package (signing-tool bundle: no application modules are imported)."""\n'

REQUIREMENTS = """\
# Optional for the update-signing tools (never part of the Monograph PDF application).
# Needed only to read update-signing.pkcs8.pem and for the second Ed25519 implementation.
# Hashes: Windows x64 wheels for CPython 3.11, as downloaded from PyPI on 2026-10-23.
# Install:  python -m pip install --require-hashes --only-binary=:all: -r requirements-signing.txt
cryptography==50.0.1 \\
    --hash=sha256:aed8db4f6d71c51efb89530e12d9464e7bf2923d46c3205dc794a2a93f8c0648
cffi==2.1.1 \\
    --hash=sha256:42f6930c31dc7f50732c9ae793c2786c7b6b044195967bbdde40bb9be81c4cc0
pycparser==3.11 \\
    --hash=sha256:51d5a8ba2be0bbe440b99d2112604c95bbbc3c2748a64260186c541e1729cd80
"""


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def build(out: Path, commit: str = "HEAD") -> dict:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    sha = git("rev-parse", commit).decode("ascii").strip()
    files: dict[str, str] = {}

    def put(rel: str, data: bytes) -> None:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        files[rel] = hashlib.sha256(data).hexdigest()

    for rel in FILES:
        put(rel, git("show", f"{sha}:{rel}"))
    put("core/__init__.py", CORE_INIT.encode("ascii"))
    put("requirements-signing.txt", REQUIREMENTS.encode("ascii"))
    manifest = {"tool": "Monograph PDF update-signing tools", "commit": sha,
                "version": git("show", f"{sha}:VERSION").decode("ascii").strip(),
                "python": "3.11 (CPython, Windows x64 tested)", "files": dict(sorted(files.items()))}
    (out / "BUNDLE_MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def verify(folder: Path) -> list[str]:
    """Problems with a bundle folder (missing, changed or extra files)."""
    manifest = json.loads((folder / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    problems = []
    for rel, digest in manifest["files"].items():
        f = folder / rel
        if not f.is_file():
            problems.append(f"missing {rel}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            problems.append(f"changed {rel}")
    listed = set(manifest["files"]) | {"BUNDLE_MANIFEST.json"}
    for f in folder.rglob("*"):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and rel not in listed and "__pycache__" not in rel:
            problems.append(f"extra {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--commit", default="HEAD")
    a = ap.parse_args(argv)
    m = build(a.out, a.commit)
    print(f"wrote {len(m['files'])} files from commit {m['commit'][:12]} to {a.out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
