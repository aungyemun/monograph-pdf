"""Golden documents: every file in tests/fixtures/golden_documents is checked against the manifest
(declared expectations) and its reference render. Runs offline. Nothing here rewrites a reference."""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from core.document import PasswordRequiredError, open_document

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "golden_documents"
MANIFEST = json.loads((GOLD / "manifest.json").read_text(encoding="utf-8"))
DOCS = MANIFEST["documents"]
PASSWORD = MANIFEST["password"]
NAMES = sorted(DOCS)


def _open_app(name: str):
    path = GOLD / DOCS[name]["file"]
    return open_document(path, password=PASSWORD) if DOCS[name].get("encrypted") else open_document(path)


def _turn(x: float, y: float, w: float, h: float, rot: int) -> tuple[float, float]:
    """Hand-written display position of an unrotated page point (independent of PyMuPDF's matrices)."""
    return {0: (x, y), 90: (h - y, x), 180: (w - x, h - y), 270: (y, w - x)}[rot]


@pytest.mark.parametrize("name", NAMES)
def test_page_count_sizes_and_rotation(name: str):
    spec = DOCS[name]
    pdf = _open_app(name)
    try:
        assert pdf.page_count == len(spec["pages"])
        for i, p in enumerate(spec["pages"]):
            w, h = p["size"]
            info = pdf.page(i)
            rot = p["rotate"]
            assert info.rotation == rot
            dw, dh = (h, w) if rot in (90, 270) else (w, h)
            assert info.display_width_pt == pytest.approx(dw, abs=0.01)
            assert info.display_height_pt == pytest.approx(dh, abs=0.01)
    finally:
        pdf.close()


@pytest.mark.parametrize("name", NAMES)
def test_text_is_where_the_manifest_says(name: str):
    spec = DOCS[name]
    pdf = _open_app(name)
    try:
        for i, p in enumerate(spec["pages"]):
            w, h = p["size"]
            rot = p["rotate"]
            for text, x, y in p.get("texts", []):
                hits = [r for pg, r in pdf.search(text) if pg == i]
                assert hits, f"{name} p{i + 1}: {text!r} not found"
                ex, ey = _turn(x, y, w, h, rot)
                # baseline origin must lie on the hit (display space), within 3 pt
                ok = any(r.x0 - 3 <= ex <= r.x1 + 3 and r.y0 - 3 <= ey <= r.y1 + 3 for r in hits)
                assert ok, f"{name} p{i + 1}: {text!r} expected near ({ex:.1f},{ey:.1f}), found {[tuple(map(round, r)) for r in hits]}"
    finally:
        pdf.close()


@pytest.mark.parametrize("name", [n for n in NAMES if DOCS[n].get("fonts_embedded")])
def test_fonts_are_embedded_and_subset(name: str):
    d = fitz.open((GOLD / DOCS[name]["file"]).as_posix())
    try:
        fonts = d[0].get_fonts(full=True)
        assert fonts
        base14 = ("Helvetica", "Times", "Courier", "Symbol", "ZapfDingbats")
        embedded = [f for f in fonts if f[1] != "n/a"]  # extension 'n/a' = not embedded
        assert embedded, "no embedded font"
        for f in fonts:
            assert f[1] != "n/a" or f[3].startswith(base14), f"non-standard font not embedded: {f}"
        # subset: the embedded program is far smaller than the 3.5 MB full font
        for f in embedded:
            assert len(d.extract_font(f[0])[3]) < 600_000, f"font looks unsubsetted: {f[3]}"
    finally:
        d.close()
    # Japanese text survives extraction from the subset font
    if "japanese" in name or "mixed" in name:
        text = "".join(p.get_text() for p in fitz.open((GOLD / DOCS[name]["file"]).as_posix()))
        assert re.search(r"[぀-ヿ一-鿿]", text)


@pytest.mark.parametrize("name", [n for n in NAMES if any("images" in p for p in DOCS[n]["pages"])])
def test_image_dimensions(name: str):
    d = fitz.open((GOLD / DOCS[name]["file"]).as_posix())
    try:
        for i, p in enumerate(DOCS[name]["pages"]):
            got = sorted([img[2], img[3]] for img in d[i].get_images(full=True))
            assert got == sorted(p["images"])
    finally:
        d.close()


def test_vector_graphics_present():
    d = fitz.open((GOLD / DOCS["vector_graphics"]["file"]).as_posix())
    try:
        assert len(d[0].get_drawings()) >= DOCS["vector_graphics"]["pages"][0]["drawings_min"]
    finally:
        d.close()


def test_annotations_and_their_positions():
    spec = DOCS["annotations"]["pages"][0]
    d = fitz.open((GOLD / DOCS["annotations"]["file"]).as_posix())
    try:
        page = d[0]
        kinds = sorted(a.type[1] for a in page.annots())
        assert kinds == sorted(spec["annots"])
        word = page.search_for("highlight")[0]
        hl = next(a for a in page.annots() if a.type[1] == "Highlight")
        # MuPDF pads the annotation box a little: it must enclose the word, never miss it by more than 6 pt
        assert hl.rect.x0 <= word.x0 + 0.5 and hl.rect.y0 <= word.y0 + 0.5 and hl.rect.x1 >= word.x1 - 0.5 and hl.rect.y1 >= word.y1 - 0.5
        assert word.x0 - hl.rect.x0 < 6 and word.y0 - hl.rect.y0 < 6
    finally:
        d.close()
    from core.annotations import list_annotations

    pdf = _open_app("annotations")
    try:
        assert sorted(a.kind for a in list_annotations(pdf)) == sorted(spec["annots"])
    finally:
        pdf.close()


