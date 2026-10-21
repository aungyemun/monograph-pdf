"""PDF compression: sizes in exact bytes (KB = 1,000), lossless integrity, lossy modes that touch only
pictures, the bounded target-size search (500 KB … 2 MB), honest failure, quality floors, cancel,
atomic output and Unicode paths."""

from __future__ import annotations

import io
import os
from pathlib import Path

import fitz
import numpy as np
import pytest
from PIL import Image

from core.convert import compress as cz


def _photo(w: int, h: int, seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([x * 255 / w, y * 255 / h, (x + y) * 128 / (w + h)], -1) + rng.normal(0, 18, (h, w, 3))
    buf = io.BytesIO()
    Image.fromarray(np.clip(base, 0, 255).astype("uint8")).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _image_pdf(pages: int = 3) -> bytes:
    """~3.8 MB: one 1600×1200 photo per page shown at 6 × 4.5 in (≈ 267 ppi), captions, a note, a form
    field, a link, bookmarks and metadata."""
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_image(fitz.Rect(72, 72, 504, 396), stream=_photo(1600, 1200, i))
        p.insert_text((72, 450), f"Figure {i + 1}: caption 日本語 α≤β", fontsize=8, fontname="japan")
    doc[0].add_text_annot((300, 500), "Reviewer note").update()
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 600, 300, 620), "Ada"
    doc[min(1, pages - 1)].add_widget(w)
    doc[-1].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 700, 200, 720), "uri": "https://example.org"})
    doc.set_toc([[1, "First", 1], [1, "Last", pages]])
    doc.set_metadata({"title": "Atlas", "author": "Lab", "keywords": "k1"})
    return doc.tobytes()


@pytest.fixture(scope="module")
def image_pdf() -> bytes:
    return _image_pdf()


def _structure(data: bytes) -> dict:
    with fitz.open("pdf", data) as d:
        return {
            "pages": d.page_count,
            "sizes": [tuple(round(v, 2) for v in p.rect) for p in d],
            "text": [p.get_text() for p in d],
            "annots": [[a.info["content"] for a in p.annots()] for p in d],
            "fields": [(w.field_name, w.field_value) for p in d for w in p.widgets()],
            "links": [[lk.get("uri") for lk in p.get_links()] for p in d],
            "toc": d.get_toc(),
            "meta": {k: d.metadata[k] for k in ("title", "author", "keywords")},
        }


def test_sizes_are_exact_bytes():
    assert cz.parse_size("956 KB") == 956_000
    assert cz.parse_size("1.99 MB") == 1_990_000
    assert cz.parse_size("1,1 mb") == 1_100_000
    assert cz.parse_size("999") == 999_000  # default unit KB
    assert cz.parse_size("2 GB") == 2_000_000_000
    assert cz.parse_size("1 MiB") == 1_048_576
    for bad in ("", "abc", "0 KB", "5 TB"):
        with pytest.raises(ValueError):
            cz.parse_size(bad)
    assert cz.format_size(948_213) == "948 KB" and cz.format_size(1_990_000) == "1.99 MB"
    assert cz.format_size(948_213, exact=True) == "948 KB (948,213 bytes)"


def test_lossless_keeps_every_pixel_and_all_structure(image_pdf):
    res = cz.compress(image_pdf, mode="lossless")
    assert not res.lossy and res.candidate.images_changed == 0
    assert _structure(res.data) == _structure(image_pdf)
    with fitz.open("pdf", image_pdf) as a, fitz.open("pdf", res.data) as b:
        for pa, pb in zip(a, b):
            xa, xb = pa.get_images()[0][0], pb.get_images()[0][0]
            assert fitz.Pixmap(a, xa).samples == fitz.Pixmap(b, xb).samples


def test_lossless_shrinks_an_uncompressed_text_pdf():
    doc = fitz.open()
    for i in range(20):
        doc.new_page().insert_text((72, 72), "Lorem ipsum dolor sit amet " * 3 + str(i), fontsize=10)
    raw = doc.tobytes(deflate=False, garbage=0)
    res = cz.compress(raw, mode="lossless")
    assert res.output_bytes < len(raw) * 0.8
    assert _structure(res.data)["text"] == _structure(raw)["text"]


@pytest.mark.parametrize("mode", ["balanced", "smallest"])
def test_lossy_modes_change_only_pictures(image_pdf, mode):
    res = cz.compress(image_pdf, mode=mode)
    assert res.lossy and res.output_bytes < len(image_pdf) / 4
    assert _structure(res.data) == _structure(image_pdf)  # text, notes, forms, links, bookmarks, metadata
    with fitz.open("pdf", res.data) as d:
        for page in d:
            info = page.get_image_info(xrefs=True)[0]
            shown_in = (info["bbox"][2] - info["bbox"][0]) / 72
            assert info["width"] / shown_in >= cz.MIN_PPI - 1  # never below the floor
            assert not page.get_text("text").strip() == ""  # text is still text


