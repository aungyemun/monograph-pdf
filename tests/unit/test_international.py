"""International Windows compatibility: Unicode file, folder and user names; locale independence.

These tests simulate localized environments (Unicode paths, temporary folders, user-data and update
folders, other process locales) on whatever system runs them. They are not a substitute for testing
on a real Japanese, Chinese, Korean, German or French Windows installation
(docs/INTERNATIONAL_WINDOWS_COMPATIBILITY.md lists what has and has not been verified that way).
"""

from __future__ import annotations

import json
import locale
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
import pytest

from core.document import open_document
from core.updates import manifest as mf
from core.updates import staging
from core.updates.semver import parse as V
from tests.fixtures.update_fixtures import make_config, manifest_bytes

NAMES = [
    ("ja", "田中太郎/Documents", "研究資料.pdf"),
    ("ja2", "研究データ/神経再生", "実験結果.pdf"),
    ("zh", "张伟/Documents", "实验报告.pdf"),
    ("ko", "김민수/Documents", "연구자료.pdf"),
    ("de", "Jürgen Müller/Dokumente", "Prüfbericht_Größe.pdf"),
    ("fr", "Élodie Lefèvre/Mes documents", "rapport_été.pdf"),
]


def _pdf(path: Path, text: str = "Monograph PDF international test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize("lang,folder,name", NAMES, ids=[n[0] for n in NAMES])
def test_open_and_save_with_unicode_folders_and_names(tmp_path, lang, folder, name):
    src = _pdf(tmp_path / folder / name)
    doc = open_document(src)
    try:
        assert doc.page_count == 1 and doc.path == src
        out = src.with_name("保存_" + name)
        doc.save_as(out)
    finally:
        doc.close()
    again = open_document(out)
    try:
        assert again.page_count == 1
    finally:
        again.close()
    assert out.read_bytes().startswith(b"%PDF")


def test_editing_and_baking_into_a_unicode_path(tmp_path):
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_into_document

    src = _pdf(tmp_path / "研究データ" / "神経再生" / "実験結果.pdf")
    doc = open_document(src)
    try:
        edit = EditableDocument(doc)
        dest = tmp_path / "研究データ" / "編集済み" / "実験結果_編集.pdf"
        dest.parent.mkdir(parents=True)
        bake_into_document(edit, dest)
    finally:
        doc.close()
    with fitz.open(dest) as check:
        assert "international" in check[0].get_text()


def test_image_conversion_with_unicode_paths(tmp_path):
    from PIL import Image

    from core.convert.images_to_pdf import images_to_pdf

    img = tmp_path / "写真" / "실험 사진 été.png"
    img.parent.mkdir(parents=True)
    Image.new("RGB", (60, 40), (200, 30, 30)).save(img)
    out = images_to_pdf([img], tmp_path / "変換結果" / "画像.pdf")
    with fitz.open(out) as d:
        assert d.page_count == 1


def test_unicode_temporary_folder(tmp_path, monkeypatch):
    """Temporary files work when %TEMP% lies under a Unicode user name (C:\\Users\\田中太郎\\AppData\\Local\\Temp)."""
    temp = tmp_path / "Users" / "田中太郎" / "AppData" / "Local" / "Temp"
    temp.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    with tempfile.TemporaryDirectory(prefix="monographpdf_") as d:
        p = Path(d) / "一時.pdf"
        _pdf(p)
        doc = open_document(p)
        doc.close()
    assert list(temp.iterdir()) == []


def test_subprocess_receives_unicode_arguments_exactly(tmp_path):
    arg = str(tmp_path / "D ソフトウェア" / "Monograph PDF" / "研究 资料 연구자료.pdf")
    out = subprocess.run([sys.executable, "-c", "import sys, json; print(json.dumps(sys.argv[1:]))", arg, "/DIR=" + arg],
                         capture_output=True, check=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert json.loads(out.stdout) == [arg, "/DIR=" + arg]


@pytest.mark.parametrize("lang,folder,name", NAMES[:4], ids=[n[0] for n in NAMES[:4]])
def test_update_staging_and_handoff_under_unicode_user_folders(tmp_path, monkeypatch, lang, folder, name):
    from core.updates import manager

    root = tmp_path / folder / "AppData" / "Local" / "Monograph PDF" / "Updates"
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(root))
    sd = staging.new_staging("0.3.1")
    sd.installer.write_bytes(b"MZ setup")
    sd.set_state("installed")
    assert staging.read_marker(sd.path)["state"] == "installed"
    h = {"install_mode": "user", "install_dir": str(tmp_path / folder / "Monograph PDF"),
         "setup_log": str(sd.path / "setup.log")}
    assert manager.setup_arguments(h)[5] == "/DIR=" + h["install_dir"]
    text = json.dumps(h, ensure_ascii=False)
    assert json.loads(text) == h
    staging.cleanup()
    assert not sd.path.exists()


def test_problem_report_records_under_a_unicode_profile(tmp_path, monkeypatch):
    from core.diagnostics import EventId, crash
    from core.diagnostics import report as reports

    monkeypatch.setenv("MONOGRAPH_PDF_DIAGNOSTICS_DIR", str(tmp_path / "김민수" / "Diagnostics"))
    crash.save_pending(reports.build(EventId.OCR_FAILED, events=[]))
    rep = crash.take_pending()
    assert rep is not None and rep["error_code"] == "OCR_FAILED"
    assert reports.validate({**rep, "display_language": "ja-JP"})
    for tag in ("ko-KR", "zh-CN", "zh-Hant-TW", "de-DE", "fr-FR", "und"):
        assert reports.validate({**rep, "display_language": tag})


def _try_setlocale(names):
    for n in names:
        try:
            return locale.setlocale(locale.LC_ALL, n)
        except locale.Error:
            continue
    return None


@pytest.mark.parametrize("names", [
    ["ja_JP.UTF-8", "Japanese_Japan.932", "ja-JP"], ["de_DE.UTF-8", "German_Germany.1252", "de-DE"],
    ["fr_FR.UTF-8", "French_France.1252", "fr-FR"], ["tr_TR.UTF-8", "Turkish_Turkey.1254", "tr-TR"],
    ["ko_KR.UTF-8", "Korean_Korea.949", "ko-KR"], ["zh_CN.UTF-8", "Chinese_China.936", "zh-CN"],
], ids=["ja", "de", "fr", "tr", "ko", "zh"])
def test_versions_and_signed_metadata_do_not_depend_on_the_locale(names):
    saved = locale.setlocale(locale.LC_ALL)
    if _try_setlocale(names) is None:
        pytest.skip(f"locale {names[0]} not installed here")
    try:
        assert V("0.10.0") > V("0.9.9") > V("0.9.9-rc.1")
        rel = mf.parse_and_verify(manifest_bytes(), make_config())
        assert str(rel.version) == "0.3.1" and rel.expires > rel.issued
        assert mf.canonical_bytes({"İ": "ı"}) == b'{"\\u0130":"\\u0131"}'  # no case or locale folding
    finally:
        locale.setlocale(locale.LC_ALL, saved)


@pytest.mark.ocr
def test_ocr_with_a_unicode_document_and_temporary_folder(tmp_path, monkeypatch):
    from core.ocr.paths import ocr_ready

    ok, detail = ocr_ready()
    if not ok:
        pytest.skip(f"OCR engine not available: {detail}")
    from core.ocr.pipeline import OcrOptions, run_ocr

    temp = tmp_path / "田中太郎" / "Temp"
    temp.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    # a scanned-looking page: text rendered to an image, no text layer
    src = tmp_path / "研究データ" / "スキャン.pdf"
    src.parent.mkdir(parents=True)
    text_doc = fitz.open()
    page = text_doc.new_page(width=420, height=160)
    page.insert_text((30, 90), "Monograph Research 2026", fontsize=28)
    pix = page.get_pixmap(dpi=200)
    scan = fitz.open()
    sp = scan.new_page(width=420, height=160)
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    scan.save(src)
    doc = open_document(src)
    try:
        out = src.with_name("検索可能.pdf")
        result = run_ocr(doc, OcrOptions(languages="eng", make_searchable=True), destination=out)
    finally:
        doc.close()
    words = " ".join(t.text for p in result.pages for t in getattr(p, "tokens", []) or [])
    with fitz.open(out) as d:
        layer = d[0].get_text()
    assert "Monograph" in (words + layer) and "Research" in (words + layer)