def test_acroform_fields_values_and_rects():
    spec = DOCS["acroform"]["pages"][0]
    pdf = _open_app("acroform")
    try:
        from core.editing.edit_model import EditableDocument

        edit = EditableDocument(pdf)
        by_name = {f.name: f for f in edit.fields.values()}
        for name, rect, val in spec["widgets"]:
            f = by_name[name]
            assert (f.rect.x, f.rect.y, f.rect.x1, f.rect.y1) == pytest.approx(tuple(rect), abs=0.01)
            if val:
                assert f.value == val
    finally:
        pdf.close()


def test_table_is_detected_with_its_grid():
    t = DOCS["table_grid"]["pages"][0]["table"]
    pdf = _open_app("table_grid")
    try:
        from core.tables.detect import detect_tables

        tables = detect_tables(pdf._backend._doc)  # noqa: SLF001
        assert len(tables) == 1
        tb = tables[0]
        assert (tb.nrows, tb.ncols) == (t["rows"], t["cols"])
        assert tb.bounds.x == pytest.approx(t["x"], abs=1.5) and tb.bounds.y == pytest.approx(t["y"], abs=1.5)
        assert tb.cells[(2, 1)].text == "R2C1"
    finally:
        pdf.close()


def test_password_protected_document():
    d = fitz.open((GOLD / DOCS["password_protected"]["file"]).as_posix())
    try:
        assert d.needs_pass and d.is_encrypted
        assert d.authenticate("wrong") == 0 and d.authenticate(PASSWORD) > 0
    finally:
        d.close()
    with pytest.raises(PasswordRequiredError):
        open_document(GOLD / DOCS["password_protected"]["file"])


def test_signature_field_is_reported_but_nothing_claims_it_is_signed():
    pdf = _open_app("signature_field")
    try:
        assert pdf.metadata().has_digital_signatures  # a signature field exists
        raw = (GOLD / DOCS["signature_field"]["file"]).read_bytes()
        assert b"/ByteRange" not in raw, "fixture must not claim a cryptographic signature"
    finally:
        pdf.close()


def test_scanned_page_ocr_matches_reference_text():
    from core.ocr.engine import get_ocr_engine
    from core.ocr.paths import ocr_ready
    from core.ocr.pipeline import OcrOptions, run_ocr

    ok, detail = ocr_ready()
    if not ok:
        pytest.skip(f"OCR engine unavailable: {detail}")
    ref = DOCS["scanned_page"]["pages"][0]["scan_text"]
    pdf = _open_app("scanned_page")
    try:
        res = run_ocr(pdf, OcrOptions(languages="eng", pages=[0], skip_native_text=False, make_searchable=False), engine=get_ocr_engine())
    finally:
        pdf.close()
    got = " ".join(p.full_text for p in res.pages)
    n = lambda t: re.sub(r"\s+", "", t)  # noqa: E731
    assert difflib.SequenceMatcher(None, n(ref), n(got)).ratio() >= 0.95, got


@pytest.mark.parametrize("name", NAMES)
def test_render_matches_reference(name: str):
    """First page at 40 dpi, grey; mean absolute difference tolerates anti-aliasing and font rasterisation."""
    from PIL import Image, ImageChops

    d = fitz.open((GOLD / DOCS[name]["file"]).as_posix())
    if d.needs_pass:
        d.authenticate(PASSWORD)
    pix = d[0].get_pixmap(dpi=MANIFEST["reference_dpi"], colorspace=fitz.csGRAY, alpha=False)
    d.close()
    got = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    ref = Image.open(GOLD / "reference" / f"{name}.png").convert("L")
    assert got.size == ref.size, f"{name}: size {got.size} vs reference {ref.size}"
    diff = ImageChops.difference(got, ref)
    mean = sum(diff.getdata()) / (diff.width * diff.height)
    worst_block = max(
        sum(diff.crop((x, y, x + 8, y + 8)).getdata()) / 64
        for x in range(0, diff.width - 7, 8) for y in range(0, diff.height - 7, 8)
    )
    assert mean < 1.0 and worst_block < 40.0, f"{name}: mean {mean:.2f}, worst 8x8 block {worst_block:.1f}"


def test_generator_refuses_to_overwrite_references_without_review_flag():
    out = subprocess.run(
        [sys.executable, str(GOLD / "make_golden.py"), "--update-references"], capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 2 and "Refusing" in out.stdout


def test_manifest_covers_every_golden_pdf():
    on_disk = {p.name for p in (GOLD / "pdf").glob("*.pdf")}
    assert on_disk == {d["file"].split("/")[-1] for d in DOCS.values()}
    refs = {p.stem for p in (GOLD / "reference").glob("*.png")}
    assert refs == set(DOCS)
