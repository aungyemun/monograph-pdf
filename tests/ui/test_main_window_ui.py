"""UI-level smoke for viewer main window."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


def test_menus_and_open_close(qtbot):
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-ui-test"])
    window = MainWindow()
    qtbot.addWidget(window)
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert "File" in menus
    assert "Edit" in menus
    assert "OCR" in menus
    assert "Convert" in menus  # Export commands now live in File ▸ Save a Copy and Convert
    assert "View" in menus
    assert "Help" in menus
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert "sample_text.pdf" in window.windowTitle()
    window.close_document()
    assert window.windowTitle().startswith("Monograph PDF")
    window.close()


def test_password_cancel_does_not_load(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow, create_application
    from ui import password_dialog

    create_application(["monograph-pdf-ui-test"])
    window = MainWindow()
    qtbot.addWidget(window)

    def _reject(self):
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(password_dialog.PasswordDialog, "exec", _reject)
    assert window.open_path(SAMPLES / "sample_password.pdf") is False
    assert window._document is None  # noqa: SLF001
    window.close()
