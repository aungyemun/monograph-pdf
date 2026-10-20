"""UI/UX consolidation regression: menus, panels, theme, prefs, contextual chrome."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    # Isolate preferences/recent from the real AppData location
    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-ui-consolidation"])
    win = MainWindow()
    qtbot.addWidget(win)
    yield win
    win.close_document(save_session=False)
    win.close()


def _menu_titles(window) -> list[str]:
    return [a.text().replace("&", "") for a in window.menuBar().actions()]


def test_primary_area_menus_present(window):
    menus = _menu_titles(window)
    for name in (
        "File",
        "Edit",
        "Insert",
        "Forms",
        "Organize",
        "Convert",
        "OCR",
        "Protect",
        "Sign",
        "View",
        "Help",
    ):
        assert name in menus, f"missing menu {name}: {menus}"
    assert "Combine" not in menus  # nested under Organize


def test_minimum_window_size_and_accessible_names(window):
    assert window.minimumWidth() >= 900
    assert window.minimumHeight() >= 600
    assert window.accessibleName()
    assert window._canvas.accessibleName()  # noqa: SLF001
    assert window._inspector.accessibleName()  # noqa: SLF001
    assert window._left.accessibleName()  # noqa: SLF001


def test_open_close_releases_document_and_status(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert window._document is not None  # noqa: SLF001
    assert "sample_text.pdf" in window.windowTitle()
    assert window._page_label.text().startswith("Page")  # noqa: SLF001
    window.close_document(save_session=False)
    assert window._document is None  # noqa: SLF001
    assert window._page_label.text() == "No document"  # noqa: SLF001
    assert window._progress_label.text() == ""  # noqa: SLF001


def test_left_rail_pages_and_search_tabs(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    left = window._left  # noqa: SLF001
    # Tabs are found by tooltip: in a narrow panel only the current tab shows its label
    tips = {left.tabToolTip(i).split(" ")[0]: i for i in range(left.count())}
    assert {"Page", "Bookmarks", "Find", "Embedded"} <= set(tips)
    assert left.isTabVisible(tips["Page"]) and left.isTabVisible(tips["Find"])
    # Bookmarks stay available (bookmarks can be added); Files is hidden when there are none
    assert left.isTabVisible(tips["Bookmarks"])
    assert not left.isTabVisible(tips["Embedded"])


def test_left_rail_labels_fit_the_panel(window):
    """Every label when they all fit; otherwise the current tab keeps its label and the rest show
    icons; icons only when very narrow."""
    assert window.open_path(SAMPLES / "sample_text.pdf")
    left = window._left  # noqa: SLF001
    visible = [i for i in range(left.count()) if left.isTabVisible(i)]
    for width in (left.maximumWidth(), 260, 200):
        left.resize(width, left.height())
        left._apply_tab_mode(compact=False)  # noqa: SLF001
        labelled = [i for i in visible if left.tabText(i)]
        if labelled != visible:
            assert labelled == [left.currentIndex()], width
    left.resize(200, left.height())
    left.setCurrentIndex(left._search_tab)  # noqa: SLF001
    assert [i for i in visible if left.tabText(i)] == [left._search_tab]  # noqa: SLF001
    assert left.tabText(left._search_tab) == "Search"  # noqa: SLF001
    left.resize(120, left.height())
    left._apply_tab_mode(compact=True)  # noqa: SLF001
    assert not any(left.tabText(i) for i in visible)
