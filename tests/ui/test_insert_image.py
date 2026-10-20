"""Insert Image in the real window: the picture keeps its proportions (regression found in the packaged exe)."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


def test_added_picture_is_not_stretched(qtbot, tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtWidgets import QFileDialog

    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-insert-image"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    pdf = tmp_path / "a.pdf"
    d = fitz.open()
    d.new_page(width=595, height=842)
    d.save(pdf.as_posix())
    d.close()
    pic = tmp_path / "wide.png"
    Image.new("RGB", (240, 120), (30, 90, 200)).save(pic)
    assert win.open_path(pdf)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(pic), "")))
    win._add_image()  # noqa: SLF001
    box = next(iter(win._edit.images.values()))  # noqa: SLF001
    assert box.rect.w / box.rect.h == pytest.approx(2.0, rel=0.01), (box.rect.w, box.rect.h)
    win.close_document(save_session=False)
    win.close()
