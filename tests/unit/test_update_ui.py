"""Update and problem-report user interface (offscreen Qt; no network)."""

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox, QPushButton  # noqa: E402

from core.diagnostics import EventId  # noqa: E402
from core.diagnostics import report as reports  # noqa: E402
from core.updates import manager, staging  # noqa: E402
from core.updates.install_target import InstallTarget  # noqa: E402
from core.updates.manager import CheckResult, UpdateStatus  # noqa: E402
from core.updates.manifest import parse_and_verify  # noqa: E402
from core.updates.state import UpdateState  # noqa: E402
from tests.fixtures.update_fixtures import make_config, manifest_bytes, setup_bytes, signed_fields  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / "Updates"))
    monkeypatch.setenv("MONOGRAPH_PDF_DIAGNOSTICS_DIR", str(tmp_path / "Diagnostics"))
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "UserData"))  # fresh preferences per test


@pytest.fixture
def window(qtbot):
    from ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def boxes(monkeypatch):
    seen = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda parent, title, text, *a, n=name, **k: seen.append((n, title, text))))
    return seen


def _available(version="0.3.1", notes="Fixes\n<b>not bold</b>"):
    rel = parse_and_verify(manifest_bytes(signed_fields(version, release_notes=notes)), make_config())
    return CheckResult(UpdateStatus.AVAILABLE, "available", "0.3.0", rel, int(time.time()))


def test_menus_offer_check_for_updates_and_settings(window):
    # menu letters are reassigned so that every item in a menu has its own (Alt+letter)
    assert window.act_check_updates.text().replace("&", "") == "Check for Updates…"
    assert window.act_settings.text().replace("&", "") == "Settings…"
    help_menu = [a.menu() for a in window.menuBar().actions() if a.text() == "&Help"][0]
    assert window.act_check_updates in help_menu.actions()
    file_menu = [a.menu() for a in window.menuBar().actions() if a.text() == "&File"][0]
    assert window.act_settings in file_menu.actions()


def test_settings_defaults_are_private(window):
    from ui.settings_dialog import SettingsDialog

    assert window._updates.configured  # the shipped configuration trusts the production key
    dlg = SettingsDialog(window._prefs, window._updates, window)
    page = dlg.updates
    # automatic checks are optional and off by default; a manual check is available
    assert not page.auto.isChecked() and page.interval.currentData() == 24 and page.stable.isChecked()
    assert page.last.text() == "Never" and page.status.text() == "Not checked yet"
    assert page.check_now.isEnabled() and page.auto.isEnabled()
    assert "Nothing is downloaded or installed" in page.auto.toolTip()


def test_settings_without_a_usable_configuration_say_so(window, monkeypatch):
    from ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(window._updates, "_config", make_config(enabled=False))
    page = SettingsDialog(window._prefs, window._updates, window).updates
    assert not page.check_now.isEnabled() and not page.auto.isEnabled()
    assert page.status.text() == "Not configured for this build"


def test_start_up_makes_no_network_request(window, monkeypatch):
    from core.updates import net

    calls = []
    monkeypatch.setattr(net, "fetch_bytes", lambda *a, **k: calls.append(a) or b"")
    monkeypatch.setattr(net, "download", lambda *a, **k: calls.append(a))
    window.after_startup()
    window._updates.maybe_auto_check()  # automatic checks are off by default
    assert calls == [] and window._updates.last is None


def test_settings_apply_when_configured(window, monkeypatch):
    from ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(window._updates, "_config", make_config())
    dlg = SettingsDialog(window._prefs, window._updates, window)
    page = dlg.updates
    assert page.check_now.isEnabled()
    page.auto.setChecked(True)
    page.interval.setCurrentIndex(page.interval.findData(168))
    page.pre.setChecked(True)
    dlg.accept()
    assert window._prefs.update_auto_check and window._prefs.update_interval_hours == 168
    assert window._prefs.update_channel == "prerelease"


def test_update_available_dialog_content_and_two_actions(qtbot):
    from ui.update_dialogs import UpdateAvailableDialog

    dlg = UpdateAvailableDialog(_available())
    qtbot.addWidget(dlg)
    from PySide6.QtWidgets import QLabel

    texts = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
    assert "MONOGRAPH PDF UPDATE AVAILABLE" in texts and "0.3.0" in texts and "0.3.1" in texts
    assert [b.text() for b in dlg.findChildren(QPushButton)] == ["Update Now", "Remind Me Later"]
    from PySide6.QtWidgets import QTextBrowser

    notes = dlg.findChild(QTextBrowser)
    assert "<b>not bold</b>" in notes.toPlainText()  # release notes are shown as text, never as HTML


