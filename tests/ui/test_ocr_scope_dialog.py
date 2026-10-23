"""Recognize Text dialog: page range, and a language list ready for many languages (search, summary,
at least one language kept)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture
def dlg(qtbot, monkeypatch):
    from core.ocr import language_packs
    from ui.main_window import create_application

    create_application(["monograph-pdf-ocr-dialog"])
    langs = {"eng": "English", "jpn": "Japanese", "deu": "German", "fra": "French", "spa": "Spanish",
             "kor": "Korean", "chi_sim": "Chinese (Simplified)", "ita": "Italian"}
    monkeypatch.setattr(language_packs, "available_languages", lambda: langs)
    from ui.ocr_dialogs import OcrScopeDialog

    d = OcrScopeDialog(page_count=12, current_page=2, selected=[], languages="eng+jpn")
    qtbot.addWidget(d)
    d.show()
    return d


def test_languages_search_summary_and_one_always_kept(dlg):
    lp = dlg.languages
    assert lp.search.isVisible(), "a search box appears for a long list"
    assert lp.value() == "eng+jpn" and "English" in lp.summary.text() and "Japanese" in lp.summary.text()
    lp.search.setText("chin")
    shown = [lp.list.item(i).text() for i in range(lp.list.count()) if not lp.list.item(i).isHidden()]
    assert len(shown) == 1 and shown[0].startswith("Chinese")
    lp.search.clear()
    for i in range(lp.list.count()):
        lp.list.item(i).setCheckState(Qt.CheckState.Unchecked)
    assert lp.value() != "", "the last language cannot be unticked"
    assert len(lp.value().split("+")) == 1


def test_page_range(dlg):
    dlg.range_edit.setText("2-4, 9")
    dlg.r_range.setChecked(True)
    assert dlg.pages() == [1, 2, 3, 8]
    dlg.range_edit.setText("15")
    dlg._accept()  # noqa: SLF001
    assert dlg.isVisible() and dlg.range_error.isVisible(), "a page outside the document is refused"
    dlg.r_all.setChecked(True)
    assert dlg.pages() == list(range(12))
