"""Printing: grayscale vs black and white, custom scale, pages per sheet, Save as PDF from the print
dialog, cancel, and real print output (Qt's PDF printer) for mixed page sizes and unsaved edits."""

from __future__ import annotations

import io
import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

A4 = (595.0, 842.0)
A3 = (842.0, 1191.0)
LEGAL = (612.0, 1008.0)
LETTER = (612.0, 792.0)


def _mixed(path: Path) -> Path:
    doc = fitz.open()
    for i, (w, h) in enumerate((A4, (A3[1], A3[0]), LEGAL, (300.0, 500.0))):
        page = doc.new_page(width=w, height=h)
        page.draw_rect(page.rect + (10, 10, -10, -10), color=(1, 0, 0), width=4)
        page.insert_text((40, 80), f"Page {i + 1} {int(w)}x{int(h)}", fontsize=24)
        page.draw_rect(fitz.Rect(40, 120, 200, 220), color=None, fill=(0.2, 0.5, 0.9))
    doc.save(path)
    doc.close()
    return path


def test_place_page_custom_percent_and_layouts():
    from core.printing import PageScaling, layout_sheet, sheet_grid, sheet_landscape
    from core.printing.ops import place_page

    assert place_page(100, 200, 400, 400, PageScaling.CUSTOM, 50) == (175.0, 150.0, 50.0, 100.0)
    assert sheet_grid(2, 800, 560) == (2, 1) and sheet_grid(2, 560, 800) == (1, 2)
    assert sheet_grid(6, 560, 800) == (2, 3)
    boxes = layout_sheet([A4, A4, A4, A4], 4, 559, 806)
    assert len(boxes) == 4 and all(abs(b[2] / b[3] - A4[0] / A4[1]) < 1e-6 for b in boxes)
    assert boxes[1][0] > boxes[0][0] and boxes[2][1] > boxes[0][1]  # reading order
    assert sheet_landscape([A4], 2) is True and sheet_landscape([A4], 4) is False


def test_grayscale_and_black_and_white_are_different():
    from PIL import Image

    from core.printing import ColorMode, apply_color_mode

    im = Image.new("RGB", (40, 10))
    for x in range(40):
        for y in range(10):
            im.putpixel((x, y), (x * 6, 120, 255 - x * 6))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    gray = Image.open(io.BytesIO(apply_color_mode(buf.getvalue(), ColorMode.GRAYSCALE)))
    mono = Image.open(io.BytesIO(apply_color_mode(buf.getvalue(), ColorMode.MONOCHROME)))
    assert gray.mode == "L" and len(set(gray.getdata())) > 10
    assert set(mono.convert("L").getdata()) <= {0, 255} and len(set(mono.convert("L").getdata())) == 2


def _qt_pdf_printer(path: Path, size_id):
    from PySide6.QtGui import QPageSize
    from PySide6.QtPrintSupport import QPrinter

    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    pr.setOutputFileName(str(path))
    pr.setPageSize(QPageSize(size_id))
    pr.setResolution(150)
    return pr


@pytest.fixture()
def app():
    from ui.main_window import create_application

    return create_application(["monograph-pdf-print"])


def test_print_job_on_a4_paper_keeps_proportions_and_scales_a3_down(app, tmp_path):
    from PySide6.QtGui import QPageSize

    from core.document import open_document
    from core.printing import PageScaling
    from ui.print_dialog import print_document_pages

    pdf = open_document(_mixed(tmp_path / "mixed.pdf"))
    out = tmp_path / "printed.pdf"
    try:
        pr = _qt_pdf_printer(out, QPageSize.PageSizeId.A4)
        n = print_document_pages(pr, pdf, [0, 1, 2, 3], dpi=150, scaling=PageScaling.SHRINK, orientation="auto")
    finally:
        pdf.close()
    assert n == 4
    with fitz.open(out) as d:
        assert d.page_count == 4
        sizes = [(round(p.rect.width), round(p.rect.height)) for p in d]
        assert sizes[0] == (595, 842) and sizes[1] == (842, 595)  # A3 landscape page -> landscape sheet
        # the A3 page was shrunk to fit: its red frame is inside the sheet, with the same proportions
        pix = d[1].get_pixmap(dpi=40)
        reds = [(x, y) for x in range(pix.width) for y in range(pix.height)
                if pix.pixel(x, y)[0] > 200 and pix.pixel(x, y)[1] < 80]
        xs, ys = [p[0] for p in reds], [p[1] for p in reds]
        assert reds and min(xs) > 0 and max(xs) < pix.width - 1
        assert abs((max(xs) - min(xs)) / (max(ys) - min(ys)) - (A3[1] - 20) / (A3[0] - 20)) < 0.08


def test_two_pages_per_sheet_and_cancel(app, tmp_path):
    from PySide6.QtGui import QPageSize

    from core.document import open_document
    from ui.print_dialog import PrintCancelled, print_document_pages

    pdf = open_document(_mixed(tmp_path / "mixed.pdf"))
    try:
        out = tmp_path / "nup.pdf"
        n = print_document_pages(_qt_pdf_printer(out, QPageSize.PageSizeId.A4), pdf, [0, 2, 3], dpi=150,
                                 orientation="auto", n_up=2)
        assert n == 3
        with fitz.open(out) as d:
            assert d.page_count == 2
        calls = []
        with pytest.raises(PrintCancelled) as info:
            print_document_pages(_qt_pdf_printer(tmp_path / "c.pdf", QPageSize.PageSizeId.A4), pdf, [0, 1, 2],
                                 dpi=100, progress=lambda done, total: calls.append(done) or done < 1)
        assert info.value.printed == 1
    finally:
        pdf.close()


