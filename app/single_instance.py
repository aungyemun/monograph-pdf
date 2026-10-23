"""One Monograph PDF per user session: a second start hands over to the running window.

Starting Monograph PDF again (from the Start menu, a shortcut or by opening a PDF in Explorer) while
it is already running does not open a second copy. The new process writes a small request — the
files to open, nothing else — into ``<runtime>\\instance\\requests``, allows the running window to
come to the front, waits until the request has been taken and exits. The running window opens the
file, or comes to the front and says it is already running.

* Detection: a named Windows mutex (``Local\\`` namespace = this logon session). The name is derived
  from the runtime folder, so the installed program, a copy run from source and the installer's
  self-check (``--runtime-dir``) never block each other.
* No network and no Qt networking: Qt's network module is not part of the build (offline design).
* Requests are local files of this user only; they are validated (JSON, a short list of existing
  files with a supported extension), consumed once and deleted. Stale requests are discarded.
* If the running copy does not take the request (not responding), the new process says so in a
  message box instead of starting a second copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

ERROR_ALREADY_EXISTS = 183
REQUEST_SUFFIX = ".json"
MAX_REQUEST_BYTES = 64 * 1024
MAX_FILES = 20
STALE_SECONDS = 120.0
HANDOVER_TIMEOUT = 10.0

_handle = None  # the mutex handle, kept for the life of the process


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def instance_folder() -> Path:
    from app.paths import RUNTIME_DIR

    return Path(RUNTIME_DIR) / "instance"


def requests_folder(folder: Path | None = None) -> Path:
    return (folder or instance_folder()) / "requests"


def mutex_name(folder: Path) -> str:
    key = os.path.normcase(str(Path(folder).resolve()))
    return "Local\\MonographPDF-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def acquire(folder: Path | None = None) -> bool:
    """True when this process is the first Monograph PDF (it then keeps the mutex). Always True
    outside Windows or if the mutex cannot be created (never blocks starting the program)."""
    global _handle
    if not _is_windows():
        return True
    folder = folder or instance_folder()
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        handle = kernel32.CreateMutexW(None, False, mutex_name(folder))
        if not handle:
            return True
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _handle = handle
        return True
    except Exception:  # noqa: BLE001 — never stop the program from starting
        return True


def release() -> None:
    global _handle
    if _handle is not None and _is_windows():
        try:
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(_handle)
        except Exception:  # noqa: BLE001
            pass
    _handle = None


def files_from_args(argv: list[str]) -> list[str]:
    out: list[str] = []
    for arg in argv[1:]:
        if not arg or arg.startswith("-"):
            continue
        try:
            p = Path(arg)
            if p.is_file():
                out.append(str(p.resolve()))
        except (OSError, ValueError):
            continue
    return out[:MAX_FILES]


def write_primary_info(folder: Path | None = None) -> None:
    """Record the running process id so a second start can let this window come to the front."""
    folder = folder or instance_folder()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        requests_folder(folder).mkdir(parents=True, exist_ok=True)
        tmp = folder / f"primary.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        os.replace(tmp, folder / "primary.json")
    except OSError:
        pass


def _primary_pid(folder: Path) -> int | None:
    try:
        pid = int(json.loads((folder / "primary.json").read_text(encoding="utf-8")).get("pid"))
        return pid if pid > 0 else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def send_request(files: list[str], folder: Path | None = None) -> Path:
    """Write a request for the running copy (atomically) and return its path."""
    folder = folder or instance_folder()
    inbox = requests_folder(folder)
    inbox.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time() * 1000)}-{uuid.uuid4().hex}"
    tmp = inbox / f"{name}.tmp"
    tmp.write_text(json.dumps({"files": list(files)[:MAX_FILES]}, ensure_ascii=False), encoding="utf-8")
    final = inbox / f"{name}{REQUEST_SUFFIX}"
    os.replace(tmp, final)
    return final


def read_requests(folder: Path | None = None) -> list[list[str]]:
    """Take every pending request (oldest first): each is the list of files to open (may be empty).
    Requests are deleted once read; malformed or stale ones are discarded."""
    inbox = requests_folder(folder)
    try:
        entries = sorted(p for p in inbox.iterdir() if p.suffix == REQUEST_SUFFIX)
    except OSError:
        return []
    out: list[list[str]] = []
    now = time.time()
    for path in entries:
        try:
            stale = now - path.stat().st_mtime > STALE_SECONDS
            data = None if stale or path.stat().st_size > MAX_REQUEST_BYTES else path.read_text(encoding="utf-8")
        except OSError:
            continue
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        if data is None:
            continue
        try:
            files = json.loads(data).get("files", [])
        except (ValueError, AttributeError):
            continue
        if not isinstance(files, list):
            continue
        out.append([f for f in files if isinstance(f, str) and f][:MAX_FILES])
    return out


def allow_primary_foreground(folder: Path | None = None) -> None:
    """The process the user just started may bring another window to the front; pass that right on."""
    if not _is_windows():
        return
    pid = _primary_pid(folder or instance_folder())
    if pid is None:
        return
    try:
        import ctypes

        ctypes.WinDLL("user32").AllowSetForegroundWindow(int(pid))
    except Exception:  # noqa: BLE001
        pass


def show_native_message(text: str, title: str = "Monograph PDF") -> None:
    if not _is_windows():
        print(text, file=sys.stderr)
        return
    try:
        import ctypes

        MB_ICONINFORMATION, MB_SETFOREGROUND = 0x40, 0x10000
        ctypes.WinDLL("user32").MessageBoxW(None, text, title, MB_ICONINFORMATION | MB_SETFOREGROUND)
    except Exception:  # noqa: BLE001
        pass


def hand_over(argv: list[str], folder: Path | None = None, *, timeout: float = HANDOVER_TIMEOUT) -> int:
    """Run in a second start: pass the files to the running copy and exit (returns the exit code)."""
    folder = folder or instance_folder()
    try:
        request = send_request(files_from_args(argv), folder)
    except OSError:
        show_native_message("Monograph PDF is already running.")
        return 0
    allow_primary_foreground(folder)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not request.exists():
            return 0
        time.sleep(0.05)
    try:
        request.unlink()
    except OSError:
        pass
    show_native_message("Monograph PDF is already running, but it is not responding right now.\n\n"
                        "Wait a moment and try again, or close the running Monograph PDF first.")
    return 0


def is_disabled(argv: list[str]) -> bool:
    """Self-check, the separate User Guide window and automated tests never use the handover."""
    from core import app_env

    if any(a in argv for a in ("--smoke-test", "--user-guide", "--new-instance")):
        return True
    return app_env.is_true("HEADLESS") or app_env.is_true("MULTI_INSTANCE")


class InstanceServer:
    """In the running copy: watch for requests from later starts and act on them in the window."""

    def __init__(self, window, folder: Path | None = None) -> None:
        from PySide6.QtCore import QFileSystemWatcher, QTimer

        self._window = window
        self._folder = folder or instance_folder()
        write_primary_info(self._folder)
        inbox = requests_folder(self._folder)
        self._watcher = QFileSystemWatcher([str(inbox)] if inbox.is_dir() else [], window)
        self._watcher.directoryChanged.connect(lambda _p: self._timer.start())
        self._timer = QTimer(window)  # coalesce bursts of change notifications
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.process)
        QTimer.singleShot(0, self.process)  # requests written while this copy was starting

    def process(self) -> None:
        for files in read_requests(self._folder):
            try:
                self._window.handle_instance_request(files)
            except Exception:  # noqa: BLE001 — a bad request must never break the running window
                pass