@pytest.mark.parametrize("target", ["500 KB", "956 KB", "999 KB", "1 MB", "1.1 MB", "1.99 MB", "2 MB"])
def test_target_sizes_are_met_in_measured_bytes(image_pdf, target):
    limit = cz.parse_size(target)
    res = cz.compress(image_pdf, mode="target", target_bytes=limit, safety_margin=0.0)
    assert res.target_met is True and res.output_bytes <= limit
    assert res.output_bytes == len(res.data)
    assert res.output_bytes >= limit * 0.6, "should not throw away far more quality than needed"
    assert len(res.tried) <= 1 + 1 + 4 + cz.REFINE_STEPS  # bounded search
    assert "achieved" in res.status()
    assert _structure(res.data)["text"] == _structure(image_pdf)["text"]


def test_impossible_target_is_reported_not_faked(image_pdf):
    res = cz.compress(image_pdf, mode="target", target_bytes=cz.parse_size("5 KB"))
    assert res.target_met is False and res.output_bytes > 5_000
    assert "cannot be achieved" in res.status() and res.notes
    # the smallest acceptable candidate still respects the quality floors
    with fitz.open("pdf", res.data) as d:
        info = d[0].get_image_info(xrefs=True)[0]
        assert info["width"] / ((info["bbox"][2] - info["bbox"][0]) / 72) >= cz.MIN_PPI - 1


def test_text_only_pdf_cannot_meet_a_tiny_target():
    doc = fitz.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "Only text " * 50, fontsize=9)
    data = doc.tobytes(garbage=4, deflate=True)
    res = cz.compress(data, mode="target", target_bytes=100)
    assert res.target_met is False and any("no images" in n for n in res.notes)


def test_scans_keep_150_ppi_and_bilevel_images_are_untouched():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=_photo(2550, 3300, 7))  # 300 ppi full-page scan
    bw = Image.fromarray((np.random.default_rng(1).random((400, 400)) > 0.5).astype("uint8") * 255).convert("1")
    buf = io.BytesIO()
    bw.save(buf, "PNG")
    p2 = doc.new_page()
    p2.insert_image(fitz.Rect(72, 72, 272, 272), stream=buf.getvalue())  # barcode-like 1-bit image
    data = doc.tobytes()
    res = cz.compress(data, mode="smallest")
    with fitz.open("pdf", res.data) as d:
        scan = d[0].get_image_info(xrefs=True)[0]
        assert abs(scan["width"] / (d[0].rect.width / 72) - cz.MIN_PPI_SCAN) < 2
        with fitz.open("pdf", data) as o:
            assert fitz.Pixmap(d, d[1].get_images()[0][0]).samples == fitz.Pixmap(o, o[1].get_images()[0][0]).samples


def test_cancel_stops_without_result(image_pdf):
    with pytest.raises(cz.CompressCancelled):
        cz.compress(image_pdf, mode="balanced", cancel=lambda: True)


def test_atomic_write_keeps_existing_file_on_failure(image_pdf, tmp_path, monkeypatch):
    res = cz.compress(image_pdf, mode="balanced")
    dest = tmp_path / "out.pdf"
    dest.write_bytes(b"%PDF-1.4 original")

    def boom(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cz.os, "replace", boom)
    with pytest.raises(OSError):
        cz.write_result(res, dest)
    assert dest.read_bytes() == b"%PDF-1.4 original"
    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]  # no partial file left behind


def test_invalid_output_is_never_written(tmp_path, image_pdf):
    res = cz.compress(image_pdf, mode="lossless")
    res.candidate.data = b"not a pdf"
    with pytest.raises(ValueError):
        cz.write_result(res, tmp_path / "x.pdf")
    assert not (tmp_path / "x.pdf").exists()


def test_unicode_paths(image_pdf, tmp_path):
    folder = tmp_path / "論文 Résumé"
    folder.mkdir()
    res = cz.compress(image_pdf, mode="smallest")
    out = cz.write_result(res, folder / "圧縮 テスト ü.pdf")
    assert out.stat().st_size == res.output_bytes and os.path.basename(out) == "圧縮 テスト ü.pdf"


def test_password_protection_is_kept(tmp_path, image_pdf):
    with fitz.open("pdf", image_pdf) as d:
        enc = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="secret")
    res = cz.compress(enc, mode="balanced", password="secret")
    with fitz.open("pdf", res.data) as d:
        assert d.needs_pass and d.authenticate("secret")
    with pytest.raises(PermissionError):
        cz.compress(enc, mode="lossless", password="wrong")


def test_estimate_is_in_the_right_range(image_pdf):
    with fitz.open("pdf", image_pdf) as d:
        prof = cz.analyze(d, len(image_pdf))
    assert prof.pages == 3 and len(prof.images) == 3 and all(i.eligible for i in prof.images)
    assert prof.annotations == 1 and prof.form_fields == 1 and not prof.signed
    est = cz.estimate_size(prof, *cz.MODE_SETTINGS["balanced"])
    real = cz.compress(image_pdf, mode="balanced").output_bytes
    assert real / 3 <= est <= real * 3  # an estimate, labelled as such in the dialog
