"""Insert ▸ Page design in the real window: header/footer, watermark, background, removal.

The modal dialogs are driven by replacing ``exec`` with a function that fills the real dialog
and accepts it; the save dialog returns a fixed path. Outputs are read back with PyMuPDF.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-page-marks"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


@pytest.fixture
def doc_window(window, tmp_path):
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    for rot in (0, 90, 0):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 300), "BODY", fontsize=14)
        p.set_rotation(rot)
    d.save(src.as_posix())
    d.close()
    assert window.open_path(src)
    return window


def _drive(monkeypatch, cls, fill, dest: Path):
    """Make ``cls.exec`` fill the dialog and accept; make the save dialog return ``dest``."""
    from ui import convert_dialogs

    seen = {}

    def fake_exec(self):
        fill(self)
        self.preview.render_now()
        seen["dialog"] = self
        seen["preview_error"] = self.preview.error
        seen["preview_null"] = self.preview.pixmap() is None or self.preview.pixmap().isNull()
        self.accept()
        return self.DialogCode.Accepted

    monkeypatch.setattr(cls, "exec", fake_exec)
    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: dest)
    return seen


def test_header_footer_from_the_menu_writes_six_slots_and_numbers(doc_window, monkeypatch, tmp_path):
    from ui.page_marks_dialogs import HeaderFooterDialog

    out = tmp_path / "hf.pdf"

    def fill(d):
        d.slots["header_left"].setText("HL")
        d.slots["header_center"].setText("Report 報告")
        d.slots["header_right"].setText("{date}")
        d.slots["footer_left"].setText("Internal")
        d.page_numbers.setChecked(True)
        d.number_format.setCurrentIndex(1)  # Page 1 of 12
        d.number_place.setCurrentIndex(1)  # bottom center

    seen = _drive(monkeypatch, HeaderFooterDialog, fill, out)
    doc_window.act_header_footer.trigger()
    assert out.exists()
    assert seen["preview_error"] == "" and not seen["preview_null"]
    with fitz.open(out) as d:
        texts = [p.get_text() for p in d]
    for i, t in enumerate(texts):
        assert "HL" in t and "Report 報告" in t and "Internal" in t and f"Page {i + 1} of 3" in t
    # the open document is unchanged
    assert doc_window._document.page_count == 3  # noqa: SLF001
    with fitz.open(doc_window._document.path) as d:  # noqa: SLF001
        assert "HL" not in d[0].get_text()


def test_settings_are_remembered_for_next_time(doc_window, monkeypatch, tmp_path):
    from ui.page_marks_dialogs import HeaderFooterDialog

    _drive(monkeypatch, HeaderFooterDialog, lambda d: d.slots["footer_right"].setText("Kept {page}"),
           tmp_path / "a.pdf")
    doc_window.act_header_footer.trigger()
    again = HeaderFooterDialog(doc_window, page_count=3, current_page=0, source=None)
    assert again.slots["footer_right"].text() == "Kept {page}"


def test_watermark_picture_behind_content(doc_window, monkeypatch, tmp_path):
    from PIL import Image

    from ui.page_marks_dialogs import WatermarkDialog

    pic = tmp_path / "logo.png"
    Image.new("RGBA", (300, 150), (0, 0, 200, 255)).save(pic)
    out = tmp_path / "wm.pdf"

    def fill(d):
        d.use_image.setChecked(True)
        d.image_path.setText(str(pic))
        d.layer.setCurrentIndex(1)  # behind
        d.rotation.setCurrentIndex(1)  # horizontal
        d.opacity.setValue(60)

    seen = _drive(monkeypatch, WatermarkDialog, fill, out)
    doc_window.act_watermark.trigger()
    assert out.exists() and seen["preview_error"] == ""
    from core.convert.page_marks import KIND_WATERMARK, count_marks

    with fitz.open(out) as d:
        assert count_marks(d)[KIND_WATERMARK] == 3
        assert all(len(p.get_images()) >= 1 or p.get_xobjects() for p in d)


def test_unreadable_picture_disables_save(doc_window, tmp_path):
    from ui.page_marks_dialogs import WatermarkDialog

    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a picture")
    with doc_window._current_document() as src:  # noqa: SLF001
        d = WatermarkDialog(doc_window, page_count=3, current_page=0, source=src)
        d.use_image.setChecked(True)
        d.image_path.setText(str(bad))
        d.preview.render_now()
        d.refresh()
        assert d.preview.error
        assert not d.buttons.button(d.buttons.StandardButton.Ok).isEnabled()


def test_background_then_remove_from_the_menu(doc_window, monkeypatch, tmp_path):
    from ui.page_marks_dialogs import BackgroundDialog, RemoveMarksDialog

    bg = tmp_path / "bg.pdf"
    _drive(monkeypatch, BackgroundDialog, lambda d: d.color.set_name("#ffeeaa"), bg)
    doc_window.act_background.trigger()
    assert bg.exists()
    with fitz.open(bg) as d:
        px = d[0].get_pixmap(dpi=20, alpha=False).pixel(2, 2)
        assert px == (255, 238, 170)

    # open the marked file and remove the background again
    assert doc_window.open_path(bg)
    plain = tmp_path / "plain.pdf"
    seen = {}

    def fake_exec(self):
        seen["counts"] = dict(self.counts)
        self.accept()
        return self.DialogCode.Accepted

    monkeypatch.setattr(RemoveMarksDialog, "exec", fake_exec)
    from ui import convert_dialogs

    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: plain)
    doc_window.act_remove_page_design.trigger()
    assert seen["counts"]["Background"] == 3
    with fitz.open(plain) as d:
        assert d[0].get_pixmap(dpi=20, alpha=False).pixel(2, 2) == (255, 255, 255)
        assert "BODY" in d[0].get_text()


def test_remove_without_marks_explains_and_writes_nothing(doc_window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
    doc_window.act_remove_page_design.trigger()
    assert shown and "No header" in shown[0]


def test_new_actions_are_in_the_insert_menu_and_disabled_without_a_document(window):
    labels = []
    for m in window.menuBar().actions():
        if m.text().replace("&", "") == "Insert":
            labels = [a.text().replace("&", "") for a in m.menu().actions()]
    assert "Background…" in labels
    assert any(lbl.startswith("Remove Header, Footer, Watermark or Background") for lbl in labels)
    assert not window.act_background.isEnabled()
    assert not window.act_remove_page_design.isEnabled()
