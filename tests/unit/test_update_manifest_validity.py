"""Manifest validity (730-day policy), timestamps, long gaps and user-facing failure messages.

Synthetic keys only; no network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.updates import manager, messages
from core.updates.manager import UpdateStatus
from core.updates.manifest import MAX_VALIDITY, ManifestError, format_time, parse_and_verify
from core.updates.state import UpdateState
from tests.fixtures.update_fixtures import make_config, manifest_bytes, signed_fields

T0 = datetime(2027, 3, 1, 9, 0, 0, tzinfo=timezone.utc)


def verify(fields: dict, now: datetime):
    return parse_and_verify(manifest_bytes(fields), make_config(), now=now)


def reason(fields: dict, now: datetime) -> str:
    with pytest.raises(ManifestError) as exc:
        verify(fields, now)
    return exc.value.code


def test_policy_is_730_days():
    assert MAX_VALIDITY == timedelta(days=730)


@pytest.mark.parametrize("days", [1, 365, 730])
def test_manifests_up_to_730_days_are_accepted(days):
    assert verify(signed_fields("1.0.0", now=T0, expires_days=days), T0).version


def test_longer_than_730_days_is_refused_even_by_one_second():
    f = signed_fields("1.0.0", now=T0)
    f["expires"] = format_time(T0 + MAX_VALIDITY + timedelta(seconds=1))
    assert reason(f, T0) == "timestamp"
    assert reason(signed_fields("1.0.0", now=T0, expires_days=731), T0) == "timestamp"
    assert reason(signed_fields("1.0.0", now=T0, expires_days=3650), T0) == "timestamp"


def test_expiry_boundary():
    f = signed_fields("1.0.0", now=T0, expires_days=730)
    end = T0 + timedelta(days=730)
    assert verify(f, end).version  # valid up to and including the expiry second
    assert reason(f, end + timedelta(seconds=1)) == "expired"


@pytest.mark.parametrize("change", [
    {"issued": "2027-03-01 09:00:00"}, {"expires": "tomorrow"}, {"issued": 1772355600},
    {"expires": "2027-02-28T09:00:00Z"},            # before issued
    {"expires": "2027-03-01T09:00:00Z"},            # equal to issued
    {"issued": "2027-02-30T09:00:00Z"},             # no such date
    {"expires": "2027-03-01T09:00:00+09:00"},       # not UTC "Z" form
])
def test_invalid_timestamps_are_refused(change):
    f = {**signed_fields("1.0.0", now=T0), **change}
    assert reason(f, T0) == "timestamp"


def test_future_dated_manifests_within_24_hours_are_accepted_beyond_that_refused():
    assert verify(signed_fields("1.0.0", now=T0 + timedelta(hours=23)), T0).version
    assert reason(signed_fields("1.0.0", now=T0 + timedelta(hours=25)), T0) == "clock"


def test_time_must_be_timezone_aware():
    with pytest.raises(ValueError):
        verify(signed_fields("1.0.0", now=T0), T0.replace(tzinfo=None))


def test_validity_belongs_to_the_manifest_not_to_the_installation_date():
    """A copy installed in October 2026 that first checks in 2029 updates with a fresh manifest."""
    in_2029 = datetime(2029, 11, 5, 8, 0, 0, tzinfo=timezone.utc)
    state = UpdateState()
    state.last_check = int(datetime(2026, 10, 25, tzinfo=timezone.utc).timestamp())
    res = manager.check(make_config(), "stable", "0.4.1", state,
                        fetch=lambda *a, **k: manifest_bytes(version="1.4.0", sequence=31, now=in_2029), now=in_2029)
    assert res.status == UpdateStatus.AVAILABLE


def test_an_expired_old_manifest_then_a_valid_newer_one():
    state = UpdateState(sequence={"stable": 1})
    old = manifest_bytes(version="0.5.0", sequence=3, now=T0, expires_days=730)
    later = T0 + timedelta(days=800)
    res = manager.check(make_config(), "stable", "0.4.1", state, fetch=lambda *a, **k: old, now=later)
    assert res.status == UpdateStatus.VERIFICATION_FAILED and res.reason == "expired"
    assert state.sequence == {"stable": 1}  # a refused manifest changes nothing
    new = manifest_bytes(version="0.9.0", sequence=1000, now=later)
    res = manager.check(make_config(), "stable", "0.4.1", state, fetch=lambda *a, **k: new, now=later)
    assert res.status == UpdateStatus.AVAILABLE and state.sequence == {"stable": 1000}


def test_retrying_repeats_the_full_verification():
    bad = json.loads(manifest_bytes(version="1.0.0", sequence=5, now=T0))
    bad["signed"]["release_notes"] = "changed"
    data = json.dumps(bad).encode()
    for _ in range(3):
        res = manager.check(make_config(), "stable", "0.4.1", UpdateState(), fetch=lambda *a, **k: data, now=T0)
        assert res.status == UpdateStatus.VERIFICATION_FAILED and res.reason == "signature"


# ------------------------------------------------------------------ release tool


@pytest.fixture
def tool(tmp_path, capsys):
    from core.updates import config as update_config
    from scripts.packaging import update_manifest

    keys = tmp_path / "keys"
    assert update_manifest.main(["keygen", "--plaintext-test-key", "--out", str(keys)]) == 0
    pub = json.loads(capsys.readouterr().out)["public_key"]
    cfg = json.loads(open("resources/update/update_config.json", encoding="utf-8").read())
    cfg["trusted_keys"] = [{"keyid": update_config.key_id(bytes.fromhex(pub)), "public_key": pub}]
    (tmp_path / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    setup = tmp_path / "MonographPDF_0.4.2_Setup.exe"
    setup.write_bytes(b"MZ" + bytes(4096))

    def run(*extra):
        return update_manifest.main(["make", "--setup", str(setup), "--channel", "stable", "--sequence", "1",
                                     "--key", str(keys / "update-signing.key"), "--config", str(tmp_path / "cfg.json"),
                                     "--out", str(tmp_path / "m.json"), *extra])

    return run, tmp_path / "m.json"


def test_release_tool_signs_for_730_days_by_default(tool):
    run, out = tool
    assert run() == 0
    s = json.loads(out.read_text(encoding="utf-8"))["signed"]
    issued = datetime.strptime(s["issued"], "%Y-%m-%dT%H:%M:%SZ")
    expires = datetime.strptime(s["expires"], "%Y-%m-%dT%H:%M:%SZ")
    assert expires - issued == timedelta(days=730)


@pytest.mark.parametrize("days", ["0", "731", "3650"])
def test_release_tool_refuses_validities_outside_1_to_730_days(tool, days):
    run, out = tool
    assert run("--expires-days", days) == 2 and not out.exists()


# ------------------------------------------------------------------ messages


def test_every_failure_reason_has_its_own_clear_title_and_says_nothing_was_installed():
    reasons = ["offline", "timeout", "http", "rate_limited", "tls", "redirect", "not_found", "network",
               "signature", "expired", "clock", "timestamp", "identity", "rollback", "artifact", "invalid"]
    for r in reasons:
        title, text = messages.check_text(r)
        assert title and text.endswith(messages.NOTHING_INSTALLED)
        assert "Ed25519" not in text and "sha" not in text.lower() and "keyid" not in text
    titles = {messages.check_text(r)[0] for r in ("offline", "http", "not_found", "signature", "expired",
                                                    "timestamp", "identity")}
    assert len(titles) == 7  # each of these situations reads differently


def test_download_failures_are_distinguished():
    assert messages.download_text("verify")[0] == "Installer integrity verification failed"
    assert messages.download_text("cancelled")[0] == "Update canceled"
    assert messages.download_text("network")[0] == "Download interrupted"
    assert messages.download_text("not_permitted", "Install 2.0.0 with Setup.") == \
        ("Unsupported upgrade path", "Install 2.0.0 with Setup.")
