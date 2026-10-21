"""Layout at 1366 x 768 and smaller: status bar messages, the responsive main toolbar, Navigation panel tabs,
start screen tiles, and dialogs that must fit the screen (Compress PDF, Stamps)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-small-screen"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1366, 740)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(window, tmp_path):
    from tests.unit.test_compress import _image_pdf

    src = tmp_path / "doc.pdf"
    src.write_bytes(_image_pdf(2))
    assert window.open_path(src)


def test_status_message_hides_zoom_instead_of_overlapping(window, tmp_path, qtbot):
    _open(window, tmp_path)
    bar = window._status  # noqa: SLF001
    bar.clearMessage()
    qtbot.waitUntil(lambda: bar.zoom_label.isVisible(), timeout=3000)
    bar.showMessage("Opened a document with a long name")
    assert not bar.zoom_label.isVisible()
    assert not any(s.isVisible() for s in bar.findChildren(type(bar.zoom_label)) if s.objectName() == "StatusSep")
    bar.clearMessage()
    assert bar.zoom_label.isVisible()


def test_main_toolbar_keeps_panel_buttons_visible_when_narrow(window, tmp_path, qtbot):
    from PySide6.QtCore import Qt

    _open(window, tmp_path)
    buttons = window._labelled_buttons  # noqa: SLF001
    assert buttons
    window.resize(1280, 720)
    qtbot.waitUntil(
        lambda: all(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly for b in buttons), timeout=3000
    )
    bar = window._main_bar  # noqa: SLF001
    assert bar.sizeHint().width() <= window.width()
    window.resize(1600, 900)
    qtbot.waitUntil(
        lambda: all(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon for b in buttons),
        timeout=3000,
    )


def test_navigation_tabs_all_fit_without_scroll_buttons(window):
    tabs = window._left.tabBar()  # noqa: SLF001
    assert not tabs.usesScrollButtons()
    tips = [tabs.tabToolTip(i) for i in range(tabs.count())]
    assert any(t.startswith("Comments") for t in tips)


def test_start_screen_tiles_include_new_tools(window):
    from ui.welcome_page import WelcomePage as welcome_page

    keys = [t[0] for t in welcome_page.TOOLS]
    for key in ("pdf_to_pptx", "compress", "merge", "ocr"):
        assert key in keys
    assert len(keys) % welcome_page.COLUMNS == 0  # full rows, no ragged last row


def test_compress_dialog_fits_1366x768_and_mode_selects_profile(qtbot):
    from tests.unit.test_compress import _image_pdf
    from ui.compress_dialog import PROFILES, CompressDialog

    dlg = CompressDialog(_image_pdf(2))
    qtbot.addWidget(dlg)
    dlg.show()
    hint = dlg.sizeHint()
    assert hint.height() <= 700 and hint.width() <= 1366
    for key in ("lossless", "balanced", "smallest", "target"):
        dlg.mode_buttons[key].setChecked(True)
        assert PROFILES[dlg.profile_combo.currentIndex()][1] == key
        assert dlg.mode() == key


def test_stamp_dialog_checkbox_label_not_clipped(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.stamp_dialog import StampLibraryDialog

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    dlg = StampLibraryDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    box = dlg.remove_white
    assert box.width() >= box.sizeHint().width()


def test_font_size_box_stays_readable(window):
    combo = window._font_size  # noqa: SLF001
    assert combo.minimumWidth() >= combo.fontMetrics().horizontalAdvance("72 pt") + 30


def test_dialogs_do_not_shadow_qdialog_result():
    """A dialog attribute named ``result`` hides QDialog.result(); code (and Qt's own helpers) calling
    dlg.result() then fails with "object is not callable"."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "ui"
    offenders = [f"{p.name}:{i}" for p in root.glob("*.py")
                 for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r"\bself\.result\s*=", line)]
    assert not offenders, offenders
