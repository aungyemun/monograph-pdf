"""Canonical product identity (Monograph PDF), PE version strings and branding assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image

from core.product_meta import (
    COPYRIGHT_DISPLAY,
    COPYRIGHT_OWNER,
    COPYRIGHT_START_YEAR,
    DATA_FOLDER_NAME,
    EXECUTABLE_NAME,
    INTERNAL_NAME,
    LEGACY_EXECUTABLE_NAME,
    LEGACY_FINAL_VERSION,
    LEGACY_PRODUCT_NAME,
    PRODUCT_DESCRIPTION,
    PRODUCT_LICENSE,
    PRODUCT_NAME,
    REPOSITORY_NAME,
    WINDOWS_EXECUTABLE_NAME,
    branding_assets_ok,
    get_product_identity,
    icon_path,
    resolve_about_logo_path,
    resolve_app_icon_path,
    version_resource_strings,
)
from core.versioning import get_version

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / "resources" / "icons"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def test_canonical_identity_strings():
    assert PRODUCT_NAME == "Monograph PDF"
    assert WINDOWS_EXECUTABLE_NAME == "MonographPDF.exe"
    if sys.platform.startswith("win"):
        assert EXECUTABLE_NAME == "MonographPDF.exe"
    else:
        assert EXECUTABLE_NAME == "MonographPDF"
    assert INTERNAL_NAME == "MonographPDF"
    assert REPOSITORY_NAME == "monograph-pdf"
    assert DATA_FOLDER_NAME == "Monograph PDF"
    assert COPYRIGHT_OWNER == "Aung Ye Mun"
    assert COPYRIGHT_START_YEAR == 2026
    assert COPYRIGHT_DISPLAY == "© 2026 Aung Ye Mun"
    assert PRODUCT_LICENSE == "AGPL-3.0-or-later"
    assert PRODUCT_DESCRIPTION.startswith("Monograph PDF is an offline, privacy-first desktop application")


def test_legacy_identity_is_internal_compatibility_only():
    assert LEGACY_PRODUCT_NAME == "PDF Editor"
    assert LEGACY_EXECUTABLE_NAME == "PDF_editor.exe"
    assert LEGACY_FINAL_VERSION == "0.1.5"


def test_version_is_on_a_public_line():
    # Option B: each platform has its own SemVer; root VERSION mirrors Windows only.
    host = get_version()
    windows = get_version("windows")
    linux = get_version("linux")
    macos = get_version("macos")
    for label, version in (("host", host), ("windows", windows), ("linux", linux), ("macos", macos)):
        major, minor, patch = (int(x) for x in re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version).groups())
        assert (major, minor, patch) >= (0, 0, 0), label
    # Windows public line remains >= 0.2; Linux/macOS may start at 0.1.0 independently.
    w_major, w_minor, _ = (int(x) for x in re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", windows).groups())
    assert (w_major, w_minor) >= (0, 2)
    assert windows == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert host in {windows, linux, macos}

def test_identity_version_from_version_file():
    identity = get_product_identity()
    assert identity.version == get_version()
    assert identity.product_name == PRODUCT_NAME
    assert identity.executable_name == EXECUTABLE_NAME
    assert identity.copyright_display == COPYRIGHT_DISPLAY
    assert identity.about_title == "About Monograph PDF"


def test_pe_version_resource_strings():
    v = get_version()
    assert version_resource_strings() == {
        "CompanyName": "Aung Ye Mun",
        "FileDescription": "Monograph PDF",
        "FileVersion": v,
        "InternalName": "MonographPDF",
        "LegalCopyright": "© 2026 Aung Ye Mun",
        "OriginalFilename": "MonographPDF.exe",
        "ProductName": "Monograph PDF",
        "ProductVersion": v,
    }


def test_make_version_info_uses_the_metadata(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("mvi", ROOT / "scripts" / "make_version_info.py")
    mvi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mvi)
    monkeypatch.setattr(mvi, "ROOT", tmp_path)
    assert mvi.main() == 0
    text = (tmp_path / "build" / "version_info.txt").read_text(encoding="utf-8")
    for key, value in version_resource_strings().items():
        assert f"StringStruct(u'{key}', u'{value}')" in text
    assert "PDF Editor" not in text and "PDF_editor" not in text


def test_branding_assets_present():
    ok, detail = branding_assets_ok()
    assert ok, detail
    assert icon_path("source/Monograph_PDF_logo.png").is_file()
    assert icon_path("source/monograph_pdf_icon_1024.png").is_file()
    assert icon_path("windows/monograph_pdf.ico").is_file()
    if sys.platform.startswith("win"):
        assert resolve_app_icon_path() == icon_path("windows/monograph_pdf.ico")
    else:
        assert resolve_app_icon_path() == icon_path("windows/monograph_pdf_256.png")
    assert resolve_about_logo_path() == icon_path("windows/monograph_pdf_256.png")
    # No loose icons in project root
    assert not (ROOT / "monograph_pdf.ico").exists()


def test_ico_has_every_size_with_transparency():
    ico = Image.open(ICONS / "windows" / "monograph_pdf.ico")
    assert sorted(s[0] for s in ico.info["sizes"]) == ICO_SIZES
    for size in ICO_SIZES:
        ico.size = (size, size)
        frame = ico.copy().convert("RGBA")
        assert frame.size == (size, size)
        lo, hi = frame.getchannel("A").getextrema()
        assert lo == 0 and hi == 255, f"{size}px frame lost its transparency"
        png = Image.open(ICONS / "windows" / f"monograph_pdf_{size}.png")
        assert png.size == (size, size) and png.mode == "RGBA"


def test_icons_come_from_the_new_logo_without_distortion():
    """The emblem is scaled uniformly from the artwork: its aspect ratio is kept in the icon."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gbi", ROOT / "scripts" / "generate_branding_icons.py")
    gbi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gbi)
    art = gbi.load_artwork()
    x0, y0, x1, y1 = gbi.emblem_box(art)
    art_ratio = (x1 - x0) / (y1 - y0)
    master = Image.open(ICONS / "source" / "monograph_pdf_icon_1024.png")
    assert master.size == (1024, 1024)
    bx = master.getchannel("A").point(lambda v: 255 if v > gbi.ALPHA_SOLID else 0).getbbox()
    icon_ratio = (bx[2] - bx[0]) / (bx[3] - bx[1])
    assert abs(icon_ratio - art_ratio) < 0.02, (icon_ratio, art_ratio)
    # not cropped: the emblem does not touch the canvas edge
    assert bx[0] > 0 and bx[1] > 0 and bx[2] < 1024 and bx[3] < 1024


def test_old_pdf_editor_logo_is_not_an_active_resource():
    names = [p.name for p in ICONS.rglob("*") if p.is_file()]
    assert not [n for n in names if n.lower().startswith("pdf_editor") or n == "PDF_logo.png"], names
    assert not (ICONS / "linux").exists() and not (ICONS / "macos").exists()
