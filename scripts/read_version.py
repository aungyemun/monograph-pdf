#!/usr/bin/env python3
"""Print the authoritative platform version (for build manifests and CI).

    python scripts/read_version.py              # host OS line
    python scripts/read_version.py --platform windows
    python scripts/read_version.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.versioning import all_platform_versions, get_version  # noqa: E402


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--platform", choices=("windows", "linux", "macos"), default=None)
    p.add_argument("--all", action="store_true", help="print every platform version")
    args = p.parse_args()
    if args.all:
        for name, ver in all_platform_versions().items():
            print(f"{name}={ver}")
    else:
        print(get_version(args.platform))
