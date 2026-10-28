"""Find Next / Find Previous make the page of the match the current page.

Regression (0.5.0 validation): Find scrolled a match into view with a minimal scroll, and the scroll
handler then set the current page back to the page in the middle of the window — one match behind.
Page commands, Select All and the page box use the current page, so they acted on the wrong page.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def doc_window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-find-focus"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 900)
    win.show()
    src = tmp_path / "work.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())  # 3 pages, "Lorem" once on each
    assert win.open_path(src)
    yield win
    win.close_document(save_session=False)
    win.close()


def _search(qtbot, win, text: str) -> None:
    from PySide6.QtCore import Qt

    win._search_edit.setText(text)  # noqa: SLF001
    qtbot.keyClick(win._search_edit, Qt.Key.Key_Return)  # noqa: SLF001
    qtbot.waitUntil(lambda: len(win._search_hits) == 3, timeout=5000)  # noqa: SLF001


def test_find_next_and_previous_follow_the_match_page(qtbot, doc_window):
    win = doc_window
    _search(qtbot, win, "Lorem")
    assert [p for p, _ in win._search_hits] == [0, 1, 2]  # noqa: SLF001
    seen = [win._canvas.focus_page]  # noqa: SLF001
    for step in (win._find_next, win._find_next, win._find_prev):  # noqa: SLF001
        step()
        qtbot.wait(30)
        seen.append(win._canvas.focus_page)  # noqa: SLF001
    assert seen == [0, 1, 2, 1]


def test_current_page_after_find_survives_pending_events(qtbot, doc_window):
    """Late scroll events after the jump must not move the current page back."""
    win = doc_window
    _search(qtbot, win, "Lorem")
    win._find_next()  # noqa: SLF001
    win._find_next()  # noqa: SLF001
    qtbot.wait(200)
    assert win._canvas.focus_page == 2  # noqa: SLF001
    assert win._search_index == 2  # noqa: SLF001
