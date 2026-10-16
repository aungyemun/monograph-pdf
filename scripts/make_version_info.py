"""Emit PyInstaller Windows version-info from canonical product metadata + VERSION."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.product_meta import version_resource_strings  # noqa: E402
from core.versioning import get_version, parse_version  # noqa: E402


def main() -> int:
    version = get_version()
    major, minor, patch = parse_version(version)
    out = ROOT / "build" / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    strings = ",\n        ".join(
        f"StringStruct(u'{key}', u'{value}')" for key, value in version_resource_strings(version).items()
    )
    # PyInstaller version-file format
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [{strings}])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    out.write_text(content, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
