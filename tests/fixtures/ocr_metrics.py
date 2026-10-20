"""OCR scoring: similarity ratio (kept for regression comparison), CER and WER.

Normalisation (stated, applied identically to reference and OCR output):
  * Unicode NFKC (full-width digits/Latin → ASCII, half-width kana → full-width)
  * all whitespace removed for CER and the similarity ratio (OCR spacing around CJK is not meaningful)
  * case is kept (case errors are errors)
  * WER tokens = whitespace-separated words of the NFKC text, so it is only meaningful for space-delimited
    scripts. For Japanese only CER is reported; no tokenizer is assumed.
CER = Levenshtein(ref_chars, hyp_chars) / len(ref_chars);  WER likewise over words.
"""

from __future__ import annotations

import difflib
import re
import unicodedata


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def chars(text: str) -> str:
    return re.sub(r"\s+", "", _nfkc(text))


def words(text: str) -> list[str]:
    return _nfkc(text).split()


def levenshtein(a, b) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def similarity(ref: str, hyp: str) -> float:
    return difflib.SequenceMatcher(None, chars(ref), chars(hyp)).ratio()


def cer(ref: str, hyp: str) -> float:
    r, h = chars(ref), chars(hyp)
    return levenshtein(r, h) / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    return levenshtein(r, h) / max(1, len(r))
