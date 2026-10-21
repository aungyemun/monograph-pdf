"""Optional OCR languages: pinned catalogue, install only a matching file, never download, merged
language folder for Tesseract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.ocr import language_packs as lp

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    for code in ("eng", "jpn", "osd"):
        (bundled / f"{code}.traineddata").write_bytes(code.encode() * 100)
    pack = b"KOREAN MODEL BYTES" * 50
    catalog = tmp_path / "language_packs.json"
    catalog.write_text(json.dumps({"schema": 1, "packs": [
        {"code": "kor", "name": "Korean", "file": "kor.traineddata", "size": len(pack),
         "sha256": hashlib.sha256(pack).hexdigest(), "url": "https://example.invalid/kor.traineddata"}]}))
    monkeypatch.setattr(lp, "CATALOG", catalog)
    monkeypatch.setattr(lp, "tessdata_dir", lambda: bundled)
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "data"))
    download = tmp_path / "Downloads" / "kor.traineddata"
    download.parent.mkdir()
    download.write_bytes(pack)
    return bundled, download


def test_shipped_catalogue_pins_the_requested_languages_from_the_bundled_release():
    data = json.loads((ROOT / "resources" / "ocr" / "language_packs.json").read_text(encoding="utf-8"))
    codes = {p["code"] for p in data["packs"]}
    assert {"jpn_vert", "chi_sim", "chi_tra", "kor", "deu", "fra", "spa"} <= codes
    assert data["source"]["tag"] == "4.1.0" and data["source"]["license"] == "Apache-2.0"
    for p in data["packs"]:
        assert len(p["sha256"]) == 64 and p["size"] > 100_000
        assert p["url"] == f"https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/{p['code']}.traineddata"
    # the bundled files come from the same release (their pins are the CI pins)
    pins = json.loads((ROOT / "scripts" / "ci" / "ocr_engine_pins.json").read_text())["tessdata"]
    assert set(pins) == {"eng.traineddata", "jpn.traineddata", "osd.traineddata"}


def test_language_packs_never_open_a_network_connection():
    text = (ROOT / "core" / "ocr" / "language_packs.py").read_text(encoding="utf-8")
    for forbidden in ("urllib", "http.client", "socket", "requests", "core.updates.net"):
        assert forbidden not in text


def test_only_a_matching_file_is_installed(env):
    bundled, download = env
    assert "kor" not in lp.available_languages()
    pack = lp.install_from_file(download)
    assert pack.code == "kor" and "kor" in lp.available_languages()
    assert (lp.user_language_dir() / "kor.traineddata").read_bytes() == download.read_bytes()
    wrong = download.with_name("other.traineddata")
    wrong.write_bytes(b"x" * download.stat().st_size)  # same size, other content
    with pytest.raises(lp.LanguagePackError):
        lp.install_from_file(wrong)


def test_a_changed_installed_file_is_not_used(env):
    bundled, download = env
    lp.install_from_file(download)
    (lp.user_language_dir() / "kor.traineddata").write_bytes(b"tampered")
    assert "kor" not in lp.available_languages()
    with pytest.raises(lp.LanguagePackError):
        lp.tessdata_for("eng+kor")


def test_tessdata_folder_for_bundled_and_optional_languages(env):
    bundled, download = env
    assert lp.tessdata_for("eng+jpn") == bundled
    lp.install_from_file(download)
    merged = lp.tessdata_for("eng+kor")
    assert merged == lp.user_language_dir()
    for code in ("eng", "jpn", "osd", "kor"):
        assert (merged / f"{code}.traineddata").is_file()
    assert (merged / "eng.traineddata").read_bytes() == (bundled / "eng.traineddata").read_bytes()
    assert lp.remove("kor") and "kor" not in lp.available_languages()
