"""Maintainer signing-key storage and self-test (scripts/packaging/signing_key.py, update_selftest.py).

All keys here are synthetic; no passphrase is ever passed on a command line."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.updates import ed25519  # noqa: E402
from scripts.packaging import signing_key, update_manifest, update_selftest  # noqa: E402

PASS = "synthetic test passphrase"


@pytest.fixture(scope="module")
def secret():
    return os.urandom(32)


@pytest.fixture(scope="module")
def doc(secret):
    return signing_key.encrypt(secret, PASS)


def test_encrypted_key_round_trips_and_never_contains_the_secret(secret, doc):
    text = json.dumps(doc)
    assert secret.hex() not in text and secret.hex().upper() not in text
    assert signing_key.decrypt(doc, PASS) == secret
    assert doc["public_key"] == ed25519.public_key(secret).hex()
    assert doc["kdf"]["n"] >= 2**17 and len(bytes.fromhex(doc["kdf"]["salt"])) == 32


def test_each_file_uses_a_new_salt_and_key_stream(secret, doc):
    other = signing_key.encrypt(secret, PASS)
    assert other["kdf"]["salt"] != doc["kdf"]["salt"] and other["ciphertext"] != doc["ciphertext"]


@pytest.mark.parametrize("field,value", [
    ("ciphertext", "00" * 32), ("mac", "00" * 32), ("created", "2000-01-01T00:00:00Z"),
    ("kdf", {"name": "scrypt", "n": 2**17, "r": 8, "p": 1, "salt": "11" * 32}),
])
def test_any_change_to_the_key_file_is_detected(doc, field, value):
    bad = {**doc, field: value}
    with pytest.raises(signing_key.KeyFileError):
        signing_key.decrypt(bad, PASS)


@pytest.mark.parametrize("kdf", [
    {"name": "scrypt", "n": 2**10, "r": 8, "p": 1}, {"name": "scrypt", "n": 3 * 2**15, "r": 8, "p": 1},
    {"name": "pbkdf2", "n": 2**17, "r": 8, "p": 1}, {"name": "scrypt", "n": 2**17, "r": 1, "p": 1},
])
def test_weak_or_unknown_key_derivation_is_refused(doc, kdf):
    bad = {**doc, "kdf": {**kdf, "salt": doc["kdf"]["salt"]}}
    with pytest.raises(signing_key.KeyFileError):
        signing_key.decrypt(bad, PASS)


def test_wrong_passphrase_is_refused(doc):
    with pytest.raises(signing_key.KeyFileError, match="wrong passphrase"):
        signing_key.decrypt(doc, PASS + "x")


def test_public_key_must_match_key_id(doc):
    with pytest.raises(signing_key.KeyFileError):
        signing_key.decrypt({**doc, "keyid": "0" * 16}, PASS)


def test_self_test_passes_for_a_key_and_its_manifests_cannot_reach_real_installations(secret):
    results = update_selftest.run_checks(secret)
    assert results and all(ok for _, ok in results), update_selftest.report(results)
    assert update_selftest.SELFTEST_REPO != "aungyemun/monograph-pdf"


def test_self_test_detects_a_broken_verifier(secret, monkeypatch):
    monkeypatch.setattr(ed25519, "verify", lambda *a: True)  # accepts every signature
    results = dict(update_selftest.run_checks(secret))
    assert not results["changed release metadata is rejected"]
    assert not results["changed installer checksum is rejected"]
    assert not next(ok for name, ok in results.items() if name.startswith("malformed signatures"))
    assert results["manifest signed by an unknown key is rejected"]  # refused by key id, before verify


def test_keygen_refuses_git_working_copies_and_used_folders(tmp_path, capsys):
    assert update_manifest.main(["keygen", "--out", str(ROOT / "build" / "keys-test")]) == 2
    assert not (ROOT / "build" / "keys-test").exists()
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "something.txt").write_text("x")
    assert update_manifest.main(["keygen", "--out", str(tmp_path / "used")]) == 2
    assert sorted(p.name for p in (tmp_path / "used").iterdir()) == ["something.txt"]


def test_keygen_needs_an_interactive_console(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", open(os.devnull))
    with pytest.raises(SystemExit, match="interactive console"):
        update_manifest.main(["keygen", "--out", str(tmp_path / "new")])
    assert not (tmp_path / "new").exists()


def test_plaintext_test_keys_only_on_request_and_never_overwritten(tmp_path, capsys):
    out = tmp_path / "k"
    assert update_manifest.main(["keygen", "--plaintext-test-key", "--out", str(out)]) == 0
    pub = json.loads(capsys.readouterr().out)["public_key"]
    secret = signing_key.load_secret(out / signing_key.KEY_FILE)
    assert ed25519.public_key(secret).hex() == pub
    before = (out / signing_key.KEY_FILE).read_bytes()
    assert update_manifest.main(["keygen", "--plaintext-test-key", "--out", str(out)]) == 2
    assert (out / signing_key.KEY_FILE).read_bytes() == before


def test_encrypted_key_needs_the_console_to_be_used(tmp_path, monkeypatch, doc):
    key = tmp_path / signing_key.KEY_FILE
    key.write_text(json.dumps(doc), encoding="ascii")
    monkeypatch.setattr(sys, "stdin", open(os.devnull))
    with pytest.raises(SystemExit, match="interactive console"):
        signing_key.load_secret(key)


def test_key_files_inside_a_git_working_copy_are_refused():
    with pytest.raises(SystemExit, match="Git working copy"):
        signing_key.load_secret(ROOT / "VERSION")
