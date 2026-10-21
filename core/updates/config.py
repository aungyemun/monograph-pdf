"""Update trust configuration (bundled, read-only; never read from a user-writable location).

``resources/update/update_config.json`` ships inside the application. It names the release source,
the hosts the updater may contact and the Ed25519 public keys trusted to sign release manifests.
Private signing keys never ship and are never in the repository (docs/SECURE_UPDATES.md).

Update checks are available only when the configuration is ``enabled`` *and* names at least
``threshold`` trusted keys; otherwise the app reports that updates are not configured for this
build — never "up to date".
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

APP_ID = "monograph-pdf"
# Inno Setup AppId of Monograph PDF (installer/MonographPDF.iss); unchanged since PDF Editor
INNO_APP_ID = "{64FC0D97-5E17-405F-9461-D6C075E1B467}"
_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$|^127\.0\.0\.1$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ConfigError(ValueError):
    pass


def key_id(public_key: bytes) -> str:
    """Stable identifier of a public key: the first 16 hex digits of its SHA-256."""
    return hashlib.sha256(public_key).hexdigest()[:16]


@dataclass(frozen=True)
class UpdateConfig:
    enabled: bool
    disabled_reason: str
    repository: str
    manifest_asset: str
    stable_manifest_url: str
    releases_api_url: str
    allowed_hosts: tuple[str, ...]
    trusted_keys: dict = field(default_factory=dict)  # keyid -> 32-byte public key
    threshold: int = 1
    require_authenticode: bool = False
    ca_file: Path | None = None  # test builds only (a local HTTPS test server's CA)
    max_manifest_bytes: int = 256 * 1024
    max_listing_bytes: int = 2 * 1024 * 1024

    @property
    def usable(self) -> bool:
        return self.enabled and len(self.trusted_keys) >= self.threshold >= 1

    def host_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme == "https" and (parts.hostname or "").lower() in self.allowed_hosts \
            and parts.username is None and parts.password is None


def default_config_path() -> Path:
    from app.paths import RESOURCES_DIR

    return RESOURCES_DIR / "update" / "update_config.json"


def load(path: Path | None = None) -> UpdateConfig:
    """Read and validate the configuration; a broken file disables updates (ConfigError)."""
    path = default_config_path() if path is None else path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"update configuration unreadable: {type(exc).__name__}") from None
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ConfigError("unsupported update configuration schema")
    hosts = raw.get("allowed_hosts") or []
    if not isinstance(hosts, list) or not all(isinstance(h, str) and _HOST_RE.match(h) for h in hosts):
        raise ConfigError("allowed_hosts must be a list of host names")
    keys: dict[str, bytes] = {}
    for entry in raw.get("trusted_keys") or []:
        pub = entry.get("public_key", "") if isinstance(entry, dict) else ""
        if not _HEX64.match(pub):
            raise ConfigError("trusted key must be 64 lowercase hex digits")
        pk = bytes.fromhex(pub)
        kid = key_id(pk)
        if entry.get("keyid") not in (None, kid):
            raise ConfigError("trusted key id does not match its public key")
        keys[kid] = pk
    threshold = raw.get("threshold", 1)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise ConfigError("threshold must be a positive integer")
    ca = raw.get("ca_file")
    ca_path = None
    if ca is not None:
        if not isinstance(ca, str) or "/" in ca or "\\" in ca or ca.startswith("."):
            raise ConfigError("ca_file must be a file name beside the configuration")
        ca_path = path.parent / ca
    cfg = UpdateConfig(
        enabled=bool(raw.get("enabled", False)),
        disabled_reason=str(raw.get("disabled_reason", ""))[:300],
        repository=str(raw.get("repository", "")),
        manifest_asset=str(raw.get("manifest_asset", "")),
        stable_manifest_url=str(raw.get("stable_manifest_url", "")),
        releases_api_url=str(raw.get("releases_api_url", "")),
        allowed_hosts=tuple(h.lower() for h in hosts),
        trusted_keys=keys,
        threshold=threshold,
        require_authenticode=bool(raw.get("require_authenticode", False)),
        ca_file=ca_path,
    )
    if cfg.enabled:
        for url in (cfg.stable_manifest_url, cfg.releases_api_url):
            if not cfg.host_allowed(url):
                raise ConfigError("source URLs must be HTTPS on an allowed host")
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", cfg.repository):
            raise ConfigError("repository must be owner/name")
        if not re.match(r"^[A-Za-z0-9_.-]+\.json$", cfg.manifest_asset):
            raise ConfigError("manifest_asset must be a .json file name")
    return cfg


def load_or_disabled(path: Path | None = None) -> UpdateConfig:
    """Like :func:`load`, but a missing or broken configuration simply disables updates."""
    try:
        return load(path)
    except ConfigError as exc:
        return UpdateConfig(False, f"Update configuration is invalid ({exc}).", "", "", "", "", ())
