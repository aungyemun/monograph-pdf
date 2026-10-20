"""Bookmarks panel editing, Remove Hidden Information, Copy Page as Picture, print options and
password strength — driven through the real main window and dialogs."""

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
    create_application(["monograph-pdf-tools"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _pdf(path, pages=4, toc=None):
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 100), f"Chapter heading {i + 1}", fontsize=14)
    if toc:
        d.set_toc(toc)
    d.set_metadata({"author": "Someone"})
    d.save(path)
    d.close()
    return path


def _answer(monkeypatch, text):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (text, True)))


def _titles(win):
    from core.organize.bookmarks import list_bookmarks

    return [b.title for b in list_bookmarks(win._document)]  # noqa: SLF001


def test_add_rename_move_delete_bookmarks_with_undo_and_save(window, monkeypatch, tmp_path):
    path = _pdf(tmp_path / "a.pdf")
    assert window.open_path(path)
    rail = window._left  # noqa: SLF001
    assert rail.isTabVisible(rail._bookmarks_tab)  # noqa: SLF001 - shown even without bookmarks
    window._canvas.go_to_page(2)  # noqa: SLF001
    _answer(monkeypatch, "Third")
    window.act_add_bookmark.trigger()
    assert _titles(window) == ["Third"]
    assert window._edit.dirty  # noqa: SLF001
    assert rail._bookmarks.count() == 1 and rail.current_bookmark() == 0  # noqa: SLF001
    window._canvas.go_to_page(0)  # noqa: SLF001
    _answer(monkeypatch, "First")
    rail._bm_buttons["add"].click()  # noqa: SLF001 - added after the selected one
    assert _titles(window) == ["Third", "First"]
    rail._bm_buttons["up"].click()  # noqa: SLF001
    assert _titles(window) == ["First", "Third"]
    _answer(monkeypatch, "Opening")
    rail._bm_buttons["rename"].click()  # noqa: SLF001
    assert _titles(window) == ["Opening", "Third"]
    window.act_undo.trigger()
    assert _titles(window) == ["First", "Third"]
    window.act_redo.trigger()
    assert _titles(window) == ["Opening", "Third"]
    rail._bookmarks.setCurrentRow(1)  # noqa: SLF001
    rail._bm_buttons["delete"].click()  # noqa: SLF001
    assert _titles(window) == ["Opening"]
    window.save_document()
    saved = fitz.open(path)
    assert saved.get_toc() == [[1, "Opening", 1]]
    saved.close()


def test_bookmark_click_goes_to_its_page_and_retarget(window, tmp_path):
    assert window.open_path(_pdf(tmp_path / "b.pdf", toc=[[1, "Two", 2]]))
    rail = window._left  # noqa: SLF001
    item = rail._bookmarks.item(0)  # noqa: SLF001
    rail._bookmarks.setCurrentItem(item)  # noqa: SLF001
    rail._on_bookmark(item)  # noqa: SLF001
    assert window._canvas.focus_page == 1  # noqa: SLF001
    window._canvas.go_to_page(3)  # noqa: SLF001
    rail._bm_buttons["target"].click()  # noqa: SLF001
    from core.organize.bookmarks import list_bookmarks

    assert list_bookmarks(window._document)[0].page == 3  # noqa: SLF001


def test_remove_hidden_information_writes_a_clean_copy(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from ui import convert_dialogs
    from ui.security_dialogs import RemoveHiddenInfoDialog

    src = _pdf(tmp_path / "c.pdf", toc=[[1, "Keep", 1]])
    assert window.open_path(src)
    seen = {}

    def run(dlg):
        seen["checks"] = {k: (cb.isEnabled(), cb.isChecked()) for k, cb in dlg._checks.items()}  # noqa: SLF001
        return dlg.DialogCode.Accepted

    monkeypatch.setattr(RemoveHiddenInfoDialog, "exec", run)
    out = tmp_path / "clean.pdf"
    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: out)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a[2])))
    window.act_remove_hidden.trigger()
    assert seen["checks"]["metadata"] == (True, True)
    assert seen["checks"]["bookmarks"] == (True, False)  # found but kept unless chosen
    assert seen["checks"]["attachments"] == (False, False)  # nothing to remove
    clean = fitz.open(out)
    assert not clean.metadata.get("author")
    assert clean.get_toc() == [[1, "Keep", 1]]
    clean.close()
    assert shown and "clean.pdf" in shown[0]
    assert fitz.open(src).metadata["author"] == "Someone"


