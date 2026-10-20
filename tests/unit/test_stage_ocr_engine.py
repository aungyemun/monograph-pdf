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
