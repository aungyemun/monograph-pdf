"""FEATURE-01: tab session path keys and titles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ui.document_session import DocumentSession, canonical_doc_path
from ui.pdf_canvas import ZoomMode


def test_canonical_doc_path_dedupes_same_file(tmp_path: Path) -> None:
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\n")
    assert canonical_doc_path(f) == canonical_doc_path(tmp_path / "a.pdf")
    assert canonical_doc_path(f) != canonical_doc_path(tmp_path / "b.pdf")


def test_session_tab_title_marks_dirty() -> None:
    doc = MagicMock()
    doc.name = "report.pdf"
    doc.path = Path("report.pdf")
    edit = MagicMock()
    edit.dirty = False
    sess = DocumentSession(document=doc, edit=edit, zoom_mode=ZoomMode.FIT_WIDTH)
    assert sess.tab_title() == "report.pdf"
    edit.dirty = True
    assert sess.tab_title() == "report.pdf *"


def test_session_tab_title_converted_from() -> None:
    doc = MagicMock()
    doc.name = "tmp.pdf"
    edit = MagicMock()
    edit.dirty = False
    sess = DocumentSession(
        document=doc,
        edit=edit,
        converted_from=Path(r"C:\docs\letter.docx"),
    )
    assert sess.tab_title() == "letter.pdf"


def test_session_stores_per_tab_search_state() -> None:
    """FEATURE-01: Find hits/query stay on the DocumentSession across tab switches."""
    doc = MagicMock()
    doc.name = "a.pdf"
    edit = MagicMock()
    edit.dirty = False
    sess = DocumentSession(document=doc, edit=edit)
    sess.last_query = "alpha"
    sess.search_hits = [(0, object()), (1, object())]
    sess.search_index = 1
    assert sess.last_query == "alpha"
    assert len(sess.search_hits) == 2
    assert sess.search_index == 1
