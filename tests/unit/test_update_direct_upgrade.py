"""Direct upgrades across skipped versions and long gaps (synthetic keys only; no network).

An installed copy reads only the newest manifest; it never needs the manifests of the versions it
skipped. Replay protection is the per-channel sequence number, which only has to grow."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from core.updates import manager, net, staging
from core.updates.install_target import InstallTarget
from core.updates.manager import UpdateStatus
from core.updates.manifest import parse_and_verify
from core.updates.state import UpdateState
from tests.fixtures.update_fixtures import (
    OTHER_SECRET,
    TEST_SECRET,
    make_config,
    manifest_bytes,
    setup_bytes,
    signed_fields,
)

NOW = datetime(2029, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / "Updates"))


def check(data: bytes, installed: str, state: UpdateState, *, cfg=None, now=NOW, channel="stable"):
    return manager.check(cfg or make_config(), channel, installed, state, fetch=lambda *a, **k: data, now=now)


@pytest.mark.parametrize("target", ["0.4.2", "0.6.0", "1.0.0", "2.3.4"])
def test_direct_upgrade_from_0_4_1_skipping_any_number_of_versions(target):
    state = UpdateState(sequence={"stable": 1})  # last seen: the manifest of 0.4.1, years ago
    res = check(manifest_bytes(version=target, sequence=40, now=NOW), "0.4.1", state)
    assert res.status == UpdateStatus.AVAILABLE and str(res.release.version) == target
    assert manager.install_permitted(res.release, "0.4.1") == ""
    assert state.sequence["stable"] == 40


def test_first_check_after_installation_years_later_needs_no_history():
    state = UpdateState()  # never checked
    state.last_check = int(time.time()) - 3 * 365 * 86400
    res = check(manifest_bytes(version="1.0.0", sequence=57, now=NOW), "0.4.1", state)
    assert res.status == UpdateStatus.AVAILABLE and state.sequence == {"stable": 57}


def test_after_a_direct_upgrade_older_manifests_are_replays():
    state = UpdateState()
    assert check(manifest_bytes(version="1.0.0", sequence=57, now=NOW), "0.4.1", state).status == UpdateStatus.AVAILABLE
    old = manifest_bytes(version="0.6.0", sequence=30, now=NOW)  # genuine, still unexpired, but older
    res = check(old, "0.4.1", state)
    assert res.status == UpdateStatus.VERIFICATION_FAILED and "replay" in res.message
    assert state.sequence["stable"] == 57


def test_newest_manifest_expired_after_a_long_gap_fails_safely():
    issued = NOW - timedelta(days=400)
    res = check(manifest_bytes(version="0.9.0", sequence=20, now=issued, expires_days=365), "0.4.1", UpdateState())
    assert res.status == UpdateStatus.VERIFICATION_FAILED and "expired" in res.message
    assert "Nothing was downloaded" in res.message


def test_a_computer_clock_years_behind_rejects_a_manifest_from_the_future():
    res = check(manifest_bytes(version="1.0.0", sequence=57, now=NOW), "0.4.1", UpdateState(),
                now=NOW - timedelta(days=800))
    assert res.status == UpdateStatus.VERIFICATION_FAILED and "clock" in res.message


def test_key_rotation_bridge_old_clients_accept_a_manifest_signed_by_old_and_new_key():
    """A release that rotates keys signs its manifest with both keys: copies that trust only the old
    key (e.g. 0.4.1) and copies that trust only the new key both accept it."""
    data = manifest_bytes(signed_fields("1.0.0", sequence=57, now=NOW), secrets=(TEST_SECRET, OTHER_SECRET))
    old_client, new_client = make_config((TEST_SECRET,)), make_config((OTHER_SECRET,))
    assert check(data, "0.4.1", UpdateState(), cfg=old_client).status == UpdateStatus.AVAILABLE
    assert check(data, "0.9.0", UpdateState(), cfg=new_client).status == UpdateStatus.AVAILABLE


def test_after_the_old_key_is_dropped_old_clients_cannot_verify_and_say_so():
    data = manifest_bytes(signed_fields("2.0.0", sequence=80, now=NOW), secrets=(OTHER_SECRET,))
    res = check(data, "0.4.1", UpdateState(), cfg=make_config((TEST_SECRET,)))
    assert res.status == UpdateStatus.VERIFICATION_FAILED and "trusted" in res.message


def test_unsupported_path_is_refused_with_a_manual_option():
    res = check(manifest_bytes(signed_fields("1.0.0", sequence=57, now=NOW, min_upgrade_from="0.6.0")), "0.4.1",
                UpdateState())
    assert res.status == UpdateStatus.AVAILABLE  # the user is told a new version exists …
    reason = manager.install_permitted(res.release, "0.4.1")
    assert "cannot be installed automatically" in reason and "Setup from the release page" in reason
    assert manager.install_permitted(res.release, "0.6.0") == ""


def test_update_now_is_disabled_for_an_unsupported_path_and_the_release_page_offered(qtbot):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QLabel

    from ui.update_dialogs import UpdateAvailableDialog

    rel = parse_and_verify(manifest_bytes(signed_fields("1.0.0", sequence=57, min_upgrade_from="0.6.0")), make_config())
    res = manager.CheckResult(UpdateStatus.AVAILABLE, "", "0.4.1", rel)
    dlg = UpdateAvailableDialog(res, install_block=manager.install_permitted(rel, "0.4.1"))
    qtbot.addWidget(dlg)
    texts = " ".join(lbl.text() for lbl in dlg.findChildren(QLabel))
    assert not dlg.update_now.isEnabled()
    assert "cannot be installed automatically" in texts and "release page" in texts


def test_a_future_manifest_format_is_refused_clearly_not_misread():
    res = check(manifest_bytes(signed_fields("3.0.0", sequence=99, now=NOW, schema=2)), "0.4.1", UpdateState())
    assert res.status == UpdateStatus.VERIFICATION_FAILED and "format" in res.message


def test_skipped_prereleases_on_the_prerelease_channel():
    cfg = make_config()
    data = manifest_bytes(version="1.0.0-rc.2", channel="prerelease", sequence=12, now=NOW)
    url = "https://github.com/aungyemun/monograph-pdf/releases/download/v1.0.0-rc.2/" + cfg.manifest_asset
    listing = json.dumps([
        {"tag_name": "v0.5.0-rc.1", "draft": False, "prerelease": True,
         "assets": [{"name": cfg.manifest_asset, "browser_download_url": url.replace("1.0.0-rc.2", "0.5.0-rc.1")}]},
        {"tag_name": "v1.0.0-rc.2", "draft": False, "prerelease": True,
         "assets": [{"name": cfg.manifest_asset, "browser_download_url": url}]}]).encode()
    asked = []

    def fetch(_cfg, u, *a, **k):
        asked.append(u)
        return listing if "api.github.com" in u else data

    state = UpdateState(sequence={"prerelease": 3})
    res = manager.check(cfg, "prerelease", "0.4.1", state, fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.AVAILABLE and str(res.release.version) == "1.0.0-rc.2"
    assert asked[1] == url and state.sequence["prerelease"] == 12  # straight to the newest, none in between


def test_setup_switches_used_by_an_old_helper_stay_the_documented_inno_switches():
    """The helper that runs the new Setup is the copy installed with the OLD version, so every future
    Setup must keep accepting exactly these switches (and the same Inno Setup AppId)."""
    handoff = {"install_mode": "user", "install_dir": r"C:\Users\x\AppData\Local\Programs\Monograph PDF",
               "setup_log": r"C:\t\setup.log"}
    assert manager.setup_arguments(handoff) == [
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER",
        r"/DIR=C:\Users\x\AppData\Local\Programs\Monograph PDF", r"/LOG=C:\t\setup.log"]
    assert manager.setup_arguments({**handoff, "install_mode": "machine"})[4] == "/ALLUSERS"


def test_interrupted_download_of_a_big_upgrade_leaves_nothing_behind():
    data = setup_bytes("1.0.0", size=8192)
    rel = parse_and_verify(manifest_bytes(signed_fields("1.0.0", sequence=57, data=data)), make_config())

    def broken(_cfg, _url, dest, size, _cancel, _report):
        with open(dest, "wb") as fh:
            fh.write(data[: size // 2])
        raise net.NetworkError("the connection was interrupted", "offline")

    with pytest.raises(manager.UpdateError):
        manager.download_and_verify(make_config(), rel, InstallTarget(ok=True), threading.Event(), downloader=broken)
    leftovers = [p for p in staging.staging_root().rglob("*") if p.is_file()] if staging.staging_root().exists() else []
    assert leftovers == []


def test_interrupted_installation_is_cleaned_up_at_the_next_start():
    """The helper was handed the update but the computer was switched off: once the helper is gone
    and the attempt is old, the next start removes the staging folder (nothing is installed half)."""
    sd = staging.new_staging("1.0.0")
    sd.installer.write_bytes(setup_bytes("1.0.0"))
    sd.set_state("handed_off", helper_pid=999_999_999)  # no such process
    marker = staging.read_marker(sd.path)
    old = time.time() + 30 * 86400
    report = staging.cleanup(now=old)
    assert sd.path.name in report.removed and not sd.path.exists(), (marker, report)
