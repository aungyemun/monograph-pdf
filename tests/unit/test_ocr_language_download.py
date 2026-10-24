"""Download and Install of an optional OCR language: only the pinned file, verified, ready at once."""

from __future__ import annotations

import hashlib
import json
import threading

import pytest

from core.ocr import language_download as ld
from core.ocr import language_packs as lp

PACK = b"KOREAN MODEL BYTES" * 50


@pytest.fixture()
def env(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    for code in ("eng", "jpn", "osd"):
        (bundled / f"{code}.traineddata").write_bytes(code.encode() * 100)
    catalog = tmp_path / "language_packs.json"
    catalog.write_text(json.dumps({"schema": 1, "packs": [
        {"code": "kor", "name": "Korean", "file": "kor.traineddata", "size": len(PACK),
         "sha256": hashlib.sha256(PACK).hexdigest(),
         "url": "https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/kor.traineddata"}]}))
    monkeypatch.setattr(lp, "CATALOG", catalog)
    monkeypatch.setattr(lp, "tessdata_dir", lambda: bundled)
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def _fake_download(payload: bytes, seen: list):
    def download(source, url, dest, expected_size, cancel, progress=None):
        seen.append((url, source.host_allowed(url), source.host_allowed("https://evil.example/x"),
                     source.host_allowed("http://github.com/x")))
        with open(dest, "xb") as fh:
            fh.write(payload)
        if progress:
            from core.updates.net import DownloadProgress

            progress(DownloadProgress(len(payload), expected_size))
    return download


def test_download_installs_the_verified_file_and_it_is_usable_at_once(env, monkeypatch):
    from core.updates import net

    seen: list = []
    monkeypatch.setattr(net, "download", _fake_download(PACK, seen))
    pack = lp.catalog()[0]
    got = []
    assert "kor" not in lp.available_languages()
    ld.download_and_install(pack, threading.Event(), lambda a, b: got.append((a, b)))
    assert "kor" in lp.available_languages()  # ready without restarting
    assert lp.tessdata_for("eng+kor") == lp.user_language_dir()
    url, allowed, evil, plain_http = seen[0]
    assert url == pack.url and allowed and not evil and not plain_http
    assert got and got[-1][0] == len(PACK)
    assert not list(lp.user_language_dir().glob("*.download"))  # nothing left behind


def test_a_wrong_download_is_not_installed(env, monkeypatch):
    from core.updates import net

    monkeypatch.setattr(net, "download", _fake_download(b"x" * len(PACK), []))
    with pytest.raises(lp.LanguagePackError):
        ld.download_and_install(lp.catalog()[0])
    assert "kor" not in lp.available_languages()
    assert not list(lp.user_language_dir().glob("*.download"))


def test_network_failure_message(env, monkeypatch):
    from core.updates import net

    def offline(*a, **k):
        raise net.NetworkError("no internet connection (the update server's name could not be resolved)", "offline")

    monkeypatch.setattr(net, "download", offline)
    with pytest.raises(lp.LanguagePackError, match="download server") as exc:
        ld.download_and_install(lp.catalog()[0])
    assert "update" not in str(exc.value)


def test_files_in_the_downloads_folder_are_offered(env, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "kor.traineddata").write_bytes(PACK)
    (downloads / "other.traineddata").write_bytes(b"zz")
    found = lp.downloads_found(downloads)
    assert [p.code for p, _ in found] == ["kor"]
    lp.install_from_file(found[0][1])
    assert lp.downloads_found(downloads) == []  # installed: no longer offered
