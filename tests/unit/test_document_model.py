"""Unit tests for document/page abstractions and render cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.document import InvalidPdfError, PasswordRequiredError, open_document
from core.page_info import PageContentKind
from core.render_cache import RenderCache, RenderKey

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


def test_open_text_pdf_pages_and_metadata():
    doc = open_document(SAMPLES / "sample_text.pdf")
    try:
        assert doc.page_count == 3
        page = doc.page(0)
        assert page.width_pt > 0 and page.height_pt > 0
        assert page.has_text
        assert page.content_kind in (PageContentKind.TEXT, PageContentKind.MIXED)
        meta = doc.metadata()
        assert meta.page_count == 3
        assert meta.encrypted is False
        assert "alpha-bravo-charlie" in doc.page_text(0)
    finally:
        doc.close()


def test_image_page_detection():
    doc = open_document(SAMPLES / "sample_image_page.pdf")
    try:
        page = doc.page(0)
        assert page.has_images
        assert page.content_kind == PageContentKind.IMAGE_SCANNED
    finally:
        doc.close()


def test_search_hits():
    doc = open_document(SAMPLES / "sample_text.pdf")
    try:
        hits = doc.search("alpha-bravo-charlie")
        assert hits
        assert hits[0][0] == 0
    finally:
        doc.close()


def test_render_cache_evicts_distant():
    cache: RenderCache[RenderKey, str] = RenderCache(max_entries=10)
    for i in range(10):
        cache.put(RenderKey.make(i, 1.0, 0, 1.0), f"p{i}")
    evicted = cache.retain_near_pages(5, radius=1, page_of=lambda k: k.page_index)
    assert len(cache) == 3  # pages 4,5,6
    assert len(evicted) == 7


def test_open_never_requires_write(tmp_path: Path):
    src = SAMPLES / "sample_text.pdf"
    data = src.read_bytes()
    copy = tmp_path / "readonly_copy.pdf"
    copy.write_bytes(data)
    before = copy.read_bytes()
    doc = open_document(copy)
    try:
        _ = doc.render_pixmap_png(0, zoom=0.5, dpr=1.0)
        _ = doc.pages()
    finally:
        doc.close()
    assert copy.read_bytes() == before


def test_password_required():
    with pytest.raises(PasswordRequiredError):
        open_document(SAMPLES / "sample_password.pdf")


def test_password_success_and_wrong():
    with pytest.raises(PasswordRequiredError):
        open_document(SAMPLES / "sample_password.pdf", password="wrong")
    doc = open_document(SAMPLES / "sample_password.pdf", password="secret")
    try:
        assert doc.page_count >= 1
        assert doc.metadata().encrypted is True
    finally:
        doc.close()


def test_malformed_graceful():
    with pytest.raises(InvalidPdfError):
        open_document(SAMPLES / "sample_malformed.pdf")


def test_save_as_does_not_touch_source(tmp_path: Path):
    src = tmp_path / "src.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    before = src.read_bytes()
    dest = tmp_path / "out.pdf"
    doc = open_document(src)
    try:
        doc.save_as(dest)
    finally:
        doc.close()
    assert dest.is_file()
    assert src.read_bytes() == before
