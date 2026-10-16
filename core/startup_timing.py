"""Startup phase timing — offline, file-backed evidence under tests/outputs/logs."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


_marks: dict[str, float] = {}
_t0: float | None = None
from core import app_env  # noqa: E402

_enabled = app_env.get("STARTUP_TIMING", "1").lower() not in (
    "0",
    "false",
    "no",
)


def reset() -> None:
    global _marks, _t0
    _marks = {}
    _t0 = time.perf_counter()


def mark(name: str) -> None:
    if not _enabled:
        return
    global _t0
    if _t0 is None:
        _t0 = time.perf_counter()
    _marks[name] = time.perf_counter() - _t0


def elapsed_ms(name: str) -> float | None:
    if name not in _marks:
        return None
    return round(_marks[name] * 1000.0, 2)


def snapshot() -> dict[str, float]:
    return {k: round(v * 1000.0, 2) for k, v in sorted(_marks.items(), key=lambda kv: kv[1])}


def _log_dir() -> Path:
    """Prefer install/project root (exe dir when frozen), not the PyInstaller extract tree."""
    try:
        from app.paths import TEST_LOGS

        return TEST_LOGS
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[1] / "tests" / "outputs" / "logs"


def write_log(path: Path | None = None, *, tag: str = "startup") -> Path | None:
    if not _enabled or not _marks:
        return None
    if path is None:
        out_dir = _log_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{tag}-{int(time.time())}.json"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "tag": tag,
        "phases_ms": snapshot(),
        "total_ms": round((_marks.get("first_visible") or max(_marks.values())) * 1000.0, 2),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Also keep a stable latest pointer for before/after comparison
    latest = path.parent / f"{tag}-latest.json"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path
