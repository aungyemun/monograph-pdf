"""CI OCR staging (scripts/ci/stage_ocr_engine.py): only a byte-identical engine is ever staged."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import stage_ocr_engine as so  # noqa: E402

LANG = {f"{lang}.traineddata": f"lang {lang}".encode() for lang in so.LANGS}


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def env(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    installed.mkdir()
    files = {"tesseract.exe": b"MZ tess", "libtesseract-5.dll": b"MZ lib"}
    for n, b in files.items():
        (installed / n).write_bytes(b)
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"tesseract_version": "x", "engine": {n: _h(b) for n, b in files.items()},
                                "tessdata": {n: _h(b) for n, b in LANG.items()}}), encoding="utf-8")
    monkeypatch.setattr(so, "PINS", pins)
    monkeypatch.setattr(so, "ENGINE", tmp_path / "repo" / "engines" / "ocr")
    monkeypatch.setattr(so, "TESSDATA", tmp_path / "repo" / "models" / "tessdata")
    served = dict(LANG)
    monkeypatch.setattr(so.urllib.request, "urlopen",
                        lambda url, timeout=0: io.BytesIO(served[url.rsplit("/", 1)[1]]))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return installed, served


def test_identical_engine_and_language_data_are_staged(env, capsys):
    installed, _ = env
    assert so.main(["--from", str(installed)]) == 0
    assert (so.ENGINE / "tesseract.exe").read_bytes() == b"MZ tess"
    assert sorted(p.name for p in so.TESSDATA.iterdir()) == sorted(LANG)
    assert "staged" in capsys.readouterr().out


@pytest.mark.parametrize("tamper", ["engine", "missing", "language"])
def test_any_difference_stages_nothing(env, capsys, tamper):
    installed, served = env
    if tamper == "engine":
        (installed / "libtesseract-5.dll").write_bytes(b"MZ other")
    elif tamper == "missing":
        (installed / "libtesseract-5.dll").unlink()
    else:
        served["jpn.traineddata"] = b"different"
    assert so.main(["--from", str(installed)]) == 0
    assert not so.ENGINE.exists() and not so.TESSDATA.exists()
    assert "not staged" in capsys.readouterr().out


def test_missing_install_is_reported_not_staged(env, tmp_path, capsys):
    assert so.main(["--from", str(tmp_path / "nowhere")]) == 0
    assert not so.ENGINE.exists()
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_require_turns_a_refused_engine_into_a_failure(env, tmp_path, capsys):
    installed, _ = env
    (installed / "libtesseract-5.dll").write_bytes(b"MZ newer build")
    assert so.main(["--from", str(installed), "--require"]) == 1
    assert not so.ENGINE.exists()
    assert so.main(["--from", str(tmp_path / "nowhere"), "--require"]) == 1


def test_the_notice_is_the_project_file_checked_against_the_pins(env, tmp_path, monkeypatch):
    installed, _ = env
    notice = tmp_path / "TESSERACT_NOTICE.txt"
    notice.write_bytes(b"Tesseract OCR notice")
    pins = json.loads(so.PINS.read_text(encoding="utf-8"))
    pins["engine"]["TESSERACT_NOTICE.txt"] = _h(b"Tesseract OCR notice")
    so.PINS.write_text(json.dumps(pins), encoding="utf-8")
    monkeypatch.setattr(so, "NOTICE", notice)
    assert so.main(["--from", str(installed), "--require"]) == 0
    assert (so.ENGINE / "TESSERACT_NOTICE.txt").read_bytes() == b"Tesseract OCR notice"
    # A changed notice is refused like any other file (no placeholder is written in its place)
    for p in (so.ENGINE, so.TESSDATA):
        for f in p.iterdir():
            f.unlink()
    notice.write_bytes(b"edited")
    assert so.main(["--from", str(installed), "--require"]) == 1
    assert not any(so.ENGINE.iterdir())


def test_language_data_comes_from_an_immutable_tag():
    assert "/tessdata_fast/raw/4.1.0/" in so.TESSDATA_URL and "/main/" not in so.TESSDATA_URL


def test_verify_accepts_only_the_pinned_files(env, capsys):
    installed, _ = env
    assert so.main(["--from", str(installed)]) == 0
    (so.ENGINE / "MANIFEST.json").write_text("{}", encoding="utf-8")  # audit note: ignored
    assert so.main(["--verify"]) == 0
    (so.ENGINE / "libextra.dll").write_bytes(b"MZ extra")  # would be shipped without a pin
    assert so.main(["--verify"]) == 1
    (so.ENGINE / "libextra.dll").unlink()
    (so.TESSDATA / "jpn.traineddata").write_bytes(b"other")
    assert so.main(["--verify"]) == 1
    (so.TESSDATA / "jpn.traineddata").unlink()
    assert so.main(["--verify"]) == 1
    assert "missing" in capsys.readouterr().out


def test_vendor_script_only_uses_the_pinned_workflow():
    """scripts/vendor_ocr.ps1 must not download or copy an unpinned engine (it used to install the newest
    Tesseract through winget and download language data from a moving branch without any hash check)."""
    text = (ROOT / "scripts" / "vendor_ocr.ps1").read_text(encoding="utf-8-sig")
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "stage_ocr_engine.py" in code and "--require" in code and "--verify" in code
    for forbidden in ("winget", "Invoke-WebRequest", "http://", "https://", "Get-Command tesseract", "Copy-Item"):
        assert forbidden not in code, forbidden


def test_release_build_verifies_the_ocr_engine_before_packaging():
    text = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8-sig")
    verify_at = text.find("stage_ocr_engine.py\") --verify")
    copy_at = text.find("foreach ($Side in @(\"engines\\ocr\", \"models\\tessdata\"))")
    assert verify_at != -1 and copy_at != -1 and verify_at < copy_at


def _snapshot(*folders: Path) -> dict[str, bytes]:
    return {f"{d.name}/{p.name}": p.read_bytes() for d in folders for p in sorted(d.iterdir())}


@pytest.mark.parametrize("bad", ["newer_engine", "language_data"])
def test_a_refused_engine_never_replaces_a_valid_one(env, bad):
    """A valid engine already in place stays byte-identical when a later staging is refused (another
    Tesseract version, or language data whose hash differs): nothing is copied before every file passed."""
    installed, served = env
    assert so.main(["--from", str(installed), "--require"]) == 0
    before = _snapshot(so.ENGINE, so.TESSDATA)
    if bad == "newer_engine":
        (installed / "tesseract.exe").write_bytes(b"MZ tess 5.5")
    else:
        served["eng.traineddata"] = b"other model"
    assert so.main(["--from", str(installed), "--require"]) == 1
    assert _snapshot(so.ENGINE, so.TESSDATA) == before
    assert so.main(["--verify"]) == 0


def test_extra_files_in_the_installation_are_never_copied(env):
    """Only pinned files are taken from the Tesseract installation; anything else there (another DLL,
    an uninstaller, documentation) is ignored, so it cannot reach the release."""
    installed, _ = env
    (installed / "libunapproved.dll").write_bytes(b"MZ extra")
    (installed / "unins000.exe").write_bytes(b"MZ uninstaller")
    assert so.main(["--from", str(installed), "--require"]) == 0
    assert sorted(p.name for p in so.ENGINE.iterdir()) == ["libtesseract-5.dll", "tesseract.exe"]
    assert so.main(["--verify"]) == 0