def test_copy_page_as_picture(window, tmp_path):
    from PySide6.QtWidgets import QApplication

    assert window.open_path(_pdf(tmp_path / "d.pdf"))
    QApplication.clipboard().clear()
    window.act_copy_page_image.trigger()
    img = QApplication.clipboard().image()
    assert not img.isNull()
    assert abs(img.width() - round(595 * 150 / 72)) <= 2  # A4 page at 150 dpi


def test_print_dialog_odd_even_reverse_and_comments(qtbot, tmp_path):
    from core.document import open_document
    from ui.print_dialog import PrintDialog

    doc = open_document(_pdf(tmp_path / "e.pdf", pages=5))
    dlg = PrintDialog(doc, doc_name="e.pdf", current_page=0, selected_pages=[0])
    qtbot.addWidget(dlg)
    assert dlg.selected_pages() == [0, 1, 2, 3, 4]
    dlg.subset.setCurrentIndex(dlg.subset.findData("even"))
    assert dlg.selected_pages() == [1, 3]
    dlg.reverse.setChecked(True)
    assert dlg.selected_pages() == [3, 1]
    dlg.r_custom.setChecked(True)
    dlg.custom.setText("2")
    dlg.subset.setCurrentIndex(dlg.subset.findData("odd"))
    assert dlg.selected_pages() == [] and dlg._range_error.isHidden()  # noqa: SLF001 - valid range, empty subset
    dlg.comments.setCurrentIndex(1)
    assert dlg.settings().comments is False
    doc.close()


def test_password_strength_and_same_password_warning(qtbot):
    from ui.security_dialogs import PasswordProtectDialog

    dlg = PasswordProtectDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.user_strength.isHidden()
    dlg.user_pw.setText("password")
    assert dlg.user_strength.isVisible() and "Very weak" in dlg.user_strength.text()
    dlg.user_pw.setText("plum-ladder-ocean-91")
    assert "strong" in dlg.user_strength.text().lower()
    dlg.user_pw_confirm.setText("plum-ladder-ocean-91")
    dlg.owner_pw.setText("plum-ladder-ocean-91")
    assert dlg._error.isVisible() and "same" in dlg._error.text()  # noqa: SLF001
    dlg.owner_pw.setText("another-long-pass-77")
    assert dlg._error.isHidden()  # noqa: SLF001


def test_header_footer_dialog_bates(qtbot, tmp_path):
    from core.document import open_document
    from ui.page_marks_dialogs import HeaderFooterDialog

    doc = open_document(_pdf(tmp_path / "f.pdf"))
    dlg = HeaderFooterDialog(page_count=doc.page_count, source=doc)
    qtbot.addWidget(dlg)
    assert not dlg._bates_row.isEnabled()  # noqa: SLF001
    dlg.bates.setChecked(True)
    dlg.bates_prefix.setText("DOC-")
    dlg.bates_start.setValue(7)
    dlg.bates_digits.setValue(4)
    spec = dlg.spec()
    slot = str(dlg.bates_place.currentData())
    assert "{bates}" in getattr(spec, slot)
    assert spec.bates(0) == "DOC-0007"
    restored = HeaderFooterDialog(page_count=doc.page_count, source=doc)
    qtbot.addWidget(restored)
    restored._restore(dlg.values())  # noqa: SLF001
    assert restored.bates.isChecked() and restored.bates_prefix.text() == "DOC-"
    doc.close()
