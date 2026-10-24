"""Only one Monograph PDF runs per session: a second start hands its file to the running window."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app import single_instance as si

has_lock = pytest.mark.skipif(
    not (sys.platform.startswith("win") or sys.platform.startswith(("darwin", "linux"))),
    reason="no single-instance lock on this platform",
)


@has_lock
def test_second_process_is_not_primary(tmp_path):
    """A real second process sees the first one's lock (and a different folder does not)."""
    root = Path(__file__).resolve().parents[2]
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, time; sys.path.insert(0, sys.argv[1]); from app import single_instance as s; "
         "from pathlib import Path; print(s.acquire(Path(sys.argv[2])), flush=True); time.sleep(30)",
         str(root), str(tmp_path / "a")],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "True"
        assert si.acquire(tmp_path / "a") is False, "a second copy must not start"
        assert si.acquire(tmp_path / "b") is True, "another runtime folder (self-check, source run) is independent"
        si.release()
    finally:
        holder.kill()
        holder.wait(10)
    time.sleep(0.2)
    assert si.acquire(tmp_path / "a") is True, "after the first copy has ended, a new start is the first again"
    si.release()


def test_requests_are_validated_consumed_once_and_stale_ones_dropped(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    si.send_request([str(pdf)], tmp_path)
    si.send_request([], tmp_path)
    inbox = si.requests_folder(tmp_path)
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")
    (inbox / "wrong.json").write_text(json.dumps({"files": "C:/x.pdf"}), encoding="utf-8")
    old = inbox / "0-old.json"
    old.write_text(json.dumps({"files": [str(pdf)]}), encoding="utf-8")
    past = time.time() - si.STALE_SECONDS - 5
    os.utime(old, (past, past))
    got = si.read_requests(tmp_path)
    # two requests written in the same instant may come in either order (separate starts never do)
    assert sorted(got) == sorted([[str(pdf)], []])
    assert list(inbox.iterdir()) == [], "every request file is removed after reading"
    assert si.read_requests(tmp_path) == []


def test_files_from_args_keeps_only_existing_files(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    assert si.files_from_args(["exe", "--flag", str(pdf), str(tmp_path / "missing.pdf"), ""]) == [str(pdf.resolve())]


def test_hand_over_returns_once_the_running_copy_took_the_request(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    taken: list = []
    monkeypatch.setattr(si, "show_native_message", lambda *a, **k: taken.append(("message", a)))

    def running_copy() -> None:
        for _ in range(100):
            got = si.read_requests(tmp_path)
            if got:
                taken.extend(got)
                return
            time.sleep(0.02)

    t = threading.Thread(target=running_copy)
    t.start()
    assert si.hand_over(["exe", str(pdf)], tmp_path, timeout=5) == 0
    t.join(5)
    assert taken == [[str(pdf.resolve())]], "the file reached the running copy and no error was shown"


def test_hand_over_explains_when_the_running_copy_does_not_answer(tmp_path, monkeypatch):
    shown: list = []
    monkeypatch.setattr(si, "show_native_message", lambda text, *a, **k: shown.append(text))
    assert si.hand_over(["exe"], tmp_path, timeout=0.3) == 0
    assert shown and "already running" in shown[0]
    assert list(si.requests_folder(tmp_path).iterdir()) == [], "the unanswered request is removed"


def test_disabled_for_self_check_user_guide_and_tests(monkeypatch):
    monkeypatch.delenv("MONOGRAPH_PDF_HEADLESS", raising=False)
    monkeypatch.delenv("MONOGRAPH_PDF_MULTI_INSTANCE", raising=False)
    assert si.is_disabled(["exe", "--smoke-test"]) and si.is_disabled(["exe", "--user-guide"])
    assert not si.is_disabled(["exe", "C:/a.pdf"])
    monkeypatch.setenv("MONOGRAPH_PDF_HEADLESS", "1")
    assert si.is_disabled(["exe"])
