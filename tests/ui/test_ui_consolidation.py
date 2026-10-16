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
    titles = [left.tabText(i) for i in range(left.count())]
    assert "Pages" in titles
    assert "Search" in titles
    # Bookmarks / Files hidden when absent
    bm_idx = next(i for i in range(left.count()) if left.tabText(i) == "Bookmarks")
    assert not left.isTabVisible(bm_idx)


def test_contextual_toolbar_no_selection(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    window._update_context_toolbar()  # noqa: SLF001
    hint = window._context_hint.text().lower()  # noqa: SLF001
    assert "create" in hint or "navigate" in hint


def test_inspector_selection_aware(window):
    from core.editing.geometry import Rect

    assert window.open_path(SAMPLES / "sample_text.pdf")
    window._refresh_inspector()  # noqa: SLF001
    # No selection → document summary, not empty
    assert window._inspector._form.rowCount() > 0  # noqa: SLF001

    window._edit.create_text_box(0, Rect(40, 40, 120, 30), text="Ctx")  # noqa: SLF001
    oid = next(iter(window._edit.objects))  # noqa: SLF001
    window._edit.selection = [oid]  # noqa: SLF001
    window._refresh_inspector()  # noqa: SLF001
    # Text selection exposes style editors
    assert window._inspector._box is not None  # noqa: SLF001


def test_theme_switch_applies_stylesheet(window):
    from PySide6.QtWidgets import QApplication

    from ui.theme import resolve_theme

    app = QApplication.instance()
    assert app is not None
    window._set_theme("dark")  # noqa: SLF001
    assert resolve_theme("dark") == "dark"
    assert "dark" in (app.styleSheet()[:200].lower() or app.property("monograph_pdf_theme") or "")
    assert app.property("monograph_pdf_theme") == "dark"
    window._set_theme("light")  # noqa: SLF001
    assert app.property("monograph_pdf_theme") == "light"


def test_preferences_persist_outside_project_root(window, tmp_path):
    from core.user_prefs import UserPreferences, user_data_dir

    data_dir = user_data_dir()
    assert ROOT not in data_dir.parents and data_dir != ROOT
    assert str(tmp_path) in str(data_dir)

    window.resize(1100, 720)
    window._persist_preferences()  # noqa: SLF001
    loaded = UserPreferences.load()
    assert loaded.window_width >= 900
    assert loaded.path().is_file()
    assert loaded.path().parent == data_dir


def test_status_bar_widgets_present(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert window._zoom_label.text()  # noqa: SLF001
    assert window._dirty_label.text() in ("Saved", "Modified", "")  # noqa: SLF001
    window.set_analysis_progress("Working…")
    assert window._progress_label.text() == "Working…"  # noqa: SLF001
    window.clear_analysis_progress()
    assert window._progress_label.text() == ""  # noqa: SLF001