def test_print_dialog_options_and_save_as_pdf(app, qtbot, tmp_path):
    from core.document import open_document
    from core.printing import ColorMode, PageScaling, save_pages_as_pdf
    from ui.print_dialog import PrintDialog

    pdf = open_document(_mixed(tmp_path / "mixed.pdf"))
    try:
        dlg = PrintDialog(pdf, doc_name="mixed.pdf", current_page=0)
        qtbot.addWidget(dlg)
        assert [dlg.color.itemData(i) for i in range(dlg.color.count())] == ["color", "grayscale", "monochrome"]
        assert not dlg.percent.isEnabled()
        dlg.scaling.setCurrentIndex(dlg.scaling.findData(PageScaling.CUSTOM.value))
        assert dlg.percent.isEnabled()
        dlg.percent.setValue(50)
        dlg.n_up.setCurrentIndex(dlg.n_up.findData(4))
        assert dlg.sheet_label.text().startswith("Sheet 1 of 1") and "pages 1–4" in dlg.sheet_label.text()
        assert len(dlg.preview.page_targets()) == 4
        dlg.color.setCurrentIndex(dlg.color.findData("monochrome"))
        s = dlg.settings()
        assert (s.n_up, s.percent, s.color_mode) == (4, 50.0, ColorMode.MONOCHROME)
        # no printer in this environment: Print is off, Save as PDF works
        assert not dlg._print_btn.isEnabled() and dlg.save_pdf_btn.isEnabled()  # noqa: SLF001
        dlg.r_custom.setChecked(True)
        dlg.custom.setText("3, 1")
        dlg.save_pdf_btn.click()
        assert dlg.save_as_pdf and dlg.result() == dlg.DialogCode.Accepted
        out = save_pages_as_pdf(pdf, dlg.settings().pages, tmp_path / "saved.pdf")
    finally:
        pdf.close()
    with fitz.open(out) as d:
        assert d.page_count == 2
        # pages in document order (a range is printed front to back), each at its own size
        assert [(round(p.rect.width), round(p.rect.height)) for p in d] == [(595, 842), (612, 1008)]
        assert "Page 1" in d[0].get_text() and "Page 3" in d[1].get_text()  # text stays text


def test_save_as_pdf_and_print_source_include_unsaved_edits(app, tmp_path):
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Rect
    from core.printing import prepare_print_source, save_pages_as_pdf

    pdf = open_document(_mixed(tmp_path / "mixed.pdf"))
    edit = EditableDocument(pdf)
    edit.create_text_box(2, Rect(60, 300, 200, 40), text="Unsaved edit")
    src = prepare_print_source(pdf, edit)
    try:
        out = save_pages_as_pdf(src.document, [2], tmp_path / "edited.pdf")
    finally:
        src.close()
        pdf.close()
    with fitz.open(out) as d:
        assert "Unsaved edit" in d[0].get_text()
    with fitz.open(tmp_path / "mixed.pdf") as d:
        assert "Unsaved edit" not in d[2].get_text()  # the source file is not changed


def test_print_resolution_follows_the_printed_size_and_is_bounded():
    from ui.print_dialog import MAX_PRINT_PIXELS, print_render_dpi

    assert print_render_dpi(300, A4, A4[0]) == 300  # actual size
    assert 200 <= print_render_dpi(300, A3, A4[0] - 20) <= 215  # A3 shrunk onto A4
    a0 = (2384.0, 3370.0)
    dpi = print_render_dpi(400, a0, a0[0] * 2)  # A0 enlarged: bounded
    assert (a0[0] / 72 * dpi) * (a0[1] / 72 * dpi) <= MAX_PRINT_PIXELS * 1.01


def test_large_pages_render_as_sharp_tiles_without_a_huge_bitmap(app, qtbot, tmp_path):
    from core.document import open_document
    from ui import pdf_canvas

    src = tmp_path / "a0.pdf"
    doc = fitz.open()
    doc.new_page(width=2384, height=3370).insert_text((100, 200), "A0 POSTER", fontsize=120)
    doc.new_page(width=595, height=842)
    doc.save(src)
    doc.close()
    pdf = open_document(src)
    canvas = pdf_canvas.PdfCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(900, 700)
    canvas.show()
    try:
        canvas.set_document(pdf)
        canvas.set_manual_zoom(3.0)
        inner = canvas._canvas  # noqa: SLF001
        inner._render_visible()  # noqa: SLF001
        assert inner._tiles, "no tiles for a page larger than the pixel limit"  # noqa: SLF001
        for pix in inner._cache._data.values():  # noqa: SLF001
            assert pix.width() * pix.height() <= pdf_canvas.MAX_PAGE_PIXELS
        assert all(p.width() <= pdf_canvas.TILE_PX and p.height() <= pdf_canvas.TILE_PX for p in inner._tiles.values())  # noqa: SLF001
        # mixed sizes: the A4 page is centred under the A0 page, at its own proportions
        a0, a4 = inner._layouts  # noqa: SLF001
        assert abs(a4.center().x() - a0.center().x()) <= 1
        assert abs(a4.width() / a4.height() - 595 / 842) < 0.01
    finally:
        canvas.clear_document()
        pdf.close()
