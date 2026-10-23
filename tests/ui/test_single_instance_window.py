"""The running window acts on a second start: opens the handed-over PDF (never inside an open
dialog), or comes to the front and says Monograph PDF is already running."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-single-instance"])
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    yield w
    w.close_document(save_session=False)
    w.close()


def _pdf(path):
    d = fitz.open()
    d.new_page().insert_text((72, 72), path.stem)
    d.save(path)
    d.close()
    return path


def test_request_from_a_second_start_opens_the_file(win, qtbot, tmp_path):
    from app.single_instance import InstanceServer, send_request

    pdf = _pdf(tmp_path / "handed_over.pdf")
    folder = tmp_path / "instance"
    server = InstanceServer(win, folder)
    win.showMinimized()
    send_request([str(pdf)], folder)
    server.process()
    qtbot.waitUntil(lambda: win._document is not None, timeout=5000)  # noqa: SLF001
    assert win._document.path.name == "handed_over.pdf"  # noqa: SLF001
    assert not win.isMinimized(), "the window comes to the front"


def test_empty_request_says_already_running(win, qtbot, tmp_path):
    from app.single_instance import InstanceServer, send_request

    folder = tmp_path / "instance"
    server = InstanceServer(win, folder)
    send_request([], folder)
    server.process()
    box = win._running_box  # noqa: SLF001
    assert box.isVisible() and "already running" in box.text()
    server.process()  # a second request does not stack another box
    box.close()


def test_file_waits_while_a_dialog_is_open(win, qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog

    pdf = _pdf(tmp_path / "later.pdf")
    dialog = QDialog(win)
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: dialog))
    win.handle_instance_request([str(pdf)])
    qtbot.wait(100)
    assert win._document is None, "nothing opens inside a dialog that is waiting for an answer"  # noqa: SLF001
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: None))
    qtbot.waitUntil(lambda: win._document is not None, timeout=3000)  # noqa: SLF001
