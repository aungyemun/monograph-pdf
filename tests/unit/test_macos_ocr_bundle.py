"""The macOS .app must carry a runnable Tesseract, not the tools/ocr-env dev wrapper."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_APP = (ROOT / "scripts/build_app.sh").read_text(encoding="utf-8")
OCR_ENV = ROOT / "tools" / "ocr-env"

sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import stage_ocr_macos  # noqa: E402


def test_bundle_symlinks_climb_out_of_their_own_directory():
    # Links sit in Contents/MacOS/engines and Contents/MacOS/models: one "../" lands in MacOS/.
    targets = re.findall(r'ln -sfn "([^"]+)" "\$MACOS_DIR/(\w+)/', BUILD_APP)
    assert targets, "build_app.sh no longer links OCR resources"
    for target, _ in targets:
        assert target.startswith("../../Resources/"), target


def test_build_does_not_copy_the_dev_wrapper_into_the_bundle():
    assert 'cp -R "$ROOT/engines/ocr"' not in BUILD_APP  # dev wrapper + Windows MANIFEST.json
    assert "stage_ocr_macos.py" in BUILD_APP
    # the published conda-forge signatures are kept (bytes = inventory) and verified, never re-signed
    assert '"$RES/engines/ocr/"*) continue' in BUILD_APP
    assert 'codesign --verify --strict "$f"' in BUILD_APP


def test_resolve_skips_system_libraries(tmp_path):
    assert stage_ocr_macos.resolve("/usr/lib/libSystem.B.dylib", tmp_path) is None
    assert stage_ocr_macos.resolve("/System/Library/Frameworks/Accelerate.framework/A", tmp_path) is None
    (tmp_path / "libfoo.1.dylib").write_bytes(b"")
    assert stage_ocr_macos.resolve("@rpath/libfoo.1.dylib", tmp_path) == tmp_path / "libfoo.1.dylib"
    with pytest.raises(FileNotFoundError):
        stage_ocr_macos.resolve("@rpath/libmissing.dylib", tmp_path)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Mach-O staging only")
@pytest.mark.skipif(not (OCR_ENV / "bin" / "tesseract").is_file(), reason="run scripts/vendor_ocr_macos.sh")
def test_staged_tesseract_runs_without_project_tools(tmp_path):
    dest = tmp_path / "App Ü" / "engines" / "ocr"
    names = stage_ocr_macos.stage(OCR_ENV, dest)
    assert "libtesseract.5.dylib" in names
    assert not any(p.is_symlink() for p in dest.rglob("*"))
    inventory = json.loads((dest / "THIRD_PARTY_OCR.json").read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in inventory}
    assert by_name["tesseract"]["license"] == "Apache-2.0"
    for package in inventory:  # every bundled package carries its own license text
        assert package["license_files"] and all((dest / f).is_file() for f in package["license_files"])
    assert {p["name"] for p in inventory if p["copyleft"]} >= {"lzo"}
    assert "Windows" not in (dest / "TESSERACT_NOTICE.txt").read_text(encoding="utf-8")
    assert not (dest / "MANIFEST.json").exists()  # the Windows vendoring manifest is not shipped
    env = {k: v for k, v in os.environ.items() if not k.startswith("DYLD_")}
    out = subprocess.run([str(dest / "bin" / "tesseract"), "--list-langs",
                          "--tessdata-dir", str(ROOT / "models" / "tessdata")],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "eng" in out.stdout
