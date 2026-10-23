"""Tests and tools only ever end processes they started themselves.

Ending processes by program name (all python.exe, all PowerShell windows, …) would also end the
user's unrelated work. Processes are ended through the handle or process ID of a process the tool
started, or through the Windows Job Object that contains exactly the tool's process tree."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

FORBIDDEN = [
    (re.compile(r"Stop-Process\s+(-Name|-ProcessName)\b", re.I), "Stop-Process by name"),
    (re.compile(r"taskkill[^\n]*\s/IM\b", re.I), "taskkill /IM (by image name)"),
    (re.compile(r"\b(pkill|killall)\b"), "pkill / killall"),
    (re.compile(r"Get-Process\s+[^|\n{]*\|\s*Stop-Process", re.I), "Get-Process <name> | Stop-Process without a filter"),
    (re.compile(r"wmic\s+process[^\n]*\bdelete\b", re.I), "wmic process … delete"),
    (re.compile(r"Get-Process[^\n]*\|\s*ForEach-Object\s*\{[^}]*\.Kill\(\)", re.I), "kill every process of a name"),
]


def _is_gitignored(path: Path) -> bool:
    """Local maintainer harnesses under scripts/qa_* are gitignored; do not fail the release gate on them."""
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", str(path.relative_to(ROOT).as_posix())],
            capture_output=True,
        )
        return r.returncode == 0
    except OSError:
        return False


def _files():
    for folder in ("scripts", "tests", "app", "core", "ui", "installer", ".github"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix.lower() in (".py", ".ps1", ".psm1", ".bat", ".cmd", ".cs", ".iss", ".yml") \
                    and path.resolve() != Path(__file__).resolve() \
                    and not _is_gitignored(path):
                yield path


def test_no_process_is_ended_by_name():
    found = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for rx, what in FORBIDDEN:
            for m in rx.finditer(text):
                found.append(f"{path.relative_to(ROOT)}:{text[:m.start()].count(chr(10)) + 1}: {what}")
        if "process_iter" in text and re.search(r"\.(kill|terminate)\(", text):
            found.append(f"{path.relative_to(ROOT)}: enumerates all processes and kills")
    assert not found, found


def test_installer_test_cleanup_ends_only_its_own_processes():
    text = (ROOT / "scripts" / "test_installer.ps1").read_text(encoding="utf-8")
    cleanup = text[text.index("Restoring this user's Monograph PDF"):]
    cleanup = cleanup[: cleanup.index("foreach ($cleanDir")]
    assert "$ScriptStart" in text and "StartTime -ge $ScriptStart" in cleanup
    assert "Stop-Process -Id $p.Id" in cleanup and "LEFT RUNNING" in cleanup


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows Job Objects")
def test_run_isolated_ends_exactly_the_command_tree_and_nothing_else(tmp_path):
    import run_isolated

    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])  # e.g. the user's own work
    try:
        pids = tmp_path / "pids.txt"
        # child starts a grandchild, records both PIDs, then both sleep far beyond the time limit
        child = (
            "import subprocess, sys, time, os;"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
            f"open(r'{pids}', 'w').write(f'{{os.getpid()}} {{g.pid}}');"
            "time.sleep(120)"
        )
        t0 = time.time()
        rc = run_isolated.run([sys.executable, "-c", child], timeout=8)
        assert rc == run_isolated.TIMEOUT_EXIT and time.time() - t0 < 60
        own = [int(x) for x in pids.read_text().split()]
        time.sleep(1)
        for pid in own:
            assert not _alive(pid), f"process {pid} of the command's tree is still running"
        assert bystander.poll() is None, "an unrelated process was ended"
    finally:
        bystander.kill()  # our own handle
        bystander.wait(10)


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows Job Objects")
def test_run_isolated_returns_the_exit_code_and_cleans_up_left_over_children(tmp_path):
    import run_isolated

    pid_file = tmp_path / "grandchild.txt"
    child = ("import subprocess, sys;"
             "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
             f"open(r'{pid_file}', 'w').write(str(g.pid)); sys.exit(3)")
    assert run_isolated.run([sys.executable, "-c", child]) == 3
    time.sleep(1)
    assert not _alive(int(pid_file.read_text()))  # left-over child ended when the job closed


def _alive(pid: int) -> bool:
    sys.path.insert(0, str(ROOT))
    from core.updates.staging import pid_alive

    return pid_alive(pid)
