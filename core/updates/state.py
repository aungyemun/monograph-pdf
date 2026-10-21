"""Small persistent update status (``Updates\\state.json``): no document data, no identifiers.

Holds the time and outcome of the last check, the highest manifest sequence accepted per channel
(so an older, replayed manifest is refused), the version the user postponed, and the outcome of
the last installation reported by the update helper.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

from core.updates.staging import updates_root


@dataclass
class UpdateState:
    last_check: int = 0              # Unix time of the last completed check (any outcome)
    last_success: int = 0            # Unix time of the last check that reached and verified the source
    last_status: str = ""            # UpdateStatus value of the last check
    latest_version: str = ""         # newest verified version seen
    sequence: dict = field(default_factory=dict)  # channel -> highest accepted manifest sequence
    remind_after: int = 0            # "Remind Me Later" for ``remind_version`` until this time
    remind_version: str = ""
    completed: list = field(default_factory=list)  # helper results already shown to the user

    @staticmethod
    def path():
        return updates_root() / "state.json"

    @classmethod
    def load(cls) -> "UpdateState":
        st = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return st
        if isinstance(data, dict):
            for k in asdict(st):
                if k in data and isinstance(data[k], type(getattr(st, k))):
                    setattr(st, k, data[k])
        return st

    def save(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        self.completed = self.completed[-20:]
        tmp.write_text(json.dumps(asdict(self), indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def due(self, interval_hours: int, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now - self.last_check >= max(1, interval_hours) * 3600
