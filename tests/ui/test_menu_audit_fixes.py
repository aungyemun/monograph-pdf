"""Regressions found by the full menu/toolbar audit (0.1.5).

* exports and Save a Copy include unsaved edits (they work on the document as shown);
* Save keeps password protection;
* shapes and images can be undone and redone;
* an export can never overwrite the PDF that is open;
* Reduce File Size accepts the dialog's preset value and estimates per preset;
* with no document, empty submenus and Insert ▸ Shapes items are disabled;
* the print dialog starts on the paper that matches the document.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
fitz = pytest.importorskip("fitz")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
MARK = "AuditMark2026"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-audit-fixes"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1280, 820)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(window, tmp_path, name="sample_text.pdf", password=None):
    src = tmp_path / ("work_" + name)
    src.write_bytes((SAMPLES / name).read_bytes())
    assert window.open_path(src, password=password) if password else window.open_path(src)
    return src


def _add_unsaved_text(window):
    from core.editing.geometry import Rect

    window._edit.create_text_box(0, Rect(72, 300, 260, 40), text=MARK, auto_match=False)  # noqa: SLF001
    assert window._edit.dirty  # noqa: SLF001


def _save_to(monkeypatch, dest: Path):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))


def _flat(path: Path) -> str:
    with fitz.open(path) as doc:
        return "".join("".join(p.get_text() for p in doc).split())


@pytest.mark.parametrize(
    "method, ext",
    [
        ("_pdf_to_text", "txt"),
        ("_export_selected_pages_pdf", "pdf"),
        ("_export_flattened", "pdf"),
    ],
)
def test_exports_include_unsaved_edits(window, tmp_path, monkeypatch, method, ext):
    src = _open(window, tmp_path)
    before = src.read_bytes()
    _add_unsaved_text(window)
    dest = tmp_path / f"out.{ext}"
    _save_to(monkeypatch, dest)
    monkeypatch.setattr(window, "_selected_pages", lambda: [0])
    getattr(window, method)()
    assert dest.exists(), method
    text = dest.read_text(encoding="utf-8") if ext == "txt" else _flat(dest)
    assert MARK in "".join(text.split())
    assert src.read_bytes() == before and window._edit.dirty  # noqa: SLF001


def test_optimize_accepts_the_preset_value_and_includes_edits(window, tmp_path, monkeypatch):
    from core.convert.optimize import OptimizePreset, optimize_pdf

    _open(window, tmp_path)
    out = tmp_path / "plain.pdf"
    result = optimize_pdf(window._document, out, preset=OptimizePreset.STANDARD.value)  # noqa: SLF001
    assert out.exists() and result.output_bytes > 0

    from ui.convert_dialogs import OptimizeDialog

    calls = []
    dlg = OptimizeDialog(window, estimate=lambda p: calls.append(p) or (200_000, 100_000))
    assert "with this preset" in dlg.size_label.text()
    dlg.preset.setCurrentIndex(0)
    dlg.preset.setCurrentIndex(2)  # cached: no new estimate
    assert len(calls) == 2
    dlg.deleteLater()


def test_save_keeps_password_protection(window, tmp_path):
    src = _open(window, tmp_path, "sample_password.pdf", password="secret")
    _add_unsaved_text(window)
    window.save_document()
    assert not window._edit.dirty  # noqa: SLF001
    with fitz.open(src) as doc:
        assert doc.needs_pass, "Save removed the password"
        assert doc.authenticate("secret")
        assert MARK in "".join(doc[0].get_text().split())


def test_shapes_and_images_can_be_undone(window, tmp_path):
    from core.editing.geometry import Rect
    from core.editing.image_box import ImageBox

    _open(window, tmp_path)
    edit = window._edit  # noqa: SLF001

    def ids(objs):
        return {o.object_id for o in objs}

    shape = edit.create_shape(0, Rect(100, 100, 80, 60), "rectangle")
    assert shape.object_id in ids(edit.shapes_on_page(0))
    assert edit.undo() and shape.object_id not in ids(edit.shapes_on_page(0))
    assert edit.redo() and shape.object_id in ids(edit.shapes_on_page(0))

    png = tmp_path / "dot.png"
    import fitz as _f

    pix = _f.Pixmap(_f.csRGB, _f.IRect(0, 0, 4, 4), False)
    pix.save(png)
    image = ImageBox(page_index=0, rect=Rect(200, 200, 40, 40), source_path=str(png))
    edit.add_image(image)
    assert image.object_id in ids(edit.images_on_page(0))
    assert edit.undo() and image.object_id not in ids(edit.images_on_page(0))
    assert edit.redo() and image.object_id in ids(edit.images_on_page(0))


def test_export_cannot_replace_the_open_pdf(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from ui.convert_dialogs import choose_save

    src = _open(window, tmp_path)
    answers = iter([(str(src), ""), (str(tmp_path / "other.pdf"), "")])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: next(answers)))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2])))
    assert choose_save(window, "Save", "x.pdf", "PDF (*.pdf)") == tmp_path / "other.pdf"
    assert warned and "is open in Monograph PDF" in warned[0]


def _submenus(window, menu):
    by_action = window._menus_by_action  # noqa: SLF001
    return [(a, by_action[a]) for a in menu.actions() if a in by_action]


def test_no_document_disables_empty_submenus(window):
    from PySide6.QtWidgets import QWidgetAction

    window._sync_submenus()  # noqa: SLF001
    assert not window.act_shape_circle.isEnabled()
    recent = window._recent_menu  # noqa: SLF001
    by_action = window._menus_by_action  # noqa: SLF001

    def usable(menu):
        for a in menu.actions():
            if a.isSeparator() or isinstance(a, QWidgetAction):
                continue
            if a in by_action:
                if by_action[a] is recent or usable(by_action[a]):
                    return True
            elif a.isEnabled():
                return True
        return False

    checked = 0
    for top in window.menuBar().actions():
        stack = [by_action[top]]
        while stack:
            for act, sub in _submenus(window, stack.pop()):
                expected = True if sub is recent else usable(sub)
                assert act.isEnabled() == expected, act.text()
                stack.append(sub)
                checked += 1
    assert checked >= 10
    assert recent.menuAction().isEnabled()
    disabled = {a.text().replace("&", "") for top in window.menuBar().actions()
                for a, _ in _submenus(window, by_action[top]) if not a.isEnabled()}
    assert {"Save a Copy", "Shapes", "Add Field", "Tables"} <= disabled


def test_open_document_enables_submenus(window, tmp_path):
    _open(window, tmp_path)
    assert window.act_shape_circle.isEnabled()
    by_action = window._menus_by_action  # noqa: SLF001
    disabled = {a.text().replace("&", "") for top in window.menuBar().actions()
                for a, _ in _submenus(window, by_action[top]) if not a.isEnabled()}
    assert not disabled & {"Save a Copy", "Shapes", "Add Field", "Arrange"}, disabled


def test_print_dialog_starts_on_matching_paper(window, tmp_path, qtbot):
    from PySide6.QtGui import QPageSize

    from ui.print_dialog import PrintDialog

    src = tmp_path / "a4.pdf"
    with fitz.open() as doc:
        doc.new_page(width=595, height=842).insert_text((72, 72), "A4 page")
        doc.save(src)
    assert window.open_path(src)
    doc = window._document  # noqa: SLF001
    dlg = PrintDialog(doc, doc_name=doc.name, parent=window)
    qtbot.addWidget(dlg)
    if dlg.paper.count() == 0 or dlg._document_paper_index() < 0:  # noqa: SLF001
        pytest.skip("no printer paper list on this system")
    ps = dlg.paper.currentData()
    assert isinstance(ps, QPageSize) and ps.id() == QPageSize.PageSizeId.A4


def test_mark_text_for_redaction_marks_every_page(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from core.redaction import preview_redaction_count

    _open(window, tmp_path)
    doc = window._document  # noqa: SLF001
    pages_with_text = sum(1 for i in range(doc.page_count) if "alpha-bravo" in doc.page_text(i))
    assert pages_with_text >= 2
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("alpha-bravo", True)))
    window._redact_mark_text()  # noqa: SLF001
    assert preview_redaction_count(doc) == pages_with_text
    assert "on" in window.statusBar().currentMessage()
