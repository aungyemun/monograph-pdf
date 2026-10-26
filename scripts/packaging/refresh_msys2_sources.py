"""Maintainer tool: rebuild OCR corresponding-source pins when ``*.src.tar.zst`` mirrors 404.

    python scripts/packaging/refresh_msys2_sources.py [--cache DIR] [--component ID]

Downloads each pinned MSYS2 recipe (PKGBUILD + patches + upstream) at ``recipe_commit``,
writes a deterministic ``*.corresponding-source.tar.gz`` into the cache, and updates
``third_party_sources.json`` with the new name, SHA-256 and provenance URLs.

Normal archive builds keep using the published ``*.src.tar.zst`` pins while mirrors still
serve them; run this only when every mirror returns 404 for a package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("third_party_sources.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=ROOT / "packages" / "sources")
    ap.add_argument("--component", action="append", dest="components",
                    help="limit to one or more component ids (default: every msys2 OCR component)")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).parent))
    from msys2_corresponding_source import refresh_component_files  # noqa: WPS433

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.cache.mkdir(parents=True, exist_ok=True)
    selected = set(args.components or [])
    updated = 0
    for comp in data["components"]:
        if not comp.get("msys2"):
            continue
        if selected and comp["id"] not in selected:
            continue
        print(f"refreshing {comp['id']} …")
        refresh_component_files(comp, args.cache)
        print(f"  {comp['files'][0]['name']}  sha256={comp['files'][0]['sha256']}")
        updated += 1
    if not updated:
        print("no matching MSYS2 components", file=sys.stderr)
        return 1
    args.manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"updated {updated} component(s) in {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
