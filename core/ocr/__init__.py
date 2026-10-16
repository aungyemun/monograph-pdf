"""Fully offline OCR workflow (Tesseract + local tessdata)."""

from core.ocr.analysis import EditableAnalysis, analyze_for_editable
from core.ocr.engine import OcrEngine, OcrUnavailableError, get_ocr_engine
from core.ocr.pipeline import OcrCancelled, OcrOptions, OcrPageResult, OcrWord, run_ocr

__all__ = [
    "EditableAnalysis",
    "OcrCancelled",
    "OcrEngine",
    "OcrOptions",
    "OcrPageResult",
    "OcrUnavailableError",
    "OcrWord",
    "analyze_for_editable",
    "get_ocr_engine",
    "run_ocr",
]
