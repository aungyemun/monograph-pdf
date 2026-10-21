r"""Update staging area: where downloads wait, and the rules for removing them again.

Layout (per user; never in Documents, Desktop or Downloads, never beside settings)::

    %LOCALAPPDATA%\Monograph PDF\Updates\
        state.json            non-sensitive status (last check, last result, rollback counters)
        update.lock           held while an update is downloaded or handed to the helper
        Staging\<update-id>\  one folder per update attempt
            .monograph-update ownership marker (JSON)
            MonographPDF_X.Y.Z_Setup.exe[.part]
            handoff.json, setup.log, MonographPDFUpdater.exe
        result-<update-id>.json   the helper's outcome, read (and removed) at the next start

Cleanup only ever touches folders directly inside ``Staging`` that carry a valid ownership marker,
and inside them only file names the updater itself creates. Unknown files and folders, links and
junctions are left alone; nothing is removed recursively.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core import app_env
from core.product_meta import DATA_FOLDER_NAME

MARKER = ".monograph-update"
OWNER = "monograph-pdf-updater"
HELPER_NAME = "MonographPDFUpdater.exe"
FIXED_NAMES = {MARKER, "handoff.json", "setup.log", HELPER_NAME}
_SETUP_RE = re.compile(r"^MonographPDF_[0-9A-Za-z.-]+_Setup\.exe(?:\.part)?$")
_ID_RE = re.compile(r"^[0-9A-Za-z.-]{1,40}-[0-9a-f]{12}$")
FAILED_RETENTION = 7 * 24 * 3600  # a failed update keeps its verified installer for a retry this long
ABANDONED_AFTER = 24 * 3600        # an unfinished download nobody is working on
LOCK_STALE_AFTER = 2 * 3600
MAX_STAGING_BYTES = 1024**3        # never keep more than ~1 GB of update files
SPACE_MARGIN = 64 * 1024**2


def updates_root() -> Path:
    override = app_env.get("UPDATES_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME / "Updates"
    return Path.home() / ".cache" / "monograph-pdf" / "updates"


def staging_root() -> Path:
    return updates_root() / "Staging"


def is_link(path: Path) -> bool:
    """A symbolic link, junction or other reparse point (never followed or deleted through)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = ctypes.c_ulong()
            k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _safe_dir(path: Path) -> None:
    """Create ``path`` (and parents) refusing to work through a link anywhere below updates_root."""
    root = updates_root()
    root.mkdir(parents=True, exist_ok=True)
    if is_link(root):
        raise OSError("the updates folder is a link; refusing to use it")
    cur = root
    for part in path.relative_to(root).parts:
        cur = cur / part
        if cur.exists() and is_link(cur):
            raise OSError("an updates sub-folder is a link; refusing to use it")
        cur.mkdir(exist_ok=True)


class UpdateLock:
    """Only one update at a time per user (also guarded by the helper's named mutex)."""

    def __init__(self) -> None:
        self.path = updates_root() / "update.lock"
        self.held = False

    def acquire(self) -> bool:
        _safe_dir(updates_root())
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._stale():
                    try:
                        self.path.unlink()
                    except OSError:
                        return False
                    continue
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"pid": os.getpid(), "time": int(time.time())}, fh)
            self.held = True
            return True
        return False

    def _stale(self) -> bool:
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
            pid, created = int(info.get("pid", 0)), int(info.get("time", 0))
        except (OSError, ValueError, TypeError):
            return True
        return not pid_alive(pid) or time.time() - created > LOCK_STALE_AFTER

    def transfer_to(self, pid: int) -> None:
        """The helper takes over the update (it holds its own mutex while it runs)."""
        if self.held:
            self.path.write_text(json.dumps({"pid": pid, "time": int(time.time())}), encoding="utf-8")
            self.held = False

    def release(self) -> None:
        if self.held:
            try:
                self.path.unlink()
            except OSError:
                pass
            self.held = False


@dataclass
class StagingDir:
    path: Path
    update_id: str
    version: str

    @property
    def installer(self) -> Path:
        return self.path / f"MonographPDF_{self.version}_Setup.exe"

    @property
    def partial(self) -> Path:
        return self.path / f"MonographPDF_{self.version}_Setup.exe.part"

    def set_state(self, state: str, **extra) -> None:
        marker = read_marker(self.path) or {}
        marker.update({"owner": OWNER, "id": self.update_id, "version": self.version,
                       "state": state, "updated": int(time.time())}, **extra)
        (self.path / MARKER).write_text(json.dumps(marker), encoding="utf-8")


