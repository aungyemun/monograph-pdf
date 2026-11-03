"""macOS OCR provenance: recipe parsing, release check failure modes, reproducible archives."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import macos_ocr_sources as mos  # noqa: E402

INVENTORY = ROOT / "scripts" / "packaging" / "macos_ocr_sources.json"

RATTLER = """recipe:
  source:
  - url: https://example.org/a-1.0.tar.gz
    sha256: %s
    patches:
    - fix-build.patch
  - url: https://example.org/data.zip
    sha256: %s
    target_directory: data
  build:
    number: 1
  requirements:
    build:
    - source: clang 19.*
""" % ("a" * 64, "b" * 64)

CONDA_BUILD = """package:
  name: x
source:
  url: http://ftp.gnu.org/pub/gnu/x/x-1.0.tar.gz
  sha256: %s
  patches:
    - utf_8_mac.patch
build:
  number: 3
""" % ("c" * 64)


def test_recipe_parsing_handles_rattler_and_conda_build_layouts():
    assert [s["fn"] for s in mos._parse_source_block(RATTLER)] == ["a-1.0.tar.gz", "data.zip"]
    only = mos._parse_source_block(CONDA_BUILD)
    assert only == [{"urls": ["http://ftp.gnu.org/pub/gnu/x/x-1.0.tar.gz"], "sha256": "c" * 64, "fn": "x-1.0.tar.gz"}]


def test_source_without_hash_is_unresolved_not_trusted():
    text = "source:\n  git_url: https://example.org/x.git\n  git_rev: v1\nbuild:\n"
    assert "unresolved" in mos._parse_source_block(text)[0]
    assert "unresolved" in mos._parse_source_block("package:\n  name: y\n")[0]


def test_committed_inventory_covers_copyleft_with_verified_source():
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in inv["components"]}
    assert {"tesseract", "leptonica", "lzo", "libiconv"} <= set(by_name)
    for c in inv["components"]:
        assert c["binaries"] and c["license"] and c["conda_package"]["sha256"]
        assert c["feedstock"]["url"].startswith("https://github.com/conda-forge/") and len(c["feedstock"]["commit"]) == 40
        assert all("unresolved" not in s for s in c["upstream_sources"]), c["name"]
        assert all(d for d in c["patches"].values()), c["name"]
        if c["copyleft"]:
            cs = c["corresponding_source"]
            assert cs and len(cs["sha256"]) == 64 and cs["upstream"]
            assert {u["sha256"] for u in cs["upstream"]} == {s["sha256"] for s in c["upstream_sources"]}
    assert {c["name"] for c in inv["components"] if c["copyleft"]} == {"lzo", "libiconv"}
    assert "/Users/" not in INVENTORY.read_text(encoding="utf-8")


def _fake_bundle(tmp_path):
    ocr = tmp_path / "Resources" / "engines" / "ocr"
    (ocr / "bin").mkdir(parents=True)
    (ocr / "lib").mkdir()
    (ocr / "licenses" / "pkg").mkdir(parents=True)
    (ocr / "bin" / "tesseract").write_bytes(b"binary")
    (ocr / "licenses" / "pkg" / "LICENSE").write_text("license")
    for name in ("TESSERACT_NOTICE.txt", "THIRD_PARTY_OCR.json"):
        (ocr / name).write_text("x")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "pkg.corresponding-source.tar.gz").write_bytes(b"src")
    inv = {"components": [{
        "name": "pkg", "version": "1", "copyleft": True, "license_dir": "engines/ocr/licenses/pkg",
        "binaries": {"engines/ocr/bin/tesseract": mos.sha256_bytes(b"binary")},
        "upstream_sources": [{"urls": ["https://x"], "sha256": "d" * 64, "fn": "x"}], "patches": {},
        "corresponding_source": {"archive": "pkg.corresponding-source.tar.gz", "sha256": mos.sha256_bytes(b"src")},
    }]}
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(inv))
    return ocr, path, sources, inv


def test_release_check_passes_complete_bundle(tmp_path):
    ocr, inv, sources, _ = _fake_bundle(tmp_path)
    assert mos.check(ocr, inv, sources) == []


@pytest.mark.parametrize("breakage, expected", [
    (lambda ocr, src, inv: (ocr / "bin" / "tesseract").write_bytes(b"other"), "differs from the inventory"),
    (lambda ocr, src, inv: (ocr / "licenses" / "pkg" / "LICENSE").unlink(), "license files missing"),
    (lambda ocr, src, inv: (src / "pkg.corresponding-source.tar.gz").unlink(), "archive missing"),
    (lambda ocr, src, inv: (src / "pkg.corresponding-source.tar.gz").write_bytes(b"x"), "hash mismatch"),
    (lambda ocr, src, inv: (ocr / "lib" / "libextra.dylib").write_bytes(b"x"), "not in the inventory"),
    (lambda ocr, src, inv: (ocr / "TESSERACT_NOTICE.txt").unlink(), "TESSERACT_NOTICE.txt"),
])
def test_release_check_fails_on_each_missing_obligation(tmp_path, breakage, expected):
    ocr, inv, sources, _ = _fake_bundle(tmp_path)
    breakage(ocr, sources, inv)
    assert any(expected in p for p in mos.check(ocr, inv, sources))


def test_copyleft_without_source_and_unverifiable_source_fail(tmp_path):
    ocr, path, sources, inv = _fake_bundle(tmp_path)
    c = inv["components"][0]
    c["corresponding_source"] = None
    c["upstream_sources"] = [{"unresolved": "git"}]
    c["patches"] = {"fix.patch": None}
    path.write_text(json.dumps(inv))
    problems = " | ".join(mos.check(ocr, path, sources))
    assert "copyleft component without a corresponding-source archive" in problems
    assert "upstream source not verifiable" in problems
    assert "fix.patch" in problems


def test_lock_is_an_explicit_spec_pinned_by_sha256():
    lines = [l for l in (ROOT / "scripts/packaging/macos_ocr_env.lock").read_text(encoding="utf-8").splitlines()
             if l and not l.startswith("#")]
    assert lines[0] == "@EXPLICIT"
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    pinned = {l.split("#")[0]: l.split("#")[1] for l in lines[1:]}
    for c in inv["components"]:  # every bundled package is installed from exactly that file
        assert pinned[c["conda_package"]["url"]] == c["conda_package"]["sha256"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS staging")
@pytest.mark.skipif(not (ROOT / "tools/ocr-env/bin/tesseract").is_file(), reason="run scripts/vendor_ocr_macos.sh")
def test_staged_engine_matches_inventory_and_has_no_builder_paths(tmp_path):
    import stage_ocr_macos

    dest = tmp_path / "Resources" / "engines" / "ocr"
    stage_ocr_macos.stage(ROOT / "tools" / "ocr-env", dest)
    assert mos.check(dest, INVENTORY, None) == []
    home = str(Path.home()).encode()
    assert not [p for p in dest.rglob("*") if p.is_file() and home in p.read_bytes()]
