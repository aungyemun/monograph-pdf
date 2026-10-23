"""verify_release.py: the signed update manifest of a release (synthetic keys only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
sys.path.insert(0, str(ROOT))

import verify_release as vr  # noqa: E402

from core.updates import config as update_config  # noqa: E402
from core.updates import ed25519  # noqa: E402
from scripts.packaging import update_manifest  # noqa: E402

VERSION = "7.8.9"


@pytest.fixture
def release(tmp_path, capsys):
    keys = tmp_path / "keys"
    assert update_manifest.main(["keygen", "--plaintext-test-key", "--out", str(keys)]) == 0
    pub = json.loads(capsys.readouterr().out)["public_key"]
    root = tmp_path / "release_root"
    cfg_dir = root / "resources" / "update"
    cfg_dir.mkdir(parents=True)
    cfg = json.loads((ROOT / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    cfg["trusted_keys"] = [{"keyid": update_config.key_id(bytes.fromhex(pub)), "public_key": pub}]
    cfg["enabled"] = True
    (cfg_dir / "update_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "installer"
    out.mkdir()
    setup = out / f"MonographPDF_{VERSION}_Setup.exe"
    setup.write_bytes(b"MZ" + bytes(5000))

    def make(*extra, version_file=setup):
        args = ["make", "--setup", str(version_file), "--channel", "stable", "--sequence", "3",
                "--key", str(keys / "update-signing.key"), "--out", str(out / vr.MANIFEST_NAME),
                "--config", str(cfg_dir / "update_config.json"), *extra]
        assert update_manifest.main(args) == 0

    return out, setup, root, make


def test_a_correct_manifest_passes(release):
    out, setup, root, make = release
    make()
    problems, detail = vr.manifest_problems(out, VERSION, setup, root)
    assert problems == [] and "sequence 3" in detail


def test_missing_manifest_fails_when_updates_are_enabled(release):
    out, setup, root, _ = release
    problems, _ = vr.manifest_problems(out, VERSION, setup, root)
    assert problems and "missing" in problems[0]


def test_manifest_for_other_bytes_or_short_validity_fails(release):
    out, setup, root, make = release
    make("--expires-days", "10")
    problems, _ = vr.manifest_problems(out, VERSION, setup, root)
    assert any("less than 30 days" in p for p in problems)
    make()
    setup.write_bytes(b"MZ" + bytes(5001))  # rebuilt after signing
    problems, _ = vr.manifest_problems(out, VERSION, setup, root)
    assert any("SHA-256" in p for p in problems)


def test_manifest_signed_by_a_key_the_release_does_not_trust_fails(release, tmp_path):
    out, setup, root, make = release
    make()
    cfg_file = root / "resources" / "update" / "update_config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    other = ed25519.public_key(bytes(range(32)))
    cfg["trusted_keys"] = [{"keyid": update_config.key_id(other), "public_key": other.hex()}]
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    problems, _ = vr.manifest_problems(out, VERSION, setup, root)
    assert problems and "does not verify" in problems[0]


def test_no_manifest_needed_and_none_allowed_when_updates_are_disabled(release):
    out, setup, root, make = release
    cfg_file = root / "resources" / "update" / "update_config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    cfg_file.write_text(json.dumps({**cfg, "enabled": False}), encoding="utf-8")
    assert vr.manifest_problems(out, VERSION, setup, root)[0] == []
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    make()
    cfg_file.write_text(json.dumps({**cfg, "enabled": False}), encoding="utf-8")
    assert vr.manifest_problems(out, VERSION, setup, root)[0]


def test_build_check_before_signing_reports_the_missing_manifest_as_not_verified():
    """build_release.ps1 verifies before the manifest exists; publishing (without the option) fails."""
    import inspect

    src = inspect.getsource(vr.main)
    assert "before_signing" in src and "NOT VERIFIED  update-manifest" in src
    build = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    assert "--before-signing" in build
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "--before-signing" not in checklist  # the publishing check never uses it

