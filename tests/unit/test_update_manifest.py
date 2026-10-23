"""Signed update manifests and the update check policy (synthetic keys, no network)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.updates import config as update_config
from core.updates import ed25519, manager, net
from core.updates.manager import UpdateStatus
from core.updates.manifest import ManifestError, canonical_bytes, parse_and_verify, sign_manifest
from core.updates.semver import parse as V
from core.updates.state import UpdateState
from tests.fixtures.update_fixtures import (
    OTHER_SECRET,
    TEST_SECRET,
    make_config,
    manifest_bytes,
    signed_fields,
)

ROOT = Path(__file__).resolve().parents[2]


def test_valid_signed_release_is_accepted():
    rel = parse_and_verify(manifest_bytes(), make_config())
    assert str(rel.version) == "0.3.1" and rel.channel == "stable" and rel.sequence == 10
    assert rel.artifact.name == "MonographPDF_0.3.1_Setup.exe" and rel.artifact.arch == "x64"
    assert len(rel.key_ids) == 1


@pytest.mark.parametrize("field,value", [
    ("version", "0.3.2"), ("sequence", 11), ("release_notes", "changed"), ("expires", "2099-01-01T00:00:00Z"),
])
def test_any_change_after_signing_is_rejected(field, value):
    doc = json.loads(manifest_bytes())
    doc["signed"][field] = value
    with pytest.raises(ManifestError) as e:
        parse_and_verify(json.dumps(doc).encode(), make_config())
    assert e.value.code == "signature"


def test_modified_installer_checksum_in_manifest_is_rejected():
    doc = json.loads(manifest_bytes())
    doc["signed"]["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ManifestError, match="not signed by a trusted"):
        parse_and_verify(json.dumps(doc).encode(), make_config())


def test_invalid_signature_wrong_key_and_unknown_key():
    # signed by a key the application does not trust
    with pytest.raises(ManifestError, match="trusted"):
        parse_and_verify(manifest_bytes(secrets=(OTHER_SECRET,)), make_config())
    # signature bytes replaced
    doc = json.loads(manifest_bytes())
    doc["signatures"][0]["sig"] = base64.b64encode(b"\0" * 64).decode()
    with pytest.raises(ManifestError):
        parse_and_verify(json.dumps(doc).encode(), make_config())
    # key id of the trusted key, signature by another key
    doc = json.loads(manifest_bytes())
    forged = json.loads(manifest_bytes(secrets=(OTHER_SECRET,)))
    doc["signatures"][0]["sig"] = forged["signatures"][0]["sig"]
    with pytest.raises(ManifestError):
        parse_and_verify(json.dumps(doc).encode(), make_config())
    # no signatures at all
    doc["signatures"] = []
    with pytest.raises(ManifestError, match="not signed"):
        parse_and_verify(json.dumps(doc).encode(), make_config())


def test_threshold_requires_distinct_trusted_keys():
    cfg = make_config((TEST_SECRET, OTHER_SECRET), threshold=2)
    with pytest.raises(ManifestError):
        parse_and_verify(manifest_bytes(), cfg)
    doc = json.loads(manifest_bytes())
    doc["signatures"] = doc["signatures"] * 2  # the same signature twice counts once
    with pytest.raises(ManifestError):
        parse_and_verify(json.dumps(doc).encode(), cfg)
    assert len(parse_and_verify(manifest_bytes(secrets=(TEST_SECRET, OTHER_SECRET)), cfg).key_ids) == 2


def test_expired_and_future_metadata():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    with pytest.raises(ManifestError) as e:
        parse_and_verify(manifest_bytes(now=old, expires_days=30), make_config())
    assert e.value.code == "expired"
    future = datetime.now(timezone.utc) + timedelta(days=5)
    with pytest.raises(ManifestError) as e:
        parse_and_verify(manifest_bytes(now=future), make_config())
    assert e.value.code == "clock"


@pytest.mark.parametrize("overrides,code", [
    ({"app_id": "other-app"}, "identity"),
    ({"inno_app_id": "{00000000-0000-0000-0000-000000000000}"}, "identity"),
    ({"repository": "someone/fork"}, "identity"),
    ({"channel": "beta"}, "channel"),
    ({"channel": "prerelease"}, "channel"),            # X.Y.Z offered as a prerelease
    ({"artifacts": []}, "artifact"),
])
def test_identity_channel_and_artifact_checks(overrides, code):
    with pytest.raises(ManifestError) as e:
        parse_and_verify(manifest_bytes(signed_fields(**overrides)), make_config())
    assert e.value.code == code


def test_incompatible_architecture_and_foreign_hosts_are_refused():
    f = signed_fields()
    f["artifacts"][0]["arch"] = "arm64"
    with pytest.raises(ManifestError, match="x64"):
        parse_and_verify(manifest_bytes(f), make_config())
    f = signed_fields()
    f["artifacts"][0]["url"] = "https://evil.example/MonographPDF_0.3.1_Setup.exe"
    with pytest.raises(ManifestError, match="allowed host"):
        parse_and_verify(manifest_bytes(f), make_config())
    f = signed_fields()
    f["artifacts"][0]["url"] = f["artifacts"][0]["url"].replace("https://", "http://")
    with pytest.raises(ManifestError, match="allowed host"):
        parse_and_verify(manifest_bytes(f), make_config())
    f = signed_fields()
    f["artifacts"][0]["name"] = "MonographPDF_0.9.9_Setup.exe"
    with pytest.raises(ManifestError, match="installer name"):
        parse_and_verify(manifest_bytes(f), make_config())


def test_malformed_documents():
    cfg = make_config()
    for raw in (b"", b"{", b"[]", b'{"signed": {}, "signatures": [], "extra": 1}', b"\xff\xfe"):
        with pytest.raises(ManifestError):
            parse_and_verify(raw, cfg)
    good = manifest_bytes().decode()
    dup = good.replace('{"signed": {', '{"signed": {"version": "9.9.9", ', 1)
    with pytest.raises(ManifestError, match="duplicate"):
        parse_and_verify(dup.encode(), cfg)
    with pytest.raises(ManifestError, match="too large"):
        parse_and_verify(b" " * (cfg.max_manifest_bytes + 1), cfg)
    with pytest.raises(ManifestError, match="floating"):
        canonical_bytes({"a": 1.5})


def test_unsupported_version_strings():
    for bad in ("1.0", "01.2.3", "1.2.3+build", "１.2.3", "v", "1.2.3-"):
        with pytest.raises(ManifestError):
            parse_and_verify(manifest_bytes(signed_fields(version=bad)), make_config())


def test_semver_precedence_and_locale_independence():
    order = ["0.2.4", "0.3.0-alpha", "0.3.0-alpha.1", "0.3.0-beta", "0.3.0-beta.2", "0.3.0-beta.11",
             "0.3.0-rc.1", "0.3.0", "0.3.1", "0.10.0", "1.0.0"]
    assert sorted(map(V, reversed(order))) == list(map(V, order))
    assert V("v0.3.0") == V("0.3.0")
    with pytest.raises(ValueError):
        V("٠.٣.٠")  # Arabic-Indic digits are not version digits


def _fetch_returning(data: bytes, record: list | None = None):
    def fetch(cfg, url, limit, accept="application/json"):
        if record is not None:
            record.append(url)
        return data
    return fetch


def test_check_reports_available_and_up_to_date():
    st = UpdateState()
    res = manager.check(make_config(), "stable", "0.3.0", st, fetch=_fetch_returning(manifest_bytes()))
    assert res.status == UpdateStatus.AVAILABLE and str(res.release.version) == "0.3.1"
    assert st.sequence["stable"] == 10 and st.last_success
    res = manager.check(make_config(), "stable", "0.3.1", st, fetch=_fetch_returning(manifest_bytes()))
    assert res.status == UpdateStatus.UP_TO_DATE
    # a release older than the installed version is never offered (no downgrade)
    res = manager.check(make_config(), "stable", "0.4.0", st, fetch=_fetch_returning(manifest_bytes()))
    assert res.status == UpdateStatus.UP_TO_DATE


def test_replayed_older_manifest_is_rejected():
    st = UpdateState()
    newer = manifest_bytes(signed_fields(version="0.3.2", sequence=20))
    assert manager.check(make_config(), "stable", "0.3.0", st, fetch=_fetch_returning(newer)).status == UpdateStatus.AVAILABLE
    older = manifest_bytes(signed_fields(version="0.3.1", sequence=10))
    res = manager.check(make_config(), "stable", "0.3.0", st, fetch=_fetch_returning(older))
    assert res.status == UpdateStatus.VERIFICATION_FAILED and res.reason == "rollback"


def test_stable_channel_refuses_a_prerelease_manifest():
    pre = manifest_bytes(signed_fields(version="0.4.0-rc.1", channel="prerelease"))
    res = manager.check(make_config(), "stable", "0.3.0", UpdateState(), fetch=_fetch_returning(pre))
    assert res.status == UpdateStatus.VERIFICATION_FAILED


def test_prerelease_channel_picks_the_newest_listed_release():
    cfg = make_config()
    listing = json.dumps([
        {"tag_name": "v0.3.1", "draft": False, "prerelease": False, "assets": [
            {"name": cfg.manifest_asset, "browser_download_url": "https://github.com/aungyemun/monograph-pdf/releases/download/v0.3.1/m.json"}]},
        {"tag_name": "v0.4.0-rc.1", "draft": False, "prerelease": True, "assets": [
            {"name": cfg.manifest_asset, "browser_download_url": "https://github.com/aungyemun/monograph-pdf/releases/download/v0.4.0-rc.1/m.json"}]},
        {"tag_name": "v9.0.0", "draft": True, "assets": [
            {"name": cfg.manifest_asset, "browser_download_url": "https://github.com/x/draft.json"}]},
        {"tag_name": "v5.0.0", "draft": False, "assets": [
            {"name": cfg.manifest_asset, "browser_download_url": "https://evil.example/m.json"}]},
    ]).encode()
    pre = manifest_bytes(signed_fields(version="0.4.0-rc.1", channel="prerelease"))
    urls: list[str] = []

    def fetch(c, url, limit, accept="application/json"):
        urls.append(url)
        return listing if "api.github.com" in url else pre

    res = manager.check(cfg, "prerelease", "0.3.0", UpdateState(), fetch=fetch)
    assert res.status == UpdateStatus.AVAILABLE and str(res.release.version) == "0.4.0-rc.1"
    assert urls[1].endswith("/v0.4.0-rc.1/m.json")


@pytest.mark.parametrize("kind", ["offline", "timeout", "rate_limited", "tls", "http", "not_found", "redirect"])
def test_unreachable_source_is_never_reported_as_up_to_date(kind):
    def fetch(*a, **k):
        raise net.NetworkError("simulated", kind)

    st = UpdateState()
    res = manager.check(make_config(), "stable", "0.3.0", st, fetch=fetch)
    assert res.status == UpdateStatus.UNAVAILABLE
    assert st.last_success == 0 and st.last_status == "unable_to_check"


def test_not_configured_build_does_not_contact_anything():
    calls = []
    res = manager.check(make_config(enabled=False), "stable", "0.3.0", UpdateState(), fetch=_fetch_returning(b"", calls))
    assert res.status == UpdateStatus.NOT_CONFIGURED and calls == []
    res = manager.check(make_config(secrets=()), "stable", "0.3.0", UpdateState(), fetch=_fetch_returning(b"", calls))
    assert res.status == UpdateStatus.NOT_CONFIGURED and calls == []


def test_install_permitted_rules():
    rel = parse_and_verify(manifest_bytes(signed_fields(min_upgrade_from="0.2.0")), make_config())
    assert manager.install_permitted(rel, "0.3.0") == ""
    assert "downgrade" in manager.install_permitted(rel, "0.3.1")
    assert "cannot be installed automatically" in manager.install_permitted(rel, "0.1.5")


# The production update-signing key (generated offline 2026-10-23; the secret key is encrypted and
# kept outside every repository). Changing the trusted keys must be a deliberate, reviewed change.
PRODUCTION_KEYID = "27c3b3b23b949c40"
PRODUCTION_PUBLIC_KEY = "13a02f80f8b1b009e5bb8ae77b15c766f06bf9ab2b640f91577b300ba552846c"


def test_shipped_configuration_trusts_exactly_the_production_key():
    from tests.fixtures.update_fixtures import TEST_SECRET

    cfg = update_config.load(ROOT / "resources" / "update" / "update_config.json")
    assert cfg.enabled is True and cfg.usable and cfg.threshold == 1
    assert cfg.trusted_keys == {PRODUCTION_KEYID: bytes.fromhex(PRODUCTION_PUBLIC_KEY)}
    assert update_config.key_id(bytes.fromhex(PRODUCTION_PUBLIC_KEY)) == PRODUCTION_KEYID
    assert update_config.key_id(ed25519.public_key(TEST_SECRET)) not in cfg.trusted_keys  # never a test key
    assert cfg.ca_file is None and cfg.require_authenticode is False
    assert set(cfg.allowed_hosts) <= {"github.com", "api.github.com", "objects.githubusercontent.com",
                                      "release-assets.githubusercontent.com"}
    assert cfg.repository == "aungyemun/monograph-pdf"
    assert cfg.stable_manifest_url == ("https://github.com/aungyemun/monograph-pdf/releases/latest/download/"
                                       "MonographPDF_update_manifest.json")


def test_configuration_validation(tmp_path):
    good = json.loads((ROOT / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    for bad in ({"schema": 2}, {"allowed_hosts": ["exa mple"]}, {"trusted_keys": [{"public_key": "zz"}]},
                {"trusted_keys": [{"public_key": "00" * 32, "keyid": "0000000000000000"}]}, {"threshold": 0},
                {"ca_file": "../x.pem"}, {"enabled": True, "stable_manifest_url": "http://github.com/x.json"}):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({**good, **bad}), encoding="utf-8")
        with pytest.raises(update_config.ConfigError):
            update_config.load(p)
        assert update_config.load_or_disabled(p).usable is False
    assert update_config.load_or_disabled(tmp_path / "missing.json").usable is False


def test_sign_manifest_helper_round_trip():
    doc = sign_manifest(signed_fields(), [TEST_SECRET])
    assert parse_and_verify(json.dumps(doc).encode(), make_config()).sequence == 10
