"""Maintainer tool for signed update manifests (docs/SECURE_UPDATES.md).

    python scripts/packaging/update_manifest.py keygen --out <new folder outside any Git working copy>
    python scripts/packaging/update_manifest.py selftest --key <folder>/update-signing.key
    python scripts/packaging/update_manifest.py export-pkcs8 --key <folder>/update-signing.key \
        --out <folder>/update-signing.pkcs8.pem
    python scripts/packaging/update_manifest.py make --setup installer/MonographPDF_X.Y.Z_Setup.exe \
        --notes docs/releases/vX.Y.Z.md --channel stable --sequence N --key <secret key file> \
        --out installer/MonographPDF_update_manifest.json [--expires-days 730] [--min-upgrade-from X.Y.Z]
    python scripts/packaging/update_manifest.py verify --manifest <file> [--config resources/update/update_config.json]

* ``keygen`` (run it in an interactive console window) asks twice for a new passphrase, writes
  ``update-signing.key`` — the Ed25519 secret encrypted with that passphrase (scrypt + HMAC-SHA256,
  scripts/packaging/signing_key.py) — and ``update-signing.pub.json`` (public key, key id,
  fingerprint) into a new folder that only the current Windows user may open, decrypts the file again
  and runs ``selftest``. It refuses folders inside a Git working copy and never overwrites a key.
  ``--plaintext-test-key`` writes an unencrypted synthetic key for automated tests only.
* ``selftest`` checks a key against the application's own verification code with fictional,
  in-memory manifests that no real installation can accept (scripts/packaging/update_selftest.py).
* ``export-pkcs8`` writes the same secret as a standard encrypted PKCS#8 file (PBES2 + scrypt +
  AES-256-CBC, same passphrase; needs the ``cryptography`` package of the signing environment),
  reads it back with ``cryptography`` and checks it reproduces the same public key. The original file
  is not changed. ``--key`` of every command accepts either format; a PKCS#8 file needs
  ``update-signing.pub.json`` beside it (its integrity check).
* ``make`` also signs with OpenSSL through ``cryptography`` when it is installed and refuses to write
  the manifest unless both Ed25519 implementations produce the identical signature and the manifest
  verifies against ``--config`` exactly as the application checks it.
* ``make`` signs the release description: version, channel, the Setup asset's URL on GitHub
  Releases, size, SHA-256, release notes, validity period and a sequence number that must grow with
  every manifest ever signed (it protects against replays of older manifests).
* ``verify`` checks a manifest exactly as the application does.

Passphrases are only read from the console (never from arguments, environment variables or files)
and the secret key is never printed. Nothing here contacts the network or publishes anything.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.updates import config as update_config  # noqa: E402
from core.updates import ed25519  # noqa: E402
from core.updates.manifest import (  # noqa: E402
    MAX_VALIDITY,
    ManifestError,
    canonical_bytes,
    format_time,
    parse_and_verify,
    sign_manifest,
)
from core.updates.semver import parse as parse_version  # noqa: E402
from scripts.packaging import signing_key, update_selftest  # noqa: E402

MAX_NOTES = 20000


def keygen_plaintext_test_key(out: Path) -> int:
    """Synthetic, unencrypted key for automated tests (never for releases)."""
    import secrets

    if signing_key.inside_git_checkout(out):
        print("refusing to write a signing key inside a Git working copy", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    key = out / signing_key.KEY_FILE
    if key.exists():
        print(f"{key} already exists; not overwritten", file=sys.stderr)
        return 2
    secret = secrets.token_bytes(32)
    signing_key.write_new(key, secret.hex() + "\n")
    pub = ed25519.public_key(secret)
    print(json.dumps({"keyid": update_config.key_id(pub), "public_key": pub.hex()}, indent=2))
    return 0


def keygen(out: Path) -> int:
    """New production key: encrypted, in a new folder restricted to the current user, self-tested."""
    import secrets

    if signing_key.inside_git_checkout(out):
        print("refusing to write a signing key inside a Git working copy", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty; choose a new folder (an existing key is never overwritten)", file=sys.stderr)
        return 2
    signing_key.require_console()
    passphrase = signing_key.ask_new_passphrase()
    out.mkdir(parents=True, exist_ok=True)
    acl = signing_key.restrict_to_current_user(out)
    secret = secrets.token_bytes(32)  # operating-system CSPRNG
    doc = signing_key.encrypt(secret, passphrase)
    key = out / signing_key.KEY_FILE
    signing_key.write_new(key, json.dumps(doc, indent=1, sort_keys=True) + "\n")
    # read the file back and decrypt it with the passphrase just entered
    again = signing_key.decrypt(json.loads(key.read_text(encoding="ascii")), passphrase)
    roundtrip = again == secret
    pub = ed25519.public_key(secret)
    results = update_selftest.run_checks(again)
    del secret, again, passphrase
    record = {
        "algorithm": "Ed25519 (RFC 8032)",
        "keyid": update_config.key_id(pub),
        "public_key": pub.hex(),
        "fingerprint_sha256": signing_key.fingerprint(pub),
        "created": doc["created"],
        "private_key_file": str(key),
        "private_key_protection": f"passphrase (scrypt N={signing_key.SCRYPT_N}, r={signing_key.SCRYPT_R}, "
                                  f"p={signing_key.SCRYPT_P}) + HMAC-SHA256; folder: {acl}",
        "file_roundtrip_decrypt": "PASS" if roundtrip else "FAIL",
        "selftest": [f"{'PASS' if ok else 'FAIL'}  {name}" for name, ok in results],
    }
    signing_key.write_new(out / signing_key.PUBLIC_FILE, json.dumps(record, indent=1) + "\n")
    print(update_selftest.report(results))
    print(json.dumps({k: record[k] for k in ("algorithm", "keyid", "public_key", "fingerprint_sha256")}, indent=2))
    print(f"Folder protection: {acl}")
    ok = roundtrip and all(ok for _, ok in results)
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


def selftest(keys: list[Path], config: Path, scan: list[Path], report: Path | None = None) -> int:
    """Open every key file (one passphrase prompt when they hold the same key), check they hold the
    same key, that the configuration trusts it, run the self-test, and look for unencrypted copies of
    the secret in the ``scan`` folders. Writes only non-secret results."""
    secrets_ = [signing_key.load_secret(k) for k in keys]
    signing_key.forget_passphrases()
    same = all(x == secrets_[0] for x in secrets_)
    public = ed25519.public_key(secrets_[0])
    kid = update_config.key_id(public)
    cfg = update_config.load(config)
    trusted = cfg.trusted_keys.get(kid) == public
    results = update_selftest.run_checks(secrets_[0])
    hits = [h for folder in scan for h in signing_key.scan_for_secret(folder, secrets_[0])]
    msg = b"monograph-pdf selftest"
    other = signing_key.sign_with_cryptography(secrets_[0], msg)
    same_sig = other is None or other == ed25519.sign(secrets_[0], msg)
    del secrets_
    lines = [f"key id: {kid}", f"key files: {', '.join(str(k) for k in keys)}",
             f"{'PASS' if same else 'FAIL'}  all key files hold the same key",
             f"{'PASS' if trusted else 'FAIL'}  {config} trusts this key",
             update_selftest.report(results)]
    if other is not None:
        lines.insert(4, f"{'PASS' if same_sig else 'FAIL'}  OpenSSL (cryptography) and the built-in Ed25519 "
                        "code sign identically")
    else:
        lines.insert(4, "NOT VERIFIED  second Ed25519 implementation (cryptography not installed)")
    for folder in scan:
        lines.append(f"{'PASS' if not hits else 'FAIL'}  no unencrypted copy of the secret under {folder}")
    lines += [f"  found in: {h}" for h in hits]
    ok = same and trusted and same_sig and all(o for _, o in results) and not hits
    lines.append("RESULT: PASS" if ok else "RESULT: FAIL")
    text = "\n".join(lines)
    print(text)
    if report is not None:
        signing_key.write_new(report, text + "\n")
    return 0 if ok else 1


def _read_secret(path: Path) -> bytes:
    return signing_key.load_secret(path)


def notes_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    return text[:MAX_NOTES]


def export_pkcs8(key: Path, out: Path) -> int:
    if signing_key.inside_git_checkout(out):
        print("refusing to write a signing key inside a Git working copy", file=sys.stderr)
        return 2
    if out.exists():
        print(f"{out} already exists; not overwritten", file=sys.stderr)
        return 2
    signing_key.require_console()
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("export-pkcs8 needs the 'cryptography' package (signing environment)", file=sys.stderr)
        return 2
    doc = json.loads(key.read_text(encoding="ascii"))
    public = signing_key.read_public(doc)
    passphrase = signing_key.ask_passphrase(doc["keyid"])
    try:
        secret = signing_key.decrypt(doc, passphrase)
    except signing_key.KeyFileError as exc:
        print(f"cannot use the signing key: {exc}", file=sys.stderr)
        return 1
    pem = signing_key.export_pkcs8(secret, passphrase)
    signing_key.write_new(out, pem.decode("ascii"))
    again = signing_key.load_pkcs8(out.read_bytes(), passphrase, public)
    ok = again == secret
    del secret, again, passphrase
    print(json.dumps({"written": str(out), "keyid": doc["keyid"], **signing_key.describe_pkcs8(pem),
                      "readback_same_key": ok}, indent=1))
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


def make(a) -> int:
    setup: Path = a.setup
    m = re.fullmatch(r"MonographPDF_([0-9A-Za-z.-]+)_Setup\.exe", setup.name)
    if not m:
        print("--setup must be MonographPDF_<version>_Setup.exe", file=sys.stderr)
        return 2
    version = str(parse_version(m.group(1)))
    if (a.channel == "stable") == parse_version(version).is_prerelease:
        print("stable releases need X.Y.Z, prereleases X.Y.Z-label", file=sys.stderr)
        return 2
    if not 1 <= a.expires_days <= MAX_VALIDITY.days:
        print(f"--expires-days must be between 1 and {MAX_VALIDITY.days}", file=sys.stderr)
        return 2
    cfg = update_config.load(a.config)
    repo = cfg.repository
    data = setup.read_bytes()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    tag = f"v{version}"
    signed = {
        "type": "monograph-pdf-update",
        "schema": 1,
        "app_id": update_config.APP_ID,
        "inno_app_id": update_config.INNO_APP_ID,
        "repository": repo,
        "version": version,
        "channel": a.channel,
        "release_date": a.release_date or now.date().isoformat(),
        "issued": format_time(now),
        "expires": format_time(now + timedelta(days=a.expires_days)),
        "sequence": a.sequence,
        "release_notes": notes_text(a.notes) if a.notes else "",
        "release_page": (f"{a.download_base.rstrip('/')}/tag/{tag}" if a.download_base
                         else f"https://github.com/{repo}/releases/tag/{tag}"),
        "installed_size": a.installed_size,
        "artifacts": [{
            "kind": "inno-setup", "os": "windows", "arch": "x64", "name": setup.name,
            "url": f"{(a.download_base or f'https://github.com/{repo}/releases/download').rstrip('/')}/{tag}/{setup.name}",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }],
    }
    if a.min_upgrade_from:
        signed["min_upgrade_from"] = str(parse_version(a.min_upgrade_from))
    secrets_ = [_read_secret(k) for k in a.key]
    doc = sign_manifest(signed, secrets_)
    body = canonical_bytes(signed)
    for sk_, entry in zip(secrets_, doc["signatures"]):
        other = signing_key.sign_with_cryptography(sk_, body)
        if other is not None and base64.b64encode(other).decode("ascii") != entry["sig"]:
            print("the two Ed25519 implementations disagree; nothing was written", file=sys.stderr)
            return 1
    del secrets_
    if cfg.usable:
        try:
            parse_and_verify(json.dumps(doc).encode("utf-8"), cfg)
        except ManifestError as exc:
            print(f"the signed manifest does not verify against {a.config}: {exc}; nothing was written",
                  file=sys.stderr)
            return 1
    a.out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {a.out} (version {version}, {a.channel}, sequence {a.sequence}, expires {signed['expires']})")
    return 0


def verify(a) -> int:
    cfg = update_config.load(a.config)
    if not cfg.trusted_keys:
        print("the configuration has no trusted keys", file=sys.stderr)
        return 1
    try:
        rel = parse_and_verify(a.manifest.read_bytes(), cfg)
    except ManifestError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"PASS: {rel.version} ({rel.channel}), sequence {rel.sequence}, signed by {', '.join(rel.key_ids)}, "
          f"expires {format_time(rel.expires)}, {rel.artifact.name} {rel.artifact.size} bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", type=Path, required=True)
    k.add_argument("--plaintext-test-key", action="store_true",
                   help="automated tests only: write an unencrypted synthetic key")
    t = sub.add_parser("selftest")
    t.add_argument("--key", type=Path, action="append", required=True,
                   help="key file; repeat to check several copies of the same key")
    t.add_argument("--config", type=Path, default=ROOT / "resources" / "update" / "update_config.json")
    t.add_argument("--scan", type=Path, action="append", default=[],
                   help="folder to search for unencrypted copies of the secret (also inside ZIP files)")
    t.add_argument("--report", type=Path, help="write the (non-secret) results to this new file")
    e = sub.add_parser("export-pkcs8")
    e.add_argument("--key", type=Path, required=True, help="the original update-signing.key")
    e.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("make")
    m.add_argument("--setup", type=Path, required=True)
    m.add_argument("--notes", type=Path)
    m.add_argument("--channel", choices=("stable", "prerelease"), required=True)
    m.add_argument("--sequence", type=int, required=True)
    m.add_argument("--key", type=Path, action="append", required=True)
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--expires-days", type=int, default=730,
                   help="validity of the manifest in days (1-730; the application refuses longer ones)")
    m.add_argument("--release-date")
    m.add_argument("--installed-size", type=int, default=0)
    m.add_argument("--min-upgrade-from")
    m.add_argument("--download-base", help="tests only: base URL of a local mock release server")
    m.add_argument("--config", type=Path, default=ROOT / "resources" / "update" / "update_config.json")
    v = sub.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--config", type=Path, default=ROOT / "resources" / "update" / "update_config.json")
    a = ap.parse_args(argv)
    if a.cmd == "keygen":
        return keygen_plaintext_test_key(a.out) if a.plaintext_test_key else keygen(a.out)
    if a.cmd == "selftest":
        return selftest(a.key, a.config, a.scan, a.report)
    if a.cmd == "export-pkcs8":
        return export_pkcs8(a.key, a.out)
    if a.cmd == "make":
        return make(a)
    return verify(a)


if __name__ == "__main__":
    sys.exit(main())
