"""macOS installer resources: guided .pkg (Installer.app) and drag-and-drop .dmg layout.

Generated at package time from text templates in installer/macos/ and the existing brand images in
resources/icons/source (no binary artwork is committed):

``pkg-resources <out dir> <version>``   welcome / readme / conclusion pages, LICENSE.txt, background
                                         artwork and distribution.xml for productbuild
``component-plist <plist>``               harden the pkgbuild component list: install exactly into
                                         /Applications (no relocation into a moved copy), upgrade in
                                         place, never downgrade
``dmg-art <out dir>``                     background.tiff (1x + 2x) for the Finder window
``dmg-layout <volume> <volume name>``     AppleScript that lays out the mounted read-write image

Usage: python scripts/packaging/macos_installer.py <command> …
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "installer" / "macos"
LOGO = ROOT / "resources" / "icons" / "source" / "Monograph_PDF_logo.png"
FONT = ROOT / "resources" / "fonts" / "NotoSans-Regular.ttf"
IDENTIFIER = "com.aungyemun.monographpdf"
MIN_MACOS = "13.0"
HOST_ARCH = "arm64"  # the bundled Python, Qt and OCR builds are arm64-only (see docs/MACOS.md)
COMPONENT_PKG = "MonographPDF-component.pkg"
PAGES = ("welcome.html", "readme.html", "conclusion.html")

# DMG Finder window (points): app on the left, Applications on the right, arrow between
DMG_WINDOW = (660, 400)
DMG_ICON_SIZE = 128
DMG_APP_POS = (170, 205)
DMG_APPS_POS = (490, 205)
NAVY, RED = (19, 48, 107), (196, 30, 36)


# --------------------------------------------------------------------------- pkg


def distribution_xml(version: str) -> str:
    v = escape(version)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Monograph PDF {v}</title>
    <organization>com.aungyemun</organization>
    <domains enable_localSystem="true" enable_currentUserHome="false" enable_anywhere="false"/>
    <options customize="never" require-scripts="false" hostArchitectures="{HOST_ARCH}"/>
    <volume-check>
        <allowed-os-versions>
            <os-version min="{MIN_MACOS}"/>
        </allowed-os-versions>
    </volume-check>
    <installation-check script="monographNoDowngrade()"/>
    <script><![CDATA[
function monographNoDowngrade() {{
    var app = system.files.bundleAtPath('/Applications/MonographPDF.app');
    if (!app || !app.CFBundleShortVersionString) {{ return true; }}
    var installed = app.CFBundleShortVersionString;
    if (system.compareVersions(installed, '{v}') > 0) {{
        my.result.type = 'Fatal';
        my.result.title = 'A newer Monograph PDF is already installed';
        my.result.message = 'Monograph PDF ' + installed + ' is installed in Applications. This installer '
            + 'contains the older version {v} and will not replace it.';
        return false;
    }}
    return true;
}}
    ]]></script>
    <welcome file="welcome.html" mime-type="text/html"/>
    <readme file="readme.html" mime-type="text/html"/>
    <license file="LICENSE.txt" mime-type="text/plain"/>
    <conclusion file="conclusion.html" mime-type="text/html"/>
    <background file="background.png" mime-type="image/png" alignment="bottomleft" scaling="none"/>
    <background-darkAqua file="background-dark.png" mime-type="image/png" alignment="bottomleft" scaling="none"/>
    <choices-outline>
        <line choice="default">
            <line choice="{IDENTIFIER}"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="{IDENTIFIER}" visible="false" title="Monograph PDF">
        <pkg-ref id="{IDENTIFIER}"/>
    </choice>
    <pkg-ref id="{IDENTIFIER}" version="{v}" onConclusion="none">{COMPONENT_PKG}</pkg-ref>
</installer-gui-script>
"""


def render_pages(out: Path, version: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in PAGES:
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        text = text.replace("{{VERSION}}", escape(version)).replace("{{MIN_MACOS}}", MIN_MACOS)
        if "{{" in text:
            raise ValueError(f"unfilled placeholder in {name}")
        (out / name).write_text(text, encoding="utf-8")
        written.append(out / name)
    shutil.copyfile(ROOT / "LICENSE", out / "LICENSE.txt")
    written.append(out / "LICENSE.txt")
    return written


def pkg_resources(out: Path, version: str) -> Path:
    render_pages(out, version)
    pkg_background(out / "background.png", dark=False)
    pkg_background(out / "background-dark.png", dark=True)
    dist = out.parent / "distribution.xml"
    dist.write_text(distribution_xml(version), encoding="utf-8")
    return dist


def harden_component_plist(path: Path) -> list[dict]:
    """pkgbuild --analyze output → install only into /Applications, upgrade in place, no downgrade."""
    with path.open("rb") as f:
        bundles = plistlib.load(f)
    for b in bundles:
        b["BundleIsRelocatable"] = False  # never redirect into a copy the user moved elsewhere
        b["BundleIsVersionChecked"] = True  # an older package does not replace a newer app
        b["BundleOverwriteAction"] = "upgrade"
        b["BundleHasStrictIdentifier"] = True
    with path.open("wb") as f:
        plistlib.dump(bundles, f)
    return bundles


# --------------------------------------------------------------------------- artwork


def _font(size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT), size)


