"""Normal use never flashes a Command Prompt or PowerShell window.

The program and its helpers are Windows GUI programs, and every console program the application
starts (OCR engine, wevtutil, Office/LibreOffice command lines, version probes) is started with
CREATE_NO_WINDOW. On macOS the same keyword is passed (value 0) for a uniform call shape."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CALLS = {"run", "Popen", "call", "check_call", "check_output"}
GUI_PROGRAMS = ("explorer.exe", "/usr/bin/open")  # GUI programs: no console window is created for them

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") and sys.platform != "darwin",
    reason="console-window policy is for Windows and macOS desktop builds",
)


def _subprocess_calls():
    for folder in ("app", "core", "ui"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
                    yield path, node, ast.get_source_segment(text, node) or ""


def test_every_console_program_is_started_without_a_window():
    missing = []
    for path, node, src in _subprocess_calls():
        if any(p in src for p in GUI_PROGRAMS):
            continue
        if not any(k.arg == "creationflags" for k in node.keywords):
            missing.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not missing, missing


def test_program_and_helpers_are_built_as_gui_programs():
    build_exe = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert "--windowed" in build_exe and "--console" not in build_exe
    build_release = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    for source in ("update_helper.cs", "uninstall_launcher.cs"):
        line = next(l for l in build_release.splitlines() if source in l and "$Csc" in l)
        assert "/target:winexe" in line, line
