"""Every number box shows its longest value: no "100" hidden under the arrows (offscreen Qt)."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def themed(qtbot):
    from PySide6.QtWidgets import QApplication

    from ui.theme import apply_theme

    apply_theme(QApplication.instance(), "light")
    return QApplication.instance()


@pytest.fixture
def pdf(tmp_path):
    from core.document import open_document

    path = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page()
    d.save(path)
    d.close()
    doc = open_document(path)
    yield doc
    doc.close()


def _dialogs(pdf):
    from ui.page_marks_dialogs import BackgroundDialog, HeaderFooterDialog, WatermarkDialog
    from ui.print_dialog import PrintDialog

    yield WatermarkDialog(page_count=1, current_page=0, source=None)
    yield HeaderFooterDialog(page_count=1, current_page=0, source=None)
    yield BackgroundDialog(page_count=1, current_page=0, source=None)
    yield PrintDialog(pdf, doc_name="doc.pdf")


def test_every_spin_box_fits_its_longest_value(themed, qtbot, pdf):
    from PySide6.QtWidgets import QAbstractSpinBox

    from ui.theme import spin_box_min_width

    checked, narrow = 0, []
    for dlg in _dialogs(pdf):
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        for box in dlg.findChildren(QAbstractSpinBox):
            if not box.isVisibleTo(dlg):
                continue
            checked += 1
            if box.width() < spin_box_min_width(box):
                narrow.append((type(dlg).__name__, box.objectName() or box.suffix(), box.width(),
                               spin_box_min_width(box)))
        dlg.close()
    assert checked >= 10, checked
    assert not narrow, narrow


def test_watermark_size_shows_three_digits(themed, qtbot):
    from ui.page_marks_dialogs import WatermarkDialog

    dlg = WatermarkDialog(page_count=1, current_page=0, source=None)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    dlg.fontsize.setValue(100)
    fm = dlg.fontsize.fontMetrics()
    assert dlg.fontsize.width() >= fm.horizontalAdvance("200 pt") + 28


def test_page_design_color_picker_is_not_tinted(themed, qtbot, monkeypatch):
    """The colour picker opens on the dialog, not on the coloured button (whose style tinted it)."""
    import ui.color_picker as color_picker
    from ui.page_marks_dialogs import WatermarkDialog

    dlg = WatermarkDialog(page_count=1, current_page=0, source=None)
    qtbot.addWidget(dlg)
    seen = {}

    def fake(initial, parent=None, title="", *a, **k):
        seen["parent"] = parent.window() if parent is not None else None
        from PySide6.QtGui import QColor

        return QColor("#1f3a5f")

    monkeypatch.setattr(color_picker, "get_color", fake)
    dlg.color_btn._pick()  # noqa: SLF001  "More colors…"
    assert seen["parent"] is dlg and dlg.color_btn.name() == "#1f3a5f"
    sheet = dlg.color_btn.styleSheet()
    assert sheet.strip().startswith("QPushButton#PageMarkColorButton")  # scoped: does not spread to children


def test_curated_swatches_apply_in_one_click(themed, qtbot):
    from ui.color_swatches import PAPER_COLORS
    from ui.page_marks_dialogs import BackgroundDialog

    dlg = BackgroundDialog(page_count=1, current_page=0, source=None)
    qtbot.addWidget(dlg)
    menu = dlg.color.menu()
    assert menu is not None
    swatches = [b for b in menu.findChildren(object) if getattr(b, "objectName", lambda: "")() == "SwatchButton"]
    assert len(swatches) >= len(PAPER_COLORS)
    swatches[1].click()  # Ivory
    assert dlg.color.name() == PAPER_COLORS[1][1].lower()
