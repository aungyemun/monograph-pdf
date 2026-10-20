"""Protect ▸ redaction in the real window: whole-page marks and the "found elsewhere" prompt."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")

SECRET = "ZEBRA-4711"


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-redaction"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _doc(path):
    d = fitz.open()
    for i in range(3):
        p = d.new_page()
        p.insert_text((72, 100), f"Page {i + 1} account {SECRET}", fontsize=12)
    d.set_toc([[1, f"About {SECRET}", 1]])
    d.set_metadata({"title": f"File {SECRET}"})
    d.save(path)
    d.close()
    return path


def test_mark_whole_pages_from_the_menu(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QInputDialog

    from core.redaction import preview_redaction_count

    assert window.open_path(_doc(tmp_path / "a.pdf"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("1, 3", True)))
    window.act_redact_pages.trigger()
    assert preview_redaction_count(window._document) == 2  # noqa: SLF001


def test_residue_prompt_removes_text_elsewhere_when_accepted(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from ui import convert_dialogs

    assert window.open_path(_doc(tmp_path / "a.pdf"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (SECRET, True)))
    window.act_redact_text.trigger()
    out = tmp_path / "redacted.pdf"
    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: out)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    prompts = []

    def fake_exec(self):
        prompts.append(self.informativeText())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if b.text() == "Remove These Too"))
    window.act_redact_apply.trigger()
    assert prompts and "bookmark" in prompts[0] and "title" in prompts[0]
    with fitz.open(out) as d:
        assert all(SECRET not in p.get_text() for p in d)
        assert d.get_toc()[0][1] == "About [redacted]"
        assert d.metadata["title"] == "File [redacted]"
    assert SECRET.encode() not in out.read_bytes()
