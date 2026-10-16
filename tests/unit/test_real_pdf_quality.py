"""Regression: page geometry, optimize modes, render cache, password dialog, audits."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.convert.optimize import OptimizePreset, optimize_pdf
from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.page_geometry import label_page_size
from core.pdf_audit import audit_pdf
from core.render_cache import RenderKey
from core.windows_paths import get_downloads_dir
from engines.bake_edits import bake_via_backend

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
OUT = Path(__file__).resolve().parents[1] / "outputs" / "generated"


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_geometry_samples import main
    from tests.fixtures.make_samples import main as base

    base()
    main()
    OUT.mkdir(parents=True, exist_ok=True)


def test_paper_labels_a4_letter_custom():
    a4 = label_page_size(595.28, 841.89)
    assert a4.name == "A4"
    assert "210" in a4.display
    letter = label_page_size(612, 792)
    assert letter.name == "Letter"
    custom = label_page_size(501, 703)
    assert custom.name == "Custom"


def test_mixed_page_sizes_preserved():
    pdf = open_document(SAMPLES / "sample_mixed_page_sizes.pdf")
    try:
        pages = list(pdf.pages())
        assert len(pages) == 5
        sizes = [(round(p.width_pt, 1), round(p.height_pt, 1)) for p in pages]
        assert len(set(sizes)) >= 4  # distinct sizes
        # Fit-width uses current page — display dims differ
        assert pages[0].display_width_pt != pages[2].display_width_pt or pages[0].display_height_pt != pages[2].display_height_pt
    finally:
        pdf.close()


def test_rotations_0_90_180_270():
    pdf = open_document(SAMPLES / "sample_rotated_pages.pdf")
    try:
        rots = [p.rotation % 360 for p in pdf.pages()]
        assert set(rots) == {0, 90, 180, 270}
    finally:
        pdf.close()


def test_render_cache_key_includes_zoom_dpr_rotation():
    a = RenderKey.make(0, 1.0, 0, 1.0)
    b = RenderKey.make(0, 2.0, 0, 1.0)
    c = RenderKey.make(0, 1.0, 0, 2.0)
    d = RenderKey.make(0, 1.0, 90, 1.0)
    assert a != b and a != c and a != d
    # Low-res key must not equal high-res key
    assert a.zoom_bucket != b.zoom_bucket
    assert a.dpr_bucket != c.dpr_bucket


def test_lossless_optimize_does_not_mark_lossy():
    pdf = open_document(SAMPLES / "sample_raster_dpi.pdf")
    try:
        dest = OUT / "opt_lossless_geom.pdf"
        result = optimize_pdf(pdf, dest, preset=OptimizePreset.LOSSLESS)
        assert result.destination.is_file()
        assert result.is_lossy is False
        assert result.images_touched == 0
        assert result.mode_label == "Lossless"
    finally:
        pdf.close()


def test_balanced_optimize_labeled_not_lossless():
    pdf = open_document(SAMPLES / "sample_raster_dpi.pdf")
    try:
        dest = OUT / "opt_balanced_geom.pdf"
        result = optimize_pdf(pdf, dest, preset=OptimizePreset.BALANCED)
        assert result.mode_label == "Balanced"
        # May or may not touch images depending on size — never claim lossless
        assert "Lossless" not in result.mode_label
    finally:
        pdf.close()


def test_save_as_preserves_page_count_and_size(tmp_path: Path):
    src = tmp_path / "mixed.pdf"
    src.write_bytes((SAMPLES / "sample_mixed_page_sizes.pdf").read_bytes())
    before = src.read_bytes()
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    assert src.read_bytes() == before
    reopened = open_document(out)
    try:
        assert reopened.page_count == 5
        p0 = list(reopened.pages())[0]
        assert abs(p0.width_pt - 595.28) < 1.0
    finally:
        reopened.close()


def test_textbox_save_does_not_rasterize_page(tmp_path: Path):
    src = tmp_path / "text.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    edit.create_text_box(0, Rect(72, 72, 180, 40), text="Sharp overlay")
    out = tmp_path / "edited.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    doc = fitz.open(out)
    try:
        # Page should still have extractable text (not a full-page image-only bake)
        text = doc.load_page(0).get_text("text") or ""
        assert len(text) > 5
        images = doc.load_page(0).get_images() or []
        # A single text-box edit must not turn the page into one huge raster
        assert len(images) < 20
    finally:
        doc.close()


def test_go_to_page_preserves_explicit_index(qtbot):
    """Regression: scroll-center focus must not overwrite thumbnail/page jumps."""
    from tests.fixtures.make_geometry_samples import write_many_pages
    from ui.main_window import MainWindow, create_application

    path = OUT / "go_page_stress.pdf"
    write_many_pages(path, 10)
    create_application(["monograph-pdf-go-page"])
    window = MainWindow()
    qtbot.addWidget(window)
    window._canvas.resize(900, 700)  # noqa: SLF001
    assert window.open_path(path)
    canvas = window._canvas  # noqa: SLF001
    for i in (3, 7, 9, 0):
        canvas.go_to_page(i)
        qtbot.wait(50)
        assert canvas.focus_page == i
    window.close_document(save_session=False)
    window.close()


def test_many_pages_open_lazy():
    import time

    path = SAMPLES / "sample_many_pages_50.pdf"
    t0 = time.perf_counter()
    pdf = open_document(path)
    open_ms = (time.perf_counter() - t0) * 1000
    try:
        assert pdf.page_count == 50
        # First page render should be quick relative to full-doc rasterization
        t1 = time.perf_counter()
        png = pdf.render_pixmap_png(0, zoom=1.0, dpr=1.0)
        render_ms = (time.perf_counter() - t1) * 1000
        assert len(png) > 100
        assert open_ms < 5000
        assert render_ms < 5000
    finally:
        pdf.close()


def test_audit_writes_machine_json(tmp_path: Path):
    from core.pdf_audit import write_audit

    path = SAMPLES / "sample_mixed_page_sizes.pdf"
    doc = fitz.open(path)
    try:
        audit = audit_pdf(doc, path=path)
        dest = OUT / "audit_mixed_page_sizes.json"
        write_audit(audit, dest)
        assert dest.is_file()
        assert audit.page_count == 5
        assert audit.byte_size > 0
    finally:
        doc.close()


def test_password_dialog_api():
    from PySide6.QtWidgets import QApplication
    from ui.password_dialog import PasswordDialog

    app = QApplication.instance() or QApplication([])
    dlg = PasswordDialog(filename="secret.pdf")
    assert dlg.windowTitle() == "Protected PDF"
    assert dlg.password() == ""
    dlg._edit.setText("x")  # noqa: SLF001
    assert dlg.password() == "x"
    dlg.set_incorrect()
    assert dlg._error.isVisible() or dlg._error.text()  # noqa: SLF001
    _ = app


def test_downloads_resolver_returns_path():
    d = get_downloads_dir()
    assert isinstance(d, Path)
    # Directory should exist on a normal Windows profile
    assert d.name.lower() == "downloads" or d.is_dir()