def test_update_now_disabled_with_a_reason_when_not_installable(qtbot):
    from ui.update_dialogs import UpdateAvailableDialog

    dlg = UpdateAvailableDialog(_available(), install_block="This copy runs from source code")
    qtbot.addWidget(dlg)
    assert not dlg.update_now.isEnabled()


@pytest.mark.parametrize("status", [UpdateStatus.UNAVAILABLE, UpdateStatus.VERIFICATION_FAILED])
def test_manual_check_never_claims_up_to_date_when_it_could_not_verify(window, boxes, monkeypatch, status):
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda box: shown.append(
        (box.icon(), box.text(), box.informativeText(), [b.text() for b in box.buttons()])) or 0)
    window._updates._checked(CheckResult(status, "simulated", "0.3.0"), True)
    assert boxes == [] and len(shown) == 1
    icon, text, informative, buttons = shown[0]
    assert icon == QMessageBox.Icon.Warning and status.label in text and "Up to date" not in text
    assert "Nothing was downloaded or installed" in informative or "nothing was downloaded or installed" in informative
    assert "Open Releases Page" in buttons


@pytest.mark.parametrize("click_open", [False, True])
def test_not_configured_offers_the_releases_page_only_when_asked(window, boxes, monkeypatch, click_open):
    from PySide6.QtGui import QDesktopServices

    from ui import update_dialogs

    shown, opened = [], []

    def fake_exec(box):
        shown.append((box.windowTitle(), box.text(), box.informativeText(), [b.text() for b in box.buttons()]))
        if click_open:
            next(b for b in box.buttons() if b.text() == "Open Releases Page").click()
        else:
            box.button(QMessageBox.StandardButton.Ok).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString())))
    window._updates._checked(CheckResult(UpdateStatus.NOT_CONFIGURED, "Download from GitHub Releases.", "0.3.0"), True)
    assert boxes == [] and len(shown) == 1
    title, text, informative, buttons = shown[0]
    assert title == "Check for Updates" and "Updates not configured" in text and "Up to date" not in text
    assert "0.3.0" in informative and "Open Releases Page" in buttons
    # nothing is opened unless the user clicks; then only the official Releases page
    assert opened == ([update_dialogs.RELEASES_PAGE] if click_open else [])


def test_status_after_a_check_does_not_repeat_updates(window, monkeypatch):
    from ui.about_dialog import AboutDialog
    from ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(window._updates, "show_not_configured", lambda res: None)
    about = AboutDialog(window, updates=window._updates)
    settings = SettingsDialog(window._prefs, window._updates, window)
    about._updates.status_changed.connect(about._update_status)
    window._updates._checked(CheckResult(UpdateStatus.NOT_CONFIGURED, "x", "0.3.0"), True)
    assert about._build_info.text().endswith("Updates: Not configured for this build")
    assert "Updates: Updates" not in about._build_info.text()
    assert settings.updates.status.text() == "Not configured for this build"
    assert window._updates.status_text() == "Not configured for this build"


def test_automatic_check_is_quiet_unless_an_update_is_available(window, boxes, monkeypatch):
    shown = []
    monkeypatch.setattr(window._updates, "show_available", lambda res: shown.append(res))
    for status in (UpdateStatus.UP_TO_DATE, UpdateStatus.UNAVAILABLE, UpdateStatus.VERIFICATION_FAILED):
        window._updates._checked(CheckResult(status, "x", "0.3.0"), False)
    assert boxes == [] and shown == []
    window._updates._checked(_available(), False)
    assert len(shown) == 1


def test_remind_me_later_postpones_that_version(window, monkeypatch):
    res = _available()
    window._updates._remind_later(res)
    st = UpdateState.load()
    assert st.remind_version == "0.3.1" and st.remind_after > time.time() + 3600
    shown = []
    monkeypatch.setattr(window._updates, "show_available", lambda r: shown.append(r))
    window._updates._checked(res, False)  # automatic: postponed
    assert shown == []
    window._updates._checked(res, True)   # manual: shown
    assert len(shown) == 1


def test_startup_is_offline_unless_automatic_checks_are_switched_on(window, monkeypatch):
    from app.offline_guard import NetworkAttempts

    monkeypatch.setattr(window._updates, "_config", make_config())
    started = []
    monkeypatch.setattr(window._updates, "check", lambda **k: started.append(k))
    with NetworkAttempts() as guard:
        window.after_startup()
    assert started == [] and guard.attempts == []
    window._prefs.update_auto_check = True
    window.after_startup()
    assert started == [{"manual": False}]
    started.clear()
    st = UpdateState.load()
    st.last_check = int(time.time())
    st.save()
    window.after_startup()  # checked recently: not due
    assert started == []


