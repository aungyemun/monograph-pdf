"""Safe temporary locations for organize ops — never project root."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from app.paths import ORGANIZE_CACHE_DIR, ORGANIZE_TEMP_DIR, RUNTIME_DIR, TEMP_DIR, ensure_runtime_layout

# Abandoned job dirs older than this are removed on cleanup
_ABANDONED_AGE_SEC = 24 * 3600
# Crash-recovery drafts nobody came back to
_SESSION_AGE_SEC = 30 * 24 * 3600


def organize_temp_dir(*, prefix: str = "job") -> Path:
    """Create a unique writable temp directory under runtime/temp/organize."""
    ensure_runtime_layout()
    path = ORGANIZE_TEMP_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def move_into_place(source: Path, destination: Path) -> Path:
    """Move a finished file from the working folder to where the user saves it.

    A plain rename fails when the destination is on another drive (the working folder is on C:,
    the user saves to D: — Windows error 17); then the file is copied next to the destination
    first and swapped in, so the destination is never left half-written.
    """
    import os

    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, destination)
        return destination
    except OSError:
        pass
    partial = destination.with_name(f".{destination.name}.{uuid.uuid4().hex[:8]}.part")
    try:
        shutil.copyfile(source, partial)
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
    source.unlink(missing_ok=True)
    return destination


def organize_cache_file(name: str) -> Path:
    ensure_runtime_layout()
    return ORGANIZE_CACHE_DIR / name


def cleanup_dir(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def cleanup_abandoned_temps(*, max_age_sec: float = _ABANDONED_AGE_SEC) -> int:
    """Remove abandoned working files older than max_age_sec (run once after start-up).

    Organize jobs, converted Office / image files, print copies and other files under
    runtime/temp, plus recovery drafts (runtime/sessions) older than 30 days. Returns the
    number of entries removed.
    """
    ensure_runtime_layout()
    removed = 0
    now = time.time()
    temp_roots = [ORGANIZE_TEMP_DIR, ORGANIZE_CACHE_DIR]
    loose: list[Path] = []
    if TEMP_DIR.is_dir():
        for child in TEMP_DIR.iterdir():
            if child == ORGANIZE_TEMP_DIR:
                continue
            (temp_roots if child.is_dir() else loose).append(child)
    sessions = RUNTIME_DIR / "sessions"
    if sessions.is_dir():
        for child in sessions.iterdir():
            try:
                if child.is_file() and now - child.stat().st_mtime >= _SESSION_AGE_SEC:
                    child.unlink(missing_ok=True)
                    removed += 1
            except Exception:  # noqa: BLE001
                continue
    for child in loose:
        try:
            if now - child.stat().st_mtime >= max_age_sec:
                child.unlink(missing_ok=True)
                removed += 1
        except Exception:  # noqa: BLE001
            continue
    for root in temp_roots:
        if not root.is_dir():
            continue
        for child in list(root.iterdir()):
            try:
                age = now - child.stat().st_mtime
                if age < max_age_sec:
                    continue
                cleanup_dir(child)
                removed += 1
            except Exception:  # noqa: BLE001
                continue
    return removed
