"""Generate every Monograph PDF icon and branding image from the canonical artwork (offline, Pillow).

Canonical input (never modified):
  resources/icons/source/Monograph_PDF_logo.png — the logo: emblem (open book with "M", PDF page
  and pen) above the "Monograph PDF" wordmark, on a transparent background.
  Import a new version with scripts/prepare_logo.py.

Writes:
  resources/icons/source/monograph_pdf_icon_1024.png  square emblem (no wordmark): the app icon master
  resources/icons/source/monograph_pdf_logo_512.png   full logo with wordmark (About box, Start page)
  resources/icons/windows/monograph_pdf_<size>.png    16 … 256
  resources/icons/windows/monograph_pdf.ico           16, 24, 32, 48, 64, 128, 256 (PNG-compressed 256)
  installer/assets/wizard_large_*.bmp, wizard_small_*.bmp  Setup wizard images

The wordmark is unreadable at icon sizes, so icons use the emblem alone: it is cut at the clear
transparent gap above the wordmark, centred on a square transparent canvas and scaled uniformly
(never stretched or cropped into). Downscaling uses Lanczos resampling; sizes up to 64 px get a
light unsharp mask so the "M" stays crisp. Transparency is preserved.

Usage: env\\Scripts\\python.exe scripts\\generate_branding_icons.py [--check]
  --check  regenerate in memory and fail if any committed file differs (no writes)
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "resources" / "icons"
SOURCE = ICONS / "source"
WINDOWS = ICONS / "windows"
ASSETS = ROOT / "installer" / "assets"
ARTWORK = SOURCE / "Monograph_PDF_logo.png"
FONT = ROOT / "resources" / "fonts" / "NotoSans-Regular.ttf"

BASENAME = "monograph_pdf"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
MASTER_SIZE = 1024
LOGO_SIZE = 512
ALPHA_SOLID = 40  # alpha above this counts as artwork when locating the emblem
PAD = 0.03  # transparent margin around the emblem, fraction of its larger side

NAVY = (24, 46, 94)
TAGLINE = "Edit · Convert · Protect · Sign"


def load_artwork(path: Path = ARTWORK) -> Image.Image:
    img = Image.open(path)
    img.load()
    if img.format != "PNG":
        raise SystemExit(f"{path} is not a PNG file")
    return img.convert("RGBA")


def emblem_box(art: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the emblem: artwork rows above the widest transparent gap below the
    vertical middle (the gap between emblem and wordmark)."""
    mask = art.getchannel("A").point(lambda v: 255 if v > ALPHA_SOLID else 0)
    w, h = mask.size
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("artwork is fully transparent")
    rows = [mask.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
    best = None  # (length, start)
    y = h // 2
    while y < bbox[3]:
        if not rows[y]:
            start = y
            while y < h and not rows[y]:
                y += 1
            if y < bbox[3] and (best is None or y - start > best[0]):
                best = (y - start, start)
        y += 1
    cut = best[1] if best else bbox[3]
    em = mask.crop((0, 0, w, cut)).getbbox()
    if em is None:
        raise SystemExit("could not find the emblem in the artwork")
    return em


def square_emblem(art: Image.Image, size: int = MASTER_SIZE) -> Image.Image:
    x0, y0, x1, y1 = emblem_box(art)
    emblem = art.crop((x0, y0, x1, y1))
    side = round(max(x1 - x0, y1 - y0) * (1 + 2 * PAD))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(emblem, ((side - emblem.width) // 2, (side - emblem.height) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def square_logo(art: Image.Image, size: int = LOGO_SIZE) -> Image.Image:
    """The whole logo (emblem + wordmark), trimmed and centred on a transparent square."""
    bbox = art.getchannel("A").point(lambda v: 255 if v > ALPHA_SOLID else 0).getbbox()
    logo = art.crop(bbox)
    side = round(max(logo.size) * (1 + 2 * PAD))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def sized(master: Image.Image, size: int) -> Image.Image:
    img = master.resize((size, size), Image.LANCZOS)
    if size <= 64:  # keep small icons crisp after heavy downscaling
        rgb = img.convert("RGB").filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
        rgb.putalpha(img.getchannel("A"))
        img = rgb
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def ico_bytes(images: list[Image.Image]) -> bytes:
    images = sorted(images, key=lambda i: i.size[0])
    buf = io.BytesIO()
    images[-1].save(buf, format="ICO", sizes=[im.size for im in images], append_images=images[:-1])
    return buf.getvalue()


def _on_white(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    base = Image.new("RGBA", img.size, bg + (255,))
    base.alpha_composite(img)
    return base.convert("RGB")


def bmp_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def wizard_large(art: Image.Image, width: int) -> Image.Image:
    """Setup's left-hand image (164 × 314 at 100 %): logo with wordmark and a short tagline."""
    height = round(width * 314 / 164)
    bg = Image.new("RGBA", (width, height))
    top, bottom = (255, 255, 255), (232, 239, 250)
    draw = ImageDraw.Draw(bg)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line([(0, y), (width, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    logo = square_logo(art, round(width * 0.86))
    bg.alpha_composite(logo, ((width - logo.width) // 2, round(height * 0.16)))
    try:
        font = ImageFont.truetype(str(FONT), max(8, round(width * 0.068)))
        tw = draw.textlength(TAGLINE, font=font)
        draw.text(((width - tw) / 2, round(height * 0.16) + logo.height + round(width * 0.05)), TAGLINE, font=font, fill=NAVY + (255,))
    except OSError:
        pass  # font missing: image without tagline
    return bg.convert("RGB")


def wizard_small(emblem_master: Image.Image, size: int) -> Image.Image:
    return _on_white(emblem_master.resize((size, size), Image.LANCZOS))


def outputs(art: Image.Image) -> dict[Path, bytes]:
    master = square_emblem(art)
    out: dict[Path, bytes] = {
        SOURCE / f"{BASENAME}_icon_{MASTER_SIZE}.png": png_bytes(master),
        SOURCE / f"{BASENAME}_logo_{LOGO_SIZE}.png": png_bytes(square_logo(art)),
    }
    icons = []
    for size in ICON_SIZES:
        img = sized(master, size)
        icons.append(img)
        out[WINDOWS / f"{BASENAME}_{size}.png"] = png_bytes(img)
    out[WINDOWS / f"{BASENAME}.ico"] = ico_bytes(icons)
    for w in (164, 328):
        out[ASSETS / f"wizard_large_{w}.bmp"] = bmp_bytes(wizard_large(art, w))
    for s in (55, 69, 83, 110):
        out[ASSETS / f"wizard_small_{s}.bmp"] = bmp_bytes(wizard_small(master, s))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if generated files are missing or out of date")
    a = ap.parse_args(argv)
    if not ARTWORK.is_file():
        raise SystemExit(f"Missing canonical artwork: {ARTWORK} (import it with scripts/prepare_logo.py)")
    files = outputs(load_artwork())
    if a.check:
        stale = [p for p, data in files.items() if not p.is_file() or p.read_bytes() != data]
        for p in stale:
            print(f"out of date: {p.relative_to(ROOT)}")
        return 1 if stale else 0
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
    print(f"Wrote {len(files)} branding files from {ARTWORK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
