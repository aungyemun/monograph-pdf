"""Linux OCR staging must not dirty the tracked engines/ocr/MANIFEST.json."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import stage_ocr_engine_linux as linux_ocr  # noqa: E402

sys.path.remove(str(ROOT / "scripts" / "ci"))


def test_stage_wrapper_writes_local_manifest_only(tmp_path, monkeypatch):
    engine = tmp_path / "engines" / "ocr"
    engine.mkdir(parents=True)
    tracked = engine / "MANIFEST.json"
    tracked.write_text('{"vendored": true}\n', encoding="utf-8")
    before = tracked.read_bytes()
    system = tmp_path / "bin" / "tesseract"
    system.parent.mkdir(parents=True)
    system.write_text("#!/bin/sh\n", encoding="utf-8")
    system.chmod(0o755)

    monkeypatch.setattr(linux_ocr, "ENGINE", engine)
    monkeypatch.setattr(linux_ocr, "LOCAL_MANIFEST", engine / "MANIFEST.local.json")
    linux_ocr.stage_wrapper(system)

    assert tracked.read_bytes() == before
    local = engine / "MANIFEST.local.json"
    assert local.is_file()
    data = json.loads(local.read_text(encoding="utf-8"))
    assert data["platform"] == "linux"
    assert data["tesseract"] == str(system)
    wrapper = engine / "tesseract"
    assert wrapper.is_symlink()
    assert wrapper.resolve() == system.resolve()


def test_download_tessdata_cleans_part_on_success(tmp_path, monkeypatch):
    payload = b"engdata"
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(
        json.dumps({"tessdata": {"eng.traineddata": hashlib.sha256(payload).hexdigest()}}),
        encoding="utf-8",
    )
    tessdata = tmp_path / "tessdata"
    monkeypatch.setattr(linux_ocr, "TESSDATA", tessdata)
    monkeypatch.setattr(linux_ocr, "LANGS", ("eng",))
    monkeypatch.setattr(linux_ocr, "PINS", pins_path)

    class Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resp())
    assert linux_ocr.download_tessdata(require=True) == 0
    assert (tessdata / "eng.traineddata").read_bytes() == payload
    assert not list(tessdata.glob("*.part"))
