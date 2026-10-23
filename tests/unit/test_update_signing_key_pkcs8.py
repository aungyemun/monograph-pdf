"""Standard encrypted PKCS#8 copy of the update-signing key (synthetic keys only).

Needs the maintainer-only ``cryptography`` package (installed in CI and in the signing environment;
never part of the application)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.updates import config as update_config  # noqa: E402
from core.updates import ed25519  # noqa: E402
from scripts.packaging import signing_key  # noqa: E402

PASS = "synthetic pass phrase \u00fc"  # non-ASCII on purpose (NFC, UTF-8)


@pytest.fixture(scope="module")
def secret():
    return os.urandom(32)


@pytest.fixture(scope="module")
def pem(secret):
    return signing_key.export_pkcs8(secret, PASS)


def _reencode(der: bytes) -> bytes:
    b64 = base64.b64encode(der).decode("ascii")
    return ("\n".join([signing_key.PEM_HEADER, *[b64[i:i + 64] for i in range(0, len(b64), 64)],
                       signing_key.PEM_FOOTER]) + "\n").encode("ascii")


def _der(pem: bytes) -> bytes:
    return base64.b64decode("".join(pem.decode("ascii").strip().splitlines()[1:-1]))


def test_pkcs8_copy_round_trips_with_the_maintained_library(secret, pem):
    assert signing_key.load_pkcs8(pem, PASS, ed25519.public_key(secret)) == secret
    assert secret not in _der(pem) and secret.hex().encode() not in pem


def test_pkcs8_uses_pbes2_scrypt_with_the_same_strength_as_the_original(pem):
    assert signing_key.describe_pkcs8(pem) == {
        "scheme": "PBES2", "kdf": "scrypt", "salt_bytes": 16, "n": signing_key.SCRYPT_N, "r": 8, "p": 1,
        "cipher": "AES-256-CBC", "iv_bytes": 16, "ciphertext_bytes": 64}


def test_library_default_pkcs8_encryption_is_weaker_and_not_used():
    """cryptography's BestAvailableEncryption for PKCS#8 is PBKDF2-HMAC-SHA256 with 2048 iterations:
    far cheaper to guess than scrypt N=2^17, so the tooling never uses it."""
    from cryptography.hazmat.primitives import serialization as s
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    der = Ed25519PrivateKey.generate().private_bytes(s.Encoding.DER, s.PrivateFormat.PKCS8,
                                                     s.BestAvailableEncryption(b"x" * 16))
    with pytest.raises(signing_key.KeyFileError, match="unsupported PKCS#8 encryption"):
        signing_key.describe_pkcs8(_reencode(der))


def test_any_change_to_the_ciphertext_or_a_wrong_key_is_refused(secret, pem):
    der = _der(pem)
    pub = ed25519.public_key(secret)
    for pos in range(len(der) - 64, len(der)):
        bad = bytearray(der)
        bad[pos] ^= 0x01
        with pytest.raises(signing_key.KeyFileError):
            signing_key.load_pkcs8(_reencode(bytes(bad)), PASS, pub)
    with pytest.raises(signing_key.KeyFileError, match="wrong passphrase"):
        signing_key.load_pkcs8(pem, PASS + "x", pub)
    with pytest.raises(signing_key.KeyFileError, match="expected public key"):
        signing_key.load_pkcs8(pem, PASS, ed25519.public_key(os.urandom(32)))


def test_weak_scrypt_parameters_are_refused(secret):
    weak = signing_key.export_pkcs8(secret, PASS, n=2**10)
    with pytest.raises(signing_key.KeyFileError, match="weaker"):
        signing_key.load_pkcs8(weak, PASS, ed25519.public_key(secret))


def test_both_ed25519_implementations_sign_identically(secret):
    msg = b"canonical manifest bytes"
    assert signing_key.sign_with_cryptography(secret, msg) == ed25519.sign(secret, msg)


def test_pkcs8_needs_the_public_key_file_beside_it(tmp_path, secret, pem):
    key = tmp_path / signing_key.PKCS8_FILE
    key.write_bytes(pem)
    with pytest.raises(signing_key.KeyFileError, match="pub.json"):
        signing_key.expected_public_for(key)
    pub = ed25519.public_key(secret)
    (tmp_path / signing_key.PUBLIC_FILE).write_text(
        json.dumps({"keyid": update_config.key_id(pub), "public_key": pub.hex()}), encoding="utf-8")
    assert signing_key.expected_public_for(key) == pub


@pytest.mark.skipif(not Path(r"C:\Program Files\Git\usr\bin\openssl.exe").is_file() and not shutil.which("openssl"),
                    reason="OpenSSL command line not available")
def test_openssl_reads_the_same_format(secret):
    """Independent implementation: OpenSSL decrypts our PBES2/scrypt encoding (at OpenSSL's own
    32 MiB scrypt memory limit, N=2^14; the production files use N=2^17, read by cryptography)."""
    exe = r"C:\Program Files\Git\usr\bin\openssl.exe"
    exe = exe if Path(exe).is_file() else shutil.which("openssl")
    pw = "synthetic-only"
    pem14 = signing_key.export_pkcs8(secret, pw, n=2**14)
    out = subprocess.run([exe, "pkey", "-outform", "DER", "-passin", "pass:" + pw], input=pem14,
                         capture_output=True, check=True).stdout
    assert out[-32:] == secret
