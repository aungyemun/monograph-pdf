"""Save (over the open file) when the disk is full: a plain explanation, the file and the edits kept.

Phase 1 audit (error injection): Save reported Python's own text, naming an internal temporary file
("OSError: [Errno 28] No space left on device: '…/.doc.saving-1a2b3c4d.pdf'"), while Save As and Save
a Copy already said "There is not enough free space on the drive to save …".
"""

from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-disk-full"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(type(win), "report_error", lambda self, title, msg, **k: errors.append((title, str(msg) + " " + k.get("hint", ""))))
    monkeypatch.setattr(type(win), "report_unexpected", lambda self, title, exc, *a, **k: errors.append((title, f"{type(exc).__name__}: {exc}")))
    win._test_errors = errors  # noqa: SLF001
    yield win
    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def test_save_on_a_full_disk_explains_and_keeps_everything(window, tmp_path, monkeypatch):
    from core.editing.geometry import Rect

    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "original")
    d.save(src)
    d.close()
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    assert window.open_path(src)
    window._edit.create_text_box(0, Rect(72, 300, 200, 20), text="unsaved edit", auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    real = fitz.Document.save

    def full(self, filename, *a, **k):
        if not isinstance(filename, (str, os.PathLike)):
            return real(self, filename, *a, **k)
        Path(os.fspath(filename)).write_bytes(b"%PDF partial")
        raise OSError(errno.ENOSPC, "No space left on device", os.fspath(filename))

    monkeypatch.setattr(fitz.Document, "save", full)
    window.save_document()
    monkeypatch.setattr(fitz.Document, "save", real)
    errors = window._test_errors  # noqa: SLF001
    assert errors, "the failure is reported"
    title, text = errors[0]
    assert "not enough free space" in text, text
    assert ".saving-" not in text and "Errno" not in text, f"internal details shown: {text}"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before, "the file changed"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")], "temporary file left behind"
    assert window._edit.dirty and window._document is not None  # noqa: SLF001
    window.save_document()  # space again: the same Save works
    assert "unsaved edit" in fitz.open(src)[0].get_text()
    assert window._document is not None and window._edit is not None, "the saved document stays open"  # noqa: SLF001
    assert not window._edit.dirty  # noqa: SLF001
