"""Unit tests for MSYS2 corresponding-source reconstruction (no public network)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import gzip
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import msys2_corresponding_source as msys  # noqa: E402

sys.path.remove(str(ROOT / "scripts" / "packaging"))

SAMPLE_PKGBUILD = """
_realname=demo
pkgver=1.2.3
pkgrel=1
source=("https://example.test/demo-${pkgver}.tar.gz"{,.sig}
        0001-fix.patch)
sha256sums=('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            'SKIP'
            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')
"""


def test_package_dir_name_strips_version_and_suffix():
    assert msys.package_dir_name("mingw-w64-glib2-2.80.2-2.src.tar.zst") == "mingw-w64-glib2"
    assert msys.corresponding_archive_name("mingw-w64-glib2-2.80.2-2.src.tar.zst").endswith(
        ".corresponding-source.tar.gz"
    )


def test_parse_pkgbuild_expands_braces_substring_and_skip():
    pairs = msys.parse_pkgbuild(SAMPLE_PKGBUILD)
    assert len(pairs) == 3
    assert pairs[0][0] == "https://example.test/demo-1.2.3.tar.gz"
    assert pairs[1][0] == "https://example.test/demo-1.2.3.tar.gz.sig"
    assert pairs[1][1] == "skip"
    assert pairs[2][0] == "0001-fix.patch"


def test_parse_pkgbuild_pkgver_substring():
    text = SAMPLE_PKGBUILD.replace(
        'source=("https://example.test/demo-${pkgver}.tar.gz"{,.sig}',
        'source=("https://example.test/demo/${pkgver:0:3}/demo-${pkgver}.tar.gz"',
    ).replace(
        "sha256sums=('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
        "            'SKIP'\n"
        "            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')",
        "sha256sums=('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')",
    )
    # simplify to one source
    text = """
_realname=demo
pkgver=1.2.3
source=("https://example.test/${pkgver:0:3}/demo-${pkgver}.tar.xz")
sha256sums=('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
"""
    pairs = msys.parse_pkgbuild(text)
    assert pairs[0][0] == "https://example.test/1.2/demo-1.2.3.tar.xz"


def test_materialize_offline_requires_cache(tmp_path):
    comp = {
        "id": "ocr-demo",
        "files": [{"name": "mingw-w64-demo-1.2.3-1.corresponding-source.tar.gz"}],
        "msys2": {
            "recipe_commit": "a" * 40,
            "source_package": "mingw-w64-demo-1.2.3-1.src.tar.zst",
            "corresponding_source": True,
        },
    }
    with pytest.raises(RuntimeError, match="offline"):
        msys.materialize(comp, tmp_path, offline=True)


def test_materialize_builds_deterministic_archive(tmp_path, monkeypatch):
    upstream = b"upstream-bytes"
    patch = b"patch-bytes"
    upstream_hash = hashlib.sha256(upstream).hexdigest()
    patch_hash = hashlib.sha256(patch).hexdigest()
    pkgbuild = f"""
_realname=demo
pkgver=1.0.0
source=("https://example.test/demo-1.0.0.tar.gz"
        0001-fix.patch)
sha256sums=('{upstream_hash}'
            '{patch_hash}')
""".encode()

    def fake_get(url, dest=None, timeout=120):  # noqa: ARG001
        if url.endswith("PKGBUILD"):
            data = pkgbuild
        elif url.endswith("0001-fix.patch"):
            data = patch
        elif url.endswith("demo-1.0.0.tar.gz"):
            data = upstream
        else:
            raise RuntimeError(f"unexpected {url}")
        if dest is not None:
            dest.write_bytes(data)
        return data

    monkeypatch.setattr(msys, "_http_get", fake_get)
    comp = {
        "id": "ocr-demo",
        "files": [{"name": "mingw-w64-demo-1.0.0-1.corresponding-source.tar.gz", "build": "msys2-corresponding"}],
        "msys2": {
            "recipe_commit": "b" * 40,
            "source_package": "mingw-w64-demo-1.0.0-1.src.tar.zst",
            "corresponding_source": True,
        },
    }
    a = msys.materialize(comp, tmp_path / "c1", offline=False)
    b = msys.materialize(comp, tmp_path / "c2", offline=False)
    assert a.read_bytes() == b.read_bytes()
    assert not list((tmp_path / "c1").glob(".rebuild-*"))
    assert not list((tmp_path / "c1").glob("*.part"))
    # Inspect members
    with gzip.open(a, "rb") as gz, tarfile.open(fileobj=gz, mode="r|") as tf:
        names = [m.name for m in tf]
    assert any(n.endswith("PKGBUILD") for n in names)
    assert any(n.endswith("demo-1.0.0.tar.gz") for n in names)


def test_http_get_rejects_non_https(tmp_path):
    with pytest.raises(RuntimeError, match="non-HTTPS"):
        msys._http_get("http://example.test/x", tmp_path / "x")
