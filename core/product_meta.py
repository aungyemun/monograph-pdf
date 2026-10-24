"""Canonical product identity — single source for name, copyright, branding and legacy names.

Version always comes from the VERSION file via core.versioning / app.read_version.
Do not duplicate product strings elsewhere; import from here.

Internal compatibility: the ``LEGACY_*`` values describe earlier internal development builds
(0.1.x); they are used only to find and migrate such an installation and its settings, never
as the active identity.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from core.versioning import get_version


def _resources_dir() -> Path:
    """Resolve bundled resources without importing app at module import time."""
    from app.paths import RESOURCES_DIR

    return RESOURCES_DIR


PRODUCT_NAME = "Monograph PDF"
INTERNAL_NAME = "MonographPDF"
# Platform executable identity: Windows keeps the historical .exe name; macOS uses the
# Mach-O binary name inside MonographPDF.app (first macOS release is independent of Windows).
EXECUTABLE_NAME = "MonographPDF.exe" if sys.platform.startswith("win") else "MonographPDF"
REPOSITORY_NAME = "monograph-pdf"
# Folder name under AppData / Application Support (and Program Files, Applications)
DATA_FOLDER_NAME = "Monograph PDF"
COPYRIGHT_OWNER = "Aung Ye Mun"
COPYRIGHT_START_YEAR = 2026
COPYRIGHT_DISPLAY = "© 2026 Aung Ye Mun"
# macOS first-release line (VERSION file); Windows releases remain on their own track.
PLATFORM_LINE = "macOS" if sys.platform == "darwin" else ("Windows" if sys.platform.startswith("win") else "other")

PRODUCT_DESCRIPTION = (
    "Monograph PDF is an offline, privacy-first desktop application for viewing, editing, "
    "organizing, converting, protecting, signing and processing PDF documents."
)
PRODUCT_LICENSE = "AGPL-3.0-or-later"

# Earlier internal development builds (internal compatibility only)
LEGACY_PRODUCT_NAME = "PDF Editor"
LEGACY_EXECUTABLE_NAME = "PDF_editor.exe"
LEGACY_DATA_FOLDER_NAME = "PDF Editor"
LEGACY_FINAL_VERSION = "0.1.5"

# Relative to resources/icons/
ICON_ARTWORK_REL = "source/Monograph_PDF_logo.png"  # canonical artwork (logo with wordmark)
ICON_PNG_MASTER_REL = "source/monograph_pdf_icon_1024.png"  # square emblem made from the artwork
ICON_ICO_REL = "windows/monograph_pdf.ico"
ICON_ICNS_REL = "macos/monograph_pdf.icns"
# About box / Start page show the emblem next to the product name as text (the wordmark's dark
# lettering would disappear on the dark theme); 256 px stays sharp at 72 px on 300 % displays
ICON_ABOUT_PNG_REL = "windows/monograph_pdf_256.png"
ICON_LOGO_PNG_REL = "source/monograph_pdf_logo_512.png"  # full logo with wordmark (documentation)


@dataclass(frozen=True)
class ProductIdentity:
    product_name: str
    executable_name: str
    copyright_owner: str
    copyright_start_year: int
    copyright_display: str
    product_description: str
    version: str

    @property
    def about_title(self) -> str:
        return f"About {self.product_name}"

    @property
    def window_title_base(self) -> str:
        """Title bar product name only — version lives in About / diagnostics."""
        return self.product_name


def get_product_identity() -> ProductIdentity:
    return ProductIdentity(
        product_name=PRODUCT_NAME,
        executable_name=EXECUTABLE_NAME,
        copyright_owner=COPYRIGHT_OWNER,
        copyright_start_year=COPYRIGHT_START_YEAR,
        copyright_display=COPYRIGHT_DISPLAY,
        product_description=PRODUCT_DESCRIPTION,
        version=get_version(),
    )


def version_resource_strings(version: str | None = None) -> dict[str, str]:
    """Windows PE version strings of MonographPDF.exe (one definition for build and tests)."""
    version = get_version() if version is None else version
    return {
        "CompanyName": COPYRIGHT_OWNER,
        "FileDescription": PRODUCT_NAME,
        "FileVersion": version,
        "InternalName": INTERNAL_NAME,
        "LegalCopyright": COPYRIGHT_DISPLAY,
        "OriginalFilename": "MonographPDF.exe",
        "ProductName": PRODUCT_NAME,
        "ProductVersion": version,
    }


def build_info() -> dict:
    """Commit and state of the source this program was built from (``resources/build_info.json``,
    written by scripts/build_exe.ps1). Empty when running from source."""
    import json

    try:
        data = json.loads((_resources_dir() / "build_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    commit = str(data.get("commit", ""))
    if not (len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)):
        commit = ""
    return {"commit": commit, "dirty": bool(data.get("dirty")), "version": str(data.get("version", ""))}


def icons_root() -> Path:
    return _resources_dir() / "icons"


def icon_path(relative: str) -> Path:
    return icons_root() / relative


def resolve_app_icon_path() -> Path | None:
    """Best available icon for window/taskbar (ICO on Windows, ICNS/PNG on macOS)."""
    if sys.platform.startswith("win"):
        order = (ICON_ICO_REL, "windows/monograph_pdf_256.png", ICON_PNG_MASTER_REL)
    elif sys.platform == "darwin":
        order = (ICON_ICNS_REL, "windows/monograph_pdf_256.png", ICON_PNG_MASTER_REL, ICON_ICO_REL)
    else:
        order = ("windows/monograph_pdf_256.png", ICON_PNG_MASTER_REL, ICON_ICO_REL)
    for rel in order:
        path = icon_path(rel)
        if path.is_file():
            return path
    return None


def resolve_about_logo_path() -> Path | None:
    for rel in (ICON_ABOUT_PNG_REL, ICON_PNG_MASTER_REL):
        path = icon_path(rel)
        if path.is_file():
            return path
    return None


def branding_assets_ok() -> tuple[bool, str]:
    """Return (ok, detail) for missing critical logo resources."""
    required = [ICON_PNG_MASTER_REL, ICON_ABOUT_PNG_REL]
    if sys.platform.startswith("win"):
        required.append(ICON_ICO_REL)
    missing = [rel for rel in required if not icon_path(rel).is_file()]
    if missing:
        return False, "Missing branding assets: " + ", ".join(missing)
    return True, "Branding assets present"
