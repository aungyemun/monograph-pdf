"""Apply Redaction honours a PDF's "no changes" permission (Phase 1 audit, P0 §7).

Every command that writes changed content checks the "edit" permission (or asks for the permissions
password); Apply Redaction did not, and wrote a changed copy of a PDF whose author forbade changes.
"""

from __future__ import annotations

import os

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
    create_application(["monograph-pdf-redaction-permissions"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    yield win
    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def _restricted(path, *, allow_modify: bool):
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Confidential SECRET-ALPHA text")
    perms = fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY
    if allow_modify:
        perms |= fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE
    d.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-only", permissions=int(perms))
    d.close()
    return path


@pytest.mark.parametrize("allow_modify", [False, True])
def test_apply_redaction_needs_the_edit_permission(window, tmp_path, monkeypatch, allow_modify):
    from PySide6.QtWidgets import QMessageBox

    from core.redaction import mark_text
    from ui import convert_dialogs

    src = _restricted(tmp_path / "restricted.pdf", allow_modify=allow_modify)
    assert window.open_path(src)  # no open password: opens, restrictions apply
    mark_text(window._document, 0, "SECRET-ALPHA")  # noqa: SLF001
    dest = tmp_path / "redacted.pdf"
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: dest)
    window._redact_apply()  # noqa: SLF001
    if allow_modify:
        assert dest.exists(), "allowed: the redacted copy is written"
    else:
        assert not dest.exists(), "changes forbidden by the PDF: no changed copy without the permissions password"
