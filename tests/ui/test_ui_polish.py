"""Focused UI polish: welcome state, title, toolbar tools, panels, footer."""

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
def window(qtbot):
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-ui-polish"])
    win = MainWindow()
    qtbot.addWidget(win)
    yield win
    win.close_document(save_session=False)
    win.close()


def test_welcome_visible_without_document(window):
    assert window._center_stack.currentWidget() is window._welcome  # noqa: SLF001
    assert window._welcome.isVisibleTo(window) or window._center_stack.currentIndex() == 0  # noqa: SLF001
    assert not window._inspector.isVisible()  # noqa: SLF001
    assert window.windowTitle() == "Monograph PDF"


def test_title_and_canvas_when_document_opens(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert window._center_stack.currentWidget() is window._canvas  # noqa: SLF001
    assert window.windowTitle() == "sample_text.pdf — Monograph PDF"
    assert "0.0." not in window.windowTitle()  # version not in title
    window._edit.create_text_box(  # noqa: SLF001
        0, __import__("core.editing.geometry", fromlist=["Rect"]).Rect(40, 40, 100, 30), text="x"
    )
    assert "*" in window.windowTitle()
    window.close_document(save_session=False)
    assert window.windowTitle() == "Monograph PDF"
    assert window._center_stack.currentWidget() is window._welcome  # noqa: SLF001


def test_select_tool_checkable_active_state(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    assert window.act_select_tool.isCheckable()
    window.act_text_tool.trigger()
    assert window.act_text_tool.isChecked()
    assert not window.act_select_tool.isChecked()
    window.act_select_tool.trigger()
    assert window.act_select_tool.isChecked()


def test_left_tabs_compact_when_narrow(window):
    left = window._left  # noqa: SLF001
    left.resize(120, 400)
    left._apply_tab_mode(compact=True)  # noqa: SLF001
    assert left.tabText(left._pages_tab) == ""  # noqa: SLF001
    left._apply_tab_mode(compact=False)  # noqa: SLF001
    # a label that would push the other tabs out of view is not shown (icons only, tooltips keep the names)
    tabs = left.tabBar()
    assert tabs.sizeHint().width() <= left.width()
    left.resize(300, 400)
    left._apply_tab_mode(compact=False)  # noqa: SLF001
    assert left.tabText(left._pages_tab) == "Pages"  # noqa: SLF001


def test_inspector_toggle_with_document(window):
    assert window.open_path(SAMPLES / "sample_text.pdf")
    window.act_toggle_right.setChecked(True)
    window._toggle_right_panel()  # noqa: SLF001
    assert not window._inspector.isHidden()  # noqa: SLF001
    window.act_toggle_right.setChecked(False)
    window._toggle_right_panel()  # noqa: SLF001
    assert window._inspector.isHidden()  # noqa: SLF001


def test_footer_copyright_centered(window, qtbot):
    from core.product_meta import COPYRIGHT_DISPLAY

    status = window._status  # noqa: SLF001
    status.resize(1000, 28)
    status._position_copyright()  # noqa: SLF001
    assert "Aung Ye Mun" in status.copyright_label.text()
    lab = status.copyright_label
    assert abs((lab.x() + lab.width() / 2) - status.width() / 2) <= 3
    assert COPYRIGHT_DISPLAY.startswith("©")


def test_startup_timing_hooks_write_log(tmp_path, monkeypatch):
    from core import startup_timing as st

    monkeypatch.setattr(st, "_enabled", True)
    st.reset()
    st.mark("process_entry")
    st.mark("first_visible")
    path = st.write_log(tmp_path / "startup-test.json", tag="startup")
    assert path is not None and path.is_file()
    data = path.read_text(encoding="utf-8")
    assert "first_visible" in data
