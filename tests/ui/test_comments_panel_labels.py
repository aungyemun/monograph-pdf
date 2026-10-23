"""Comments panel: a highlight with no note shows the words it marks, each entry shows its color, and
a see-through ink stroke (free-area highlight) is listed as a Highlight, not a drawing."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-comments-labels"])
    src = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Important sentence here", fontsize=14)
    quads = page.search_for("Important sentence")
    hl = page.add_highlight_annot(quads)
    hl.set_colors(stroke=(1, 0.85, 0))
    hl.update()
    ink = page.add_ink_annot([[(72, 300), (200, 300), (300, 310)]])
    ink.set_colors(stroke=(0.2, 0.8, 0.2))
    ink.set_opacity(0.4)
    ink.update()
    doc.save(src)
    doc.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    assert w.open_path(src)
    yield w
    w.close_document(save_session=False)
    w.close()


def _entries(panel):
    out = []
    for i in range(panel.tree.topLevelItemCount()):
        group = panel.tree.topLevelItem(i)
        for j in range(group.childCount()):
            out.append(group.child(j))
    return out


def test_comment_entries_show_marked_words_color_and_highlight_label(win):
    panel = win._left.comments  # noqa: SLF001
    panel.refresh()
    items = _entries(panel)
    texts = [it.text(0) for it in items]
    assert any("Highlight" in t and "“Important sentence" in t for t in texts), texts
    assert sum(t.startswith("Highlight") for t in texts) == 2, texts  # the see-through ink stroke too
    assert all(not it.icon(0).isNull() for it in items), "each entry shows its color"
