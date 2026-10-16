"""Security regressions through the main window: passwords never persisted, protection kept by
Save As, no recovery copy for protected PDFs, and no network use during typical work."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
fitz = pytest.importorskip("fitz")

PASSWORD = "Sup3r-Secret-Pa55"
MARK = "SecurityMark2026"


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-security"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _protected_pdf(path: Path) -> Path:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Confidential page")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=PASSWORD, owner_pw=PASSWORD + "-owner",
             permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY)
    doc.close()
    return path


def _add_text(window):
    from core.editing.geometry import Rect

    window._edit.create_text_box(0, Rect(72, 300, 260, 40), text=MARK, auto_match=False)  # noqa: SLF001


def _all_files(*roots: Path):
    for root in roots:
        if root.exists():
            yield from (p for p in root.rglob("*") if p.is_file())


def test_password_and_protected_content_never_written_to_disk(window, tmp_path):
    from app.paths import RUNTIME_DIR
    from core.editing.session_store import session_path_for

    src = _protected_pdf(tmp_path / "protected.pdf")
    assert window.open_path(src, password=PASSWORD)
    _add_text(window)
    window._autosave_session()  # noqa: SLF001 - the timer would do this
    window.close_document(save_session=True)
    assert not session_path_for(src).exists(), "a recovery copy of a protected PDF was written"
    leaks = [p for p in _all_files(RUNTIME_DIR, tmp_path / "appdata")
             if PASSWORD.encode() in p.read_bytes() or MARK.encode() in p.read_bytes()]
    assert not leaks, leaks
    recent = (tmp_path / "appdata" / "recent_files.json")
    assert recent.exists() and PASSWORD not in recent.read_text(encoding="utf-8")


def test_unprotected_documents_still_get_a_recovery_copy(window, tmp_path):
    from core.editing.session_store import clear_session, session_path_for

    src = tmp_path / "plain.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Plain page")
    doc.save(src)
    doc.close()
    assert window.open_path(src)
    _add_text(window)
    window._autosave_session()  # noqa: SLF001
    try:
        assert session_path_for(src).exists()
    finally:
        clear_session(src)


def test_save_as_keeps_password_protection(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    src = _protected_pdf(tmp_path / "protected.pdf")
    dest = tmp_path / "copy.pdf"
    assert window.open_path(src, password=PASSWORD)
    _add_text(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    window.save_as_dialog()
    assert window._document is not None and Path(window._document.path) == dest  # noqa: SLF001
    with fitz.open(dest) as out:
        assert out.needs_pass, "Save As removed the password"
        assert out.authenticate(PASSWORD)
        assert MARK in "".join(out[0].get_text().split())
        assert not out.permissions & fitz.PDF_PERM_MODIFY  # permissions kept


def test_no_network_use_during_typical_work(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from app.offline_guard import NetworkAttempts

    src = tmp_path / "work.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Offline check page")
    doc.save(src)
    doc.close()
    with NetworkAttempts() as guard:
        assert window.open_path(src)
        _add_text(window)
        for method, name in (("_pdf_to_text", "out.txt"), ("_export_flattened", "flat.pdf")):
            target = tmp_path / name
            monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, t=target, **k: (str(t), "")))
            getattr(window, method)()
            assert target.exists(), method
        from core.convert.pdf_to_docx import layout_engine_available, pdf_to_docx

        if layout_engine_available():
            pdf_to_docx(window._document, tmp_path / "out.docx", engine="layout")  # noqa: SLF001
        window.save_document()
    assert guard.attempts == []
