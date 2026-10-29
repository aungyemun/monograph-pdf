"""Save As / Save a Copy onto a PDF that is open in another tab, and file integrity when a save fails
(0.5.1 regression).

0.5.0: saving over a file open in another tab failed with an error naming an internal temporary file
("[WinError 5] Access is denied: '….part' -> 'B.pdf' — Pick a writable folder"), or, when the document
had no changes (byte-for-byte copy), silently overwrote the other tab's file and left it open twice.
A byte-for-byte copy that failed part-way truncated the existing destination. Every test compares
SHA-256 hashes of the files on disk before and after.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
fitz = pytest.importorskip("fitz")


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _pdf(path: Path, word: str) -> Path:
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), f"{word} original", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def _text(path: Path) -> str:
    with fitz.open(path) as d:
        return " ".join("".join(p.get_text() for p in d).split())


def _temp_files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(".part") or ".saving-" in p.name)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-save-as-conflicts"])
    win = MainWindow()
    # not qtbot.addWidget(): pytest-qt would close the window in its teardown hook, before this
    # fixture can clear the test's unsaved changes, and the close prompt would hit the patched dialogs
    win.resize(1200, 800)
    win.show()
    yield win
    win._is_headless_ui = lambda: True  # noqa: SLF001 — close without prompts, whatever a test patched
    for sess in list(win._sessions):  # noqa: SLF001
        sess.edit.dirty = False
    win.close_document(save_session=False)
    win.close()


@pytest.fixture
def dialogs(window, monkeypatch):
    """Answer message boxes by button text and record what they said."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    state = {"answer": "Cancel", "texts": [], "dest": None}

    def fake_exec(box):
        state["texts"].append(box.text() + "\n" + box.informativeText())
        state["buttons"] = [b.text() for b in box.buttons()]
        for b in box.buttons():
            if b.text().replace("&", "") == state["answer"]:
                box.clickedButton = lambda b=b: b
                return 0
        raise AssertionError(f"no button {state['answer']!r} in {state['buttons']}")

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: state["texts"].append(str(a[2])) or QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(state["dest"]), "PDF Files (*.pdf)")))
    monkeypatch.setattr(window, "_is_headless_ui", lambda: False)
    return state


def _edit(window, word: str) -> None:
    from core.editing.geometry import Rect

    window._edit.create_text_box(0, Rect(72, 300, 300, 40), text=word)  # noqa: SLF001


def _two_tabs(window, tmp_path, *, edit_a=True, edit_b=False):
    a, b = _pdf(tmp_path / "A.pdf", "alpha"), _pdf(tmp_path / "B 書類.pdf", "beta")
    assert window.open_path(a) and window.open_path(b)
    if edit_b:
        _edit(window, "UNSAVEDB")
    window._activate_session(0)  # noqa: SLF001
    if edit_a:
        _edit(window, "EDITA")
    return a, b, _sha(a), _sha(b)


def _tabs(window) -> list[str]:
    return [s.tab_title() for s in window._sessions]  # noqa: SLF001


# ------------------------------------------------------------------ open in another tab
def test_cancel_leaves_both_files_and_tabs_untouched(window, dialogs, tmp_path):
    a, b, ha, hb = _two_tabs(window, tmp_path)
    dialogs["dest"], dialogs["answer"] = b, "Cancel"
    window.save_as_dialog()
    assert "is open in another tab" in dialogs["texts"][0]
    assert dialogs["buttons"][-1] in ("Cancel", "&Cancel")
    assert _sha(a) == ha and _sha(b) == hb
    assert _tabs(window) == ["A.pdf *", "B 書類.pdf"]
    assert not any("Access is denied" in t or ".part" in t for t in dialogs["texts"])
    assert _temp_files(tmp_path) == []


def test_close_it_and_replace_saves_over_the_closed_tab(window, dialogs, tmp_path):
    a, b, ha, _hb = _two_tabs(window, tmp_path)
    dialogs["dest"], dialogs["answer"] = b, "Close It and Replace"
    window.save_as_dialog()
    assert _sha(a) == ha
    assert "EDITA" in _text(b).replace(" ", "") and "alpha" in _text(b)
    assert _tabs(window) == ["B 書類.pdf"]  # one tab, now the saved file, clean
    assert Path(window._document.path).name == "B 書類.pdf"  # noqa: SLF001
    assert _temp_files(tmp_path) == []


def test_other_tab_with_unsaved_changes_names_the_loss_and_needs_the_explicit_button(window, dialogs, tmp_path):
    a, b, ha, hb = _two_tabs(window, tmp_path, edit_b=True)
    dialogs["dest"], dialogs["answer"] = b, "Cancel"
    window.save_as_dialog()
    assert "unsaved changes will be lost" in dialogs["texts"][0]
    assert "Discard Its Changes and Replace" in dialogs["buttons"]
    assert "Close It and Replace" not in dialogs["buttons"]
    assert _sha(b) == hb and [s.edit.dirty for s in window._sessions] == [True, True]  # noqa: SLF001
    dialogs["answer"] = "Discard Its Changes and Replace"
    window.save_as_dialog()
    t = _text(b).replace(" ", "")
    assert "EDITA" in t and "UNSAVEDB" not in t and _sha(a) == ha
    assert _tabs(window) == ["B 書類.pdf"]


