"""Integration: open/render/close, password failure, large lifecycle, malformed."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document import InvalidPdfError, PasswordRequiredError, open_document
from core.render_cache import RenderCache, RenderKey

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


def test_open_render_close():
    doc = open_document(SAMPLES / "sample_text.pdf")
    try:
        png = doc.render_pixmap_png(0, zoom=1.0, dpr=1.0)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        thumb = doc.render_thumbnail_png(0)
        assert thumb[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        doc.close()
    assert doc.is_closed
    with pytest.raises(Exception):
        doc.page_count


def test_password_failure_integration():
    with pytest.raises(PasswordRequiredError):
        open_document(SAMPLES / "sample_password.pdf", password=None)


def test_large_document_lifecycle_cache_bound():
    doc = open_document(SAMPLES / "sample_large.pdf")
    try:
        assert doc.page_count == 40
        cache: RenderCache[RenderKey, bytes] = RenderCache(max_entries=8)
        # Simulate walking through the document while retaining nearby only
        for focus in range(0, 40, 3):
            for i in range(max(0, focus - 1), min(40, focus + 2)):
                key = RenderKey.make(i, 0.5, 0, 1.0)
                if cache.get(key) is None:
                    cache.put(key, doc.render_pixmap_png(i, zoom=0.4, dpr=1.0))
            cache.retain_near_pages(focus, radius=2, page_of=lambda k: k.page_index)
            assert len(cache) <= 8
        diag = doc.diagnostics()
        assert diag.text_pages + diag.mixed_pages + diag.empty_pages + diag.image_scanned_pages == 40
    finally:
        doc.close()


def test_malformed_file_graceful_failure():
    with pytest.raises(InvalidPdfError):
        open_document(SAMPLES / "sample_malformed.pdf")


def test_ui_open_close_smoke(qtbot):
    pytest.importorskip("PySide6")
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-test"])
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert window._document is not None  # noqa: SLF001
    assert window._document.page_count == 3
    window.close_document()
    assert window._document is None  # noqa: SLF001
    window.close()
