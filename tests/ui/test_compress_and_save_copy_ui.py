"""Compress dialog (slider and numeric entry in step, exact byte targets, estimate vs measured), compress
of a document with unsaved edits, replacing the open file only after confirmation, Save a Copy, the
unsaved-changes decision before conversions, and the PDF to PowerPoint size options."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
fitz = pytest.importorskip("fitz")

from tests.unit.test_compress import _image_pdf  # noqa: E402

MARK = "CompressMark2026"


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-compress"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(window, tmp_path) -> Path:
    src = tmp_path / "photos 写真.pdf"
    src.write_bytes(_image_pdf(2))
    assert window.open_path(src)
    return src


def _edit(window):
    from core.editing.geometry import Rect

    window._edit.create_text_box(0, Rect(72, 420, 300, 30), text=MARK, auto_match=False)  # noqa: SLF001
    assert window._edit.dirty  # noqa: SLF001


def test_slider_and_numeric_target_stay_in_step(qtbot):
    from core.convert import compress as cz
    from ui.compress_dialog import CompressDialog

    dlg = CompressDialog(_image_pdf(2))
    qtbot.addWidget(dlg)
    dlg.profile_combo.setCurrentIndex(5)  # custom maximum size
    assert dlg.mode() == "target" and dlg.size_spin.isEnabled() and dlg.slider.isEnabled()
    dlg.unit.setCurrentText("KB")
    dlg.size_spin.setValue(956)
    assert dlg.target_bytes() == 956_000
    pos = dlg.slider.value()
    assert abs(dlg._slider_to_bytes(pos) - 956_000) / 956_000 < 0.02  # noqa: SLF001
    dlg.unit.setCurrentText("MB")  # same byte value, shown in MB (rounded down, never up)
    assert dlg.size_spin.value() == pytest.approx(0.95) and dlg.target_bytes() == 950_000
    dlg.size_spin.setValue(1.99)
    assert dlg.target_bytes() == 1_990_000
    dlg.slider.setValue(dlg.slider.value() - 100)
    assert dlg.target_bytes() < 1_990_000 and dlg.mode() == "target"
    assert "Target" in dlg.estimate_label.text() and "Preview measures" in dlg.estimate_label.text()
    # profiles set mode and size
    dlg.profile_combo.setCurrentIndex(4)
    assert dlg.target_bytes() == 2 * cz.MB
    dlg.profile_combo.setCurrentIndex(0)
    assert dlg.mode() == "lossless" and not dlg.size_spin.isEnabled()


def test_preview_measures_and_compress_returns_result(qtbot):
    from ui.compress_dialog import CompressDialog

    data = _image_pdf(2)
    dlg = CompressDialog(data)
    qtbot.addWidget(dlg)
    dlg.profile_combo.setCurrentIndex(5)
    dlg.unit.setCurrentText("KB")
    dlg.size_spin.setValue(500)
    dlg.preview_btn.click()
    assert dlg.result_ is not None and dlg.result_.target_met and dlg.result_.output_bytes <= 500_000
    assert "achieved" in dlg.result_label.text() and "bytes" in dlg.result_label.text()
    assert dlg.new_view.pixmap() is not None and not dlg.new_view.pixmap().isNull()
    dlg.ok_btn.click()
    assert dlg.result() == dlg.DialogCode.Accepted


def test_compress_includes_unsaved_edits_and_never_touches_the_source(window, tmp_path, monkeypatch):
    from core.convert import compress as cz
    from ui import compress_dialog

    src = _open(window, tmp_path)
    before = src.read_bytes()
    _edit(window)

    def fake_exec(dlg):
        dlg.mode_buttons["balanced"].setChecked(True)
        dlg._on_ok()  # noqa: SLF001
        return dlg.result()

    monkeypatch.setattr(compress_dialog.CompressDialog, "exec", fake_exec)
    dest = tmp_path / "out" / "photos 写真-compressed.pdf"
    dest.parent.mkdir()
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    window._optimize_pdf()  # noqa: SLF001
    assert dest.exists() and dest.stat().st_size < len(before) / 3
    with fitz.open(dest) as d:
        assert MARK in "".join(d[0].get_text().split())
    assert src.read_bytes() == before and window._edit.dirty  # noqa: SLF001
    assert cz.format_size(dest.stat().st_size) in window.statusBar().currentMessage()


def test_replacing_the_open_file_needs_confirmation(window, tmp_path):
    from core.convert import compress as cz

    src = _open(window, tmp_path)
    before = src.read_bytes()
    res = cz.compress(before, mode="smallest")
    assert window.write_compressed(res, src, confirm_replace=lambda: False) is None
    assert src.read_bytes() == before
    assert window.write_compressed(res, src, confirm_replace=lambda: True) == src
    assert src.stat().st_size == res.output_bytes
    assert window._document is not None and window._document.page_count == 2  # noqa: SLF001


def test_save_a_copy_keeps_working_on_the_open_document(window, tmp_path):
    src = _open(window, tmp_path)
    before = src.read_bytes()
    _edit(window)
    out = window.save_copy_dialog(tmp_path / "copy.pdf")
    assert out is not None and out.exists()
    with fitz.open(out) as d:
        assert MARK in "".join(d[0].get_text().split())
    assert src.read_bytes() == before
    assert window._edit.dirty and window._document.path == src  # noqa: SLF001
    assert window.save_copy_dialog(src) is None  # the open file itself is refused (Save replaces it)
    assert window._edit.undo()  # noqa: SLF001 — history kept
    out2 = window.save_copy_dialog(tmp_path / "copy2.pdf")
    with fitz.open(out2) as d:
        assert MARK not in "".join(d[0].get_text().split())


def test_unsaved_changes_decision_before_conversion(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    src = _open(window, tmp_path)
    _edit(window)
    monkeypatch.setattr(window, "_is_headless_ui", lambda: False)
    seen = {}

    def fake_exec(box):
        seen["text"] = box.text()
        seen["buttons"] = [b.text() for b in box.buttons()]
        box.clickedButton = lambda: [b for b in box.buttons() if "Cancel" in b.text()][0]
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert window._confirm_unsaved_for_export("PDF to Word") is False  # noqa: SLF001
    assert "unsaved changes" in seen["text"] and {"Save", "Save As…"} <= set(seen["buttons"])
    assert window._edit.dirty and MARK not in fitz.open(src)[0].get_text()  # noqa: SLF001 — nothing lost/written

    def choose_save(box):
        box.clickedButton = lambda: [b for b in box.buttons() if b.text() == "Save"][0]
        return 0

    monkeypatch.setattr(QMessageBox, "exec", choose_save)
    assert window._confirm_unsaved_for_export("PDF to Word") is True  # noqa: SLF001
    assert not window._edit.dirty  # noqa: SLF001
    with fitz.open(src) as d:
        assert MARK in "".join(d[0].get_text().split())


def test_powerpoint_dialog_offers_size_policies_for_mixed_pages(qtbot):
    from ui.convert_dialogs import PdfToPowerPointDialog

    single = PdfToPowerPointDialog(page_groups=[("A4 portrait", [0, 1])])
    qtbot.addWidget(single)
    assert [single.size_policy.itemData(i) for i in range(single.size_policy.count())] == ["true_size", "custom"]
    mixed = PdfToPowerPointDialog(page_groups=[("A4 portrait", [0]), ("A3 landscape", [1])])
    qtbot.addWidget(mixed)
    keys = [mixed.size_policy.itemData(i) for i in range(mixed.size_policy.count())]
    assert keys == ["true_size", "fit", "first_page", "custom", "split"]
    assert not mixed.custom_size.isEnabled()
    mixed.size_policy.setCurrentIndex(keys.index("custom"))
    mixed.custom_size.setCurrentText("Widescreen 16:9")
    assert mixed.custom_size.isEnabled()
    assert mixed.options() == {"mode": "layout", "dpi": 200, "size_policy": "custom", "custom_size_pt": (960.0, 540.0)}
    mixed.size_policy.setCurrentIndex(keys.index("split"))
    assert "size_policy" not in mixed.options() and mixed.policy() == "split"


def test_save_a_copy_menu_action_opens_the_file_dialog(window, tmp_path, monkeypatch):
    """Regression (live GUI test): QAction.triggered passes checked=False, which reached save_copy_dialog
    as the destination and raised TypeError."""
    from PySide6.QtWidgets import QFileDialog

    src = _open(window, tmp_path)
    _edit(window)
    dest = tmp_path / "menu copy.pdf"
    seen = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (seen.append(1), (str(dest), ""))[1]))
    window.act_save_copy.trigger()
    assert seen and dest.exists() and window._document.path == src  # noqa: SLF001
