#!/usr/bin/env python3
"""Bump VERSION after a successful application/runtime/UI/resource/dependency fix.

Usage:
  python scripts/bump_version.py           # patch bump
  python scripts/bump_version.py --print   # show current only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.versioning import bump_patch, get_version, write_version  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump or print project VERSION")
    parser.add_argument("--print", action="store_true", help="Print current version only")
    args = parser.parse_args()
    current = get_version()
    if args.print:
        print(current)
        return 0
    nxt = bump_patch(current)
    write_version(nxt)
    print(f"{current} -> {nxt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
