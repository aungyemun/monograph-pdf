r"""Unhandled exceptions, Qt errors and unexpected termination.

Normal use writes no report files. Two tiny records exist under
``%LOCALAPPDATA%\Monograph PDF\Diagnostics``:

* ``session-<pid>.json`` while the application runs (version and start time only), removed at a
  normal exit. Finding one for a process that no longer runs means the application ended
  unexpectedly; the next start offers a "termination" report built from approved fields only.
* ``pending-report.json`` (one, bounded): a validated report of an unhandled exception that could
  not be shown, offered at the next start.
* ``fault-<pid>.log`` while the application runs: empty unless the process hits a fatal native error
  (for example an access violation), when Python's ``faulthandler`` writes the stack of the failing
  thread into it. The next start turns it into approved fields only — the kind of fault and
  Monograph PDF's own ``module:function:line`` entries — and deletes it. The session record also
  keeps the identifiers of the most recent actions (never names or content), so a report of a hard
  crash can say what was being done.

Both expire after :data:`MAX_AGE` and are removed once the user has decided.
"""

from __future__ import annotations

import faulthandler
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
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
        self.fault_path = diagnostics_dir() / f"fault-{os.getpid()}.log"
        self._fault_file = None
        self._record: dict = {}

    def start(self) -> None:
        from core.versioning import get_version

        self._record = {"pid": os.getpid(), "version": get_version(), "started": int(time.time()), "events": []}
        try:
            _write_json(self.path, self._record)
        except OSError:
            pass
        try:  # a fatal native error (access violation …) writes the failing stack here
            self.fault_path.parent.mkdir(parents=True, exist_ok=True)
            self._fault_file = open(self.fault_path, "w", encoding="utf-8")  # noqa: SIM115 — kept open
            faulthandler.enable(file=self._fault_file, all_threads=False)
        except (OSError, RuntimeError, ValueError):
            self._fault_file = None
        diagnostics.set_listener(self._events_changed)

    def _events_changed(self, events: list[str]) -> None:
        self._record["events"] = list(events)[-30:]
        try:
            _write_json(self.path, self._record)
        except OSError:
            pass

    def end(self) -> None:
        diagnostics.set_listener(None)
        if self._fault_file is not None:
            try:
                faulthandler.disable()
                self._fault_file.close()
            except (OSError, ValueError):
                pass
            self._fault_file = None
        for path in (self.path, self.fault_path):
            try:
                path.unlink()
            except OSError:
                pass


@dataclass
class Termination:
    """What is known about an earlier run that ended unexpectedly (approved values only)."""

    events: list[str] = field(default_factory=list)
    fault_kind: str = ""  # ACCESS_VIOLATION … ; "" = nothing recorded (power off, ended in Task Manager)
    code_location: list[str] = field(default_factory=list)  # oldest call first, own modules only
    faulting_module: str = ""  # a file of Monograph PDF itself (e.g. python311.dll) or "external"


_FAULT_KINDS = (
    ("access violation", "ACCESS_VIOLATION"), ("segmentation fault", "ACCESS_VIOLATION"),
    ("stack overflow", "STACK_OVERFLOW"), ("illegal instruction", "ILLEGAL_INSTRUCTION"),
    ("divide by zero", "INT_DIVIDE_BY_ZERO"), ("floating point", "FLOATING_POINT"),
    ("aborted", "ABORT"), ("fatal python error", "FATAL_ERROR"), ("bus error", "ACCESS_VIOLATION"),
)
_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+) in (?P<func>\S+)')
_APP_FILE = re.compile(r"(?:^|[\\/])(app|core|ui|engines)[\\/](?P<rest>[^\"]+?)\.pyc?$", re.I)


def parse_fault_log(text: str) -> tuple[str, list[str]]:
    """(fault kind, ``module:function:line`` of Monograph PDF's own frames, oldest call first) from a
    faulthandler dump. Only the last dump counts; nothing else of the text (paths …) is kept."""
    from core.diagnostics import report as reports

    blocks = re.split(r"(?=^(?:Windows fatal exception|Fatal Python error)[^\n]*$)", text, flags=re.M)
    block = next((b for b in reversed(blocks) if b.strip()), "")
    if not block.strip():
        return "", []
    head = block.strip().splitlines()[0].lower()
    kind = next((k for needle, k in _FAULT_KINDS if needle in head), "OTHER")
    frames: list[str] = []
    in_current = False
    for line in block.splitlines():
        if line.startswith(("Current thread", "Thread 0x", "Stack (most recent call first)")):
            in_current = line.startswith(("Current thread", "Stack"))
            continue
        if not in_current:
            continue
        m = _FRAME.match(line)
        if not m:
            continue
        f = _APP_FILE.search(m.group("file").replace("\\", "/"))
        if not f:
            continue
        module = (f.group(1).lower() + "." + f.group("rest").replace("\\", "/").replace("/", ".")).removesuffix(".__init__")
        entry = f"{module}:{m.group('func')}:{m.group('line')}"
        if reports._ok("code_location", entry):  # noqa: SLF001
            frames.append(entry)
    frames.reverse()  # faulthandler lists the most recent call first
    return kind, frames[-12:]


