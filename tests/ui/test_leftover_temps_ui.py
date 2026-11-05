"""The window lists temporary files of an interrupted save when a document is opened, and never
deletes them by itself (0.6.0, F-13)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from core.leftover_temps import MIN_AGE_SECONDS  # noqa: E402


def _file(p: Path, data: bytes = b"partial", age: float = MIN_AGE_SECONDS + 60) -> Path:
    p.write_bytes(data)
    t = time.time() - age
    os.utime(p, (t, t))
    return p


def test_window_reports_leftovers_without_deleting(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-leftovers"])
    win = MainWindow()
    qtbot.addWidget(win)
    msgs: list[str] = []
    win.statusBar().messageChanged.connect(msgs.append)
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page()
    d.save(src)
    d.close()
    part = _file(tmp_path / ".doc.0a1b2c3d.part")
    assert win.open_path(src)
    qtbot.waitUntil(lambda: any("interrupted save" in m for m in msgs), timeout=3000)
    assert part.exists()
    # reported once per session
    msgs.clear()
    assert win._report_leftover_temporaries(src) == []  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()
