"""User preferences must live in OS app-data, never project root."""

from __future__ import annotations

from pathlib import Path

from core.user_prefs import UserPreferences, recent_files_path, user_cache_dir, user_data_dir

ROOT = Path(__file__).resolve().parents[2]


def test_user_data_dir_not_project_root():
    d = user_data_dir()
    assert d.is_absolute()
    assert d != ROOT
    assert ROOT not in d.parents or "Monograph PDF" in d.name or "monograph-pdf" in d.name


def test_preferences_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_prefs.user_data_dir", lambda: tmp_path / "data")
    prefs = UserPreferences(theme="dark", left_panel_width=220)
    prefs.save()
    loaded = UserPreferences.load()
    assert loaded.theme == "dark"
    assert loaded.left_panel_width == 220
    assert loaded.path().parent == tmp_path / "data"
    assert ROOT not in loaded.path().parents


def test_recent_and_cache_paths_under_app_data(tmp_path, monkeypatch):
    import core.user_prefs as up

    monkeypatch.setattr(up, "user_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(up, "user_cache_dir", lambda: tmp_path / "cache")
    assert up.recent_files_path().parent == tmp_path / "data"
    assert up.user_cache_dir() == tmp_path / "cache"