def test_update_now_downloads_verifies_asks_about_changes_then_hands_off(window, monkeypatch, tmp_path, qtbot):
    import ui.update_dialogs as ud

    data = setup_bytes("0.3.1")
    res = CheckResult(UpdateStatus.AVAILABLE, "", "0.3.0",
                      parse_and_verify(manifest_bytes(signed_fields(data=data)), make_config()))
    folder = tmp_path / "Monograph PDF"
    folder.mkdir()
    target = InstallTarget(True, "", folder, "user", "0.3.0", "")
    order = []
    monkeypatch.setattr(ud.install_target, "detect", lambda: target)

    def fake_download(cfg, release, tgt, cancel, progress=None, **kw):
        order.append("download+verify")
        sd = staging.new_staging("0.3.1")
        sd.installer.write_bytes(data)
        return sd

    monkeypatch.setattr(ud.manager, "download_and_verify", fake_download)
    monkeypatch.setattr(window, "_confirm_unsaved", lambda verb: order.append(f"unsaved:{verb}") or True)
    monkeypatch.setattr(ud.manager, "hand_off", lambda sd, rel, tgt, lock: order.append("hand_off") or 1)
    monkeypatch.setattr(window, "close_for_update", lambda: order.append("close"))
    window._updates.start_update(res)
    assert order == ["download+verify", "unsaved:updating", "hand_off", "close"]


def test_cancelling_at_the_unsaved_changes_prompt_removes_the_download(window, monkeypatch, tmp_path):
    import ui.update_dialogs as ud

    data = setup_bytes("0.3.1")
    res = CheckResult(UpdateStatus.AVAILABLE, "", "0.3.0",
                      parse_and_verify(manifest_bytes(signed_fields(data=data)), make_config()))
    folder = tmp_path / "app"
    folder.mkdir()
    monkeypatch.setattr(ud.install_target, "detect", lambda: InstallTarget(True, "", folder, "user", "0.3.0", ""))
    made = []

    def fake_download(*a, **k):
        sd = staging.new_staging("0.3.1")
        sd.installer.write_bytes(data)
        made.append(sd)
        return sd

    monkeypatch.setattr(ud.manager, "download_and_verify", fake_download)
    monkeypatch.setattr(window, "_confirm_unsaved", lambda verb: False)
    called = []
    monkeypatch.setattr(ud.manager, "hand_off", lambda *a: called.append(1))
    window._updates.start_update(res)
    assert called == [] and not made[0].path.exists()
    assert staging.UpdateLock().acquire()  # the lock was released


def test_update_refused_for_a_copy_that_is_not_the_registered_installation(window, boxes, monkeypatch):
    import ui.update_dialogs as ud

    monkeypatch.setattr(ud.install_target, "detect", lambda: InstallTarget(False, "ambiguous installation"))
    downloads = []
    monkeypatch.setattr(ud.manager, "download_and_verify", lambda *a, **k: downloads.append(1))
    window._updates.start_update(_available())
    assert downloads == [] and "ambiguous" in boxes[-1][2]


def test_failed_download_reports_the_real_reason(window, boxes, monkeypatch, tmp_path):
    import ui.update_dialogs as ud

    folder = tmp_path / "app"
    folder.mkdir()
    monkeypatch.setattr(ud.install_target, "detect", lambda: InstallTarget(True, "", folder, "user", "0.3.0", ""))

    def failing(*a, **k):
        raise manager.UpdateError("The downloaded installer does not match the signed update information", "verify")

    monkeypatch.setattr(ud.manager, "download_and_verify", failing)
    window._updates.start_update(_available())
    assert boxes[-1][1] == "Update not installed" and "does not match" in boxes[-1][2]


def _sending_config():
    from core.diagnostics.client import ReportingConfig

    return ReportingConfig(True, "https://reports.example.invalid/v1")


def test_error_report_dialog_has_exactly_two_decision_buttons(qtbot):
    from ui.error_report_dialog import DONT_SEND, SEND, ErrorReportDialog

    dlg = ErrorReportDialog(reports.build(EventId.PDF_SAVE_FAILED, events=[]), summary="Save failed",
                            config=_sending_config())
    qtbot.addWidget(dlg)
    assert sorted(b.text() for b in dlg.findChildren(QPushButton)) == sorted([DONT_SEND, SEND])
    from PySide6.QtWidgets import QPlainTextEdit

    details = dlg.findChild(QPlainTextEdit)
    assert details.isReadOnly() and "error_code: PDF_SAVE_FAILED" in details.toPlainText()


