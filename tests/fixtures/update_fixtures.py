"""Synthetic update keys, configurations and signed manifests for the update tests.

The keys are generated from fixed test seeds; they are not and never were production keys.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.updates import config as update_config
from core.updates import ed25519
from core.updates.manifest import format_time, sign_manifest

TEST_SECRET = hashlib.sha256(b"monograph-pdf synthetic update test key 1").digest()
OTHER_SECRET = hashlib.sha256(b"monograph-pdf synthetic update test key 2 (not trusted)").digest()
REPO = "aungyemun/monograph-pdf"
HOSTS = ("github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")


def make_config(secrets=(TEST_SECRET,), *, threshold: int = 1, enabled: bool = True, hosts=HOSTS,
                ca_file: Path | None = None, base: str = "https://github.com") -> update_config.UpdateConfig:
    keys = {}
    for s in secrets:
        pk = ed25519.public_key(s)
        keys[update_config.key_id(pk)] = pk
    # Discovery uses the Releases API listing only (never repository-wide Latest).
    # stable_manifest_url is optional/legacy and left empty for production-like tests.
    api = (f"https://api.github.com/repos/{REPO}/releases?per_page=100" if base == "https://github.com"
           else f"{base}/api/releases")
    return update_config.UpdateConfig(
        enabled=enabled, disabled_reason="", repository=REPO,
        manifest_asset="MonographPDF_update_manifest.json",
        stable_manifest_url="",
        releases_api_url=api,
        allowed_hosts=tuple(hosts), trusted_keys=keys, threshold=threshold, ca_file=ca_file)


def setup_bytes(version: str = "0.3.1", size: int = 4096) -> bytes:
    body = (f"fake Monograph PDF {version} Setup ".encode() * (size // 20 + 1))[: size - 2]
    return b"MZ" + body


def signed_fields(version: str = "0.3.1", *, channel: str = "stable", sequence: int = 10, data: bytes | None = None,
                  base: str = "https://github.com", now: datetime | None = None, expires_days: int = 730,
                  **overrides) -> dict:
    data = setup_bytes(version) if data is None else data
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    name = f"MonographPDF_{version}_Setup.exe"
    fields = {
        "type": "monograph-pdf-update", "schema": 1, "app_id": update_config.APP_ID,
        "inno_app_id": update_config.INNO_APP_ID, "repository": REPO, "version": version, "channel": channel,
        "release_date": now.date().isoformat(), "issued": format_time(now),
        "expires": format_time(now + timedelta(days=expires_days)), "sequence": sequence,
        "release_notes": f"Monograph PDF {version}\n- Fixes", "release_page": f"https://github.com/{REPO}/releases/tag/v{version}",
        "installed_size": 0,
        "artifacts": [{"kind": "inno-setup", "os": "windows", "arch": "x64", "name": name,
                       "url": f"{base}/{REPO}/releases/download/v{version}/{name}",
                       "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}],
    }
    fields.update(overrides)
    return fields


def manifest_bytes(fields: dict | None = None, secrets=(TEST_SECRET,), **kw) -> bytes:
    fields = signed_fields(**kw) if fields is None else fields
    return json.dumps(sign_manifest(fields, list(secrets))).encode("utf-8")


def with_hosts(cfg: update_config.UpdateConfig, *hosts: str) -> update_config.UpdateConfig:
    return replace(cfg, allowed_hosts=tuple(hosts))


def listing_with_manifest(version: str, *, draft: bool = False, prerelease: bool = False,
                          tag_name: str | None = None, include_manifest: bool = True,
                          manifest_url: str | None = None,
                          base: str = "https://github.com") -> dict:
    """One GitHub Releases API entry for Windows-line discovery tests."""
    tag = tag_name if tag_name is not None else f"v{version}"
    asset = "MonographPDF_update_manifest.json"
    url = manifest_url or f"{base}/{REPO}/releases/download/{tag}/{asset}"
    assets = [{"name": asset, "browser_download_url": url}] if include_manifest else []
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "assets": assets}


def release_listing(*entries: dict) -> bytes:
    return json.dumps(list(entries)).encode("utf-8")
