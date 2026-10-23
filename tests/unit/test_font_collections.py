"""Fonts installed as collections (.ttc: MS Mincho, MS Gothic, Meiryo, Yu Gothic, SimSun …) are
embedded in saved PDFs — only the requested face, subset — instead of being replaced by a built-in
font ("font collections (.ttc) are not embedded")."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
import pytest

pytest.importorskip("fontTools")

from core.editing import system_fonts as sf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "resources" / "fonts"


@pytest.fixture
def collection(tmp_path) -> Path:
    """A two-face collection made from the bundled Noto Sans and Noto Serif."""
    from fontTools.ttLib import TTCollection, TTFont

    coll = TTCollection()
    coll.fonts = [TTFont(str(FONTS / "NotoSans-Regular.ttf")), TTFont(str(FONTS / "NotoSerif-Regular.ttf"))]
    path = tmp_path / "noto.ttc"
    coll.save(str(path))
    return path


def test_the_requested_face_is_found_in_a_collection(collection):
    assert sf.collection_index(str(collection), "Noto Sans") == 0
    assert sf.collection_index(str(collection), "noto serif") == 1
    assert sf.collection_index(str(collection), "Noto Sans", bold=True) is None  # no bold face in it
    assert sf.embedding_verdict(str(collection), 1) == (True, "")


def test_a_face_of_a_collection_is_embedded_as_a_subset(collection):
    font = sf._load_face(str(collection), 1)  # noqa: SLF001
    assert sf.is_system_font(font)
    doc = fitz.open()
    page = doc.new_page()
    tw = fitz.TextWriter(page.rect)
    tw.append((72, 100), "Serif from a collection", font=font, fontsize=14)
    tw.write_text(page)
    doc.subset_fonts()
    back = fitz.open("pdf", doc.tobytes(garbage=3, deflate=True))
    assert back[0].get_text().strip() == "Serif from a collection"
    assert any("NotoSerif" in f[3].replace(" ", "") for f in back[0].get_fonts())


def test_restricted_faces_are_still_refused():
    assert sf._check_fstype(2)[0] is False  # noqa: SLF001
    assert sf._check_fstype(0x0200)[0] is False  # noqa: SLF001
    assert sf._check_fstype(8) == (True, "")  # noqa: SLF001


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows fonts")
def test_ms_mincho_is_embedded_on_save(tmp_path):
    if sf.find_font_file("MS Mincho") is None:
        pytest.skip("MS Mincho is not installed")
    sf.take_notes()
    font = sf.load("MS Mincho")
    assert font is not None, sf.take_notes()
    assert sf.take_notes() == {}, "no 'similar font was used' note for MS Mincho"
    p = sf.load("MS PMincho")
    assert p is not None and p is not font, "the proportional face of the same collection"
