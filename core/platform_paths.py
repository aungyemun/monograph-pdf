"""Cross-platform user data / runtime folder resolution.

Windows keeps the historical AppData layout; macOS uses Application Support and Caches;
Linux uses XDG. Overrides via ``MONOGRAPH_PDF_*`` still win (see ``core.app_env``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.product_meta import DATA_FOLDER_NAME


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def user_data_base() -> Path:
    """Roaming-equivalent settings root (preferences, recent files)."""
    if is_windows():
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / DATA_FOLDER_NAME
    if is_macos():
        return Path.home() / "Library" / "Application Support" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".local" / "share" / "monograph-pdf"


def user_local_base() -> Path:
    """Local / machine-specific data (runtime caches when installed)."""
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME
    if is_macos():
        return Path.home() / "Library" / "Application Support" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".local" / "share" / "monograph-pdf"


def user_cache_base() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME / "Cache"
    if is_macos():
        return Path.home() / "Library" / "Caches" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".cache" / "monograph-pdf"


def frozen_install_root() -> Path | None:
    """Directory that holds the frozen executable (``Contents/MacOS`` inside a .app)."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def is_macos_app_bundle() -> bool:
    root = frozen_install_root()
    if root is None or not is_macos():
        return False
    # .../MonographPDF.app/Contents/MacOS
    return root.name == "MacOS" and root.parent.name == "Contents" and root.parent.parent.suffix == ".app"
