"""Test-wide isolation: never read or write the real user's settings or recent files."""

from __future__ import annotations

import os
import tempfile

import pytest

# Working files (recovery drafts, temp conversions, caches) go to a throwaway folder, never the
# project's own runtime folder. Set before any test imports app.paths.
os.environ.setdefault("MONOGRAPH_PDF_RUNTIME_DIR", tempfile.mkdtemp(prefix="monographpdf-test-runtime-"))


@pytest.fixture(autouse=True, scope="session")
def _isolated_user_data(tmp_path_factory):
    old = os.environ.get("MONOGRAPH_PDF_USER_DATA_DIR")
    os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(tmp_path_factory.mktemp("userdata"))
    yield
    if old is None:
        os.environ.pop("MONOGRAPH_PDF_USER_DATA_DIR", None)
    else:
        os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = old
