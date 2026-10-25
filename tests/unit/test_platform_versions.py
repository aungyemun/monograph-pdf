"""Independent platform version lines (Option B)."""

from __future__ import annotations

from core import versioning


def test_host_version_matches_platform_file():
    plat = versioning.current_platform()
    assert versioning.get_version() == versioning.get_version(plat)
    assert versioning.get_version("windows") == "0.5.0"
    assert versioning.get_version("linux") == "0.1.0"
    assert versioning.get_version("macos") == "0.1.0"


def test_windows_root_version_mirrors_windows_line():
    # Packaging tools that still read root VERSION see the Windows line.
    assert (versioning.project_root() / "VERSION").read_text(encoding="utf-8").strip() == "0.5.0"
    assert versioning.get_version("windows") == "0.5.0"


def test_all_platform_versions():
    assert versioning.all_platform_versions() == {
        "windows": "0.5.0",
        "linux": "0.1.0",
        "macos": "0.1.0",
    }


def test_write_version_linux_does_not_change_windows(tmp_path, monkeypatch):
    root = tmp_path
    (root / "versions").mkdir()
    (root / "versions" / "windows.txt").write_text("0.5.0\n", encoding="utf-8")
    (root / "versions" / "linux.txt").write_text("0.1.0\n", encoding="utf-8")
    (root / "versions" / "macos.txt").write_text("0.1.0\n", encoding="utf-8")
    (root / "VERSION").write_text("0.5.0\n", encoding="utf-8")
    monkeypatch.setattr(versioning, "project_root", lambda: root)
    versioning.write_version("0.1.1", platform="linux")
    assert versioning.get_version("linux") == "0.1.1"
    assert versioning.get_version("windows") == "0.5.0"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "0.5.0"
