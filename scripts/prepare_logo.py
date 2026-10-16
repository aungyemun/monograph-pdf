"""Import the Monograph PDF logo artwork into the project as the canonical branding source.

Copies the PNG byte-for-byte to resources/icons/source/Monograph_PDF_logo.png (the original is
only read, never changed), after checking that it is a readable PNG with transparency and a
square-ish shape, then runs scripts/generate_branding_icons.py to rebuild every icon from it.

By default the file is taken from the current user's Downloads folder, found through the Windows
known-folder API (not a hard-coded C:\\Users\\<name>\\Downloads path).

Usage: env\\Scripts\\python.exe scripts\\prepare_logo.py [--from PATH] [--no-generate]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "resources" / "icons" / "source" / "Monograph_PDF_logo.png"
FILE_NAME = "Monograph_PDF_logo.png"
# FOLDERID_Downloads
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


def downloads_folder() -> Path:
    """The user's Downloads folder (Windows known folder; ~/Downloads elsewhere)."""
    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(_DOWNLOADS_GUID)
        guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
        if hr != 0:
            raise OSError(f"SHGetKnownFolderPath failed ({hr:#x})")
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    return Path.home() / "Downloads"


def inspect(path: Path) -> dict:
    """Validate the artwork and describe it (dimensions, alpha, aspect ratio)."""
    with Image.open(path) as probe:
        probe.verify()  # structure / CRC check
    with Image.open(path) as img:
        if img.format != "PNG":
            raise SystemExit(f"{path} is not a PNG")
        has_alpha = "A" in img.getbands() or "transparency" in img.info
        alpha = img.convert("RGBA").getchannel("A")
        info = {
            "size": img.size,
            "mode": img.mode,
            "has_alpha": has_alpha,
            "alpha_range": alpha.getextrema(),
            "aspect_ratio": round(img.width / img.height, 4),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    if not has_alpha or info["alpha_range"][0] == 255:
        raise SystemExit(f"{path} has no transparency; the icons need a transparent background")
    if not 0.8 <= info["aspect_ratio"] <= 1.25:
        raise SystemExit(f"{path} is {img.width} x {img.height}; expected a roughly square logo")
    if min(img.size) < 512:
        raise SystemExit(f"{path} is too small ({img.width} x {img.height}); at least 512 px is needed for 256 px icons")
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", type=Path, help=f"artwork file (default: <Downloads>\\{FILE_NAME})")
    ap.add_argument("--no-generate", action="store_true", help="only import; do not regenerate the icons")
    a = ap.parse_args(argv)
    src = a.src or downloads_folder() / FILE_NAME
    if not src.is_file():
        raise SystemExit(f"Not found: {src}")
    info = inspect(src)
    print(f"{src}: {info['size'][0]} x {info['size'][1]} {info['mode']}, alpha {info['alpha_range']}, "
          f"aspect {info['aspect_ratio']}, sha256 {info['sha256']}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, DEST)  # byte copy; the original is left as it is
    if hashlib.sha256(DEST.read_bytes()).hexdigest() != info["sha256"]:
        raise SystemExit("copy verification failed")
    print(f"Copied to {DEST.relative_to(ROOT)}")
    if not a.no_generate:
        return subprocess.call([sys.executable, str(ROOT / "scripts" / "generate_branding_icons.py")], timeout=300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
