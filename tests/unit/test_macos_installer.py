"""macOS installer design: guided .pkg, drag-and-drop .dmg, signing modes (no macOS tools needed)."""

import plistlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import macos_installer as mi  # noqa: E402

PACKAGE = (ROOT / "scripts" / "package_macos.sh").read_text(encoding="utf-8")
BUILD = (ROOT / "scripts" / "build_app.sh").read_text(encoding="utf-8")


def test_distribution_is_a_guided_all_users_install_without_scripts():
    dist = ET.fromstring(mi.distribution_xml("0.1.0"))
    assert dist.findtext("title") == "Monograph PDF 0.1.0"
    for tag in ("welcome", "readme", "license", "conclusion", "background", "background-darkAqua"):
        assert dist.find(tag) is not None, tag
    assert dist.find("volume-check/allowed-os-versions/os-version").get("min") == "13.0"
    opts = dist.find("options")
    assert opts.get("require-scripts") == "false" and opts.get("customize") == "never"
    assert opts.get("hostArchitectures") == "arm64"
    dom = dist.find("domains")
    assert (dom.get("enable_localSystem"), dom.get("enable_currentUserHome"), dom.get("enable_anywhere")) == ("true", "false", "false")
    # an older package is refused up front (the receipt would otherwise claim the older version)
    assert dist.find("installation-check").get("script") == "monographNoDowngrade()"
    script = dist.findtext("script")
    assert "compareVersions(installed, '0.1.0') > 0" in script and "'Fatal'" in script
    ref = [r for r in dist.iter("pkg-ref") if r.text]
    assert ref[0].text == mi.COMPONENT_PKG and ref[0].get("id") == "com.aungyemun.monographpdf"


def test_pages_name_the_version_and_ship_the_agpl(tmp_path):
    written = mi.render_pages(tmp_path, "0.1.0")
    assert {p.name for p in written} == {"welcome.html", "readme.html", "conclusion.html", "LICENSE.txt"}
    welcome = (tmp_path / "welcome.html").read_text(encoding="utf-8")
    assert "Monograph PDF" in welcome and "0.1.0" in welcome and "13.0" in welcome
    assert "{{" not in "".join(p.read_text(encoding="utf-8") for p in written)
    assert "kept" in welcome  # upgrades keep settings and recent files
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (tmp_path / "LICENSE.txt").read_text(encoding="utf-8")


def test_component_installs_only_into_applications_and_upgrades_in_place(tmp_path):
    plist = tmp_path / "component.plist"
    plist.write_bytes(plistlib.dumps([{"RootRelativeBundlePath": "Applications/MonographPDF.app",
                                       "BundleIsRelocatable": True, "BundleIsVersionChecked": False}]))
    (b,) = mi.harden_component_plist(plist)
    assert b["BundleIsRelocatable"] is False  # never redirected into a copy moved elsewhere (no duplicates)
    assert b["BundleIsVersionChecked"] is True  # an older package cannot downgrade a newer app
    assert b["BundleOverwriteAction"] == "upgrade"
    assert plistlib.loads(plist.read_bytes())[0]["BundleIsRelocatable"] is False


def test_dmg_layout_places_app_and_applications_with_an_arrow_between():
    script = mi.dmg_layout_script("Monograph PDF 0.1.0")
    assert 'disk "Monograph PDF 0.1.0"' in script
    assert 'item "MonographPDF.app"' in script and 'item "Applications"' in script
    assert ".background:background.tiff" in script and "toolbar visible of container window to false" in script
    assert mi.DMG_APP_POS[0] < mi.DMG_APPS_POS[0] and mi.DMG_APP_POS[1] == mi.DMG_APPS_POS[1]


@pytest.mark.skipif(sys.platform != "darwin", reason="tiffutil is macOS-only")
def test_dmg_and_pkg_artwork_render(tmp_path):
    from PIL import Image

    tiff = mi.dmg_art(tmp_path / "bg")
    with Image.open(tiff) as img:
        assert img.size == mi.DMG_WINDOW
    png = mi.pkg_background(tmp_path / "background.png", dark=False)
    with Image.open(png) as img:
        assert img.size == (1240, 836)


def test_packaging_uses_native_tools_and_no_install_scripts():
    assert "pkgbuild --analyze" in PACKAGE and "--component-plist" in PACKAGE
    assert "productbuild --distribution" in PACKAGE and "--resources" in PACKAGE
    assert "--scripts" not in PACKAGE  # nothing runs as root during installation
    assert "ditto -c -k --sequesterRsrc --keepParent" in PACKAGE
    assert "verify_macos_release.py" in PACKAGE
    assert ".DS_Store missing" in PACKAGE  # a DMG without its Finder layout fails the build


def test_production_mode_needs_real_apple_credentials_and_never_fakes_notarization():
    for var in ("MONOGRAPH_MACOS_SIGN_IDENTITY", "MONOGRAPH_MACOS_INSTALLER_IDENTITY", "MONOGRAPH_NOTARY_PROFILE"):
        assert var in PACKAGE
    assert "xcrun notarytool submit" in PACKAGE and "xcrun stapler staple" in PACKAGE
    assert "NOT notarized" in PACKAGE
    assert "update-signing" not in PACKAGE + BUILD  # the Windows update-manifest key is never used
    assert '--options runtime' in BUILD and "entitlements.plist" in BUILD
    assert 'security find-identity -v -p codesigning' in BUILD


def test_entitlements_are_minimal():
    ent = plistlib.loads((ROOT / "installer" / "macos" / "entitlements.plist").read_bytes())
    assert ent == {"com.apple.security.cs.allow-unsigned-executable-memory": True}
