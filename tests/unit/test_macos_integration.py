"""Regression checks for macOS functionality retained from the pre-unification branch."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fontTools.ttLib import TTCollection, TTFont

from core.editing import system_fonts as sf
from engines import probe

ROOT = Path(__file__).resolve().parents[2]


def test_installed_base14_font_keeps_mupdf_field_appearance(tmp_path, monkeypatch):
    from core.forms.appearance import needs_custom_appearance

    installed = tmp_path / "Helvetica.ttf"
    installed.write_bytes((ROOT / "resources/fonts/NotoSans-Regular.ttf").read_bytes())
    monkeypatch.setattr(sf, "_registry_fonts", lambda: {"helvetica": installed})
    field = SimpleNamespace(value="Plain text 123", font_family="Helvetica", font_size=12)
    assert sf.load("Helvetica") is None  # base-14 families intentionally use MuPDF's built-in face
    assert not needs_custom_appearance(field)


def test_macos_catalog_reads_font_names_and_collection_faces(tmp_path):
    folder = tmp_path / "Fonts 日本語"
    folder.mkdir()
    regular = folder / "renamed.ttf"
    regular.write_bytes((ROOT / "resources/fonts/NotoSans-Regular.ttf").read_bytes())
    collection = TTCollection()
    collection.fonts = [TTFont(str(ROOT / "resources/fonts/NotoSerif-Regular.ttf"))]
    try:
        collection.save(str(folder / "collection.ttc"))
    finally:
        collection.close()
    found = sf._macos_fonts((folder, tmp_path / "missing"))
    assert found["noto sans"] == regular
    assert found["noto serif"] == folder / "collection.ttc"


def test_macos_font_embedding_still_rejects_restricted_fonts(tmp_path, monkeypatch):
    font = TTFont(str(ROOT / "resources/fonts/NotoSans-Regular.ttf"))
    restricted = tmp_path / "restricted.ttf"
    try:
        font["OS/2"].fsType = 2
        font.save(str(restricted))
    finally:
        font.close()
    monkeypatch.setattr(sf, "_registry_fonts", lambda: {"noto sans": restricted})
    assert sf.load("Noto Sans") is None
    assert "license" in sf.take_notes()["Noto Sans"]


def test_macos_regular_family_does_not_resolve_to_first_bold_file(tmp_path):
    regular = tmp_path / "regular.ttf"
    regular.write_bytes((ROOT / "resources/fonts/NotoSans-Regular.ttf").read_bytes())
    bold = tmp_path / "bold.ttf"
    font = TTFont(str(regular))
    try:
        for record in font["name"].names:
            if record.nameID in (2, 17):
                record.string = "Bold".encode(record.getEncoding())
            elif record.nameID == 4:
                record.string = "Noto Sans Bold".encode(record.getEncoding())
        font.save(str(bold))
    finally:
        font.close()
    found = {}
    sf._index_font_file(found, bold)
    sf._index_font_file(found, regular)
    assert found["noto sans"] == regular
    assert found["noto sans bold"] == bold


@pytest.mark.parametrize("platform,expected", [("darwin", "mac"), ("win32", "win"), ("linux", None)])
def test_font_catalog_dispatch_preserves_windows_and_linux(platform, expected, monkeypatch):
    monkeypatch.setattr(sf, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(sf, "_macos_fonts", lambda: {"mac": Path("mac.ttf")})
    monkeypatch.setattr(sf, "_windows_registry_fonts", lambda: {"win": Path("win.ttf")})
    sf._registry_fonts.cache_clear()
    try:
        found = sf._registry_fonts()
        assert set(found) == ({expected} if expected else set())
    finally:
        sf._registry_fonts.cache_clear()


def test_qpdf_probe_finds_unix_engine_outside_install_root(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "darwin")
    engine = tmp_path / "external engines/qpdf/bin/qpdf"
    engine.parent.mkdir(parents=True)
    engine.write_bytes(b"synthetic engine")
    monkeypatch.setattr(probe, "ENGINES_DIR", tmp_path / "external engines")
    monkeypatch.setattr(probe, "ROOT", tmp_path / "app")
    status = probe.probe_qpdf()
    assert status.available and status.detail == str(engine)


def test_reveal_in_finder_uses_absolute_tool_and_keeps_unicode_path(tmp_path, monkeypatch):
    import subprocess
    from ui import main_window

    monkeypatch.setattr(main_window, "sys", SimpleNamespace(platform="darwin"))
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: calls.append(args))
    file = tmp_path / "資料 with spaces.pdf"
    file.write_bytes(b"synthetic")
    window = SimpleNamespace(_open_folder=lambda path: pytest.fail("Finder reveal was bypassed"))
    main_window.MainWindow._reveal_file(window, file)
    assert calls == [["/usr/bin/open", "-R", str(file)]]


def test_macos_default_app_handler_uses_system_settings(monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox
    from ui import main_window

    monkeypatch.setattr(main_window, "sys", SimpleNamespace(platform="darwin"))
    messages, urls = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: urls.append(url.toString()) or False)
    main_window.MainWindow._make_default_app(SimpleNamespace())
    assert len(messages) == 1 and "macOS" in messages[0]
    assert urls[-1] == "x-apple.systempreferences:"
    assert all(url.startswith("x-apple.systempreferences:") for url in urls)
