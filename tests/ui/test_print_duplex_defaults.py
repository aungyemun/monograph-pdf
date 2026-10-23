"""Print dialog defaults: all pages, actual size, and both sides (flip on long edge) whenever the
printer driver reports two-sided printing. No job is sent to any printer."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def dialog(qtbot, tmp_path):
    from core.document import open_document
    from ui.print_dialog import PrintDialog

    path = tmp_path / "two.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=595, height=842)
    doc.save(path)
    doc.close()
    pdf = open_document(path)
    dlg = PrintDialog(pdf, doc_name="two.pdf", current_page=1)
    qtbot.addWidget(dlg)
    yield dlg
    pdf.close()


def test_defaults_all_pages_and_actual_size(dialog):
    from core.printing import PageScaling

    assert dialog.r_all.isChecked() and dialog.selected_pages() == [0, 1]
    assert dialog.scaling.currentData() == PageScaling.ACTUAL.value
    assert dialog.settings().scaling == PageScaling.ACTUAL


def test_duplex_printer_starts_two_sided_long_edge(dialog):
    from PySide6.QtPrintSupport import QPrinter

    D = QPrinter.DuplexMode
    dialog._duplex_supported = False  # noqa: SLF001  as for a newly chosen printer
    dialog._set_duplex_support([D.DuplexNone, D.DuplexAuto, D.DuplexLongSide, D.DuplexShortSide])  # noqa: SLF001
    assert dialog.both_sides.isEnabled() and dialog.both_sides.isChecked()
    assert dialog.flip_long.isChecked() and dialog.flip_long.isEnabled() and dialog.flip_short.isEnabled()
    assert dialog.duplex_mode() == D.DuplexLongSide
    dialog.flip_short.setChecked(True)
    assert dialog.duplex_mode() == D.DuplexShortSide
    dialog.both_sides.setChecked(False)
    assert dialog.duplex_mode() == D.DuplexNone
    assert not dialog.flip_long.isEnabled() and not dialog.flip_short.isEnabled()
    # a choice made in the dialog is kept when switching to another two-sided printer
    dialog._set_duplex_support([D.DuplexNone, D.DuplexLongSide, D.DuplexShortSide])  # noqa: SLF001
    assert not dialog.both_sides.isChecked()


def test_one_sided_printer_offers_no_two_sided_option(dialog):
    from PySide6.QtPrintSupport import QPrinter

    D = QPrinter.DuplexMode
    dialog._set_duplex_support([D.DuplexNone])  # noqa: SLF001  e.g. Microsoft Print to PDF
    assert not dialog.both_sides.isEnabled() and not dialog.both_sides.isChecked()
    assert dialog.duplex_mode() == D.DuplexNone
    # back to a two-sided printer: switched on again by default
    dialog._set_duplex_support([D.DuplexNone, D.DuplexLongSide, D.DuplexShortSide])  # noqa: SLF001
    assert dialog.both_sides.isChecked() and dialog.duplex_mode() == D.DuplexLongSide


def test_only_the_edges_the_driver_reports_can_be_chosen(dialog):
    from PySide6.QtPrintSupport import QPrinter

    D = QPrinter.DuplexMode
    dialog.flip_long.setChecked(True)
    dialog._duplex_supported = False  # noqa: SLF001
    dialog._set_duplex_support([D.DuplexNone, D.DuplexShortSide])  # noqa: SLF001
    assert dialog.flip_short.isChecked() and not dialog.flip_long.isEnabled()
    assert dialog.duplex_mode() == D.DuplexShortSide


def test_configured_printer_carries_the_two_sided_choice(dialog, monkeypatch):
    """The QPrinter handed to the print job gets the dialog's choice (checked without printing)."""
    from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

    D = QPrinter.DuplexMode
    if dialog._info() is None:  # noqa: SLF001
        pytest.skip("no printer installed")
    seen = []
    monkeypatch.setattr(QPrinter, "setDuplex", lambda self, mode: seen.append(mode))
    dialog._duplex_supported = False  # noqa: SLF001
    dialog._set_duplex_support([D.DuplexLongSide, D.DuplexShortSide])  # noqa: SLF001
    dialog.printer()
    dialog.flip_short.setChecked(True)
    dialog.printer()
    dialog.both_sides.setChecked(False)
    dialog.printer()
    assert seen == [D.DuplexLongSide, D.DuplexShortSide, D.DuplexNone]
    assert isinstance(dialog._info(), QPrinterInfo)  # noqa: SLF001
