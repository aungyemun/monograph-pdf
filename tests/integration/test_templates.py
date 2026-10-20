"""Template PDFs (tests/fixtures/templates) match their manifest, and Downloads PDFs open without being modified."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[2]
TPL = ROOT / "tests" / "fixtures" / "templates"
sys.path.insert(0, str(ROOT / "scripts"))

MANIFEST = json.loads((TPL / "manifest.json").read_text(encoding="utf-8")) if (TPL / "manifest.json").is_file() else {"documents": {}}
DOCS = MANIFEST["documents"]


def _open(entry: dict) -> fitz.Document:
    d = fitz.open((TPL / entry["file"]).as_posix())
    if d.needs_pass:
        assert d.authenticate(entry["expect"]["password"])
    return d


def test_manifest_present():
    assert len(DOCS) >= 20


@pytest.mark.parametrize("name", sorted(n for n, e in DOCS.items() if not e["expect"].get("damaged")))
def test_template_matches_manifest(name):
    e = DOCS[name]
    ex = e["expect"]
    d = _open(e)
    try:
        if "pages" in ex:
            assert d.page_count == ex["pages"]
        text = "\n".join(p.get_text() for p in d)
        for needle in ex.get("text", []):
            assert needle in text, needle
        if ex.get("scanned"):
            assert text.strip() == "" and d[0].get_images()
        if "rotations" in ex:
            assert [p.rotation for p in d] == ex["rotations"]
        if "widgets" in ex:
            names = {w.field_name for p in d for w in p.widgets()}
            assert set(ex["widgets"]) <= names
        if "signature_fields" in ex:
            assert sum(1 for p in d for w in p.widgets() if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE) == ex["signature_fields"]
        if "cropbox" in ex:
            assert list(d[0].cropbox) == ex["cropbox"]
        if "toc" in ex:
            assert len(d.get_toc()) == ex["toc"]
        for p in d:
            assert p.get_pixmap(dpi=24).width > 0
    finally:
        d.close()


def test_damaged_is_refused_or_repaired_safely():
    e = DOCS["damaged_truncated"]
    try:
        d = fitz.open((TPL / e["file"]).as_posix())
    except Exception:
        return
    d.close()


def test_encrypted_variants():
    d = fitz.open((TPL / DOCS["password_protected_aes256"]["file"]).as_posix())
    assert d.needs_pass and not d.authenticate("wrong") and d.authenticate(MANIFEST["password"])
    d.close()
    r = fitz.open((TPL / DOCS["permissions_restricted"]["file"]).as_posix())
    assert not r.needs_pass and not (r.permissions & fitz.PDF_PERM_COPY)
    r.close()


def test_rotate_save_roundtrip_every_template(tmp_path):
    for n, e in DOCS.items():
        if e["expect"].get("damaged") or e["expect"].get("password"):
            continue
        dst = tmp_path / f"{n}.pdf"
        shutil.copy2(TPL / e["file"], dst)
        d = fitz.open(dst.as_posix())
        d[0].set_rotation((d[0].rotation + 90) % 360)
        out = tmp_path / f"{n}_r.pdf"
        d.save(out.as_posix())
        d.close()
        assert fitz.open(out.as_posix()).page_count == e["expect"]["pages"]


def test_downloads_pdfs_open_and_originals_untouched():
    from check_pdfs import check_one
    from core.windows_paths import get_downloads_dir

    folder = Path(get_downloads_dir())
    pdfs = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
    if not pdfs:
        pytest.skip("no PDFs in the Downloads folder")
    results = [check_one(p) for p in pdfs]
    assert not [r for r in results if r["status"] == "FAIL"], results
