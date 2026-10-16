"""Ensure path helpers point inside the project and known output dirs."""

from __future__ import annotations

from app.paths import ROOT, RUNTIME_DIR, TEST_OUTPUTS, VERSION_FILE, ensure_runtime_layout


def test_version_file_exists():
    assert VERSION_FILE.is_file()
    assert VERSION_FILE.parent == ROOT


def test_test_outputs_under_tests():
    assert TEST_OUTPUTS == ROOT / "tests" / "outputs"


def test_ensure_runtime_layout():
    ensure_runtime_layout()
    # the runtime folders are created on demand; none has to exist in a fresh checkout
    assert (RUNTIME_DIR / "bin").is_dir()
    assert (RUNTIME_DIR / "sessions").is_dir()
