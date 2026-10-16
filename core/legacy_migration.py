"""One-time copy of a user's earlier internal-build (<= 0.1.5) data into Monograph PDF folders.

Earlier internal builds kept data in ``%APPDATA%\\PDF Editor`` and ``%LOCALAPPDATA%\\PDF Editor``;
Monograph PDF uses ``%APPDATA%\\Monograph PDF`` and ``%LOCALAPPDATA%\\Monograph PDF``. The first
time Monograph PDF starts for a Windows user, it copies what is still useful:

* ``preferences.json`` — copied (only keys Monograph PDF knows are used when it is read);
* ``recent_files.json`` — copied, keeping only entries that are still existing files;
* recovery sessions (``runtime\\sessions\\*.json``, format version 1) — copied when Monograph PDF
  has no session for the same document, so unsaved edits can still be recovered;
* nothing else: the cache is rebuilt, temporary files and logs are not carried over, and
  password-protected documents never have recovery copies.

The earlier internal AppData folders are never changed or deleted here. A record
(``legacy_migration.json`` in the new settings folder) makes it run once and tells the
uninstaller that those folders belonged to this user's earlier internal installation.
Each user is handled by their own first start, so a per-machine upgrade works for every
account on the computer. This never runs for the self-check or the tests (the user-data
folder is redirected there) or when ``MONOGRAPH_PDF_NO_LEGACY_MIGRATION=1``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from core import app_env
from core.product_meta import (
    DATA_FOLDER_NAME,
    LEGACY_DATA_FOLDER_NAME,
    LEGACY_PRODUCT_NAME,
    PRODUCT_NAME,
)

MARKER_NAME = "legacy_migration.json"
SESSION_FORMAT = 1


@dataclass
class MigrationResult:
    ran: bool = False
    reason: str = ""
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Locations:
    legacy_roaming: Path
    legacy_local: Path
    roaming: Path
    local: Path


def default_locations() -> Locations | None:
    """Windows AppData locations of both products, or None where no legacy data can exist."""
    if not sys.platform.startswith("win"):
        return None
    roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Locations(
        legacy_roaming=roaming / LEGACY_DATA_FOLDER_NAME,
        legacy_local=local / LEGACY_DATA_FOLDER_NAME,
        roaming=roaming / DATA_FOLDER_NAME,
        local=local / DATA_FOLDER_NAME,
    )


def _is_link(path: Path) -> bool:
    """A symbolic link or junction is never followed (the data could be someone else's)."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError:
        return True


def _read_json(path: Path):
    # utf-8-sig: also accept a file saved with a byte-order mark (e.g. edited in Notepad / PowerShell)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _copy_preferences(loc: Locations, res: MigrationResult) -> None:
    src, dst = loc.legacy_roaming / "preferences.json", loc.roaming / "preferences.json"
    if not src.is_file() or _is_link(src):
        return
    if dst.exists():
        res.skipped.append("preferences.json (Monograph PDF already has settings)")
        return
    try:
        data = _read_json(src)
        if not isinstance(data, dict):
            raise ValueError("not a settings object")
        dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
        res.copied.append("preferences.json")
    except (OSError, ValueError) as exc:
        res.errors.append(f"preferences.json: {exc}")


def _copy_recent_files(loc: Locations, res: MigrationResult) -> None:
    src, dst = loc.legacy_roaming / "recent_files.json", loc.roaming / "recent_files.json"
    if not src.is_file() or _is_link(src):
        return
    if dst.exists():
        res.skipped.append("recent_files.json (Monograph PDF already has a list)")
        return
    try:
        data = _read_json(src)
        if not isinstance(data, list):
            raise ValueError("not a list")
        kept = [str(item) for item in data if isinstance(item, str) and Path(item).is_absolute() and Path(item).is_file()]
        dst.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        res.copied.append(f"recent_files.json ({len(kept)} of {len(data)} entries)")
    except (OSError, ValueError) as exc:
        res.errors.append(f"recent_files.json: {exc}")


def _copy_sessions(loc: Locations, res: MigrationResult, runtime_dir: Path | None) -> None:
    src_dir = loc.legacy_local / "runtime" / "sessions"
    if runtime_dir is None or not src_dir.is_dir() or _is_link(src_dir):
        return
    dst_dir = runtime_dir / "sessions"
    count = 0
    for src in sorted(src_dir.glob("*.json")):
        if _is_link(src) or not src.is_file():
            continue
        dst = dst_dir / src.name
        if dst.exists():
            res.skipped.append(f"session {src.name} (already present)")
            continue
        try:
            data = _read_json(src)
            if not isinstance(data, dict) or data.get("version") != SESSION_FORMAT:
                res.skipped.append(f"session {src.name} (unknown format; left in {src_dir})")
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            # written in the format Monograph PDF reads (UTF-8 JSON), the content unchanged
            dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            count += 1
        except (OSError, ValueError) as exc:
            res.errors.append(f"session {src.name}: {exc}")
    if count:
        res.copied.append(f"{count} recovery session(s)")


def migrate(loc: Locations | None = None, *, runtime_dir: Path | None = None) -> MigrationResult:
    """Copy PDF Editor settings, recent files and recovery sessions once. Never deletes anything."""
    res = MigrationResult()
    if app_env.is_true("NO_LEGACY_MIGRATION"):
        res.reason = "disabled"
        return res
    if loc is None:
        if app_env.get("USER_DATA_DIR"):
            res.reason = "user-data folder redirected"
            return res
        loc = default_locations()
        if loc is None:
            res.reason = "not Windows"
            return res
    marker = loc.roaming / MARKER_NAME
    if marker.exists():
        res.reason = "already migrated"
        return res
    if not loc.legacy_roaming.is_dir() and not loc.legacy_local.is_dir():
        res.reason = "no PDF Editor data"
        return res
    if _is_link(loc.legacy_roaming) or _is_link(loc.legacy_local):
        res.reason = "PDF Editor data folder is a link; not migrated"
        return res
    try:
        loc.roaming.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        res.reason = f"cannot create {loc.roaming}: {exc}"
        return res
    res.ran = True
    _copy_preferences(loc, res)
    _copy_recent_files(loc, res)
    _copy_sessions(loc, res, runtime_dir)
    record = {
        "from": LEGACY_PRODUCT_NAME,
        "to": PRODUCT_NAME,
        "migrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "legacy_roaming": str(loc.legacy_roaming),
        "legacy_local": str(loc.legacy_local),
        "copied": res.copied,
        "skipped": res.skipped,
        "errors": res.errors,
        "note": "The PDF Editor folders were left unchanged.",
    }
    try:
        marker.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError as exc:
        res.errors.append(f"{MARKER_NAME}: {exc}")
    return res


def migrate_at_startup() -> MigrationResult:
    """Called once before settings are read. Recovery sessions go to the per-user runtime folder
    only for an installed copy (a project / portable copy keeps its own ./runtime)."""
    try:
        from app.paths import INSTALLED_READ_ONLY, RUNTIME_DIR

        loc = None if app_env.get("USER_DATA_DIR") else default_locations()
        runtime = RUNTIME_DIR if INSTALLED_READ_ONLY and not app_env.get("RUNTIME_DIR") else None
        if loc is None:
            return migrate(None)
        return migrate(loc, runtime_dir=runtime)
    except Exception as exc:  # noqa: BLE001 - migration must never stop the app from starting
        return MigrationResult(reason=f"failed: {exc}")
