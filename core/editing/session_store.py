"""Local editing session cache for crash-safe recovery. Never overwrites source PDF."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.paths import RUNTIME_DIR


def session_dir() -> Path:
    d = RUNTIME_DIR / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_path_for(source: Path) -> Path:
    key = str(source.resolve()).replace(":", "_").replace("\\", "_").replace("/", "_")
    if len(key) > 120:
        key = key[-120:]
    return session_dir() / f"{key}.json"


def write_session(source: Path, payload: dict[str, Any]) -> Path:
    path = session_path_for(source)
    data = {
        "version": 1,
        "saved_at": time.time(),
        "source": str(source.resolve()),
        "payload": payload,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read_session(source: Path) -> dict[str, Any] | None:
    path = session_path_for(source)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(Path(data.get("source", "")).resolve()) != str(source.resolve()):
            # still accept if key matched
            pass
        return data
    except Exception:  # noqa: BLE001
        return None


def clear_session(source: Path) -> None:
    path = session_path_for(source)
    path.unlink(missing_ok=True)
    path.with_suffix(".tmp").unlink(missing_ok=True)


def list_recoverable() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in session_dir().glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            payload = data.get("payload") or {}
            if payload.get("dirty") and payload.get("objects"):
                out.append(data)
        except Exception:  # noqa: BLE001
            continue
    return out
