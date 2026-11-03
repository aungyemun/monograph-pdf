"""Pasting into a form field keeps bold, italic and real colours, not the source's font or size.

Before 0.5.1 RC 3, text copied from a web page, chat or word processor carried that program's
font (for example "Segoe UI") and size into the field. Japanese in a Latin-only font was then
drawn in a gothic fallback face that looked bold beside the rest of the form.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

WEB = (
    '<p style="font-family:\'Segoe UI\';font-size:11pt;color:#1f1f1f">'
    "東浦町へ戻り、招へい人宅に滞在。</p>"
)


@pytest.fixture
def editor(qtbot):
    from ui.pdf_canvas import _FieldTextEdit

    ed = _FieldTextEdit()
    qtbot.addWidget(ed)
    ed.px_per_pt = 1.5
    ed.base_pt = 7.0
    return ed


def _paste(ed, html: str) -> None:
    from PySide6.QtCore import QMimeData

    data = QMimeData()
    data.setHtml(html)
    from PySide6.QtGui import QTextDocument

    probe = QTextDocument()
    probe.setHtml(html)
    data.setText(probe.toPlainText())
    ed.insertFromMimeData(data)


def test_web_text_takes_field_font_size_and_colour(editor):
    from ui.rich_field_text import runs_from_document

    _paste(editor, WEB)
    text, runs = runs_from_document(editor.document())
    assert text == "東浦町へ戻り、招へい人宅に滞在。"
    assert runs == []  # nothing of the source's look is kept: same as typed text


def test_bold_italic_and_real_colour_are_kept(editor):
    from ui.rich_field_text import runs_from_document

    _paste(
        editor,
        '<span style="font-family:Arial;font-size:14pt">普通</span>'
        '<b style="font-family:Arial;color:#d00000">強調</b><i>斜体</i>',
    )
    text, runs = runs_from_document(editor.document())
    assert text == "普通強調斜体"
    assert all(r["family"] is None and r["size"] is None for r in runs)
    by_text = {r["text"]: r for r in runs}
    assert by_text["強調"]["bold"] is True and by_text["強調"]["color"] == "#d00000"
    assert by_text["斜体"]["italic"] is True and by_text["斜体"]["color"] is None


def test_paste_continues_the_size_of_the_words_around_it(editor):
    """Words the user set to 7 pt stay 7 pt when web text is pasted after them (like typing)."""
    from PySide6.QtGui import QTextCursor

    from core.forms.rich_text import make_run
    from ui.rich_field_text import apply_runs, runs_from_document

    editor.setPlainText("滞在。")
    apply_runs(editor.document(), [make_run("滞在。", size=7.0)], editor.px_per_pt)
    cur = editor.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cur)
    _paste(editor, WEB)
    text, runs = runs_from_document(editor.document())
    assert text == "滞在。東浦町へ戻り、招へい人宅に滞在。"
    assert len(runs) == 1 and runs[0]["size"] == 7.0 and runs[0]["family"] is None