def faulting_module(pid: int, *, timeout: float = 5.0) -> str:
    """The file in which Windows recorded the crash of process ``pid`` (Windows Error Reporting,
    event 1000 in the local Application log): its name when it belongs to Monograph PDF itself,
    "external" for anything else (another program's file is never named). "" when unknown."""
    if not sys.platform.startswith("win") or pid <= 0:
        return ""
    # XML, not text: the text form is in the Windows display language (e.g. Japanese); the XML field
    # names are not. Windows itself selects the record of this process.
    query = ("*[System[Provider[@Name='Application Error'] and (EventID=1000)]"
             f" and EventData[Data[@Name='ProcessId']='0x{pid:x}']]")
    from core.safe_paths import windows_tool

    try:  # full path of the Windows tool (a bare name could start a look-alike from another folder)
        out = subprocess.run([windows_tool("wevtutil.exe"), "qe", "Application", f"/q:{query}", "/c:1", "/rd:true", "/f:xml"],
                             capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return module_from_wer_xml(out.decode("utf-8", errors="replace"), pid, Path(sys.executable).resolve().parent)


def module_from_wer_xml(xml: str, pid: int, own_folder: Path) -> str:
    """The faulting file of process ``pid`` in a Windows Error Reporting event (XML): its name when it
    is one of the program's own files (under ``own_folder``), "external" otherwise, "" when absent."""
    def data(name: str) -> str:
        m = re.search(r"<Data Name='" + name + r"'>([^<]*)</Data>", xml) or \
            re.search(r'<Data Name="' + name + r'">([^<]*)</Data>', xml)
        return m.group(1).strip() if m else ""

    try:
        if int(data("ProcessId"), 16) != int(pid):
            return ""
    except ValueError:
        return ""
    module_path = data("ModulePath")
    if not module_path:
        return ""
    try:
        path = Path(module_path).resolve()
        inside = path.is_relative_to(own_folder)
    except (OSError, ValueError):
        inside = False
    name = path.name if inside else "external"
    return name if re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}\.(dll|exe|pyd)|external", name, re.I) else ""


def take_terminations(now: float | None = None) -> list[Termination]:
    """Details of earlier runs that ended unexpectedly; their records are removed."""
    from core.updates.staging import pid_alive

    now = time.time() if now is None else now
    out: list[Termination] = []
    folder = diagnostics_dir()
    if not folder.is_dir():
        return out
    for f in folder.glob("session-*.json"):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            pid, started = int(info.get("pid", 0)), int(info.get("started", 0))
            events = [e for e in info.get("events", []) if isinstance(e, str)]
        except (OSError, ValueError, TypeError, AttributeError):
            pid, started, events = 0, 0, []
        if pid == os.getpid():
            continue
        if pid and pid_alive(pid) and now - started < MAX_AGE:
            continue  # another window of Monograph PDF is still running
        fault = folder / f"fault-{pid}.log"
        if now - started < MAX_AGE:
            t = Termination(events=events[-30:])
            try:
                text = fault.read_text(encoding="utf-8", errors="replace")[-20000:]
            except OSError:
                text = ""
            t.fault_kind, t.code_location = parse_fault_log(text)
            if t.fault_kind:
                t.faulting_module = faulting_module(pid)
            out.append(t)
        for path in (f, fault):
            try:
                path.unlink()
            except OSError:
                pass
    for fault in folder.glob("fault-*.log"):  # left over without a session record
        try:
            pid = int(fault.stem.split("-", 1)[1])
        except (IndexError, ValueError):
            pid = 0
        if pid != os.getpid() and not (pid and pid_alive(pid)):
            try:
                fault.unlink()
            except OSError:
                pass
    return out


def previous_terminations(now: float | None = None) -> int:
    """Count (and remove) session records of earlier runs that did not end normally."""
    return len(take_terminations(now))


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
