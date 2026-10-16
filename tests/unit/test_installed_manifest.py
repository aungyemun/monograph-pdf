"""Installed-file manifest used by Setup upgrade cleanup."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import write_installed_manifest as wim  # noqa: E402


def test_safe_rel_paths():
    assert wim.is_safe_rel("MonographPDF.exe")
    assert wim.is_safe_rel("_internal/foo.dll")
    assert wim.is_safe_rel("docs/USER_GUIDE.md")
    assert not wim.is_safe_rel("")
    assert not wim.is_safe_rel("../x")
    assert not wim.is_safe_rel("C:/Windows")
    assert not wim.is_safe_rel("/etc/passwd")
    assert not wim.is_safe_rel("a/../../b")
    assert not wim.is_safe_rel("..\\x")


def test_build_manifest_contains_expected_entries(tmp_path: Path):
    payload = tmp_path / "payload"
    (payload / "_internal").mkdir(parents=True)
    (payload / "MonographPDF.exe").write_bytes(b"MZ")
    (payload / "_internal" / "x.pyd").write_bytes(b"x")
    root = tmp_path / "root"
    (root / "engines" / "ocr").mkdir(parents=True)
    (root / "models" / "tessdata").mkdir(parents=True)
    (root / "engines" / "ocr" / "tesseract.exe").write_bytes(b"MZ")
    (root / "models" / "tessdata" / "eng.traineddata").write_bytes(b"e")
    (root / "third_party" / "licenses").mkdir(parents=True)
    (root / "third_party" / "licenses" / "LGPL-3.0.txt").write_text("L", encoding="utf-8")
    paths = wim.build_manifest(payload, root=root)
    assert "MonographPDF.exe" in paths
    assert "_internal/x.pyd" in paths
    assert "engines/ocr/tesseract.exe" in paths
    assert "licenses/LGPL-3.0.txt" in paths
    assert "installed_files.txt" in paths
    assert "uninstall.exe" in paths
    assert all(wim.is_safe_rel(p) for p in paths)


def test_write_manifest_roundtrip(tmp_path: Path):
    out = tmp_path / "installed_files.txt"
    wim.write_manifest(["MonographPDF.exe", "_internal/a.dll"], out)
    text = out.read_text(encoding="utf-8")
    assert "MonographPDF.exe" in text
    assert not any(line.startswith("C:") for line in text.splitlines())
    meta = out.with_suffix(".json")
    assert meta.is_file()
    assert "legacy_owned_dirs" in meta.read_text(encoding="utf-8")


def test_legacy_allowlist_still_knows_pdf_editor():
    """Upgrading PDF Editor <= 0.1.5 (no installed_files.txt) removes its PDF_editor.exe safely."""
    assert "PDF_editor.exe" in wim.LEGACY_OWNED_FILES
    assert "MonographPDF.exe" in wim.LEGACY_OWNED_FILES
    assert all(wim.is_safe_rel(p) for p in wim.LEGACY_OWNED_FILES + wim.LEGACY_OWNED_DIRS)


def test_v0_2_manifest_lists_monograph_files_only(tmp_path: Path):
    payload = tmp_path / "payload"
    (payload / "_internal" / "resources" / "icons" / "windows").mkdir(parents=True)
    (payload / "MonographPDF.exe").write_bytes(b"MZ")
    (payload / "_internal" / "resources" / "icons" / "windows" / "monograph_pdf.ico").write_bytes(b"\0")
    paths = wim.build_manifest(payload, root=tmp_path / "empty-root")
    assert "MonographPDF.exe" in paths
    assert "_internal/resources/icons/windows/monograph_pdf.ico" in paths
    assert not [p for p in paths if "PDF_editor" in p or "pdf_editor" in p]
    header = "\n".join(wim.__doc__.splitlines()[:1])
    assert "Monograph PDF" in header
