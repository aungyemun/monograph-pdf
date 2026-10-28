"""macOS parity: updater line, Finder/Dock file opens, app-menu roles, default PDF app, dark mode."""

import sys
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QAction, QFileOpenEvent

from app import file_open
from core.updates import manager


@pytest.fixture
def qapp():
    from app.qt_app import create_application

    return create_application(["monograph-pdf-macos-parity"])


@pytest.fixture
def main_window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-macos-parity"])
    win = MainWindow()
    qtbot.addWidget(win)
    yield win
    win.close_document(save_session=False)
    win.close()


def test_mac_build_is_never_offered_the_windows_update_line(monkeypatch):
    from ui import update_dialogs

    monkeypatch.setattr(update_dialogs.sys, "platform", "darwin")
    shown = []
    ctl = SimpleNamespace(_worker=None, _checked=lambda res, manual: shown.append((res, manual)),
                          _window=SimpleNamespace(_prefs=None))
    update_dialogs.UpdateController.check(ctl, manual=True)  # would start a network worker otherwise
    assert shown[0][0].status == manager.UpdateStatus.NOT_CONFIGURED
    assert shown[0][0].message == manager.MACOS_UPDATES_TEXT
    update_dialogs.UpdateController.maybe_auto_check(ctl)  # prefs=None: returns before reading them


class _Window:
    def __init__(self):
        self.requests = []

    def handle_instance_request(self, files):
        self.requests.append(list(files))


def test_file_open_events_queue_until_window_then_arrive_together(qapp):
    router = file_open.FileOpenRouter()
    for path in ("/tmp/a b.pdf", "/tmp/日本語.pdf"):
        assert router.eventFilter(None, QFileOpenEvent(path)) is True
    window = _Window()
    router.attach(window)
    QCoreApplication.processEvents()
    assert window.requests == [["/tmp/a b.pdf", "/tmp/日本語.pdf"]]


def test_file_open_after_start_is_handed_to_running_window(qapp):
    router = file_open.FileOpenRouter()
    window = _Window()
    router.attach(window)
    router.eventFilter(None, QFileOpenEvent("/tmp/x.pdf"))
    QCoreApplication.processEvents()
    assert window.requests == [["/tmp/x.pdf"]]


def test_application_menu_roles(main_window):
    w = main_window
    assert w.act_about.menuRole() == QAction.MenuRole.AboutRole
    assert w.act_settings.menuRole() == QAction.MenuRole.PreferencesRole
    assert w.act_exit.menuRole() == QAction.MenuRole.QuitRole
    assert w.act_check_updates.menuRole() == QAction.MenuRole.ApplicationSpecificRole


def test_frozen_mac_default_app_uses_launch_services(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from core import macos_desktop
    from ui import main_window

    monkeypatch.setattr(main_window, "sys", SimpleNamespace(platform="darwin", frozen=True))
    monkeypatch.setattr(macos_desktop, "set_default_pdf_handler", lambda: (True, "done"))
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    main_window.MainWindow._make_default_app(SimpleNamespace())
    assert messages == ["done"]


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreServices")
def test_launch_services_query_is_readable():
    from core import macos_desktop

    handler = macos_desktop.default_pdf_handler()
    assert handler is None or "." in handler


def test_mac_dark_mode_follows_system_scheme(monkeypatch):
    from ui import theme

    monkeypatch.setattr(theme.sys, "platform", "darwin")
    monkeypatch.setattr(theme.app_env, "get", lambda key, *a: "1" if key == "FORCE_DARK" else None)
    assert theme.detect_system_dark() is True


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS key mapping")
def test_mac_shortcuts_avoid_system_reserved_keys(main_window):
    from PySide6.QtGui import QKeySequence

    w = main_window
    tab_keys = {k.toString() for k in w.act_next_tab.shortcuts()}
    assert "Ctrl+Tab" not in tab_keys  # Command+Tab is the system app switcher
    assert {"Meta+Tab", "Ctrl+}"} <= tab_keys
    assert QKeySequence("F11") not in w.act_fullscreen.shortcuts()  # Show Desktop on macOS
    assert w.act_fullscreen.shortcuts()
    assert "⌘" in w._page_edit.toolTip() and "Ctrl+G" not in w._page_edit.toolTip()


def test_leaving_zoom_box_unchanged_keeps_text_box_open_and_fit_mode(main_window, tmp_path):
    # On macOS the toolbar zoom box has keyboard focus when the window opens; moving focus into a
    # text box fired editingFinished, re-applied the same zoom and closed the new editor at once.
    import shutil
    from pathlib import Path

    from core.editing.geometry import Rect

    w = main_window
    src = tmp_path / "work.pdf"
    shutil.copy(Path(__file__).resolve().parents[1] / "samples" / "sample_text.pdf", src)
    assert w.open_path(src)
    inner = w._canvas._canvas
    mode = inner.zoom_mode
    box = w._edit.create_text_box(0, Rect(72, 72, 200, 40), text="Hello")
    assert inner.open_text_editor(box.object_id)
    w._toolbar_zoom.lineEdit().editingFinished.emit()  # focus left the box, text unchanged
    assert inner._text_editor is not None
    assert inner.zoom_mode == mode
    w._toolbar_zoom.setEditText("150%")  # a typed new zoom still applies
    w._toolbar_zoom.lineEdit().editingFinished.emit()
    assert abs(w._canvas.zoom - 1.5) < 1e-6


def test_mac_question_boxes_get_a_visible_icon_only_on_cocoa(qapp, monkeypatch):
    # Qt's macOS question glyph is near-black and vanishes on the dark theme
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QMessageBox

    from ui import theme

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Question)
    theme.mac_question_icon(box)  # offscreen platform: unchanged
    assert box.icon() == QMessageBox.Icon.Question
    pm = QPixmap(64, 64)
    pm.fill()
    monkeypatch.setattr(theme.sys, "platform", "darwin")
    cocoa = SimpleNamespace(platformName=lambda: "cocoa", windowIcon=lambda: QIcon(pm))
    # replace the module's name only — never patch Qt's own class (it is shared by every test)
    monkeypatch.setattr(theme, "QGuiApplication", SimpleNamespace(instance=lambda: cocoa))
    theme.mac_question_icon(box)
    assert box.icon() == QMessageBox.Icon.NoIcon and not box.iconPixmap().isNull()
    warn = QMessageBox()
    warn.setIcon(QMessageBox.Icon.Warning)
    theme.mac_question_icon(warn)  # other icons are visible already
    assert warn.icon() == QMessageBox.Icon.Warning
