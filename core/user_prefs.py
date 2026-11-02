"""Persistent user preferences in OS application-data location (not project root).

``preferences.json`` must survive upgrades across many versions (for example 0.4.1 directly to a much
later release) and a return to an older version:

* ``_schema`` records the file layout; :data:`MIGRATIONS` upgrades older layouts step by step on load
  (files written before 0.4.1 have no ``_schema``: layout 0);
* a value of the wrong type (hand-edited, or written by another version) is ignored and the default
  used, instead of failing later;
* settings this version does not know (written by a newer version) are kept and written back
  unchanged, so going back and forth between versions loses nothing;
* an unreadable file is copied to ``preferences.json.unreadable-<time>`` before defaults are used, so
  it is never silently overwritten;
* saving is atomic (a new file replaces the old one only when completely written).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable

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
    isolated = app_env.profile_subdir("Cache")
    if isolated is not None:
        return isolated
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / DATA_FOLDER_NAME
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "monograph-pdf"
    return Path.home() / ".cache" / "monograph-pdf"


SCHEMA = 1  # layout of preferences.json written by this version


def _migrate_0_to_1(data: dict) -> dict:
    """Layout 0 (before 0.4.1) and 1 have the same keys; 1 only adds ``_schema``."""
    return data


# MIGRATIONS[n] turns layout n into layout n + 1. Never remove or change an entry: a user may upgrade
# directly from any older version, so every step must stay available.
MIGRATIONS: dict[int, Callable[[dict], dict]] = {0: _migrate_0_to_1}

_TYPES = {"bool": bool, "int": int, "float": float, "str": str, "list": list, "dict": dict, "None": type(None)}


def _accepts(type_text: str, value) -> bool:
    for name in (t.strip() for t in str(type_text).split("|")):
        want = _TYPES.get(name)
        if want is None:
            continue
        if want is int and isinstance(value, bool):
            continue  # True is an int in Python, not a valid number here
        if want is float and isinstance(value, int) and not isinstance(value, bool):
            return True
        if isinstance(value, want):
            return True
    return False


def migrate(data: dict) -> dict:
    """Apply every migration from the file's layout up to :data:`SCHEMA` (newer layouts unchanged)."""
    version = data.get("_schema", 0)
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        version = 0
    while version < SCHEMA:
        data = MIGRATIONS[version](dict(data))
        version += 1
        data["_schema"] = version
    return data


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _keep_unreadable(path: Path) -> Path | None:
    """Copy an unreadable settings file aside (never overwriting) before defaults replace it."""
    dest = path.with_name(f"{path.name}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
    if dest.exists():
        return None
    try:
        shutil.copy2(path, dest)
        return dest
    except OSError:
        return None


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
    highlight_color: str = "#ffff00"  # markup highlight stroke (CSS hex)
    underline_color: str = "#0000ff"
    strikeout_color: str = "#ff0000"
    last_fit_mode: str = "fit_width"  # fit_width | fit_page | actual_size
    recent_fonts: list | None = None
    recent_colors: list | None = None
    inspector_sections: dict | None = None
    page_mark_presets: dict | None = None  # last settings of Header/Footer, Watermark and Background
    # Updates (Settings > Updates). Automatic checks are off until the user turns them on: Monograph
    # PDF does not contact the network on its own unless asked to.
    update_auto_check: bool = False
    update_interval_hours: int = 24
    update_channel: str = "stable"  # stable | prerelease
    # OCR languages used by every OCR command ("eng+jpn" = English and Japanese; optional languages
    # once installed, OCR > OCR Languages)
    ocr_languages: str = "eng+jpn"
    note_color: str = "#fbbf24"
    note_icon: str = "Comment"  # sticky note icon for new notes (core/annotations/note_style.NOTE_ICONS)
    squiggly_color: str = "#dc2626"
    # Rendered pages are converted from sRGB to the monitor's colour profile when it is not sRGB
    # (wide-gamut monitors); View > Match Colors to Monitor Profile (ui/display_color.py)
    match_monitor_colors: bool = True

    def path(self) -> Path:
        return user_data_dir() / "preferences.json"

    @classmethod
    def load(cls) -> "UserPreferences":
        prefs = cls()
        prefs._extra = {}
        path = prefs.path()
        if not path.is_file():
            return prefs
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except Exception:  # noqa: BLE001 - unreadable: keep a copy, use the defaults
            _keep_unreadable(path)
            return prefs
        try:
            data = migrate(data)
        except Exception:  # noqa: BLE001 - a failed migration must not lose the file
            _keep_unreadable(path)
            return prefs
        known = {f.name: f for f in fields(cls)}
        for k, v in data.items():
            f = known.get(k)
            if f is not None:
                if _accepts(f.type, v):
                    setattr(prefs, k, float(v) if f.type == "float" else v)
            elif k != "_schema":
                prefs._extra[k] = v  # written by a newer version: keep it
        prefs._schema = max(SCHEMA, data.get("_schema", SCHEMA)) if isinstance(data.get("_schema"), int) else SCHEMA
        return prefs

    def save(self) -> None:
        data = {**getattr(self, "_extra", {}), **asdict(self), "_schema": getattr(self, "_schema", SCHEMA)}
        _write_atomic(self.path(), json.dumps(data, indent=2))


def recent_files_path() -> Path:
    return user_data_dir() / "recent_files.json"
