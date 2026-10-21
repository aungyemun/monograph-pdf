r"""Unhandled exceptions, Qt errors and unexpected termination.

Normal use writes no report files. Two tiny records exist under
``%LOCALAPPDATA%\Monograph PDF\Diagnostics``:

* ``session-<pid>.json`` while the application runs (version and start time only), removed at a
  normal exit. Finding one for a process that no longer runs means the application ended
  unexpectedly; the next start offers a "termination" report built from approved fields only.
* ``pending-report.json`` (one, bounded): a validated report of an unhandled exception that could
  not be shown, offered at the next start.

Both expire after :data:`MAX_AGE` and are removed once the user has decided.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from core import app_env
from core.diagnostics import report as reports
from core.diagnostics.events import EventId, diagnostics
from core.product_meta import DATA_FOLDER_NAME

MAX_AGE = 14 * 24 * 3600
PENDING = "pending-report.json"


def diagnostics_dir() -> Path:
    override = app_env.get("DIAGNOSTICS_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / DATA_FOLDER_NAME / "Diagnostics"
    return Path.home() / ".cache" / "monograph-pdf" / "diagnostics"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


class SessionGuard:
    def __init__(self) -> None:
        self.path = diagnostics_dir() / f"session-{os.getpid()}.json"

    def start(self) -> None:
        from core.versioning import get_version

        try:
            _write_json(self.path, {"pid": os.getpid(), "version": get_version(), "started": int(time.time())})
        except OSError:
            pass

    def end(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def previous_terminations(now: float | None = None) -> int:
    """Count (and remove) session records of earlier runs that did not end normally."""
    from core.updates.staging import pid_alive

    now = time.time() if now is None else now
    found = 0
    folder = diagnostics_dir()
    if not folder.is_dir():
        return 0
    for f in folder.glob("session-*.json"):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            pid, started = int(info.get("pid", 0)), int(info.get("started", 0))
        except (OSError, ValueError, TypeError):
            pid, started = 0, 0
        if pid == os.getpid():
            continue
        if pid and pid_alive(pid) and now - started < MAX_AGE:
            continue  # another window of Monograph PDF is still running
        if now - started < MAX_AGE:
            found += 1
        try:
            f.unlink()
        except OSError:
            pass
    return found


def save_pending(report: dict) -> None:
    try:
        _write_json(diagnostics_dir() / PENDING, {"saved": int(time.time()), "report": reports.validate(report)})
    except (OSError, reports.ReportError):
        pass


def take_pending(now: float | None = None) -> dict | None:
    """The pending report (validated again), removed from disk in any case."""
    path = diagnostics_dir() / PENDING
    now = time.time() if now is None else now
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    try:
        if now - int(data.get("saved", 0)) > MAX_AGE:
            return None
        return reports.validate(data.get("report"))
    except (reports.ReportError, ValueError, TypeError, AttributeError):
        return None


def install_hooks(show: Callable[[dict], bool] | None = None) -> None:
    """Route unhandled exceptions to ``show`` (returns False when no UI can show it right now, in
    which case the report is kept for the next start)."""
    previous = sys.excepthook

    def handle(exc_type, exc, tb, *, thread: bool = False):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            previous(exc_type, exc, tb)
            return
        diagnostics.record(EventId.UNHANDLED_EXCEPTION)
        try:
            if exc is not None and exc.__traceback__ is None:
                exc = exc.with_traceback(tb)
            rep = reports.build(EventId.UNHANDLED_EXCEPTION, exc, report_type="crash")
        except Exception:  # noqa: BLE001 — never fail inside the hook
            rep = None
        shown = False
        if rep is not None and show is not None and not thread:
            try:
                shown = bool(show(rep))
            except Exception:  # noqa: BLE001
                shown = False
        if rep is not None and not shown:
            save_pending(rep)
        previous(exc_type, exc, tb)

    sys.excepthook = lambda t, e, tb: handle(t, e, tb)
    threading.excepthook = lambda a: handle(a.exc_type, a.exc_value, a.exc_traceback, thread=True)


def install_qt_message_handler() -> None:
    """Record Qt critical/fatal messages as event identifiers only (their text may hold paths)."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return
    previous = None

    def handler(mode, context, message):
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            diagnostics.record(EventId.QT_CRITICAL)
            if mode == QtMsgType.QtFatalMsg:
                try:
                    save_pending(reports.build(EventId.QT_CRITICAL, report_type="crash"))
                except Exception:  # noqa: BLE001
                    pass
        if previous is not None:
            previous(mode, context, message)
        else:
            sys.stderr.write(message + "\n")

    previous = qInstallMessageHandler(handler)
