"""Ensure path helpers point inside the project and known output dirs."""

from __future__ import annotations

from app.paths import ROOT, TEST_OUTPUTS, VERSION_FILE, ensure_runtime_layout


def test_version_file_exists():
    assert VERSION_FILE.is_file()
    assert VERSION_FILE.parent == ROOT


def test_test_outputs_under_tests():
    assert TEST_OUTPUTS == ROOT / "tests" / "outputs"


def test_ensure_runtime_layout():
    ensure_runtime_layout()
    assert (ROOT / "runtime" / "bin").is_dir()
    assert (ROOT / "engines" / "ocr").is_dir()