def test_unchanged_document_no_longer_overwrites_the_open_tab_silently(window, dialogs, tmp_path):
    # 0.5.0: byte-for-byte copy over B while B was open; two tabs then showed "B"
    a, b, ha, hb = _two_tabs(window, tmp_path, edit_a=False)
    dialogs["dest"], dialogs["answer"] = b, "Cancel"
    window.save_as_dialog()
    assert _sha(b) == hb and len(_tabs(window)) == 2
    keys = [str(s.path_key()) for s in window._sessions]  # noqa: SLF001
    assert len(keys) == len(set(keys))


def test_save_a_copy_onto_an_open_tab_asks_and_keeps_working_on_the_document(window, dialogs, tmp_path):
    a, b, ha, hb = _two_tabs(window, tmp_path)
    dialogs["answer"] = "Cancel"
    assert window.save_copy_dialog(b) is None and _sha(b) == hb
    dialogs["answer"] = "Close It and Replace"
    assert window.save_copy_dialog(b) == b
    assert "EDITA" in _text(b).replace(" ", "") and _sha(a) == ha
    assert _tabs(window) == ["A.pdf *"]  # Save a Copy keeps working on A with its unsaved changes


def test_without_a_window_to_ask_in_the_save_is_refused(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    a, b, ha, hb = _two_tabs(window, tmp_path)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(b), "")))
    window.save_as_dialog()  # headless: no prompt possible -> refuse, never replace
    assert _sha(b) == hb and _tabs(window) == ["A.pdf *", "B 書類.pdf"]


def test_save_as_onto_its_own_path_is_a_plain_save(window, dialogs, tmp_path):
    a = _pdf(tmp_path / "A.pdf", "alpha")
    assert window.open_path(a)
    _edit(window, "EDITA")
    dialogs["dest"] = a
    window.save_as_dialog()
    assert dialogs["texts"] == [] and "EDITA" in _text(a).replace(" ", "")
    assert _tabs(window) == ["A.pdf"]


# ------------------------------------------------------------------ failed saves keep the files
def test_disk_full_during_save_as_keeps_existing_file_and_edits(window, dialogs, tmp_path, monkeypatch):
    a, x = _pdf(tmp_path / "A.pdf", "alpha"), _pdf(tmp_path / "X.pdf", "xray")
    ha, hx = _sha(a), _sha(x)
    assert window.open_path(a)
    _edit(window, "EDITA")
    real = fitz.Document.save

    def half_then_full(self, filename, *args, **kw):
        real(self, filename, *args, **kw)
        p = Path(filename)
        p.write_bytes(p.read_bytes()[: p.stat().st_size // 2])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fitz.Document, "save", half_then_full)
    for dest in (x, tmp_path / "new.pdf"):
        dialogs["dest"] = dest
        window.save_as_dialog()
    assert _sha(a) == ha and _sha(x) == hx and not (tmp_path / "new.pdf").exists()
    assert window._edit.dirty and _temp_files(tmp_path) == []  # noqa: SLF001
    assert any("not enough free space" in t for t in dialogs["texts"])


def test_failed_byte_for_byte_copy_no_longer_truncates_the_destination(window, dialogs, tmp_path, monkeypatch):
    a, x = _pdf(tmp_path / "A.pdf", "alpha"), _pdf(tmp_path / "X.pdf", "xray")
    ha, hx = _sha(a), _sha(x)
    assert window.open_path(a)  # unchanged: Save As copies the file byte for byte

    def partial_copy(src, dst, *args, **kw):
        Path(dst).write_bytes(Path(src).read_bytes()[:100])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(shutil, "copyfile", partial_copy)
    for dest in (x, tmp_path / "new.pdf"):
        dialogs["dest"] = dest
        window.save_as_dialog()
    assert _sha(a) == ha and _sha(x) == hx and "xray" in _text(x)
    assert not (tmp_path / "new.pdf").exists() and _temp_files(tmp_path) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows read-only attribute semantics")
def test_read_only_destination_is_named_and_kept(window, dialogs, tmp_path):
    a, x = _pdf(tmp_path / "A.pdf", "alpha"), _pdf(tmp_path / "X.pdf", "xray")
    hx = _sha(x)
    os.chmod(x, stat.S_IREAD)
    try:
        assert window.open_path(a)
        _edit(window, "EDITA")
        dialogs["dest"] = x
        window.save_as_dialog()
    finally:
        os.chmod(x, stat.S_IREAD | stat.S_IWRITE)
    assert _sha(x) == hx and window._edit.dirty  # noqa: SLF001
    assert any("read-only" in t for t in dialogs["texts"]) and _temp_files(tmp_path) == []


def test_unicode_names_and_a_protected_pdf_round_trip(window, dialogs, tmp_path, monkeypatch):
    import ui.main_window as mw

    src = tmp_path / "資料 é ①.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 100), "secret original", fontsize=14)
    d.save(src, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw1", owner_pw="pw1-owner",
           permissions=int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE))
    d.close()
    hs = _sha(src)

    class _Pw:
        class DialogCode:
            Accepted = 1

        def __init__(self, *a, **k): ...
        def exec(self): return 1
        def password(self): return "pw1"
        def set_incorrect(self): ...

    monkeypatch.setattr(mw, "PasswordDialog", _Pw)
    assert window.open_path(src)
    _edit(window, "EDITP")
    dest = tmp_path / "保存先 ü 한글.pdf"
    dialogs["dest"] = dest
    window.save_as_dialog()
    assert _sha(src) == hs
    with fitz.open(dest) as out:
        assert out.needs_pass and out.authenticate("pw1")
        assert "EDITP" in "".join(out[0].get_text().split())
    assert Path(window._document.path).name == dest.name  # noqa: SLF001
