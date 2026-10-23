"""Run a command (e.g. the test suite) inside its own Windows Job Object, with an optional time limit.

    python scripts/run_isolated.py [--timeout SECONDS] [--pid-file FILE] -- <command> [args...]

Every process the command starts belongs to the job (unless it explicitly breaks away). When the
command finishes, times out or this runner is interrupted, the runner ends **only the processes in
that job** — the exact process tree it started — and never looks processes up by name. Unrelated
Python programs, shells, editors and the installed Monograph PDF are never touched.

The process is created suspended, assigned to the job, then resumed, so not even its first child can
start outside the job. The job is created with KILL_ON_JOB_CLOSE: if this runner itself is killed,
Windows ends the job's processes when its handle closes. Exit code: the command's, or 124 on timeout.
On other systems the command runs in a new process group that is ended on timeout.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
TIMEOUT_EXIT = 124


class WindowsJob:
    """A Job Object owning the process tree of one command."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct, self._wt = ctypes, wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                  ctypes.c_void_p]
        self._k32 = k32
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes",
                                                       "WriteBytes", "OtherBytes")]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = EXTENDED()
        # breakaway allowed: the application's update helper deliberately leaves the job of its parent
        info.Basic.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK
        if not k32.SetInformationJobObject(self.handle, JobObjectExtendedLimitInformation,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def start(self, cmd: list[str], **kw) -> subprocess.Popen:
        proc = subprocess.Popen(cmd, creationflags=CREATE_SUSPENDED | kw.pop("creationflags", 0), **kw)
        if not self._k32.AssignProcessToJobObject(self.handle, int(proc._handle)):  # noqa: SLF001
            err = self._ct.get_last_error()
            proc.kill()  # our own, still suspended process
            raise OSError(err, "AssignProcessToJobObject failed")
        ntdll = self._ct.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [self._wt.HANDLE]
        ntdll.NtResumeProcess(int(proc._handle))  # noqa: SLF001
        return proc

    def pids(self) -> list[int]:
        ct = self._ct

        class LIST(ct.Structure):
            _fields_ = [("Assigned", ct.c_uint32), ("InList", ct.c_uint32), ("Ids", ct.c_size_t * 4096)]

        lst = LIST()
        if not self._k32.QueryInformationJobObject(self.handle, JobObjectBasicProcessIdList, ct.byref(lst),
                                                   ct.sizeof(lst), None):
            return []
        return [int(lst.Ids[i]) for i in range(lst.InList)]

    def terminate(self, code: int = 1) -> None:
        self._k32.TerminateJobObject(self.handle, code)

    def close(self) -> None:
        if self.handle:
            self._k32.CloseHandle(self.handle)  # KILL_ON_JOB_CLOSE ends whatever is left
            self.handle = None


def run(cmd: list[str], timeout: float | None = None, pid_file: str | None = None, **kw) -> int:
    if sys.platform.startswith("win"):
        job = WindowsJob()
        try:
            proc = job.start(cmd, **kw)
            if pid_file:
                with open(pid_file, "w", encoding="ascii") as fh:
                    fh.write(f"{proc.pid}\n")
            try:
                return proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"run_isolated: time limit reached; ending the {len(job.pids())} process(es) of this "
                      f"command's job only", file=sys.stderr)
                job.terminate(TIMEOUT_EXIT)
                proc.wait(30)
                return TIMEOUT_EXIT
        finally:
            job.close()
    proc = subprocess.Popen(cmd, start_new_session=True, **kw)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, 9)
        proc.wait(30)
        return TIMEOUT_EXIT


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    i = argv.index("--")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeout", type=float)
    ap.add_argument("--pid-file")
    a = ap.parse_args(argv[:i])
    started = time.time()
    rc = run(argv[i + 1:], a.timeout, a.pid_file)
    print(f"run_isolated: exit {rc} after {time.time() - started:.0f} s", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
