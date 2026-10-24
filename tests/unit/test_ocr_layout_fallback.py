"""OCR: when automatic page layout (psm 3) finds no text, the page is read as one block (psm 6).

Measured on Windows: Burmese text that Tesseract reads well with psm 6 gave no words with psm 3."""

from __future__ import annotations

import fitz

from core.document import open_document
from core.ocr.engine import RawOcrToken
from core.ocr.pipeline import OcrOptions, run_ocr


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def detect_orientation(self, image_path):
        return {"rotate": 0, "orientation_confidence": 0.0, "script": "Unknown"}

    def run_tsv(self, image_path, *, lang="eng", psm=3, oem=1, extra_args=None, tessdata=None):
        self.calls.append(psm)
        if psm == 3:
            return []
        return [RawOcrToken(text="မြန်မာ", conf=91.0, left=10, top=10, width=200, height=40,
                            line_num=1, block_num=1, par_num=1)]


def test_empty_layout_falls_back_to_one_block(tmp_path):
    p = tmp_path / "scan.pdf"
    d = fitz.open()
    d.new_page(width=300, height=200).draw_rect(fitz.Rect(10, 10, 100, 40), fill=(0, 0, 0))
    d.save(p.as_posix())
    d.close()
    doc = open_document(p)
    engine = FakeEngine()
    try:
        res = run_ocr(doc, OcrOptions(languages="eng", pages=[0], make_searchable=False, skip_native_text=False),
                      engine=engine)
    finally:
        doc.close()
    assert engine.calls == [3, 6]
    assert "မြန်မာ" in res.pages[0].full_text
