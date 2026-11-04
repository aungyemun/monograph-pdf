"""Save sequences after the Phase 1 fixes (Phase 1.1 verification).

Repeated Saves accumulate rotation, annotations and form values; Save As onto an existing file replaces
it completely; a searchable (OCR) PDF keeps its text layer through edit + Save; no temporary file is ever
left behind and the original is untouched until a Save succeeds.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

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
    create_application(["monograph-pdf-save-sequences"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    errors: list = []
    monkeypatch.setattr(type(win), "report_error", lambda self, t, m, **k: errors.append((t, str(m))))
    monkeypatch.setattr(type(win), "report_unexpected", lambda self, t, e, *a, **k: errors.append((t, str(e))))
    win._test_errors = errors  # noqa: SLF001
    yield win
    if win._edit is not None:  # noqa: SLF001
        win._edit.dirty = False  # noqa: SLF001
    win.close_document(save_session=False)
    win.close()


def _form(path: Path) -> Path:
    d = fitz.open()
    for _ in range(3):
        d.new_page(width=595, height=842)
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 90, 300, 112), ""
    d[0].add_widget(w)
    c = fitz.Widget()
    c.field_name, c.field_type, c.rect = "agree", fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.Rect(72, 130, 86, 144)
    d[0].add_widget(c)
    d[0].insert_text((72, 200), "Body text", fontsize=12)
    d.save(path)
    d.close()
    return path


def _leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith(".") or p.suffix == ".part")


def _field(win, name):
    return next(f for f in win._edit.fields.values() if f.name == name)  # noqa: SLF001


def test_repeated_saves_accumulate_every_kind_of_change(window, tmp_path):
    from core.editing.annot_commands import MarkupAnnotCommand
    from core.editing.geometry import Rect

    src = _form(tmp_path / "doc.pdf")
    assert window.open_path(src)
    # Save 1: a form value and a checkbox (edit model)
    window._edit.set_field_value(_field(window, "name").object_id, "first")  # noqa: SLF001
    window._edit.set_field_value(_field(window, "agree").object_id, checked=True)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    window.save_document()
    # Save 2: a highlight (stored in the document itself) and a rotated page
    window._edit.commands.execute(MarkupAnnotCommand(  # noqa: SLF001
        window._document, window._edit, 0, "highlight", [Rect(72, 190, 100, 14)], color=(1, 1, 0)))  # noqa: SLF001
    window._after_annotation(0, "Highlight")  # noqa: SLF001
    assert window._rotate_pages([1], 90)  # noqa: SLF001
    window.save_document()
    # Save 3: change the form value again and add a text box
    window._edit.set_field_value(_field(window, "name").object_id, "third")  # noqa: SLF001
    window._edit.create_text_box(2, Rect(72, 300, 200, 20), text="box on page 3", auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    window.save_document()
    assert window._test_errors == []  # noqa: SLF001
    assert not window._edit.dirty  # noqa: SLF001
    with fitz.open(src) as d:
        assert d.page_count == 3
        assert d[1].rotation == 90
        assert any(a.type[1] == "Highlight" for a in d[0].annots() or [])
        values = {w.field_name: w.field_value for w in d[0].widgets() or []}
        assert values["name"] == "third"
        assert values["agree"] not in ("Off", "", None, False)
        assert "box on page 3" in d[2].get_text()
        assert "box on page 3" not in d[0].get_text() + d[1].get_text()
        assert d[2].get_text().count("box on page 3") == 1, "text box written once, not again on a later Save"
    assert _leftovers(tmp_path) == []


def test_save_as_onto_an_existing_file_replaces_it_completely(window, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from core.editing.geometry import Rect

    src = _form(tmp_path / "doc.pdf")
    target = tmp_path / "existing.pdf"
    d = fitz.open()
    for i in range(7):
        d.new_page().insert_text((72, 72), f"OLD CONTENT {i}")
    d.save(target)
    d.close()
    src_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    assert window.open_path(src)
    window._edit.create_text_box(0, Rect(72, 300, 200, 20), text="new content", auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    import ui.main_window as mw

    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), "PDF Files (*.pdf)"))
    try:
        window.save_as_dialog()
    finally:
        QFileDialog.getSaveFileName = orig
    _ = mw
    assert window._test_errors == []  # noqa: SLF001
    with fitz.open(target) as d:
        assert d.page_count == 3
        text = "".join(p.get_text() for p in d)
        assert "new content" in text and "OLD CONTENT" not in text
    assert hashlib.sha256(src.read_bytes()).hexdigest() == src_hash, "the source file is not changed by Save As"
    assert _leftovers(tmp_path) == []


def test_searchable_ocr_pdf_keeps_its_text_layer_through_edit_and_save(window, tmp_path):
    from core.ocr.paths import ocr_ready

    ok, _detail = ocr_ready()
    if not ok:
        pytest.skip("OCR engine not installed in this environment")
    from PIL import Image, ImageDraw, ImageFont

    from core.editing.geometry import Rect
    from core.ocr.pipeline import OcrOptions, run_ocr

    im = Image.new("RGB", (1240, 1754), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(im).text((120, 200), "Recognized audit sentence", fill="black", font=font)
    scan = tmp_path / "scan.pdf"
    d = fitz.open()
    png = tmp_path / "p.png"
    im.save(png)
    d.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), filename=str(png))
    d.save(scan)
    d.close()
    png.unlink()
    assert window.open_path(scan)
    searchable = tmp_path / "scan-ocr.pdf"
    run_ocr(window._document, OcrOptions(languages="eng"), destination=searchable)  # noqa: SLF001
    window.close_document(save_session=False)
    assert window.open_path(searchable)
    window._edit.create_text_box(0, Rect(72, 700, 200, 20), text="after OCR", auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    window.save_document()
    with fitz.open(searchable) as d:
        text = d[0].get_text()
        assert "Recognized" in text and "after OCR" in text, text
    assert _leftovers(tmp_path) == []


def test_safe_write_refuses_a_read_only_destination_and_cleans_up(tmp_path):
    import stat

    from core.safe_write import save_pdf_atomic

    dest = tmp_path / "ro.pdf"
    d = fitz.open()
    d.new_page()
    d.save(dest)
    before = hashlib.sha256(dest.read_bytes()).hexdigest()
    os.chmod(dest, stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            save_pdf_atomic(d, dest)
    finally:
        os.chmod(dest, stat.S_IREAD | stat.S_IWRITE)
        d.close()
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ro.pdf"]


def test_safe_write_onto_a_folder_fails_cleanly_and_leaves_other_temporary_files_alone(tmp_path):
    from core.safe_write import save_pdf_atomic

    (tmp_path / "folder.pdf").mkdir()
    unrelated = tmp_path / ".folder.deadbeef.part"
    unrelated.write_bytes(b"someone else's file")
    d = fitz.open()
    d.new_page()
    try:
        with pytest.raises(OSError):
            save_pdf_atomic(d, tmp_path / "folder.pdf")
    finally:
        d.close()
    assert (tmp_path / "folder.pdf").is_dir()
    assert unrelated.read_bytes() == b"someone else's file"
    assert sorted(p.name for p in tmp_path.iterdir()) == [".folder.deadbeef.part", "folder.pdf"]


def test_safe_write_uses_a_unique_temporary_name_every_time(tmp_path, monkeypatch):
    from core import safe_write

    names = {safe_write.temporary_sibling(tmp_path / "a.pdf").name for _ in range(200)}
    assert len(names) == 200
    assert all(n.startswith(".a.") and n.endswith(".part") for n in names)


def test_save_flushes_the_new_file_before_it_replaces_the_original(window, tmp_path, monkeypatch):
    """Phase 1.1 finding F-09: Save wrote the temporary file without flushing it and then swapped it over
    the original, so the only flush happened for Save As onto an existing file. Every file that replaces
    the open document must have been flushed first."""
    import core.safe_write as sw

    flushed: list[str] = []
    real_flush, real_replace = sw.flush_to_disk, os.replace
    replaced: list[tuple[str, bool]] = []

    def flush(p):
        flushed.append(os.path.normcase(os.fspath(p)))
        return real_flush(p)

    def replace(a, b, *args, **kwargs):
        replaced.append((os.fspath(b), os.path.normcase(os.fspath(a)) in flushed))
        return real_replace(a, b, *args, **kwargs)

    src = _form(tmp_path / "doc.pdf")
    assert window.open_path(src)
    window._edit.set_field_value(_field(window, "name").object_id, "flushed")  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    monkeypatch.setattr(sw, "flush_to_disk", flush)
    monkeypatch.setattr(os, "replace", replace)
    window.save_document()
    monkeypatch.setattr(os, "replace", real_replace)
    assert not window._test_errors, window._test_errors  # noqa: SLF001
    swaps = [r for r in replaced if Path(r[0]) == src]
    assert swaps, "Save did not replace the file"
    assert all(ok for _, ok in swaps), "the original was replaced by a file that was not flushed first"
    assert _leftovers(tmp_path) == []
    with fitz.open(src) as d:
        assert next(w for w in d[0].widgets() if w.field_name == "name").field_value == "flushed"


def test_save_never_replaces_the_open_file_once_it_is_read_only(window, tmp_path):
    """Phase 1.1 finding F-12: after the open file was made read-only, Save replaced it on Linux and
    macOS (and left it writable), and on Windows reported it, after ~4.5 s of retries, as "open in
    another program". It must be refused at once on every platform, naming the real cause."""
    import stat

    from core.editing.geometry import Rect

    src = _form(tmp_path / "doc.pdf")
    assert window.open_path(src)
    window._edit.create_text_box(0, Rect(300, 600, 200, 24), text="kept box", auto_match=False)  # noqa: SLF001
    window._edit.mark_dirty()  # noqa: SLF001
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    os.chmod(src, stat.S_IREAD)
    try:
        window.save_document()
    finally:
        still_read_only = not (src.stat().st_mode & stat.S_IWRITE)
        os.chmod(src, stat.S_IREAD | stat.S_IWRITE)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before, "the read-only file was replaced"
    assert still_read_only
    assert window._edit.dirty  # noqa: SLF001 — the changes are still unsaved, not lost
    assert any("read-only" in m for _, m in window._test_errors), window._test_errors  # noqa: SLF001
    assert _leftovers(tmp_path) == []
    window.save_document()  # writable again: the same changes now save
    with fitz.open(src) as d:
        assert "kept box" in d[0].get_text()
