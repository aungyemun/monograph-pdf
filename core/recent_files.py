"""Recent local files list (paths only; no cloud). Stored in user app-data."""

from __future__ import annotations

import json
from pathlib import Path

from core.user_prefs import recent_files_path

_NOT_USER_FILES = ("monographpdf-smoke-", "pdfeditor-smoke-", "pytest-of-", "\\tests\\samples\\", "\\tests\\outputs\\", "/tests/samples/", "/tests/outputs/")


class RecentFiles:
    def __init__(self, path: Path | None = None, limit: int = 12) -> None:
        self.path = path or recent_files_path()
        self.limit = limit
        self._items: list[str] = []
        self.load()

    def load(self) -> None:
        self._items = []
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items = [str(x) for x in data]
                # Drop files left behind by the installer self-check and test runs of
                # earlier versions (they were written to the real list by mistake).
                clean = [x for x in items if not any(m in x for m in _NOT_USER_FILES)]
                self._items = clean[: self.limit]
                if len(clean) != len(items):
                    try:
                        self.save()
                    except OSError:
                        pass
        except Exception:  # noqa: BLE001
            self._items = []

    def save(self) -> None:
        from core.user_prefs import _write_atomic

        _write_atomic(self.path, json.dumps(self._items, indent=2))

    def add(self, file_path: str | Path) -> None:
        resolved = str(Path(file_path).resolve())
        self._items = [p for p in self._items if p != resolved]
        self._items.insert(0, resolved)
        self._items = self._items[: self.limit]
        self.save()

    def list(self) -> list[Path]:
        out: list[Path] = []
        for item in self._items:
            p = Path(item)
            if p.is_file():
                out.append(p)
        return out

    def remove(self, file_path: str | Path) -> None:
        resolved = str(Path(file_path).resolve())
        self._items = [p for p in self._items if p != resolved]
        self.save()

    def clear(self) -> None:
        self._items = []
        self.save()
