"""Signed release manifests: parsing, signature verification and update policy.

A manifest is published as a release asset next to Setup.exe::

    {"signed": {...release description...},
     "signatures": [{"keyid": "<16 hex>", "sig": "<base64 Ed25519 signature>"}]}

The signature covers the canonical JSON encoding of ``signed`` (sorted keys, no whitespace, ASCII
only; floats are not allowed). The manifest — not GitHub, the TLS connection or a checksum on
its own — is what authenticates an update: Setup.exe is accepted only when its size and SHA-256
equal the values inside a manifest signed by a trusted key.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.updates import ed25519
from core.updates.config import APP_ID, INNO_APP_ID, UpdateConfig
from core.updates.semver import Version, parse as parse_version

MANIFEST_TYPE = "monograph-pdf-update"
SCHEMA = 1
CHANNELS = ("stable", "prerelease")
MAX_NOTES = 20000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSET_NAME = re.compile(r"^MonographPDF_[0-9A-Za-z.-]+_Setup\.exe$")
_KEYID = re.compile(r"^[0-9a-f]{16}$")
_TIME = "%Y-%m-%dT%H:%M:%SZ"
CLOCK_SKEW = timedelta(hours=24)
# Longest validity a manifest may declare (issued -> expires). The release tool signs for exactly this
# by default. A longer-lived manifest is refused so a captured one cannot be replayed indefinitely.
MAX_VALIDITY = timedelta(days=730)


class ManifestError(ValueError):
    """The manifest is malformed, unsigned, or not acceptable for this installation."""

    def __init__(self, message: str, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code


def canonical_bytes(obj) -> bytes:
    def check(value):
        if isinstance(value, float):
            raise ManifestError("floating-point values are not allowed in signed metadata")
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str):
                    raise ManifestError("object keys must be strings")
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)

    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ManifestError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _time(value, name: str) -> datetime:
    if not isinstance(value, str):
        raise ManifestError(f"{name} must be a UTC timestamp", "timestamp")
    try:
        return datetime.strptime(value, _TIME).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ManifestError(f"{name} must look like 2026-01-31T00:00:00Z", "timestamp") from None


@dataclass(frozen=True)
class Artifact:
    name: str
    url: str
    size: int
    sha256: str
    arch: str
    kind: str


@dataclass(frozen=True)
class ReleaseInfo:
    version: Version
    channel: str
    release_date: str
    issued: datetime
    expires: datetime
    sequence: int
    release_notes: str
    release_page: str
    artifact: Artifact
    min_upgrade_from: Version | None
    installed_size: int
    key_ids: tuple[str, ...]


def sign_manifest(signed: dict, secrets: list[bytes]) -> dict:
    """Release tooling: sign ``signed`` with each 32-byte secret key."""
    body = canonical_bytes(signed)
    sigs = []
    for sk in secrets:
        pk = ed25519.public_key(sk)
        from core.updates.config import key_id

        sigs.append({"keyid": key_id(pk), "sig": base64.b64encode(ed25519.sign(sk, body)).decode("ascii")})
    return {"signed": signed, "signatures": sigs}


def verify_signatures(document: dict, config: UpdateConfig) -> tuple[str, ...]:
    """Return the trusted key ids with a valid signature; ManifestError below the threshold."""
    sigs = document.get("signatures")
    if not isinstance(sigs, list) or not sigs or len(sigs) > 8:
        raise ManifestError("the update information is not signed", "signature")
    body = canonical_bytes(document.get("signed"))
    good: list[str] = []
    for entry in sigs:
        if not isinstance(entry, dict):
            continue
        kid, sig = entry.get("keyid"), entry.get("sig")
        if not isinstance(kid, str) or not _KEYID.match(kid) or kid not in config.trusted_keys or kid in good:
            continue  # unknown or repeated key: never counts
        try:
            raw = base64.b64decode(sig, validate=True) if isinstance(sig, str) else b""
        except (binascii.Error, ValueError):
            continue
        if ed25519.verify(config.trusted_keys[kid], body, raw):
            good.append(kid)
    if len(good) < config.threshold:
        raise ManifestError("the update information is not signed by a trusted Monograph PDF key", "signature")
    return tuple(good)


def parse_and_verify(data: bytes, config: UpdateConfig, *, now: datetime | None = None) -> ReleaseInfo:
    """Authenticate a downloaded manifest and return the release it describes.

    Checks, in order: size and JSON form, signatures (before any field is trusted), product
    identity, schema, channel, version, timestamps and expiry, and the Windows x64 Setup artifact.
    """
    if len(data) > config.max_manifest_bytes:
        raise ManifestError("the update information is too large")
    try:
        doc = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except ManifestError:
        raise
    except (UnicodeDecodeError, ValueError):
        raise ManifestError("the update information is not valid JSON") from None
    if not isinstance(doc, dict) or set(doc) != {"signed", "signatures"} or not isinstance(doc["signed"], dict):
        raise ManifestError("the update information has an unexpected layout")
    key_ids = verify_signatures(doc, config)
    s = doc["signed"]
    if s.get("type") != MANIFEST_TYPE or s.get("schema") != SCHEMA:
        raise ManifestError("unsupported update information format", "identity")
    if s.get("app_id") != APP_ID or s.get("inno_app_id") != INNO_APP_ID:
        raise ManifestError("the update is for a different application", "identity")
    if config.repository and s.get("repository") != config.repository:
        raise ManifestError("the update comes from a different repository", "identity")
    channel = s.get("channel")
    if channel not in CHANNELS:
        raise ManifestError("unknown release channel", "channel")
    try:
        version = parse_version(s.get("version", ""))
    except ValueError:
        raise ManifestError("invalid version in the update information") from None
    if (channel == "stable") == version.is_prerelease:
        raise ManifestError("release channel and version do not match", "channel")
    sequence = s.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or not 0 < sequence < 2**53:
        raise ManifestError("invalid sequence number")
    issued = _time(s.get("issued"), "issued")
    expires = _time(s.get("expires"), "expires")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
    if expires <= issued:
        raise ManifestError("invalid validity period", "timestamp")
    if expires - issued > MAX_VALIDITY:
        raise ManifestError("the validity period of the update information is longer than allowed", "timestamp")
    if now > expires:
        raise ManifestError("the update information has expired (it may be outdated or replayed)", "expired")
    if issued > now + CLOCK_SKEW:
        raise ManifestError("the update information is dated in the future; check the computer's clock", "clock")
    release_date = s.get("release_date")
    if not isinstance(release_date, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", release_date):
        raise ManifestError("invalid release date")
    notes = s.get("release_notes", "")
    if not isinstance(notes, str) or len(notes) > MAX_NOTES:
        raise ManifestError("invalid release notes")
    page = s.get("release_page", "")
    if not isinstance(page, str) or (page and not config.host_allowed(page)):
        raise ManifestError("invalid release page link")
    minimum = s.get("min_upgrade_from")
    min_version = None
    if minimum is not None:
        try:
            min_version = parse_version(minimum)
        except ValueError:
            raise ManifestError("invalid minimum version") from None
    installed_size = s.get("installed_size", 0)
    if not isinstance(installed_size, int) or isinstance(installed_size, bool) or not 0 <= installed_size < 2**40:
        raise ManifestError("invalid installed size")
    artifact = _select_artifact(s.get("artifacts"), config, str(version))
    return ReleaseInfo(version, channel, release_date, issued, expires, sequence, notes, page, artifact,
                       min_version, installed_size, key_ids)


def _select_artifact(items, config: UpdateConfig, version: str) -> Artifact:
    if not isinstance(items, list) or not items or len(items) > 16:
        raise ManifestError("the update lists no installer", "artifact")
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "inno-setup" or item.get("os") != "windows" or item.get("arch") != "x64":
            continue
        name, url, size, digest = item.get("name"), item.get("url"), item.get("size"), item.get("sha256")
        if not isinstance(name, str) or not _ASSET_NAME.match(name) or name != f"MonographPDF_{version}_Setup.exe":
            raise ManifestError("unexpected installer name", "artifact")
        if not isinstance(url, str) or not config.host_allowed(url) or not url.endswith("/" + name):
            raise ManifestError("installer link is not on an allowed host", "artifact")
        if not isinstance(size, int) or isinstance(size, bool) or not 1024 <= size <= 2 * 1024**3:
            raise ManifestError("invalid installer size", "artifact")
        if not isinstance(digest, str) or not _SHA256.match(digest):
            raise ManifestError("invalid installer checksum", "artifact")
        return Artifact(name, url, size, digest, "x64", "inno-setup")
    raise ManifestError("no Windows x64 installer in this update", "artifact")


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_TIME)
