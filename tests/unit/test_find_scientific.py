"""Find understands how scientific text is written: Greek letters and their names, micro and mu,
minus signs and dashes, degree signs, unit exponents, ligatures, non-Latin capitals, and pasted
text with line breaks."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "resources" / "fonts" / "NotoSans-Regular.ttf"


@pytest.fixture
def doc(tmp_path):
    from core.document import open_document

    if not FONT.is_file():
        pytest.skip("bundled Noto Sans missing")
    d = fitz.open()
    p = d.new_page()
    lines = ["the immune", "evasion of TNF-α and IL-1β at 5 μM,", "37 °C, 3 cm² and k = 0.2 s⁻¹, −20 dB",
             "Δ fold change, MÜLLER et al., Ω-3"]
    for i, line in enumerate(lines):
        p.insert_text((60, 100 + 16 * i), line, fontsize=11, fontfile=str(FONT), fontname="noto")
    path = tmp_path / "sci.pdf"
    d.save(path)
    d.close()
    document = open_document(path)
    yield document
    document.close()


@pytest.mark.parametrize("query", [
    "TNF-alpha", "tnf-α", "TNF-Α", "IL-1beta", "il1β".replace("1", "-1"), "5 µM", "5 μm", "37 °C", "37 ºC",
    "cm2", "cm²", "s-1", "s⁻¹", "Delta fold", "δ fold", "müller", "omega-3", "immune\nevasion", "immune   evasion",
])
def test_scientific_forms_are_found(doc, query):
    assert doc.search(query), query


def test_unrelated_forms_are_not_found(doc):
    assert not doc.search("TNF-beta")
    assert not doc.search("cm3")
    assert not doc.search("①")


def test_variants_are_bounded_and_typed_form_first():
    from engines.mupdf_backend import MAX_SEARCH_VARIANTS, search_variants

    v = search_variants("TNF-alpha IL-1beta −20 °C cm2")
    assert v[0] == "TNF-alpha IL-1beta −20 °C cm2" and len(v) <= MAX_SEARCH_VARIANTS
    assert search_variants("2月") == ["2月", "２月"]
    assert search_variants("") == []
