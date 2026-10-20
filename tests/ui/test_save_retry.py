"""Saving over the open file while another program briefly holds it: the save waits and succeeds; a lock that
does not go away produces the explanatory error, never data loss, and the lock is never bypassed."""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytestmark = pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows file-sharing semantics")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-save-retry"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(type(win), "report_error", lambda self, title, msg, **k: errors.append((title, msg)))
    win._test_errors = errors  # noqa: SLF001
    from PySide6.QtWidgets import QMessageBox

    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(str(a[2]))))
    win._test_dialogs = shown  # noqa: SLF001
    yield win
    win.close_document(save_session=False)
    win.close()


def _open_copy(window, tmp_path: Path) -> Path:
    doc = tmp_path / "doc.pdf"
    doc.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    assert window.open_path(doc)
    return doc


def _edit(window, text: str) -> None:
    from core.editing.geometry import Rect

    window._edit.create_text_box(0, Rect(50, 300, 200, 20), text=text, auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001


def test_a_short_lock_is_waited_out(window, tmp_path):
    import fitz

    doc = _open_copy(window, tmp_path)
    _edit(window, "retry me")
    held = threading.Event()

    def hold():
        with open(doc, "rb") as f:
            f.read(10)
            held.set()
            time.sleep(0.8)  # another program (scanner / preview) has the file open for a moment

    t = threading.Thread(target=hold)
    t.start()
    held.wait(2)
    window.save_document()
    t.join()
    assert window._test_errors == []  # noqa: SLF001
    assert window._test_dialogs == [], window._test_dialogs  # noqa: SLF001
    assert "retry me" in fitz.open(doc.as_posix())[0].get_text()
    assert not list(tmp_path.glob(".*saving*")), "temporary file left behind"


def test_a_lock_that_stays_gives_the_explanation_and_keeps_everything(window, tmp_path):
    doc = _open_copy(window, tmp_path)
    before = hashlib.sha256(doc.read_bytes()).hexdigest()
    _edit(window, "must not be lost")
    done = threading.Event()
    held = threading.Event()

    def hold():
        with open(doc, "rb") as f:
            f.read(10)
            held.set()
            done.wait(30)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(2)
    try:
        window.save_document()
    finally:
        done.set()
        t.join()
    errors = window._test_errors  # noqa: SLF001
    assert errors and "open in another program" in errors[0][1]
    assert hashlib.sha256(doc.read_bytes()).hexdigest() == before, "the original file changed although the save failed"
    assert not list(tmp_path.glob(".*saving*")), "temporary file left behind"
    # the edits are still in the window; once the lock is gone the same Save works
    assert window._document is not None  # noqa: SLF001
    window.save_document()
    import fitz

    assert "must not be lost" in fitz.open(doc.as_posix())[0].get_text()
