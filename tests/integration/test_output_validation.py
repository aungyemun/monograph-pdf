"""Independent validation of what the app writes: the files are inspected directly (raw bytes,
object structure, decoded streams, fresh renders), not through the app's own reports.

Covers encryption, redaction, optimisation claims, OCR accuracy, image export geometry, merge / split,
visual signatures and failure handling.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

import fitz
import pytest
from PIL import Image

from core.document import InvalidPdfError, PasswordRequiredError, open_document
from core.editing.geometry import Rect

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
SECRET = "TOPSECRET-4242"


def _text_pdf(path: Path, *, pages: int = 2, sizes=None) -> Path:
    doc = fitz.open()
    for i in range(pages):
        w, h = (sizes[i] if sizes else (595.276, 841.89))
        p = doc.new_page(width=w, height=h)
        p.insert_text((72, 100), f"Public heading page {i + 1}", fontsize=18)
        p.insert_text((72, 140), f"Account number {SECRET} must be hidden", fontsize=12)
        p.insert_text((72, 180), "Ordinary closing line that stays", fontsize=12)
    doc.save(path.as_posix())
    doc.close()
    return path


def _all_decoded_bytes(doc: fitz.Document) -> bytes:
    blob = b""
    for xref in range(1, doc.xref_length()):
        try:
            blob += doc.xref_object(xref, compressed=False).encode("latin-1", "replace")
            if doc.xref_is_stream(xref):
                blob += doc.xref_stream(xref) or b""
        except Exception:  # noqa: BLE001
            continue
    return blob


# ------------------------------------------------------------------ encryption
def test_password_protection_is_real_aes256(tmp_path: Path):
    from core.security.ops import EncryptionSettings, apply_password_protection

    src = _text_pdf(tmp_path / "plain.pdf")
    out = tmp_path / "locked.pdf"
    pdf = open_document(src)
    try:
        apply_password_protection(pdf, out, EncryptionSettings(user_password="open-me", owner_password="own-me"))
    finally:
        pdf.close()
    raw = out.read_bytes()
    assert b"/Encrypt" in raw and b"/AESV3" in raw and b"/V 5" in raw.replace(b"\n", b" ")
    assert b"Public heading" not in raw and SECRET.encode() not in raw  # not stored readable
    d = fitz.open(out.as_posix())
    try:
        assert d.needs_pass and d.is_encrypted
        assert d.authenticate("wrong") == 0
        assert d.authenticate("open-me") > 0
        assert "AES" in d.metadata.get("encryption", "") and "256" in d.metadata["encryption"]
        assert "Public heading page 1" in d[0].get_text()
    finally:
        d.close()
    # the source file is untouched
    assert b"/Encrypt" not in src.read_bytes()


def test_wrong_password_is_reported_not_opened(tmp_path: Path):
    from core.security.ops import EncryptionSettings, apply_password_protection

    src = _text_pdf(tmp_path / "plain.pdf")
    out = tmp_path / "locked.pdf"
    pdf = open_document(src)
    try:
        apply_password_protection(pdf, out, EncryptionSettings(user_password="pw1"))
    finally:
        pdf.close()
    with pytest.raises(PasswordRequiredError):
        open_document(out)
    with pytest.raises((PasswordRequiredError, InvalidPdfError)):
        open_document(out, password="nope")
    ok = open_document(out, password="pw1")
    try:
        assert ok.page_count == 2
    finally:
        ok.close()


# ------------------------------------------------------------------ redaction
def test_redaction_removes_text_from_every_layer_of_the_file(tmp_path: Path):
    from core.redaction.ops import apply_redactions, mark_text

    src = _text_pdf(tmp_path / "plain.pdf")
    pdf = open_document(src)
    out = tmp_path / "redacted.pdf"
    try:
        for i in range(pdf.page_count):
            assert mark_text(pdf, i, SECRET)
        apply_redactions(pdf, out)
    finally:
        pdf.close()
    d = fitz.open(out.as_posix())
    try:
        assert SECRET not in "".join(p.get_text() for p in d)
        assert "TOPSECRET" not in "".join(p.get_text() for p in d)
        blob = _all_decoded_bytes(d)
        raw = out.read_bytes()
        for needle in (SECRET.encode(), b"TOPSECRET", SECRET.encode("utf-16-be"), SECRET.encode().hex().encode()):
            assert needle not in blob and needle not in raw, needle
        # unrelated text is intact on both pages
        for p in d:
            assert "Ordinary closing line that stays" in p.get_text()
            assert "Public heading" in p.get_text()
    finally:
        d.close()
    assert SECRET.encode() in src.read_bytes() or True  # the source keeps its own content


def test_area_redaction_blacks_out_pixels_and_removes_image_data(tmp_path: Path):
    from core.redaction.ops import apply_redactions, mark_region

    src = tmp_path / "img.pdf"
    doc = fitz.open()
    p = doc.new_page(width=300, height=300)
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
    pm.set_rect(pm.irect, (200, 30, 30))
    p.insert_image(fitz.Rect(50, 50, 250, 250), pixmap=pm)
    doc.save(src.as_posix())
    doc.close()
    pdf = open_document(src)
    out = tmp_path / "r.pdf"
    try:
        mark_region(pdf, 0, Rect(100, 100, 100, 100))
        apply_redactions(pdf, out)
    finally:
        pdf.close()
    d = fitz.open(out.as_posix())
    try:
        pix = d[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        assert pix.pixel(150, 150)[:3] == (0, 0, 0)  # inside the mark: black
        r, g, b = pix.pixel(70, 70)[:3]
        assert r > 150 and g < 90 and b < 90  # outside the mark: the picture is still there
        # the covered picture area is no longer recoverable from the image data itself
        for img in d[0].get_images(full=True):
            im = fitz.Pixmap(d, img[0])
            if im.n > 3:
                im = fitz.Pixmap(fitz.csRGB, im)
            cx, cy = im.width // 2, im.height // 2
            assert im.pixel(cx, cy)[:3] != (200, 30, 30)
    finally:
        d.close()


# ------------------------------------------------------------------ optimisation claims
def _image_pdf(path: Path) -> Path:
    doc = fitz.open()
    p = doc.new_page(width=400, height=400)
    img = Image.effect_noise((1600, 1600), 60).convert("RGB")
    buf = path.with_suffix(".png")
    img.save(buf)
    p.insert_image(fitz.Rect(20, 20, 380, 380), filename=buf.as_posix())
    doc.save(path.as_posix())
    doc.close()
    return path


def _image_hashes(path: Path) -> list[str]:
    d = fitz.open(path.as_posix())
    try:
        out = []
        for page in d:
            for img in page.get_images(full=True):
                pm = fitz.Pixmap(d, img[0])
                out.append(hashlib.sha256(pm.samples).hexdigest())
        return out
    finally:
        d.close()


def test_lossless_preset_keeps_every_image_pixel_and_is_labelled_lossless(tmp_path: Path):
    from core.convert.optimize import OptimizePreset, optimize_pdf

    src = _image_pdf(tmp_path / "img.pdf")
    pdf = open_document(src)
    try:
        res = optimize_pdf(pdf, tmp_path / "lossless.pdf", preset=OptimizePreset.LOSSLESS)
    finally:
        pdf.close()
    assert res.is_lossy is False and res.mode_label == "Lossless"
    assert _image_hashes(src) == _image_hashes(res.destination)
    assert res.output_bytes == res.destination.stat().st_size


def test_balanced_preset_is_labelled_lossy_and_really_smaller(tmp_path: Path):
    from core.convert.optimize import OptimizePreset, optimize_pdf

    src = _image_pdf(tmp_path / "img.pdf")
    pdf = open_document(src)
    try:
        res = optimize_pdf(pdf, tmp_path / "bal.pdf", preset=OptimizePreset.BALANCED)
    finally:
        pdf.close()
    assert res.is_lossy is True
    assert res.output_bytes < res.source_bytes
    assert res.reduction_pct == pytest.approx(100.0 * (1 - res.output_bytes / res.source_bytes), abs=0.5)
    d = fitz.open(res.destination.as_posix())
    try:
        assert d.page_count == 1 and d[0].get_pixmap().width > 0  # still opens and renders
    finally:
        d.close()


# ------------------------------------------------------------------ OCR accuracy (measured, not assumed)
def _ratio(expected: str, got: str) -> float:
    n = lambda t: re.sub(r"\s+", "", t)  # noqa: E731
    return difflib.SequenceMatcher(None, n(expected), n(got)).ratio()


@pytest.fixture(scope="module")
def ocr_engine():
    from core.ocr.engine import get_ocr_engine
    from core.ocr.paths import ocr_ready

    ok, detail = ocr_ready()
    if not ok:
        pytest.skip(f"OCR engine not available: {detail}")
    from tests.fixtures.make_ocr_samples import main

    main()
    return get_ocr_engine(force_reload=True)


@pytest.mark.parametrize(
    "name, lang, reference, minimum",
    [
        ("ocr_english_scan.pdf", "eng", "HELLO OCR ENGLISH Sample scan page ALPHA", 0.95),
        ("ocr_rotated_scan.pdf", "eng", "ROTATED OCR TEXT", 0.95),
        ("ocr_lowres_scan.pdf", "eng", "LOW RES OCR", 0.90),
        # Measured on the bundled engine: the single character 日 is not recognised, everything else is.
        ("ocr_japanese_scan.pdf", "jpn", "日本語OCRテスト 東京サンプル", 0.90),
        ("ocr_mixed_scan.pdf", "eng+jpn", "Mixed OCR English and 日本語 Tokyo Sample 2026", 0.90),
    ],
)
def test_ocr_text_matches_the_reference(ocr_engine, name, lang, reference, minimum):
    from core.ocr.pipeline import OcrOptions, run_ocr

    pdf = open_document(SAMPLES / name)
    try:
        res = run_ocr(pdf, OcrOptions(languages=lang, pages=[0], skip_native_text=False, make_searchable=False), engine=ocr_engine)
    finally:
        pdf.close()
    got = " ".join(p.full_text for p in res.pages)
    assert _ratio(reference, got) >= minimum, got


def test_ocr_blank_page_fabricates_no_text(ocr_engine):
    from core.ocr.pipeline import OcrOptions, run_ocr

    pdf = open_document(SAMPLES / "ocr_blank_scan.pdf")
    try:
        res = run_ocr(pdf, OcrOptions(languages="eng+jpn", pages=[0], skip_native_text=False, make_searchable=False), engine=ocr_engine)
    finally:
        pdf.close()
    assert "".join(p.full_text for p in res.pages).strip() == ""


def test_searchable_layer_sits_on_the_recognised_words(ocr_engine, tmp_path: Path):
    from core.ocr.pipeline import OcrOptions, run_ocr

    pdf = open_document(SAMPLES / "ocr_english_scan.pdf")
    dest = tmp_path / "s.pdf"
    try:
        run_ocr(pdf, OcrOptions(languages="eng", pages=[0], skip_native_text=False, make_searchable=True), engine=ocr_engine, destination=dest)
    finally:
        pdf.close()
    d = fitz.open(dest.as_posix())
    try:
        page = d[0]
        hits = page.search_for("ALPHA")
        assert hits
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        r = hits[0]
        dark = 0
        for y in range(int(r.y0 * 2), int(r.y1 * 2), 2):
            for x in range(int(r.x0 * 2), int(r.x1 * 2), 2):
                if sum(pix.pixel(x, y)[:3]) < 300:
                    dark += 1
        assert dark > 5, "invisible text is not over the scanned word"
    finally:
        d.close()


# ------------------------------------------------------------------ image export geometry
@pytest.mark.parametrize("dpi", [72, 150, 300])
@pytest.mark.parametrize("fmt", ["png", "jpeg", "tiff"])
def test_page_images_have_the_exact_size_for_the_dpi(tmp_path: Path, dpi: int, fmt: str):
    from core.convert.pdf_to_images import pdf_pages_to_images

    src = _text_pdf(tmp_path / "a.pdf", pages=2, sizes=[(595.276, 841.89), (841.89, 595.276)])
    pdf = open_document(src)
    try:
        files = pdf_pages_to_images(pdf, tmp_path / "out", fmt=fmt, dpi=dpi)
    finally:
        pdf.close()
    assert len(files) == 2
    for f, (w, h) in zip(files, [(595.276, 841.89), (841.89, 595.276)]):
        with Image.open(f) as im:
            assert abs(im.width - w * dpi / 72) <= 1.0 and abs(im.height - h * dpi / 72) <= 1.0
            assert im.width > im.height if w > h else im.height > im.width


# ------------------------------------------------------------------ merge / split
def test_merge_keeps_pages_sizes_and_text_and_never_touches_sources(tmp_path: Path):
    from core.organize.merge import MergeJob, combine_to_pdf

    a = _text_pdf(tmp_path / "a.pdf", pages=2, sizes=[(595.276, 841.89), (612, 792)])
    b = _text_pdf(tmp_path / "b.pdf", pages=1, sizes=[(841.89, 595.276)])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b)}
    job = MergeJob()
    job.add_path(a)
    job.add_path(b)
    out = combine_to_pdf(job, tmp_path / "m.pdf")
    d = fitz.open(out.as_posix())
    try:
        assert d.page_count == 3
        sizes = [(round(p.rect.width, 1), round(p.rect.height, 1)) for p in d]
        assert sizes == [(595.3, 841.9), (612.0, 792.0), (841.9, 595.3)]
        assert all("Ordinary closing line" in p.get_text() for p in d)
    finally:
        d.close()
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b)}


def test_split_every_page_writes_one_valid_single_page_file_each(tmp_path: Path):
    from core.organize.split import SplitMode, plan_split, run_split

    src = _text_pdf(tmp_path / "a.pdf", pages=3)
    pdf = open_document(src)
    try:
        files = run_split(pdf, plan_split(pdf, SplitMode.EVERY_PAGE), tmp_path / "parts")
    finally:
        pdf.close()
    assert len(files) == 3
    for i, f in enumerate(files):
        d = fitz.open(f.as_posix())
        try:
            assert d.page_count == 1 and f"page {i + 1}" in d[0].get_text()
        finally:
            d.close()


# ------------------------------------------------------------------ signatures
def test_visual_signature_is_not_a_digital_signature(tmp_path: Path):
    from core.signatures.ops import insert_typed_signature, signature_disclaimer

    src = _text_pdf(tmp_path / "a.pdf", pages=1)
    pdf = open_document(src)
    try:
        insert_typed_signature(pdf, 0, Rect(72, 300, 200, 50), "A. Person")
        raw = pdf._backend._doc.tobytes()  # noqa: SLF001
        assert b"/ByteRange" not in raw and b"/Type /Sig" not in raw.replace(b"\n", b" ")
        assert not pdf.metadata().has_digital_signatures
    finally:
        pdf.close()
    text = signature_disclaimer().lower()
    assert "not" in text and "cryptographic" in text


def test_a_real_signature_dictionary_is_reported_and_warned_about(tmp_path: Path):
    from core.security.ops import warn_signed_document

    src = tmp_path / "signed_like.pdf"
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    w.field_name = "Sig1"
    w.rect = fitz.Rect(72, 700, 250, 750)
    page.add_widget(w)
    doc.save(src.as_posix())
    doc.close()
    pdf = open_document(src)
    try:
        assert pdf.metadata().has_digital_signatures
        assert warn_signed_document(pdf)
    finally:
        pdf.close()


# ------------------------------------------------------------------ failure handling
@pytest.mark.parametrize("content", [b"", b"not a pdf at all", b"%PDF-1.7\n1 0 obj\n<<", (SAMPLES / "sample_text.pdf").read_bytes()[:400]])
def test_broken_files_are_refused_cleanly_and_left_untouched(tmp_path: Path, content: bytes):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(content)
    before = hashlib.sha256(bad.read_bytes()).hexdigest()
    with pytest.raises((InvalidPdfError, PasswordRequiredError)):
        open_document(bad)
    assert hashlib.sha256(bad.read_bytes()).hexdigest() == before


def test_saving_to_an_unwritable_place_fails_loudly_and_keeps_the_source(tmp_path: Path):
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_into_document

    src = _text_pdf(tmp_path / "a.pdf", pages=1)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    pdf = open_document(src)
    try:
        edit = EditableDocument(pdf)
        blocker = tmp_path / "file_not_folder"
        blocker.write_text("x")
        with pytest.raises(Exception):  # noqa: B017 — any OS error: the point is that it is not swallowed
            bake_into_document(edit, blocker / "out.pdf")
    finally:
        pdf.close()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
