"""Stamps can be changed after placing them: type (theme), wording, font, colours, frame, corners,
line thickness, opacity and rotation — by double-clicking the stamp. Undo restores the old look."""

from __future__ import annotations

import json
import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


def test_old_stamps_without_look_keys_keep_their_look():
    from core.annotations.stamps import StampSpec

    old = json.dumps({"text": "APPROVED", "color": "#15803d", "subtitle": "", "opacity": 1.0,
                      "rotation": 0.0, "image_path": "", "extra": {}})
    spec = StampSpec.from_json(old)
    assert (spec.frame, spec.corners, spec.font, spec.bold, spec.line_scale) == ("double", "rounded", "Helvetica", True, 1.0)
    assert spec.text_color == spec.border_color == spec.fill_color == ""


def test_style_dialog_switches_theme_and_reports_the_look(qtbot):
    from core.annotations.stamps import PRESETS, StampSpec
    from ui.stamp_dialog import StampStyleDialog

    dlg = StampStyleDialog(None, StampSpec(text="DRAFT", color="#6b7280"))
    qtbot.addWidget(dlg)
    rejected = next(p for p in PRESETS if p.label == "REJECTED")
    dlg.theme.setCurrentIndex(dlg.theme.findData(rejected))
    dlg.frame.setCurrentIndex(dlg.frame.findData("single"))
    dlg.corners.setCurrentIndex(dlg.corners.findData("pill"))
    dlg.font.setCurrentIndex(dlg.font.findData("Times"))
    dlg.thickness.setCurrentIndex(3)
    dlg.fill_color.set_value("#fffbe6")
    spec = dlg.spec()
    assert (spec.text, spec.color) == ("REJECTED", rejected.color)
    assert (spec.frame, spec.corners, spec.font, spec.fill_color) == ("single", "pill", "Times", "#fffbe6")
    assert spec.line_scale > 2
    assert not dlg.preview.pixmap().isNull()


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-stamp-edit"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def test_double_click_edit_changes_the_placed_stamp_and_undo_restores_it(win, monkeypatch):
    from core.annotations.stamps import StampSpec, add_custom_stamp, stamp_spec
    import ui.stamp_dialog as sd

    w = win
    holder = {}

    def create():
        holder["xref"] = add_custom_stamp(w._document, 0, fitz.Rect(100, 100, 260, 150),  # noqa: SLF001
                                          StampSpec(text="APPROVED", color="#15803d"))
        return holder["xref"]

    w._run_annot_command(0, create, "Add Stamp")  # noqa: SLF001
    xref = next(int(a.xref) for a in w._document._backend._doc[0].annots())  # noqa: SLF001

    def fake_exec(dlg):
        dlg.text.setText("CHECKED")
        dlg.frame.setCurrentIndex(dlg.frame.findData("none"))
        dlg.font.setCurrentIndex(dlg.font.findData("Courier"))
        dlg.border_color.set_value("#b91c1c")
        return sd.StampStyleDialog.DialogCode.Accepted

    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1:3]))
    monkeypatch.setattr(sd.StampStyleDialog, "exec", fake_exec)
    w._is_headless_ui = lambda: False  # noqa: SLF001 — only for this action (closing must not ask to save)
    try:
        w._comment_edit_text(w._annot_ref(0, xref))  # noqa: SLF001 — what a double-click on the stamp does
    finally:
        del w._is_headless_ui
    assert warnings == []
    spec, _size = stamp_spec(w._document, xref)  # noqa: SLF001
    assert (spec.text, spec.frame, spec.font, spec.border_color) == ("CHECKED", "none", "Courier", "#b91c1c")
    assert "CHECKED" in w._document._backend._doc[0].annots().__next__().info["content"]  # noqa: SLF001
    w.act_undo.trigger()
    spec, _size = stamp_spec(w._document, xref)  # noqa: SLF001
    assert (spec.text, spec.frame, spec.font) == ("APPROVED", "double", "Helvetica")
