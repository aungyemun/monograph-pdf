"""The window honours a protected PDF's permissions and keeps signed files byte-identical when unchanged."""

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
    create_application(["monograph-pdf-protected"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1100, 760)
    w.show()
    yield w
    w.close_document(save_session=False)
    w.close()


def test_unchanged_save_as_is_a_byte_identical_copy(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    src = tmp_path / "s.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "signed content")
    d.save(src.as_posix())
    d.close()
    assert window.open_path(src)
    dest = tmp_path / "copy.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    window.save_as_dialog()
    assert dest.read_bytes() == src.read_bytes()
    copy2 = tmp_path / "copy2.pdf"
    assert window.save_copy_dialog(copy2) == copy2
    assert copy2.read_bytes() == src.read_bytes()


def test_restricted_pdf_conversion_needs_the_permissions_password(window, tmp_path, monkeypatch):
    import ui.security_dialogs as sd

    src = tmp_path / "p.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "protected")
    d.save(src.as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o",
           permissions=fitz.PDF_PERM_PRINT)
    d.close()
    from core.document import open_document

    window._load_document(open_document(src, password="u"))  # noqa: SLF001
    assert not window._allow("copy", "Converting to Word")  # noqa: SLF001 — headless: refused, no dialog
    assert window._allow("print", "Printing")  # noqa: SLF001
    # with a window: the permissions password dialog unlocks it
    monkeypatch.setattr(window, "_is_headless_ui", lambda: False)
    monkeypatch.setattr(sd.PermissionsPasswordDialog, "exec", lambda self: sd.QDialog.DialogCode.Accepted)
    monkeypatch.setattr(sd.PermissionsPasswordDialog, "password", lambda self: "o")
    assert window._allow("copy", "Converting to Word")  # noqa: SLF001
    assert window._allow("owner", "Changing the password protection")  # noqa: SLF001


def test_pdf_outputs_with_unsaved_changes_stay_protected(window, tmp_path):
    from core.convert.copy_pdf import copy_pdf_preserving_metadata
    from core.document import open_document
    from core.editing.geometry import Rect

    src = tmp_path / "p.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "protected")
    d.save(src.as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o",
           permissions=fitz.PDF_PERM_PRINT)
    d.close()
    window._load_document(open_document(src, password="o"))  # noqa: SLF001
    window._edit.create_text_box(0, Rect(72, 300, 260, 40), text="UNSAVEDMARK", auto_match=False)  # noqa: SLF001
    out = tmp_path / "copy.pdf"
    with window._current_document(keep_protection=True) as current:  # noqa: SLF001
        copy_pdf_preserving_metadata(current, out)
    with fitz.open(out.as_posix()) as d2:
        assert d2.needs_pass and d2.authenticate("u")
        assert "UNSAVEDMARK" in d2[0].get_text().replace(" ", "")
        assert not int(d2.permissions) & fitz.PDF_PERM_COPY
    # an export source is still readable without the password (conversions read it)
    with window._current_document() as current:  # noqa: SLF001
        assert "UNSAVEDMARK" in current.page_text(0).replace(" ", "")
