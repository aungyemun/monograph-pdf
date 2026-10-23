"""Stand-alone signing-tool bundle and the multi-copy self-test (synthetic keys only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.updates import config as update_config  # noqa: E402
from scripts.packaging import make_signing_bundle, signing_key, update_manifest  # noqa: E402


@pytest.fixture
def synthetic(tmp_path, capsys):
    keys = tmp_path / "keys"
    assert update_manifest.main(["keygen", "--plaintext-test-key", "--out", str(keys)]) == 0
    pub = json.loads(capsys.readouterr().out)["public_key"]
    cfg = json.loads((ROOT / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    cfg["trusted_keys"] = [{"keyid": update_config.key_id(bytes.fromhex(pub)), "public_key": pub}]
    cfg_file = tmp_path / "update_config.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / signing_key.KEY_FILE).write_bytes((keys / signing_key.KEY_FILE).read_bytes())
    return keys / signing_key.KEY_FILE, copy / signing_key.KEY_FILE, cfg_file, tmp_path


def test_selftest_checks_copies_trust_and_writes_a_report_without_the_secret(synthetic, capsys):
    key, copy, cfg_file, tmp = synthetic
    scan = tmp / "scan"
    scan.mkdir()
    (scan / "notes.txt").write_text("nothing secret here", encoding="utf-8")
    report = tmp / "report.txt"
    rc = update_manifest.main(["selftest", "--key", str(key), "--key", str(copy), "--config", str(cfg_file),
                               "--scan", str(scan), "--report", str(report)])
    text = report.read_text(encoding="utf-8")
    assert rc == 0 and "RESULT: PASS" in text and "all key files hold the same key" in text
    assert key.read_text(encoding="ascii").strip() not in text


def test_selftest_fails_for_an_untrusted_key_or_a_leaked_secret(synthetic, capsys):
    key, _, cfg_file, tmp = synthetic
    assert update_manifest.main(["selftest", "--key", str(key)]) == 1  # the shipped config trusts only production
    assert "FAIL" in capsys.readouterr().out
    leak = tmp / "leak"
    leak.mkdir()
    (leak / "oops.txt").write_text("key: " + key.read_text(encoding="ascii").strip().upper(), encoding="utf-8")
    import zipfile

    with zipfile.ZipFile(leak / "backup.zip", "w") as z:
        z.writestr("inner.txt", key.read_text(encoding="ascii"))
    assert update_manifest.main(["selftest", "--key", str(key), "--config", str(cfg_file), "--scan", str(leak)]) == 1
    out = capsys.readouterr().out
    assert "oops.txt" in out and "backup.zip!inner.txt" in out


def test_bundle_is_complete_self_contained_and_does_not_load_the_application(tmp_path):
    out = tmp_path / "bundle"
    manifest = make_signing_bundle.build(out)
    assert make_signing_bundle.verify(out) == []
    assert set(manifest["files"]) == set(make_signing_bundle.FILES) | {"core/__init__.py", "requirements-signing.txt"}
    assert not any(p.suffix in (".key", ".pem", ".exe", ".dll", ".pyd") for p in out.rglob("*"))
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); from scripts.packaging import update_manifest; "
             "print(sorted(m for m in ('fitz', 'pymupdf', 'PySide6', 'app') if m in sys.modules))")
    res = subprocess.run([sys.executable, "-I", "-c", probe, str(out)], capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "[]"
    (out / "core" / "updates" / "manifest.py").write_text("# changed", encoding="utf-8")
    assert make_signing_bundle.verify(out) == ["changed core/updates/manifest.py"]


def test_bundle_tools_verify_a_manifest_in_a_separate_process(tmp_path):
    out = tmp_path / "bundle"
    make_signing_bundle.build(out)
    tool = out / "scripts" / "packaging" / "update_manifest.py"
    keys = tmp_path / "keys"
    res = subprocess.run([sys.executable, "-I", str(tool), "keygen", "--plaintext-test-key", "--out", str(keys)],
                         capture_output=True, text=True, check=True)
    pub = json.loads(res.stdout)["public_key"]
    cfg = json.loads((out / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    cfg["trusted_keys"] = [{"keyid": update_config.key_id(bytes.fromhex(pub)), "public_key": pub}]
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    res = subprocess.run([sys.executable, "-I", str(tool), "selftest", "--key", str(keys / signing_key.KEY_FILE),
                          "--config", str(cfg_file)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "RESULT: PASS" in res.stdout