def test_dont_send_transmits_nothing(qtbot, monkeypatch):
    from core.diagnostics import client
    from ui.error_report_dialog import ErrorReportDialog

    sent = []
    monkeypatch.setattr(client, "send", lambda *a, **k: sent.append(a))
    dlg = ErrorReportDialog(reports.build(EventId.PDF_SAVE_FAILED, events=[]), summary="x",
                            config=_sending_config())
    qtbot.addWidget(dlg)
    dlg.dont_send.click()
    assert sent == [] and dlg.result() == 0


def test_send_to_developer_sends_exactly_the_shown_report_once(qtbot, monkeypatch, boxes):
    from core.diagnostics import client
    from ui.error_report_dialog import ErrorReportDialog

    sent = []
    monkeypatch.setattr(client, "send", lambda rep, cfg=None: sent.append(rep) or client.SendResult(False, "offline"))
    rep = reports.build(EventId.PDF_SAVE_FAILED, events=[])
    dlg = ErrorReportDialog(rep, summary="x", config=_sending_config())
    qtbot.addWidget(dlg)
    dlg.send_button.click()
    qtbot.waitUntil(lambda: dlg.sent is not None, timeout=5000)
    assert sent == [rep] and boxes[-1][0] == "warning" and boxes[-1][2] == "offline"  # genuine failure shown


def test_build_without_reporting_service_offers_no_send_button(qtbot, monkeypatch):
    """Regression: a disabled build offered "Send to Developer", showed "Sending…", then failed."""
    from PySide6.QtGui import QGuiApplication

    from core.diagnostics import client
    from core.diagnostics.client import ReportingConfig
    from ui.error_report_dialog import CLOSE, COPY, OPEN_ISSUES, SEND, ErrorReportDialog

    sent = []
    monkeypatch.setattr(client, "send", lambda *a, **k: sent.append(a))
    dlg = ErrorReportDialog(reports.build(EventId.PDF_SAVE_FAILED, events=[]), summary="x",
                            config=ReportingConfig(False, ""))
    qtbot.addWidget(dlg)
    texts = sorted(b.text() for b in dlg.findChildren(QPushButton))
    assert texts == sorted([CLOSE, COPY, OPEN_ISSUES]) and SEND not in texts
    dlg.copy_button.click()
    assert "error_code: PDF_SAVE_FAILED" in QGuiApplication.clipboard().text()
    dlg.dont_send.click()
    assert sent == [] and dlg.result() == 0


def test_unexpected_errors_offer_a_report_but_ordinary_file_problems_do_not(window, monkeypatch, boxes):
    import ui.error_report_dialog as erd

    offered = []
    monkeypatch.setattr(erd.ErrorReportDialog, "exec", lambda self: offered.append(self.report) or 0)
    monkeypatch.setattr(window, "_is_headless_ui", lambda: False)
    window.report_unexpected("Save failed", PermissionError(13, "locked"), EventId.PDF_SAVE_FAILED)
    assert offered == [] and boxes[-1][1] == "Save failed"
    try:
        raise ValueError("C:/Users/tanaka/secret.pdf broke")
    except ValueError as exc:
        window.report_unexpected("Save failed", exc, EventId.PDF_SAVE_FAILED)
    assert len(offered) == 1 and offered[0]["error_code"] == "PDF_SAVE_FAILED"
    assert "tanaka" not in str(offered[0])


def test_about_shows_build_channel_and_update_status(window):
    from ui.about_dialog import AboutDialog

    dlg = AboutDialog(window, updates=window._updates)
    text = dlg._build_info.text()
    assert "Build:" in text and ("x64" in text or "x86" in text or "ARM64" in text)
    assert "Release channel: Stable" in text and "Updates: Not checked yet" in text
    assert "Check for Updates…" in [b.text() for b in dlg.findChildren(QPushButton)]


def test_update_result_from_the_helper_is_shown_once(window, boxes):
    import json

    root = staging.updates_root()
    root.mkdir(parents=True, exist_ok=True)
    f = root / "result-0.3.1-0123456789ab.json"
    f.write_text(json.dumps({"schema": 1, "status": "failed", "code": "setup_exit_4", "expected_version": "0.3.1"}),
                 encoding="utf-8")
    window.after_startup()
    assert any("was not installed" in b[2] for b in boxes) and not f.exists()
    boxes.clear()
    window.after_startup()
    assert boxes == []
