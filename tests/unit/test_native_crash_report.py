"""A hard crash (access violation) of an earlier run produces a useful report at the next start: the
kind of fault, Monograph PDF's own code location and the recent actions — still approved values only
(0.4.0 said just "did not close normally": nothing survived a native crash)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def diag(tmp_path, monkeypatch):
    folder = tmp_path / "Diagnostics"
    monkeypatch.setenv("MONOGRAPH_PDF_DIAGNOSTICS_DIR", str(folder))
    return folder


def _crash_child(tmp_path: Path, diag: Path) -> subprocess.CompletedProcess:
    probe = tmp_path / "fake" / "core" / "native_probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text(textwrap.dedent("""
        import ctypes

        def boom():
            ctypes.string_at(0)  # reads address 0: access violation / segmentation fault
    """), encoding="utf-8")
    script = textwrap.dedent(f"""
        import importlib.util, sys
        sys.path.insert(0, {str(ROOT)!r})
        from core.diagnostics import EventId, diagnostics
        from core.diagnostics.crash import SessionGuard
        guard = SessionGuard()
        guard.start()
        diagnostics.record(EventId.TEXT_EDIT_STARTED)
        diagnostics.record(EventId.STYLE_CHANGED)
        diagnostics.record(EventId.STYLE_CHANGED)  # a run of the same action is kept once
        spec = importlib.util.spec_from_file_location("native_probe", {str(probe)!r})
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        mod.boom()
    """)
    env = dict(os.environ, MONOGRAPH_PDF_DIAGNOSTICS_DIR=str(diag))
    return subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, timeout=120)


def test_hard_crash_is_reported_with_kind_location_and_recent_actions(tmp_path, diag):
    from core.diagnostics import EventId
    from core.diagnostics import crash
    from core.diagnostics import report as reports

    proc = _crash_child(tmp_path, diag)
    assert proc.returncode != 0, "the child must really crash"
    assert list(diag.glob("session-*.json")) and list(diag.glob("fault-*.log"))
    found = crash.take_terminations()
    assert len(found) == 1
    t = found[0]
    assert t.fault_kind == "ACCESS_VIOLATION"
    assert t.code_location and t.code_location[-1].startswith("core.native_probe:boom:")
    assert t.events == ["APP_STARTED", "TEXT_EDIT_STARTED", "STYLE_CHANGED"] or t.events[-2:] == ["TEXT_EDIT_STARTED", "STYLE_CHANGED"]
    assert not list(diag.glob("*")), "the records are removed once read"
    rep = reports.build(EventId.UNEXPECTED_TERMINATION, report_type="termination", events=t.events, fault=t)
    text = json.dumps(rep)
    assert "\\\\" not in text and "/" not in text.replace("://", ""), "no paths in the report"
    assert str(tmp_path.name) not in text
    summary = reports.describe(rep)
    assert "memory access error" in summary and "boom in core.native_probe" in summary
    assert "changing fonts or formatting" in summary


def test_parse_fault_log_keeps_only_own_frames_and_the_last_dump():
    from core.diagnostics.crash import parse_fault_log

    log = (
        "Windows fatal exception: code 0xe06d7363\n\nCurrent thread 0x1 (most recent call first):\n"
        '  File "C:\\Program Files\\Monograph PDF\\_internal\\ui\\old.py", line 1 in earlier\n\n'
        "Windows fatal exception: access violation\n\n"
        "Thread 0x2 (most recent call first):\n"
        '  File "C:\\Users\\someone\\ui\\other_thread.py", line 9 in worker\n\n'
        "Current thread 0x3 (most recent call first):\n"
        '  File "C:\\Program Files\\Monograph PDF\\_internal\\ui\\font_picker.py", line 28 in paint\n'
        '  File "C:\\Users\\someone\\site-packages\\shiboken6\\x.py", line 5 in call\n'
        '  File "C:\\Program Files\\Monograph PDF\\_internal\\app\\bootstrap.py", line 160 in main\n'
    )
    kind, frames = parse_fault_log(log)
    assert kind == "ACCESS_VIOLATION"
    assert frames == ["app.bootstrap:main:160", "ui.font_picker:paint:28"]
    assert parse_fault_log("") == ("", [])


def test_clean_exit_leaves_no_records(diag):
    from core.diagnostics.crash import SessionGuard

    g = SessionGuard()
    g.start()
    assert g.path.exists() and g.fault_path.exists()
    g.end()
    assert not list(diag.glob("*"))


def test_termination_without_details_says_so(diag):
    from core.diagnostics import EventId
    from core.diagnostics import report as reports
    from core.diagnostics.crash import Termination

    rep = reports.build(EventId.UNEXPECTED_TERMINATION, report_type="termination", events=[], fault=Termination())
    assert "no error was recorded" in reports.describe(rep)
    assert "fault_kind" not in rep


def test_gateway_accepts_exactly_the_same_fields():
    sys.path.insert(0, str(ROOT / "services" / "report_gateway"))
    try:
        import report_schema as gw
    finally:
        sys.path.pop(0)
    from core.diagnostics import EventId
    from core.diagnostics import report as reports

    assert set(gw.SCHEMA) == set(reports.SCHEMA)
    assert {k: v[0].pattern for k, v in gw.SCHEMA.items()} == {k: v[0].pattern for k, v in reports.SCHEMA.items()}
    assert gw.EVENT_NAMES == {e.value for e in EventId}


def test_faulting_module_names_only_the_programs_own_files(tmp_path):
    from core.diagnostics.crash import module_from_wer_xml

    own = tmp_path / "Monograph PDF"
    (own / "_internal").mkdir(parents=True)
    xml = ("<Event><EventData><Data Name='AppName'>MonographPDF.exe</Data>"
           "<Data Name='ProcessId'>0xa1fc</Data>"
           f"<Data Name='ModulePath'>{own / '_internal' / 'python311.dll'}</Data></EventData></Event>")
    assert module_from_wer_xml(xml, 0xA1FC, own) == "python311.dll"
    assert module_from_wer_xml(xml, 0xA1FC, tmp_path / "other") == "external"  # never another program's file
    assert module_from_wer_xml(xml, 0x1234, own) == ""  # another process
    assert module_from_wer_xml("", 0xA1FC, own) == ""