def new_staging(version: str) -> StagingDir:
    safe = re.sub(r"[^0-9A-Za-z.-]", "", version)[:40] or "update"
    update_id = f"{safe}-{secrets.token_hex(6)}"
    path = staging_root() / update_id
    _safe_dir(staging_root())
    path.mkdir()
    sd = StagingDir(path, update_id, version)
    sd.set_state("created", created=int(time.time()))
    return sd


def read_marker(folder: Path) -> dict | None:
    try:
        info = json.loads((folder / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or info.get("owner") != OWNER or info.get("id") != folder.name:
        return None
    return info


def has_space(folder: Path, needed: int) -> bool:
    """Free space on the drive of ``folder`` (or of its nearest existing parent) covers ``needed``."""
    probe = Path(folder)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free >= needed + SPACE_MARGIN
    except OSError:
        return False


def _owned_files(folder: Path) -> list[Path]:
    out = []
    for entry in folder.iterdir():
        if is_link(entry) or not entry.is_file():
            continue
        if entry.name in FIXED_NAMES or _SETUP_RE.match(entry.name):
            out.append(entry)
    return out


def remove_staging(folder: Path, keep: tuple[str, ...] = ()) -> bool:
    """Remove the updater's own files in one staging folder, then the folder if it is empty.

    Returns True when the folder is gone. Files in use (for example the running helper) stay.
    """
    if is_link(folder) or folder.parent != staging_root() or read_marker(folder) is None:
        return False
    for f in _owned_files(folder):
        if f.name in keep or f.name == MARKER:
            continue
        try:
            f.unlink()
        except OSError:
            pass
    remaining = [p for p in folder.iterdir() if p.name != MARKER]
    if remaining:
        return False
    try:
        (folder / MARKER).unlink()
        folder.rmdir()
        return True
    except OSError:
        return False


@dataclass
class CleanupReport:
    removed: list[str]
    kept: list[str]
    skipped_unknown: list[str]


def cleanup(active_id: str | None = None, now: float | None = None) -> CleanupReport:
    """Startup / helper cleanup of the staging area (see the module docstring for the rules).

    * completed (``installed``) and ``cancelled`` attempts: removed;
    * ``failed`` attempts: the verified installer is kept for a retry for FAILED_RETENTION, other
      files removed; only the newest failed attempt is kept;
    * unfinished downloads (``created`` / ``downloading``) older than ABANDONED_AFTER: removed;
    * attempts handed to the helper are left while the helper may still be running;
    * whatever is left is trimmed, oldest first, to MAX_STAGING_BYTES.
    """
    now = time.time() if now is None else now
    report = CleanupReport([], [], [])
    root = staging_root()
    if not root.is_dir() or is_link(root):
        return report
    entries = []
    for folder in sorted(root.iterdir()):
        if is_link(folder) or not folder.is_dir() or not _ID_RE.match(folder.name):
            report.skipped_unknown.append(folder.name)
            continue
        info = read_marker(folder)
        if info is None:
            report.skipped_unknown.append(folder.name)
            continue
        entries.append((folder, info))
    newest_failed = max((i.get("updated", 0) for _, i in entries if i.get("state") == "failed"), default=None)
    for folder, info in entries:
        state, age = info.get("state"), now - float(info.get("updated", 0) or 0)
        if folder.name == active_id:
            report.kept.append(folder.name)
            continue
        if state == "handed_off" and pid_alive(int(info.get("helper_pid", 0) or 0)) and age < LOCK_STALE_AFTER:
            report.kept.append(folder.name)
            continue
        if state == "failed" and info.get("updated") == newest_failed and age < FAILED_RETENTION:
            remove_staging(folder, keep=(f"MonographPDF_{info.get('version')}_Setup.exe",))
            report.kept.append(folder.name)
            continue
        if state in ("created", "downloading", "verified") and age < ABANDONED_AFTER:
            report.kept.append(folder.name)
            continue
        (report.removed if remove_staging(folder) else report.kept).append(folder.name)
    _trim(report)
    return report


def _size(folder: Path) -> int:
    return sum(f.stat().st_size for f in _owned_files(folder))


def _trim(report: CleanupReport) -> None:
    root = staging_root()
    kept = [root / n for n in report.kept if (root / n).is_dir()]
    kept.sort(key=lambda f: (read_marker(f) or {}).get("updated", 0))
    total = sum(_size(f) for f in kept)
    for folder in kept:
        if total <= MAX_STAGING_BYTES:
            break
        info = read_marker(folder) or {}
        if info.get("state") == "handed_off":
            continue
        size = _size(folder)
        if remove_staging(folder):
            total -= size
            report.kept.remove(folder.name)
            report.removed.append(folder.name)
