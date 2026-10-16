#!/usr/bin/env python3
"""Print authoritative VERSION (for build manifests and CI)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.versioning import get_version  # noqa: E402


if __name__ == "__main__":
    print(get_version())
