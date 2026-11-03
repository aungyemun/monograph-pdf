"""Linux desktop entry: PNG icon and WM class without a Windows .exe suffix."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from core.product_meta import EXECUTABLE_NAME, REPOSITORY_NAME, resolve_app_icon_path

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux FreeDesktop .desktop entry and installer/linux/install.sh only",
)


def test_resolve_app_icon_prefers_png_on_linux():
    icon = resolve_app_icon_path()
    assert icon is not None and icon.is_file()
    assert icon.suffix.lower() == ".png"
    assert icon.name == "monograph_pdf_256.png"


def test_desktop_entry_uses_png_icon_and_linux_wmclass(tmp_path, monkeypatch):
    from core import linux_desktop

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    desktop_id = linux_desktop.ensure_desktop_entry()
    assert desktop_id == f"{REPOSITORY_NAME}.desktop"
    path = tmp_path / "applications" / desktop_id
    text = path.read_text(encoding="utf-8")
    icon = resolve_app_icon_path()
    assert f"Icon={icon}" in text
    assert icon.suffix.lower() == ".png"
    assert ".ico" not in text
    assert f"StartupWMClass={EXECUTABLE_NAME}" in text
    assert EXECUTABLE_NAME == "MonographPDF"
    assert "MonographPDF.exe" not in text


def test_install_script_desktop_entry_prefers_png(tmp_path):
    """installer/linux/install.sh must point Icon= at an installed PNG, not .ico."""
    src = tmp_path / "src"
    icons = src / "resources" / "icons" / "windows"
    icons.mkdir(parents=True)
    (src / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (src / "MonographPDF").write_bytes(b"#!/bin/true\n")
    (src / "MonographPDF").chmod(0o755)
    (icons / "monograph_pdf.ico").write_bytes(b"ico")
    (icons / "monograph_pdf_256.png").write_bytes(b"png256")
    xdg = tmp_path / "xdg"
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(xdg / "data"),
        "XDG_BIN_HOME": str(xdg / "bin"),
        # xdg-mime writes mimeapps.list here; never touch the real user's default PDF app.
        "XDG_CONFIG_HOME": str(xdg / "config"),
    }
    import subprocess

    root = Path(__file__).resolve().parents[2]
    script = root / "installer" / "linux" / "install.sh"
    proc = subprocess.run(
        ["bash", str(script), str(src)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    desk = (xdg / "data" / "applications" / "monograph-pdf.desktop").read_text(encoding="utf-8")
    assert "monograph_pdf_256.png" in desk
    assert ".ico" not in desk
    assert "StartupWMClass=MonographPDF" in desk


def test_install_script_finds_icon_in_pyinstaller_layout(tmp_path):
    """A PyInstaller onedir build keeps resources under _internal/; Icon= must still be a PNG path."""
    src = tmp_path / "src"
    icons = src / "_internal" / "resources" / "icons" / "windows"
    icons.mkdir(parents=True)
    (src / "VERSION").write_text("0.1.1\n", encoding="utf-8")
    (src / "MonographPDF").write_bytes(b"#!/bin/true\n")
    (src / "MonographPDF").chmod(0o755)
    (icons / "monograph_pdf_256.png").write_bytes(b"png256")
    xdg = tmp_path / "xdg"
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(xdg / "data"),
        "XDG_BIN_HOME": str(xdg / "bin"),
        "XDG_CONFIG_HOME": str(xdg / "config"),
    }
    import subprocess

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["bash", str(root / "installer" / "linux" / "install.sh"), str(src)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    desk = (xdg / "data" / "applications" / "monograph-pdf.desktop").read_text(encoding="utf-8")
    dest = xdg / "data" / "Monograph PDF"
    assert f"Icon={dest / '_internal' / 'resources' / 'icons' / 'windows' / 'monograph_pdf_256.png'}" in desk
    assert '"version":"0.1.1"' in (dest / ".monograph-installed").read_text(encoding="utf-8")
