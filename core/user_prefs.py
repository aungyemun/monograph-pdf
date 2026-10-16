"""Persistent user preferences in OS application-data location (not project root)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from core import app_env
from core.product_meta import DATA_FOLDER_NAME, LEGACY_DATA_FOLDER_NAME


def user_data_dir() -> Path:
    """Portable app-data root: Windows AppData, macOS Application Support, Linux XDG.

    ``MONOGRAPH_PDF_USER_DATA_DIR`` redirects it (used by the self-check and the tests so they
    never touch the user's real settings or recent-files list).
    """
    override = app_env.get("USER_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / DATA_FOLDER_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".local" / "share" / "monograph-pdf"


def legacy_user_data_dir() -> Path | None:
    """Settings folder of PDF Editor (<= 0.1.5) on Windows, for one-time migration; None elsewhere
    or when the user-data folder is redirected (tests, self-check)."""
    if app_env.get("USER_DATA_DIR") or not sys.platform.startswith("win"):
        return None
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / LEGACY_DATA_FOLDER_NAME


def user_cache_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".cache" / "monograph-pdf"


@dataclass
class UserPreferences:
    theme: str = "system"  # system | light | dark
    left_panel_width: int = 200
    right_panel_width: int = 280
    left_panel_collapsed: bool = False
    right_panel_collapsed: bool = False
    window_width: int = 1280
    window_height: int = 800
    window_x: int | None = None
    window_y: int | None = None
    zoom_remember: bool = False
    last_zoom: float = 1.0
    show_bookmarks_tab: bool = True
    show_attachments_tab: bool = True
    recent_limit: int = 12
    highlight_fillable_fields: bool = True
    last_fit_mode: str = "fit_width"  # fit_width | fit_page | actual_size
    recent_fonts: list | None = None
    recent_colors: list | None = None
    inspector_sections: dict | None = None

    def path(self) -> Path:
        return user_data_dir() / "preferences.json"

    @classmethod
    def load(cls) -> "UserPreferences":
        prefs = cls()
        path = prefs.path()
        if not path.is_file():
            return prefs
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in known:
                    setattr(prefs, k, v)
        except Exception:  # noqa: BLE001
            pass
        return prefs

    def save(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def recent_files_path() -> Path:
    return user_data_dir() / "recent_files.json"
