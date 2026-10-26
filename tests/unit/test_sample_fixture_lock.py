"""Shared sample fixtures must tolerate a locked sample_text.pdf (live GUI)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.fixtures.make_samples import SAMPLES, main as make_samples_main


def test_make_samples_skips_existing_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONOGRAPH_REGEN_SAMPLES", raising=False)
    # Point SAMPLES at an isolated dir for this test only.
    monkeypatch.setattr("tests.fixtures.make_samples.SAMPLES", tmp_path)
    first = tmp_path / "sample_text.pdf"
    first.write_bytes(b"%PDF-1.4\nkeep-me\n%%EOF\n")
    make_samples_main(force=False)
    assert first.read_bytes().startswith(b"%PDF-1.4\nkeep-me")


def test_make_samples_tolerates_replace_permission_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: locked shared fixture must not abort the suite (Permission denied)."""
    import os

    monkeypatch.setattr("tests.fixtures.make_samples.SAMPLES", tmp_path)
    target = tmp_path / "sample_text.pdf"
    target.write_bytes(b"%PDF-1.4\nlocked-fixture\n%%EOF\n")
    original = target.read_bytes()

    real_replace = os.replace

    def _deny_replace(src, dst):  # noqa: ANN001
        # Only the shared fixture under test is locked; others may still be created.
        if Path(dst).name == "sample_text.pdf":
            raise OSError(13, "Permission denied", str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _deny_replace)
    make_samples_main(force=True)
    assert target.read_bytes() == original


def test_session_start_does_not_require_rewrite_when_present() -> None:
    """conftest only generates samples when sample_text.pdf is missing."""
    assert (SAMPLES / "sample_text.pdf").is_file()
    # Default main must be a no-op rewrite for existing files.
    before = (SAMPLES / "sample_text.pdf").stat().st_mtime_ns
    os.environ.pop("MONOGRAPH_REGEN_SAMPLES", None)
    make_samples_main(force=False)
    after = (SAMPLES / "sample_text.pdf").stat().st_mtime_ns
    assert before == after
