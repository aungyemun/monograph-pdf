"""OCR regression on the generated corpus (tests/fixtures/ocr_corpus.py): CER ceilings per case.

The ceilings sit a little above what the bundled engine achieved when they were set (see
reports/audit/MONOGRAPH_PDF_COMPREHENSIVE_QA_REPORT.md). They catch regressions; they are not accuracy
claims. The corpus is synthetic (rendered, then blurred / noised / skewed), not real scans."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.document import open_document
from core.ocr.engine import get_ocr_engine
from core.ocr.paths import ocr_ready
from core.ocr.pipeline import OcrOptions, run_ocr
from tests.fixtures import ocr_corpus
from tests.fixtures import ocr_metrics as M

CER_CEILING = {
    "en_paragraph": 0.02, "en_small_8pt": 0.03, "en_scientific": 0.03, "en_math_ascii": 0.12, "en_table": 0.05,
    "jp_paragraph": 0.10, "jp_with_ri": 0.05, "mixed_en_jp": 0.05, "en_rotated_90": 0.05, "en_lowres_100dpi": 0.05,
    "en_noisy_skewed": 0.05, "jp_noisy": 0.10,
}


@pytest.fixture(scope="module")
def engine():
    ok, detail = ocr_ready()
    if not ok:
        pytest.skip(f"OCR engine unavailable: {detail}")
    return get_ocr_engine(force_reload=True)


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    return {c.name: c for c in ocr_corpus.build(tmp_path_factory.mktemp("ocr_corpus"))}


@pytest.mark.parametrize("name", sorted(CER_CEILING))
def test_cer_stays_under_its_ceiling(engine, cases, name):
    c = cases[name]
    pdf = open_document(c.path)
    try:
        res = run_ocr(pdf, OcrOptions(languages=c.lang, pages=[0], skip_native_text=False, make_searchable=False), engine=engine)
    finally:
        pdf.close()
    hyp = " ".join(p.full_text for p in res.pages)
    assert M.cer(c.reference, hyp) <= CER_CEILING[name], f"{name}: CER {M.cer(c.reference, hyp):.3f}, got {hyp!r}"


def test_metric_definitions():
    assert M.cer("abc", "abc") == 0 and M.cer("abc", "abd") == pytest.approx(1 / 3) and M.cer("abc", "") == 1
    assert M.cer("日本語", "本語") == pytest.approx(1 / 3)
    assert M.wer("the cat sat", "the cat") == pytest.approx(1 / 3)
    assert M.chars("Ａ Ｂ１") == "AB1"  # NFKC: full-width → ASCII, whitespace removed


def test_leading_nichi_is_lost_only_by_page_segmentation_on_a_nearly_empty_page(engine, tmp_path):
    """Root cause of the 日 miss in tests/samples/ocr_japanese_scan.pdf: the glyph is recognised when the
    line is given to the engine as a line (psm 7) or block (psm 6); the automatic layout analysis (psm 3)
    drops it on a page holding just two short lines."""
    import fitz

    f = fitz.Font("cjk")
    d = fitz.open()
    p = d.new_page(width=420, height=120)
    p.insert_font(fontname="jpf", fontbuffer=f.buffer)
    p.insert_text((20, 70), "日本語", fontsize=28, fontname="jpf")
    img = tmp_path / "nichi.png"
    p.get_pixmap(dpi=200, alpha=False).save(img.as_posix())
    assert [t.text for t in engine.run_tsv(img, lang="jpn", psm=7)] == ["日", "本", "語"]
    assert "日" not in "".join(t.text for t in engine.run_tsv(img, lang="jpn", psm=3))
