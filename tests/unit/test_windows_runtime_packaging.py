"""Windows runtime dependency audit and reproducible launcher time stamps (0.3.0 packaging tools)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

pefile = pytest.importorskip("pefile")

from pe_fixture import build_pe  # noqa: E402

import normalize_pe  # noqa: E402
import runtime_dependencies as rd  # noqa: E402


def _layout(tmp_path: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return tmp_path


# --- normalize_pe -------------------------------------------------------------------------------

def test_normalize_sets_coff_and_debug_stamps_and_a_valid_checksum(tmp_path):
    exe = tmp_path / "MonographPDF.exe"
    exe.write_bytes(build_pe(timestamp=1_800_000_000, overlay=b"PYINSTALLER-ARCHIVE" * 50))
    assert normalize_pe.normalize(exe, 1_760_000_000) is True
    pe = pefile.PE(str(exe))
    assert pe.FILE_HEADER.TimeDateStamp == 1_760_000_000
    assert [d.struct.TimeDateStamp for d in pe.DIRECTORY_ENTRY_DEBUG] == [1_760_000_000]
    assert pe.OPTIONAL_HEADER.CheckSum == pe.generate_checksum()
    pe.close()


def test_normalize_changes_only_stamp_and_checksum_bytes_and_keeps_the_overlay(tmp_path):
    original = build_pe(timestamp=1_800_000_000, overlay=b"\x01\x02ARCHIVE" * 100)
    exe = tmp_path / "a.exe"
    exe.write_bytes(original)
    normalize_pe.normalize(exe, 1_700_000_000)
    after = exe.read_bytes()
    assert len(after) == len(original)
    assert after.endswith(b"\x01\x02ARCHIVE" * 100)
    changed = [i for i, (x, y) in enumerate(zip(original, after)) if x != y]
    pe = pefile.PE(data=original, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DEBUG"]])
    allowed = set()
    for off in (pe.FILE_HEADER.get_field_absolute_offset("TimeDateStamp"),
                pe.DIRECTORY_ENTRY_DEBUG[0].struct.get_field_absolute_offset("TimeDateStamp"),
                pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum")):
        allowed |= set(range(off, off + 4))
    assert changed and set(changed) <= allowed


def test_two_builds_differing_only_in_build_time_become_identical(tmp_path):
    a, b = tmp_path / "a.exe", tmp_path / "b.exe"
    a.write_bytes(build_pe(timestamp=1_792_574_846, overlay=b"same archive"))
    b.write_bytes(build_pe(timestamp=1_792_574_993, overlay=b"same archive"))
    assert a.read_bytes() != b.read_bytes()
    for f in (a, b):
        normalize_pe.normalize(f, 1_761_000_000)
    assert a.read_bytes() == b.read_bytes()
    assert normalize_pe.normalize(a, 1_761_000_000) is False  # idempotent


def test_normalize_cli_rejects_an_out_of_range_epoch(tmp_path):
    exe = tmp_path / "a.exe"
    exe.write_bytes(build_pe())
    assert normalize_pe.main(["--epoch", "0", str(exe)]) == 2


def test_build_exe_normalizes_the_launcher_with_the_commit_time():
    text = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert "normalize_pe.py" in text and "SOURCE_DATE_EPOCH" in text and "log -1 --format=%ct" in text
    # normalized before the launcher is copied to the project root and packaged
    assert text.index("normalize_pe.py") < text.index('Copy-Item -Force $OutExe "$Root\\MonographPDF.exe"')


# --- runtime_dependencies ------------------------------------------------------------------------

@pytest.mark.parametrize("dll,expected", [
    ("kernel32.dll", "windows"), ("api-ms-win-crt-runtime-l1-1-0.dll", "windows"),
    ("ext-ms-win-ntuser-window-l1-1-0.dll", "windows"), ("ucrtbase.dll", "windows"),
    ("vcruntime140.dll", "vc-runtime"), ("msvcp140_1.dll", "vc-runtime"), ("vcomp140.dll", "vc-runtime"),
    ("mscoree.dll", "dotnet"), ("libgcc_s_seh-1.dll", "unresolved"), ("python311.dll", "unresolved"),
])
def test_classification_without_bundled_files(dll, expected):
    assert rd.classify(dll, {}) == expected


def test_a_bundled_file_wins_over_every_other_class():
    assert rd.classify("vcruntime140.dll", {"vcruntime140.dll": ["_internal/VCRUNTIME140.dll"]}) == "bundled"


def test_a_layout_with_bundled_vc_runtime_passes(tmp_path):
    layout = _layout(tmp_path, {
        "MonographPDF.exe": build_pe(imports=("kernel32.dll", "python311.dll")),
        "_internal/python311.dll": build_pe(imports=("VCRUNTIME140.dll", "api-ms-win-crt-heap-l1-1-0.dll")),
        "_internal/VCRUNTIME140.dll": build_pe(imports=("kernel32.dll",)),
        "_internal/PySide6/Qt6Core.dll": build_pe(imports=("MSVCP140.dll", "VCRUNTIME140_1.dll")),
        "_internal/PySide6/MSVCP140.dll": build_pe(imports=("kernel32.dll",)),
        "_internal/PySide6/VCRUNTIME140_1.dll": build_pe(imports=("kernel32.dll",)),
        "uninstall.exe": build_pe(imports=("mscoree.dll",), machine=0x14C),
    })
    r = rd.audit(layout)
    assert r["vc_runtime_not_bundled"] == [] and r["unresolved"] == []
    assert set(r["vc_runtime_imports"]) == {"vcruntime140.dll", "msvcp140.dll", "vcruntime140_1.dll"}
    assert r["not_x64"] == ["uninstall.exe (machine 0x014c)"]
    assert rd.main([str(layout), "--check", "--json", str(tmp_path / "r.json")]) == 0
    assert json.loads((tmp_path / "r.json").read_text())["imports"]["mscoree.dll"]["class"] == "dotnet"


def test_a_vc_runtime_import_that_is_not_bundled_fails_the_check(tmp_path, capsys):
    layout = _layout(tmp_path / "l", {"_internal/x.pyd": build_pe(imports=("MSVCP140_2.dll",))})
    assert rd.audit(layout)["vc_runtime_not_bundled"] == ["msvcp140_2.dll"]
    assert rd.main([str(layout), "--check"]) == 1
    assert "NOT BUNDLED" in capsys.readouterr().out


def test_an_unknown_dll_fails_the_check(tmp_path):
    layout = _layout(tmp_path / "l", {"engines/ocr/tesseract.exe": build_pe(imports=("libstdc++-6.dll",))})
    assert rd.audit(layout)["unresolved"] == ["libstdc++-6.dll"]
    assert rd.main([str(layout), "--check"]) == 1


def test_a_32_bit_library_in_the_program_fails_but_32_bit_helpers_do_not(tmp_path):
    ok = _layout(tmp_path / "ok", {"unins000.exe": build_pe(imports=("kernel32.dll",), machine=0x14C)})
    assert rd.main([str(ok), "--check"]) == 0
    bad = _layout(tmp_path / "bad", {"_internal/x.dll": build_pe(imports=("kernel32.dll",), machine=0x14C)})
    assert rd.main([str(bad), "--check"]) == 1


def test_non_pe_files_with_program_suffixes_are_ignored(tmp_path):
    layout = _layout(tmp_path / "l", {"_internal/readme.dll": b"not a program"})
    assert rd.audit(layout)["layout_program_files"] == 0


def test_a_library_that_finds_msvcp_only_through_pyside6_fails_until_placed_app_local(tmp_path, capsys):
    layout = _layout(tmp_path / "l", {
        "_internal/pymupdf/mupdfcpp64.dll": build_pe(imports=("MSVCP140.dll", "VCRUNTIME140.dll")),
        "_internal/VCRUNTIME140.dll": build_pe(imports=("kernel32.dll",)),
        "_internal/PySide6/MSVCP140.dll": build_pe(imports=("VCRUNTIME140.dll",)),
        "_internal/PySide6/plugins/platforms/qwindows.dll": build_pe(imports=("MSVCP140.dll",)),
    })
    r = rd.audit(layout)
    assert r["vc_runtime_search_path_dependent"]["msvcp140.dll"] == [
        "_internal/PySide6/plugins/platforms/qwindows.dll", "_internal/pymupdf/mupdfcpp64.dll"]
    # Qt plugins are fine (PySide6 adds its folder); MuPDF would depend on import order
    assert rd.risky_search_dependent(r) == {"msvcp140.dll": ["_internal/pymupdf/mupdfcpp64.dll"]}
    assert rd.main([str(layout), "--check"]) == 1
    assert "found only through another package's folder" in capsys.readouterr().out
    assert rd.main([str(layout), "--place-app-local", "--check"]) == 0
    placed = layout / "_internal" / "MSVCP140.dll"
    assert placed.read_bytes() == (layout / "_internal" / "PySide6" / "MSVCP140.dll").read_bytes()
    assert rd.place_app_local(layout) == []  # nothing left to place


def test_placement_takes_the_newest_bundled_copy(tmp_path, monkeypatch):
    layout = _layout(tmp_path / "l", {
        "_internal/x.pyd": build_pe(imports=("MSVCP140.dll",)),
        "_internal/PySide6/MSVCP140.dll": build_pe(timestamp=1),
        "_internal/shiboken6/MSVCP140.dll": build_pe(timestamp=2),
    })
    versions = {"PySide6": (14, 39, 1, 0), "shiboken6": (14, 40, 0, 0)}
    monkeypatch.setattr(rd, "file_version", lambda p: versions.get(p.parent.name, (0, 0, 0, 0)))
    (line,) = rd.place_app_local(layout)
    assert "from _internal/shiboken6/MSVCP140.dll" in line and "14.40.0.0" in line
    assert (layout / "_internal" / "MSVCP140.dll").read_bytes() == (layout / "_internal" / "shiboken6" / "MSVCP140.dll").read_bytes()


def test_build_exe_places_and_checks_the_vc_runtime():
    text = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert "runtime_dependencies.py" in text and "--place-app-local" in text and "--check" in text
