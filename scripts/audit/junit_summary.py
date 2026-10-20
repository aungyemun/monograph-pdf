"""Per-file pass/fail/skip counts from a JUnit XML file (pytest --junitxml)."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def main(path: str, pattern: str = "") -> None:
    root = ET.parse(path).getroot()
    stats = defaultdict(lambda: [0, 0, 0])
    skip_msgs = defaultdict(set)
    for tc in root.iter("testcase"):
        mod = tc.get("classname", "")
        if pattern and pattern not in mod:
            continue
        kind = 0
        for child in tc:
            if child.tag in ("failure", "error"):
                kind = 1
            elif child.tag == "skipped":
                kind = 2
                skip_msgs[mod].add((child.get("message") or "")[:90])
        stats[mod][kind] += 1
    for mod in sorted(stats):
        p, f, s = stats[mod]
        print(f"{mod:70s} pass={p:4d} fail={f:3d} skip={s:3d}")
        for m in sorted(skip_msgs[mod])[:2]:
            print(f"    skip: {m}")


if __name__ == "__main__":
    main(*sys.argv[1:])
