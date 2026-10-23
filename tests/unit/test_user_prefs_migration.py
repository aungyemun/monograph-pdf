"""Settings survive direct upgrades across versions, hand edits, newer versions and damage."""

from __future__ import annotations

import json

import pytest

from core import user_prefs
from core.recent_files import RecentFiles
from core.user_prefs import UserPreferences


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path))
    return tmp_path


def write(data_dir, obj) -> None:
    (data_dir / "preferences.json").write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def test_a_0_4_0_settings_file_loads_unchanged_and_gains_the_layout_version(data_dir):
    old = {"theme": "dark", "window_width": 1500, "last_zoom": 2, "recent_fonts": ["Georgia"],
           "update_auto_check": False, "ocr_languages": "eng"}  # no _schema: written before 0.4.1
    write(data_dir, old)
    p = UserPreferences.load()
    assert (p.theme, p.window_width, p.last_zoom, p.recent_fonts, p.ocr_languages) == ("dark", 1500, 2.0, ["Georgia"], "eng")
    assert isinstance(p.last_zoom, float)
    p.save()
    saved = json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert saved["_schema"] == user_prefs.SCHEMA and saved["theme"] == "dark"


def test_values_of_the_wrong_type_fall_back_to_defaults_without_losing_the_rest(data_dir):
    write(data_dir, {"theme": "light", "window_width": "1500", "update_auto_check": "yes",
                     "update_interval_hours": True, "window_x": None, "recent_colors": {"x": 1}})
    p, d = UserPreferences.load(), UserPreferences()
    assert p.theme == "light" and p.window_x is None
    assert (p.window_width, p.update_auto_check, p.update_interval_hours, p.recent_colors) == \
        (d.window_width, d.update_auto_check, d.update_interval_hours, d.recent_colors)


def test_settings_of_a_newer_version_are_kept_when_an_older_version_saves(data_dir):
    write(data_dir, {"_schema": 7, "theme": "dark", "future_option": {"a": 1}, "another": [1, 2]})
    p = UserPreferences.load()
    p.window_width = 1111
    p.save()
    saved = json.loads((data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert saved["future_option"] == {"a": 1} and saved["another"] == [1, 2]
    assert saved["_schema"] == 7 and saved["window_width"] == 1111 and saved["theme"] == "dark"


@pytest.mark.parametrize("content", ["{not json", "[1, 2, 3]", "\x00\x01garbage"])
def test_an_unreadable_settings_file_is_kept_aside_before_defaults_are_used(data_dir, content):
    write(data_dir, content)
    p = UserPreferences.load()
    assert p.theme == UserPreferences().theme
    copies = list(data_dir.glob("preferences.json.unreadable-*"))
    assert len(copies) == 1 and copies[0].read_text(encoding="utf-8") == content
    p.save()  # the original is replaced only now; its copy stays
    assert copies[0].read_text(encoding="utf-8") == content


def test_a_failing_migration_keeps_the_file_and_uses_defaults(data_dir, monkeypatch):
    def boom(data):
        raise KeyError("broken migration")

    monkeypatch.setitem(user_prefs.MIGRATIONS, 0, boom)
    write(data_dir, {"theme": "dark"})
    p = UserPreferences.load()
    assert p.theme == UserPreferences().theme
    assert len(list(data_dir.glob("preferences.json.unreadable-*"))) == 1


def test_migrations_run_step_by_step_from_any_older_layout(monkeypatch):
    calls = []
    monkeypatch.setattr(user_prefs, "SCHEMA", 3)
    def rename(d):
        calls.append(1)
        d["renamed"] = d.pop("old_name", None)
        return d

    monkeypatch.setattr(user_prefs, "MIGRATIONS", {
        0: lambda d: calls.append(0) or d,
        1: rename,
        2: lambda d: calls.append(2) or d})
    out = user_prefs.migrate({"old_name": "v"})
    assert calls == [0, 1, 2] and out["_schema"] == 3 and out["renamed"] == "v" and "old_name" not in out
    calls.clear()
    assert user_prefs.migrate({"_schema": 2, "x": 1})["_schema"] == 3 and calls == [2]


def test_every_layout_since_0_has_a_migration():
    assert all(n in user_prefs.MIGRATIONS for n in range(user_prefs.SCHEMA))


def test_saving_is_atomic_and_leaves_no_temporary_file(data_dir, monkeypatch):
    UserPreferences(theme="dark").save()
    before = (data_dir / "preferences.json").read_text(encoding="utf-8")

    def fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(user_prefs.os, "replace", fail)
    with pytest.raises(OSError):
        UserPreferences(theme="light").save()
    assert (data_dir / "preferences.json").read_text(encoding="utf-8") == before  # old file intact


def test_recent_files_save_atomically(data_dir, tmp_path):
    doc = tmp_path / "a.pdf"
    doc.write_bytes(b"%PDF-1.7")
    r = RecentFiles(limit=12)
    r.add(doc)
    assert json.loads((data_dir / "recent_files.json").read_text(encoding="utf-8")) == [str(doc.resolve())]
    assert not list(data_dir.glob("*.tmp"))
