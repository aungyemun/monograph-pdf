"""Private error reporting: approved fields only, consent before sending, bounded local records."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.diagnostics import EventId, client, crash, diagnostics
from core.diagnostics import report as reports
from core.diagnostics.events import Diagnostics

ROOT = Path(__file__).resolve().parents[2]
SECRETS = [
    "/home/tanaka/Documents/研究資料.pdf", r"C:\Users\田中太郎\Documents\研究資料.pdf", "研究資料.pdf",
    r"D:\研究データ\神経再生\実験結果.pdf", r"C:\Users\张伟\Documents\实验报告.pdf", r"C:\Users\김민수\Documents\연구자료.pdf",
    "tanaka@example.com", "ghp_" + "A" * 36, "hunter2", "Confidential patient 4711", "田中太郎", "AKIA" + "ABCDEFGHIJKLMNOP",
]


@pytest.fixture(autouse=True)
def diag_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_DIAGNOSTICS_DIR", str(tmp_path / "Diagnostics"))
    diagnostics.clear()
    yield tmp_path / "Diagnostics"
    diagnostics.clear()


def _failing_save(path: str):
    # simulates application code that fails with a message full of private data
    raise ValueError(f"cannot write {path} for tanaka@example.com (password hunter2) {' '.join(SECRETS)}")


def _report_from_app_code():
    from core.diagnostics import events  # an application module, so its frame counts as code location

    ns: dict = {"__name__": "core.document_save_sim"}
    exec("def save(p):\n    raise ValueError('cannot write ' + p)\n", ns)  # noqa: S102 — test-only stand-in
    try:
        ns["save"](" ".join(SECRETS))
    except ValueError as exc:
        return reports.build(events.EventId.PDF_SAVE_FAILED, exc)


def test_reports_never_contain_paths_names_content_or_credentials():
    diagnostics.record(EventId.PDF_OPEN_STARTED)
    diagnostics.record(EventId.PDF_SAVE_STARTED)
    try:
        _failing_save(" ".join(SECRETS))
    except ValueError as exc:
        rep = reports.build(EventId.PDF_SAVE_FAILED, exc)
    text = json.dumps(rep, ensure_ascii=False) + reports.render(rep)
    for secret in SECRETS + [os.getlogin() if hasattr(os, "getlogin") and _safe_login() else "§§"]:
        assert secret not in text, secret
    assert str(Path.home()) not in text and str(ROOT) not in text
    assert rep["error_code"] == "PDF_SAVE_FAILED" and rep["component"] == "pdf" and rep["operation"] == "PDF_SAVE"
    assert rep["exception_type"] == "ValueError"
    assert rep["recent_events"] == ["PDF_OPEN_STARTED", "PDF_SAVE_STARTED"]
    assert set(rep) <= set(reports.SCHEMA)


def _safe_login() -> bool:
    try:
        return len(os.getlogin()) >= 4
    except OSError:
        return False


def test_code_location_is_module_function_line_only():
    rep = _report_from_app_code()
    assert rep["code_location"] == ["core.document_save_sim:save:2"]
    for secret in SECRETS:
        assert secret not in json.dumps(rep, ensure_ascii=False)


def test_only_predefined_events_are_recorded_and_the_buffer_is_bounded():
    d = Diagnostics(size=5)
    d.record("PDF_OPEN_STARTED")
    d.record("open C:/Users/tanaka/secret.pdf")  # not an identifier: ignored
    d.record("TYPED: hello world")
    for _ in range(10):
        d.record(EventId.OCR_STARTED)
    assert d.recent() == ["OCR_STARTED"] * 5


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(extra="x"), lambda r: r.update(component="C:\\Users\\x"), lambda r: r.pop("fingerprint"),
    lambda r: r.update(exception_type="ValueError: /home/x/a.pdf"), lambda r: r.update(recent_events=["NOT_A_REAL_EVENT"]),
    lambda r: r.update(code_location=["C:/Users/x/core/doc.py:1"]), lambda r: r.update(app_version="0.3.0; rm -rf"),
    lambda r: r.update(display_language="ja-JP\n@everyone"), lambda r: r.update(recent_events=["PDF_OPEN_STARTED"] * 31),
    lambda r: r.update(schema=True), lambda r: r.update(timestamp="2026-10-21T07:19:13Z"),
])
def test_schema_rejects_anything_outside_the_allow_list(mutate):
    rep = reports.build(EventId.PDF_SAVE_FAILED, events=[])
    mutate(rep)
    with pytest.raises(reports.ReportError):
        reports.validate(rep)


def test_fingerprint_groups_software_failures_not_users():
    a = _report_from_app_code()
    b = _report_from_app_code()
    assert a["fingerprint"] == b["fingerprint"]
    c = reports.build(EventId.PDF_OPEN_FAILED, events=[])
    assert c["fingerprint"] != a["fingerprint"]
    basis_fields = {"error_code", "exception_type", "code_location", "app_version"}
    assert basis_fields.isdisjoint({"display_language", "os_version", "timestamp"})  # no device data in it


def test_timestamp_is_minute_resolution_utc():
    rep = reports.build(EventId.OCR_FAILED, events=[])
    assert rep["timestamp"].endswith(":00Z")


def test_unhandled_exception_without_a_window_is_kept_for_the_next_start(diag_dir, monkeypatch):
    shown = []
    previous = sys.excepthook
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    import threading

    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    crash.install_hooks(lambda rep: shown.append(rep) or False)
    try:
        raise RuntimeError("secret /home/tanaka/a.pdf")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    assert shown and shown[0]["error_code"] == "UNHANDLED_EXCEPTION" and shown[0]["report_type"] == "crash"
    pending = crash.take_pending()
    assert pending is not None and pending["exception_type"] == "RuntimeError"
    assert "tanaka" not in json.dumps(pending)
    assert crash.take_pending() is None  # removed once taken
    assert sys.excepthook is not previous


def test_shown_report_is_not_stored(diag_dir, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    crash.install_hooks(lambda rep: True)
    try:
        raise KeyError("x")
    except KeyError:
        sys.excepthook(*sys.exc_info())
    assert not (diag_dir / crash.PENDING).exists()


def test_pending_reports_expire_and_are_revalidated(diag_dir):
    rep = reports.build(EventId.QT_CRITICAL, events=[])
    crash.save_pending(rep)
    assert crash.take_pending(now=time.time() + crash.MAX_AGE + 10) is None
    diag_dir.mkdir(parents=True, exist_ok=True)
    (diag_dir / crash.PENDING).write_text(json.dumps({"saved": int(time.time()), "report": {**rep, "path": "C:/x"}}),
                                          encoding="utf-8")
    assert crash.take_pending() is None and not (diag_dir / crash.PENDING).exists()


def test_unexpected_termination_is_detected_from_a_stale_session(diag_dir):
    g = crash.SessionGuard()
    g.start()
    assert crash.previous_terminations() == 0  # our own session
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (diag_dir / f"session-{dead.pid}.json").write_text(json.dumps({"pid": dead.pid, "started": int(time.time())}),
                                                       encoding="utf-8")
    assert crash.previous_terminations() == 1
    assert crash.previous_terminations() == 0  # reported once
    g.end()
    assert list(diag_dir.glob("session-*.json")) == []


def test_normal_use_writes_no_report_files(diag_dir):
    for e in EventId:
        diagnostics.record(e)
    reports.build(EventId.PDF_SAVE_FAILED)
    assert not diag_dir.exists() or list(diag_dir.iterdir()) == []


def test_sending_is_disabled_in_this_build_and_never_touches_the_network():
    from app.offline_guard import NetworkAttempts

    cfg = client.load_config(ROOT / "resources" / "diagnostics" / "reporting.json")
    assert cfg.enabled is False and not cfg.usable
    rep = reports.build(EventId.PDF_SAVE_FAILED, events=[])
    with NetworkAttempts() as guard:
        res = client.send(rep, cfg)
    assert not res.ok and "not enabled" in res.message and guard.attempts == []


def test_send_refuses_an_invalid_report_before_connecting():
    from app.offline_guard import NetworkAttempts

    cfg = client.ReportingConfig(True, "https://reports.example/v1/reports")
    with NetworkAttempts() as guard:
        res = client.send({"schema": 1, "free_text": "C:/Users/x/a.pdf"}, cfg)
    assert not res.ok and "privacy check" in res.message and guard.attempts == []


def test_send_failure_is_reported_truthfully_offline():
    from app.offline_guard import NetworkAttempts

    cfg = client.ReportingConfig(True, "https://reports.example/v1/reports")
    with NetworkAttempts() as guard:
        res = client.send(reports.build(EventId.PDF_SAVE_FAILED, events=[]), cfg)
    assert not res.ok and "could not be reached" in res.message
    assert len(guard.attempts) == 1  # exactly one attempt, no silent retry


def test_gateway_and_client_share_one_schema():
    from services.report_gateway import report_schema as gw

    assert set(gw.SCHEMA) == set(reports.SCHEMA)
    for name, (pattern, required) in reports.SCHEMA.items():
        assert gw.SCHEMA[name][0].pattern == pattern.pattern and gw.SCHEMA[name][1] == required, name
    assert gw.EVENT_NAMES == {e.value for e in EventId}
    assert gw.LIST_FIELDS == reports.LIST_FIELDS and gw.MAX_REPORT_BYTES == reports.MAX_REPORT_BYTES
    rep = reports.build(EventId.OCR_FAILED)
    assert gw.validate(rep) == rep
