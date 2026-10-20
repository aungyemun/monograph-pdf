"""Word / Excel / PowerPoint → PDF through Monograph PDF, using the installed Microsoft Office.

Reference documents are created by the real Office applications (scripts/make_office_refs.ps1) with known
content; the PDFs Monograph PDF produces are inspected for page count and size, orientation, text,
searchability, table words in grid positions and the picture. Skipped when Office is not installed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from core.convert.office_bridge import office_availability
from core.convert.office_to_pdf import office_to_pdf

ROOT = Path(__file__).resolve().parents[2]
JP = "日本語のテキスト"
MIX = "Order 2026-17 注文番号 Hello"

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or not office_availability().any, reason="Microsoft Office (or LibreOffice) not available"
)


@pytest.fixture(scope="module")
def refs(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("office_refs")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "make_office_refs.ps1"), "-Out", str(out)],
        check=True, capture_output=True, timeout=240,
    )
    return out


def _convert(refs: Path, name: str, tmp: Path) -> fitz.Document:
    src = refs / name
    if not src.is_file():
        pytest.skip(f"{name} could not be created with the installed Office")
    from core.convert.office_bridge import OfficeAvailability  # noqa: F401

    avail = office_availability()
    if not avail.can_convert(src.suffix.lower()):
        pytest.skip(f"no converter for {src.suffix}")
    dest = tmp / (src.stem + src.suffix.replace(".", "_") + ".pdf")
    office_to_pdf(src, dest)
    return fitz.open(dest.as_posix())


def _words_grid(page: fitz.Page, words: list[str]) -> dict[str, tuple[float, float]]:
    found: dict[str, tuple[float, float]] = {}
    for w in page.get_text("words"):
        if w[4] in words and w[4] not in found:
            found[w[4]] = (w[0], w[1])
    return found


def test_word_to_pdf(refs, tmp_path):
    d = _convert(refs, "ref.docx", tmp_path)
    try:
        assert d.page_count == 3  # page 1, page-break page, landscape section
        sizes = [(round(p.rect.width), round(p.rect.height)) for p in d]
        assert sizes[0][0] < sizes[0][1], sizes  # portrait first page
        assert sizes[-1][0] > sizes[-1][1], sizes  # last section is landscape
        text = "\n".join(p.get_text() for p in d)
        for needle in ("Quarterly Report Heading", "Body paragraph one", JP, MIX, "Second page in landscape", "Landscape section text"):
            assert needle in text.replace("\xa0", " "), needle
        assert d[0].search_for("Quarterly Report Heading") and d[0].search_for(JP)
        # table: words sit in a 3 × 3 grid (same x per column, same y per row)
        g = _words_grid(d[0], ["Item", "Qty", "Price", "Apple", "12", "1.25", "Pear", "7", "0.80"])
        assert len(g) == 9, g
        assert abs(g["Item"][0] - g["Apple"][0]) < 3 and abs(g["Apple"][0] - g["Pear"][0]) < 3
        assert abs(g["Item"][1] - g["Qty"][1]) < 3 and abs(g["Apple"][1] - g["12"][1]) < 3
        assert g["Item"][1] < g["Apple"][1] < g["Pear"][1]
        # picture: the red square is rendered on page 1
        pix = d[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        red = sum(1 for y in range(0, pix.height, 2) for x in range(0, pix.width, 2) if pix.pixel(x, y)[:3] == (255, 0, 0))
        assert red > 20, "the picture is missing"
        assert d[0].get_images() or d[0].get_drawings()
    finally:
        d.close()


def test_excel_to_pdf(refs, tmp_path):
    d = _convert(refs, "ref.xlsx", tmp_path)
    try:
        assert d.page_count >= 1
        assert d[0].rect.width > d[0].rect.height, "the sheet was set to landscape"
        text = d[0].get_text().replace("\xa0", " ")
        for needle in ("Item", "Qty", "Price", "Apple", "Pear", "12", "1.25", "0.8", JP, MIX):
            assert needle in text, needle
        g = _words_grid(d[0], ["Item", "Apple", "Pear", "Qty", "12"])
        assert g["Item"][1] < g["Apple"][1] < g["Pear"][1]
        # Excel right-aligns numbers and left-aligns text, so only require the same column (one default column is ~48 pt wide)
        assert abs(g["Qty"][0] - g["12"][0]) < 50
        assert d[0].get_drawings(), "cell borders are missing"
    finally:
        d.close()


def test_powerpoint_to_pdf(refs, tmp_path):
    d = _convert(refs, "ref.pptx", tmp_path)
    try:
        assert d.page_count == 3
        w, h = d[0].rect.width, d[0].rect.height
        assert w / h == pytest.approx(16 / 9, rel=0.02), (w, h)
        assert all(abs(p.rect.width - w) < 1 for p in d)
        assert "Slide One Title" in d[0].get_text()
        assert JP in d[0].get_text().replace(" ", "") or d[0].search_for(JP)
        assert MIX.split()[0] in d[0].get_text()
        g = _words_grid(d[1], ["Item", "Apple", "Pear", "Qty"])
        assert len(g) == 4 and g["Item"][1] < g["Apple"][1] < g["Pear"][1]
        pix = d[2].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        blue = sum(1 for y in range(0, pix.height, 2) for x in range(0, pix.width, 2) if pix.pixel(x, y)[:3] == (30, 90, 200))
        assert blue > 100, "the picture is missing from slide 3"
    finally:
        d.close()