def _gradient(size, top, bottom):
    from PIL import Image

    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        row = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def pkg_background(path: Path, *, dark: bool) -> Path:
    """Installer.app sidebar art: the logo faded into the bottom-left corner (2x pixels, 144 dpi)."""
    from PIL import Image

    scale = 2
    size = (620 * scale, 418 * scale)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    logo = Image.open(LOGO).convert("RGBA")
    # the emblem only (the wordmark below it would be clipped by the window edge)
    logo = logo.crop((0, 0, logo.width, int(logo.height * 0.75)))
    logo = logo.crop(logo.getbbox())
    width = 170 * scale
    logo = logo.resize((width, round(logo.height * width / logo.width)), Image.LANCZOS)
    alpha = logo.getchannel("A").point(lambda a: int(a * (0.16 if dark else 0.13)))
    logo.putalpha(alpha)
    canvas.alpha_composite(logo, (14 * scale, size[1] - logo.height - 16 * scale))
    canvas.save(path, dpi=(144, 144))
    return path


def dmg_art(out: Path) -> Path:
    """Finder background: soft brand gradient, an arrow from the app to Applications, one short line."""
    from PIL import Image, ImageDraw

    out.mkdir(parents=True, exist_ok=True)
    pngs = []
    for scale in (1, 2):
        w, h = DMG_WINDOW[0] * scale, DMG_WINDOW[1] * scale
        img = _gradient((w, h), (250, 251, 254), (226, 233, 246)).convert("RGBA")
        d = ImageDraw.Draw(img)
        # arrow between the two icon centres
        y = DMG_APP_POS[1] * scale
        x0 = (DMG_APP_POS[0] + DMG_ICON_SIZE // 2 + 34) * scale
        x1 = (DMG_APPS_POS[0] - DMG_ICON_SIZE // 2 - 34) * scale
        d.line([(x0, y), (x1 - 14 * scale, y)], fill=NAVY + (255,), width=6 * scale)
        d.polygon([(x1, y), (x1 - 24 * scale, y - 16 * scale), (x1 - 24 * scale, y + 16 * scale)], fill=NAVY + (255,))
        title = "Drag Monograph PDF to Applications to install"
        f = _font(17 * scale)
        tw = d.textlength(title, font=f)
        d.text(((w - tw) / 2, 58 * scale), title, font=f, fill=NAVY + (255,))
        note = "Your settings and recent files are kept when you replace an earlier version."
        f2 = _font(12 * scale)
        nw = d.textlength(note, font=f2)
        d.text(((w - nw) / 2, h - 52 * scale), note, font=f2, fill=(91, 107, 138, 255))
        d.rectangle([(w / 2 - 28 * scale, 92 * scale), (w / 2 + 28 * scale, 95 * scale)], fill=RED + (255,))
        p = out / f"background{'@2x' if scale == 2 else ''}.png"
        img.convert("RGB").save(p, dpi=(72 * scale, 72 * scale))
        pngs.append(p)
    tiff = out / "background.tiff"
    subprocess.run(["tiffutil", "-cathidpicheck", str(pngs[0]), str(pngs[1]), "-out", str(tiff)],
                   check=True, capture_output=True)
    for p in pngs:
        p.unlink()
    return tiff


# --------------------------------------------------------------------------- dmg layout


def dmg_layout_script(volume_name: str) -> str:
    w, h = DMG_WINDOW
    left, top = 200, 120
    return f'''
tell application "Finder"
  tell disk "{volume_name}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {{{left}, {top}, {left + w}, {top + h + 28}}}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to {DMG_ICON_SIZE}
    set text size of opts to 13
    set background picture of opts to file ".background:background.tiff"
    set position of item "MonographPDF.app" of container window to {{{DMG_APP_POS[0]}, {DMG_APP_POS[1]}}}
    set position of item "Applications" of container window to {{{DMG_APPS_POS[0]}, {DMG_APPS_POS[1]}}}
    update without registering applications
    delay 1
    close
    open
    delay 1
    close
  end tell
end tell
'''


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "pkg-resources" and len(argv) == 3:
        print(pkg_resources(Path(argv[1]), argv[2]))
    elif cmd == "component-plist" and len(argv) == 2:
        harden_component_plist(Path(argv[1]))
    elif cmd == "dmg-art" and len(argv) == 2:
        print(dmg_art(Path(argv[1])))
    elif cmd == "dmg-layout" and len(argv) == 2:
        print(dmg_layout_script(argv[1]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
