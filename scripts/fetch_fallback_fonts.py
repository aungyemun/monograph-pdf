"""Download compact OFL fallback fonts into resources/fonts (dev/setup only)."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "resources" / "fonts"

# Compact, redistributable OFL fonts (not Microsoft proprietary faces).
# Noto Sans JP variable is larger; we fetch a single Regular weight when available.
_SOURCES = [
    {
        "family": "Noto Sans",
        "style": "Regular",
        "file": "NotoSans-Regular.ttf",
        "scripts": ["latin", "symbols"],
        "license": "OFL-1.1",
        "urls": [
            # Google Fonts GitHub (noto-fonts)
            "https://github.com/notofonts/latin-greek-cyrillic/raw/main/fonts/NotoSans/full/ttf/NotoSans-Regular.ttf",
            "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
        ],
    },
    {
        "family": "Noto Serif",
        "style": "Regular",
        "file": "NotoSerif-Regular.ttf",
        "scripts": ["latin"],
        "license": "OFL-1.1",
        "urls": [
            "https://github.com/notofonts/latin-greek-cyrillic/raw/main/fonts/NotoSerif/full/ttf/NotoSerif-Regular.ttf",
            "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerif/NotoSerif-Regular.ttf",
        ],
    },
    {
        "family": "Noto Sans JP",
        "style": "Regular",
        "file": "NotoSansJP-Regular.ttf",
        "scripts": ["japanese", "latin", "cjk-punctuation"],
        "license": "OFL-1.1",
        "urls": [
            "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
            "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
        ],
        # otf fallback filename remap
        "save_as_alt": "NotoSansCJKjp-Regular.otf",
    },
]

_OFL_TEXT = """SIL OPEN FONT LICENSE Version 1.1

Copyright (c) Noto Fonts authors / Google Inc.

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is available with a FAQ at: https://scripts.sil.org/OFL
"""


def _download(urls: list[str], dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        print(f"Exists: {dest.name}")
        return True
    for url in urls:
        try:
            print(f"Fetching {url} -> {dest.name}")
            urllib.request.urlretrieve(url, dest.as_posix())
            if dest.is_file() and dest.stat().st_size > 1000:
                return True
        except Exception as exc:  # noqa: BLE001
            print(f"  failed: {exc}")
            if dest.is_file():
                dest.unlink(missing_ok=True)
    return False


def main() -> int:
    FONTS.mkdir(parents=True, exist_ok=True)
    (FONTS / "OFL.txt").write_text(_OFL_TEXT, encoding="utf-8")
    fonts_meta = []
    ok = 0
    for item in _SOURCES:
        # Prefer listed file; for CJK otf use alt name when url ends with .otf
        dest = FONTS / item["file"]
        urls = list(item["urls"])
        if any(u.endswith(".otf") for u in urls):
            dest = FONTS / str(item.get("save_as_alt") or item["file"]).replace(".ttf", ".otf")
            if not str(dest).endswith(".otf"):
                dest = FONTS / (Path(item["file"]).stem + ".otf")
        if _download(urls, dest):
            ok += 1
            fonts_meta.append(
                {
                    "family": item["family"] if "CJK" not in dest.name else "Noto Sans CJK JP",
                    "style": item["style"],
                    "file": dest.name,
                    "scripts": item["scripts"],
                    "license": item["license"],
                }
            )
        else:
            print(f"WARNING: could not fetch {item['family']} — system fonts will be used")

    manifest = {
        "note": "Bundled OFL fallback fonts for offline editing. Viewing uses embedded PDF fonts via MuPDF.",
        "fonts": fonts_meta,
    }
    (FONTS / "FONT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Bundled {ok}/{len(_SOURCES)} fonts into {FONTS}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
