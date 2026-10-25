"""Canonical product identity — single source for name, copyright, branding and legacy names.

Version comes from platform files via core.versioning.get_version / app.read_version
(Option B: versions/<platform>.txt; root VERSION mirrors Windows).
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
WINDOWS_EXECUTABLE_NAME = "MonographPDF.exe"
EXECUTABLE_NAME = WINDOWS_EXECUTABLE_NAME if sys.platform.startswith("win") else "MonographPDF"
REPOSITORY_NAME = "monograph-pdf"
# Folder name under %APPDATA% / %LOCALAPPDATA% (and Program Files, Start menu)
DATA_FOLDER_NAME = "Monograph PDF"
COPYRIGHT_OWNER = "Aung Ye Mun"
COPYRIGHT_START_YEAR = 2026
COPYRIGHT_DISPLAY = "© 2026 Aung Ye Mun"

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
        "OriginalFilename": WINDOWS_EXECUTABLE_NAME,
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
    """Best available icon for window/taskbar/desktop.

    Windows prefers the multi-size ``.ico``. Linux and macOS prefer PNG (``.ico`` is a
    poor fit for FreeDesktop / many Qt builds on Unix).
    """
    if sys.platform.startswith("win"):
        candidates = (ICON_ICO_REL, ICON_ABOUT_PNG_REL, ICON_PNG_MASTER_REL)
    else:
        candidates = (ICON_ABOUT_PNG_REL, ICON_PNG_MASTER_REL, ICON_ICO_REL)
    for rel in candidates:
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
    missing = [rel for rel in (ICON_PNG_MASTER_REL, ICON_ICO_REL, ICON_ABOUT_PNG_REL) if not icon_path(rel).is_file()]
    if missing:
        return False, "Missing branding assets: " + ", ".join(missing)
    return True, "Branding assets present"
