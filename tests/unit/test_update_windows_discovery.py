"""Windows update discovery must ignore GitHub Latest and other platform lines.

Discovery uses the Releases API listing only as a hint; authenticity always comes from the
Ed25519-signed Windows manifest. These tests never contact the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.updates import manager, net
from core.updates.manager import UpdateStatus
from core.updates.state import UpdateState
from tests.fixtures.update_fixtures import (
    TEST_SECRET,
    listing_with_manifest,
    make_config,
    manifest_bytes,
    release_listing,
    signed_fields,
)

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
ASSET = "MonographPDF_update_manifest.json"


def _fetch_map(listing: bytes, manifests: dict[str, bytes]):
    """Return a fetch callable: API listing URL → listing; other URLs → named manifest bytes."""

    def fetch(_cfg, url, *_a, **_k):
        if "api.github.com" in url or url.rstrip("/").endswith("/api/releases") or "/releases?" in url:
            return listing
        for key, data in manifests.items():
            if key in url:
                return data
        raise net.NetworkError(f"unexpected URL in test: {url}", "not_found")

    return fetch


def _check(listing_entries, manifests, installed="0.4.0", state=None, *, channel="stable", cfg=None):
    cfg = cfg or make_config()
    listing = release_listing(*listing_entries)
    return manager.check(
        cfg, channel, installed, state or UpdateState(),
        fetch=_fetch_map(listing, manifests), now=NOW,
    )


def test_github_latest_points_at_macos_windows_still_finds_windows_release():
    """GitHub Latest may be macOS; discovery must still pick the newest Windows-line manifest."""
    win = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    # A macOS release listed first (as Latest would be) with a decoy asset name must be ignored.
    res = _check(
        [
            listing_with_manifest("0.1.0", tag_name="v0.1.0-macos-1"),
            listing_with_manifest("0.4.0"),
            listing_with_manifest("0.3.0"),
        ],
        {"v0.4.0": win},
        installed="0.3.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"


def test_github_latest_points_at_linux_windows_still_finds_windows_release():
    win = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.1.0", tag_name="v0.1.0-linux"),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.4.0": win},
        installed="0.3.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"


def test_newer_windows_release_not_github_latest_is_still_discovered():
    """A newer Windows release that is not repository Latest must still be selected."""
    newer = manifest_bytes(version="0.5.0", sequence=30, now=NOW)
    older = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.1.0", tag_name="v0.1.0-macos-1"),  # would be Latest
            listing_with_manifest("0.5.0"),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.5.0": newer, "v0.4.0": older},
        installed="0.4.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.5.0"


def test_multiple_windows_versions_skipped_offers_newest_only():
    newest = manifest_bytes(version="0.5.0", sequence=40, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.5.0"),
            listing_with_manifest("0.4.2"),
            listing_with_manifest("0.4.1"),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.5.0": newest},
        installed="0.3.0",
        state=UpdateState(sequence={"stable": 5}),
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.5.0"
    assert res.release.sequence == 40
    assert manager.install_permitted(res.release, "0.3.0") == ""


def test_newest_windows_release_is_draft_is_skipped():
    published = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.5.0", draft=True),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.4.0": published},
        installed="0.3.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"


def test_newest_windows_release_is_github_prerelease_skipped_on_stable():
    stable = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.5.0", prerelease=True),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.4.0": stable},
        installed="0.3.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"


def test_windows_release_without_signed_manifest_does_not_fall_back_to_older():
    """Newest eligible Windows release missing the manifest asset → not_found (no older offer)."""
    older = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    res = _check(
        [
            listing_with_manifest("0.5.0", include_manifest=False),
            listing_with_manifest("0.4.0"),
        ],
        {"v0.4.0": older},
        installed="0.3.0",
    )
    assert res.status == UpdateStatus.UNAVAILABLE
    assert res.reason == "not_found"
    assert "0.5.0" in res.detail


def test_windows_release_with_invalid_manifest_signature_fails_verification():
    bad = manifest_bytes(signed_fields("0.5.0", sequence=30, now=NOW), secrets=(TEST_SECRET,))
    # Flip one signature byte after signing.
    doc = json.loads(bad.decode())
    import base64
    raw = bytearray(base64.b64decode(doc["signatures"][0]["sig"]))
    raw[0] ^= 1
    doc["signatures"][0]["sig"] = base64.b64encode(bytes(raw)).decode()
    tampered = json.dumps(doc).encode()
    res = _check(
        [listing_with_manifest("0.5.0")],
        {"v0.5.0": tampered},
        installed="0.4.0",
    )
    assert res.status == UpdateStatus.VERIFICATION_FAILED
    assert res.reason == "signature"


def test_older_valid_manifest_replay_is_rejected():
    state = UpdateState(sequence={"stable": 30})
    older = manifest_bytes(version="0.4.0", sequence=20, now=NOW)  # still unexpired, lower sequence
    res = _check(
        [listing_with_manifest("0.4.0")],
        {"v0.4.0": older},
        installed="0.3.0",
        state=state,
    )
    assert res.status == UpdateStatus.VERIFICATION_FAILED
    assert res.reason == "rollback"


def test_newer_release_with_incompatible_min_upgrade_from_is_offered_but_not_auto_installable():
    data = manifest_bytes(signed_fields("0.5.0", sequence=30, now=NOW, min_upgrade_from="0.4.5"))
    res = _check(
        [listing_with_manifest("0.5.0")],
        {"v0.5.0": data},
        installed="0.4.0",
    )
    assert res.status == UpdateStatus.AVAILABLE
    reason = manager.install_permitted(res.release, "0.4.0")
    assert "cannot be installed automatically" in reason


def test_github_unavailable_reports_unable_to_check():
    cfg = make_config()

    def fetch(_c, url, *_a, **_k):
        raise net.NetworkError("connection failed", "offline")

    res = manager.check(cfg, "stable", "0.4.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.UNAVAILABLE
    assert res.reason == "offline"
    assert "Nothing was downloaded" in res.message or res.message  # offline copy remains usable


def test_malformed_release_listing_is_unable_to_check():
    cfg = make_config()

    def fetch(_c, url, *_a, **_k):
        if "api.github.com" in url:
            return b"{not-json"
        raise net.NetworkError("unexpected", "http")

    res = manager.check(cfg, "stable", "0.4.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.UNAVAILABLE
    assert res.reason == "http"


def test_malicious_listing_object_instead_of_array_is_unable_to_check():
    cfg = make_config()

    def fetch(_c, url, *_a, **_k):
        if "api.github.com" in url:
            return b'{"tag_name":"v9.9.9"}'
        raise net.NetworkError("unexpected", "http")

    res = manager.check(cfg, "stable", "0.4.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.UNAVAILABLE


def test_malicious_listing_never_downloads_installer_before_manifest_checks():
    """Even if a listing points at an installer URL, check() only fetches the manifest asset."""
    cfg = make_config()
    listing = release_listing({
        "tag_name": "v0.5.0", "draft": False, "prerelease": False,
        "assets": [
            {"name": "MonographPDF_0.5.0_Setup.exe",
             "browser_download_url": "https://github.com/aungyemun/monograph-pdf/releases/download/v0.5.0/"
                                     "MonographPDF_0.5.0_Setup.exe"},
            {"name": ASSET,
             "browser_download_url": "https://github.com/aungyemun/monograph-pdf/releases/download/v0.5.0/" + ASSET},
        ],
    })
    data = manifest_bytes(version="0.5.0", sequence=30, now=NOW)
    asked = []

    def fetch(_c, url, *_a, **_k):
        asked.append(url)
        if "api.github.com" in url:
            return listing
        if ASSET in url:
            return data
        raise AssertionError(f"installer or unexpected URL fetched during check: {url}")

    res = manager.check(cfg, "stable", "0.4.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.AVAILABLE
    assert all("Setup.exe" not in u for u in asked)
    assert any(ASSET in u for u in asked)


def test_stable_manifest_url_latest_is_not_contacted():
    """Shipped configs may leave stable_manifest_url empty; even if set to Latest, check ignores it."""
    from dataclasses import replace

    cfg = replace(
        make_config(),
        stable_manifest_url=(
            "https://github.com/aungyemun/monograph-pdf/releases/latest/download/" + ASSET
        ),
    )
    data = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    asked = []

    def fetch(_c, url, *_a, **_k):
        asked.append(url)
        if "api.github.com" in url:
            return release_listing(listing_with_manifest("0.4.0"))
        if ASSET in url and "latest" not in url:
            return data
        raise AssertionError(f"Latest or unexpected URL contacted: {url}")

    res = manager.check(cfg, "stable", "0.3.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.AVAILABLE
    assert all("/latest/" not in u for u in asked)


def test_tag_is_windows_line_rejects_platform_suffixes():
    assert manager._tag_is_windows_line("v0.4.0", allow_prerelease=False) is True
    assert manager._tag_is_windows_line("v0.5.0-rc.1", allow_prerelease=False) is False
    assert manager._tag_is_windows_line("v0.5.0-rc.1", allow_prerelease=True) is True
    assert manager._tag_is_windows_line("v0.1.0-macos-1", allow_prerelease=True) is False
    assert manager._tag_is_windows_line("v0.1.0-linux", allow_prerelease=True) is False
    assert manager._tag_is_windows_line("v0.1.0-darwin", allow_prerelease=True) is False


def test_no_compatible_windows_release_reports_not_found():
    res = _check(
        [
            listing_with_manifest("0.1.0", tag_name="v0.1.0-macos-1"),
            listing_with_manifest("0.1.0", tag_name="v0.1.0-linux"),
            listing_with_manifest("0.5.0", draft=True),
        ],
        {},
        installed="0.4.0",
    )
    assert res.status == UpdateStatus.UNAVAILABLE
    assert res.reason == "not_found"


def test_invalid_newest_manifest_does_not_fall_back_to_older_valid():
    """Tampered newest Windows manifest → verification_failed; older valid manifest is not used."""
    import base64

    newer = manifest_bytes(version="0.5.0", sequence=30, now=NOW)
    doc = json.loads(newer.decode())
    raw = bytearray(base64.b64decode(doc["signatures"][0]["sig"]))
    raw[0] ^= 1
    doc["signatures"][0]["sig"] = base64.b64encode(bytes(raw)).decode()
    tampered = json.dumps(doc).encode()
    older = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    asked = []

    def fetch(_c, url, *_a, **_k):
        asked.append(url)
        if "api.github.com" in url or "/releases?" in url:
            return release_listing(
                listing_with_manifest("0.5.0"),
                listing_with_manifest("0.4.0"),
            )
        if "v0.5.0" in url:
            return tampered
        if "v0.4.0" in url:
            raise AssertionError("must not fall back to older manifest after newest failed verification")
        raise net.NetworkError(f"unexpected URL: {url}", "not_found")

    res = manager.check(make_config(), "stable", "0.3.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.VERIFICATION_FAILED
    assert res.reason == "signature"
    assert all("v0.4.0" not in u for u in asked)


def test_pagination_finds_windows_release_on_later_page():
    """When page 1 is only foreign platforms, page 2 still yields the Windows candidate."""
    win = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    page1 = [listing_with_manifest("0.1.0", tag_name=f"v0.1.0-macos-{i}") for i in range(1, 101)]
    assert len(page1) == 100
    page2 = [listing_with_manifest("0.4.0"), listing_with_manifest("0.3.0")]
    pages_seen = []

    def fetch(_c, url, *_a, **_k):
        if "api.github.com" in url or "/api/releases" in url or "/releases?" in url:
            # Match &page=N (not the "page=1" substring inside per_page=100).
            if url.endswith("page=1") or "&page=1&" in url or "?page=1&" in url:
                pages_seen.append(1)
                return release_listing(*page1)
            if url.endswith("page=2") or "&page=2&" in url or "?page=2&" in url:
                pages_seen.append(2)
                return release_listing(*page2)
            pages_seen.append(url)
            return b"[]"
        if "v0.4.0" in url and ASSET in url:
            return win
        raise net.NetworkError(f"unexpected URL: {url}", "not_found")

    res = manager.check(make_config(), "stable", "0.3.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"
    assert pages_seen == [1, 2]


def test_listing_metadata_is_not_treated_as_authenticated():
    """A listing can claim any version; only the signed manifest version is trusted."""
    # Listing advertises v9.9.9; signed body is 0.4.0 — client must use signed fields.
    data = manifest_bytes(version="0.4.0", sequence=20, now=NOW)
    listing = release_listing({
        "tag_name": "v9.9.9", "draft": False, "prerelease": False,
        "assets": [{"name": ASSET,
                    "browser_download_url":
                        "https://github.com/aungyemun/monograph-pdf/releases/download/v0.4.0/" + ASSET}],
    })

    def fetch(_c, url, *_a, **_k):
        if "api.github.com" in url or "/releases?" in url:
            return listing
        return data

    res = manager.check(make_config(), "stable", "0.3.0", UpdateState(), fetch=fetch, now=NOW)
    assert res.status == UpdateStatus.AVAILABLE
    assert str(res.release.version) == "0.4.0"  # from signed body, not listing tag
