"""Low memory use while Monograph PDF is minimized (memory-saving mode).

Called by the main window a few seconds after it is minimized: rendered pages, tiles, pictures and
thumbnails are dropped by the window itself (they are drawn again when needed); this module
releases what is left on the library side and asks Windows to take back unused memory:

* MuPDF's internal store of decoded fonts and images is emptied (``store_shrink``).
* Python's garbage collector runs once.
* The process working set is trimmed (``SetProcessWorkingSetSize(-1, -1)``): pages not in use
  return to Windows; nothing is lost, they are read back if touched.
* Windows efficiency mode (EcoQoS, the leaf in Task Manager) is switched on — only when no
  background job such as OCR or a conversion is running, so minimizing never slows real work —
  and switched off again as soon as the window is restored.

Everything here is best effort and never raises: a failure only means less memory is saved.
"""

from __future__ import annotations

import gc
import sys

PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
ProcessPowerThrottling = 4  # PROCESS_INFORMATION_CLASS


def _win() -> bool:
    return sys.platform.startswith("win")


def shrink_mupdf_store() -> None:
    try:
        import fitz

        fitz.TOOLS.store_shrink(100)
    except Exception:  # noqa: BLE001
        pass


def trim_working_set() -> bool:
    if not _win():
        return False
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessWorkingSetSize.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t)
        handle = kernel32.GetCurrentProcess()
        return bool(kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1)))
    except Exception:  # noqa: BLE001
        return False


def set_efficiency_mode(on: bool) -> bool:
    """Windows 10 1709+ / 11: EcoQoS for this process (True when Windows accepted the setting)."""
    if not _win():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _State(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]

        state = _State(PROCESS_POWER_THROTTLING_CURRENT_VERSION, PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
                       PROCESS_POWER_THROTTLING_EXECUTION_SPEED if on else 0)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessInformation.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        return bool(kernel32.SetProcessInformation(kernel32.GetCurrentProcess(), ProcessPowerThrottling,
                                                   ctypes.byref(state), ctypes.sizeof(state)))
    except Exception:  # noqa: BLE001
        return False


def background_work_running() -> bool:
    """True while a worker thread (OCR, conversion, compression, batch job, update download …) runs."""
    try:
        from PySide6.QtCore import QThread, QThreadPool

        if QThreadPool.globalInstance().activeThreadCount() > 0:
            return True
        return any(isinstance(o, QThread) and o.isRunning() for o in gc.get_objects())
    except Exception:  # noqa: BLE001
        return True  # unknown: do not slow anything down


def working_set_bytes() -> int | None:
    """Current physical memory (working set) of this process, Windows only."""
    if not _win():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        c = _Counters()
        c.cb = ctypes.sizeof(c)
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD)
        if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return int(c.WorkingSetSize)
    except Exception:  # noqa: BLE001
        pass
    return None


def release_library_memory() -> None:
    """MuPDF store, garbage collection and working-set trim (after the window dropped its caches)."""
    try:
        from core.editing import text_layout

        text_layout.clear_layout_cache()
    except Exception:  # noqa: BLE001
        pass
    try:
        from PySide6.QtGui import QPixmapCache

        QPixmapCache.clear()
    except Exception:  # noqa: BLE001
        pass
    shrink_mupdf_store()
    gc.collect()
    trim_working_set()
