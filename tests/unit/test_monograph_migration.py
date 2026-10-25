"""PDF Editor (<= 0.1.5) -> Monograph PDF 0.2.0 migration: settings, environment overrides,
temporary-folder names, installer upgrade/migration logic and frozen-release protection.

The installer itself is exercised end to end (with the real PDF Editor 0.1.5 Setup) by
scripts/test_installer.ps1 sections 14-21; these tests pin the logic that makes that work.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from core import app_env
from core import legacy_migration as lm

ROOT = Path(__file__).resolve().parents[2]
ISS = (ROOT / "installer" / "MonographPDF.iss").read_text(encoding="utf-8-sig")


def _section(name: str) -> str:
    m = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[[A-Za-z]+\]\s*$|\Z)", ISS, flags=re.M | re.S)
    return m.group(1) if m else ""


# ----------------------------------------------------------------- environment overrides


def test_new_environment_variable_wins_over_the_deprecated_alias(monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_RUNTIME_DIR", "new")
    monkeypatch.setenv("PDFEDITOR_RUNTIME_DIR", "old")
    assert app_env.get("RUNTIME_DIR") == "new"


def test_deprecated_alias_is_still_read(monkeypatch):
    monkeypatch.delenv("MONOGRAPH_PDF_USER_DATA_DIR", raising=False)
    monkeypatch.setenv("PDFEDITOR_USER_DATA_DIR", "legacy-dir")
    assert app_env.get("USER_DATA_DIR") == "legacy-dir"
    monkeypatch.delenv("PDFEDITOR_USER_DATA_DIR")
    assert app_env.get("USER_DATA_DIR", "default") == "default"


def test_blank_value_counts_as_unset(monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_HEADLESS", "  ")
    monkeypatch.setenv("PDFEDITOR_HEADLESS", "1")
    assert app_env.is_true("HEADLESS")


def test_set_writes_the_new_name_and_drops_the_alias(monkeypatch):
    monkeypatch.setenv("PDFEDITOR_RUNTIME_DIR", "old")
    app_env.set("RUNTIME_DIR", "x")
    import os

    assert os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] == "x" and "PDFEDITOR_RUNTIME_DIR" not in os.environ
    monkeypatch.delenv("MONOGRAPH_PDF_RUNTIME_DIR")


def test_user_data_dir_follows_the_override_and_the_new_name(monkeypatch, tmp_path):
    from core import user_prefs

    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "ud"))
    assert user_prefs.user_data_dir() == tmp_path / "ud"
    monkeypatch.delenv("MONOGRAPH_PDF_USER_DATA_DIR")
    monkeypatch.delenv("PDFEDITOR_USER_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert user_prefs.user_data_dir() == tmp_path / "Roaming" / "Monograph PDF"
    assert user_prefs.legacy_user_data_dir() == tmp_path / "Roaming" / "PDF Editor"


def test_no_active_code_reads_only_the_legacy_variables():
    hits = []
    for folder in ("app", "core", "ui", "engines"):
        for f in (ROOT / folder).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            if f.name == "app_env.py":
                continue
            if re.search(r'["\']PDFEDITOR_[A-Z_]+["\']', text):
                hits.append(str(f.relative_to(ROOT)))
    assert not hits, hits


# ----------------------------------------------------------------- temporary folder names


def test_new_temporary_folders_use_monograph_prefixes():
    stale = []
    for folder in ("app", "core", "ui"):
        for f in (ROOT / folder).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for m in re.finditer(r'prefix="([^"]+)"', text):
                # product-named prefixes (in %TEMP%) must be the new ones; others live in our runtime folder
                if re.search(r"(?i)pdf.?editor|monograph", m.group(1)) and not m.group(1).startswith("monographpdf"):
                    stale.append(f"{f.relative_to(ROOT)}: {m.group(1)}")
    assert not stale, stale
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert '"monograph-pdf-theme"' in theme and '"pdf-' + 'editor-theme"' not in theme


def test_uninstall_recognises_old_and_new_temporary_folders_only():
    code = _section("Code")
    assert "RemoveTempMatches(Temp, 'monograph*')" in code and "RemoveTempMatches(Temp, 'pdf*editor*')" in code
    assert "function IsOwnTempName" in code


# ----------------------------------------------------------------- AppData migration


def _locations(tmp_path: Path) -> lm.Locations:
    roaming, local = tmp_path / "Roaming", tmp_path / "Local"
    return lm.Locations(roaming / "PDF Editor", local / "PDF Editor", roaming / "Monograph PDF", local / "Monograph PDF")


def _plant_legacy(loc: lm.Locations, existing: Path) -> None:
    loc.legacy_roaming.mkdir(parents=True)
    (loc.legacy_roaming / "preferences.json").write_text(json.dumps({"theme": "dark", "recent_limit": 7}), encoding="utf-8")
    (loc.legacy_roaming / "recent_files.json").write_text(json.dumps([str(existing), str(existing.parent / "gone.pdf"), "relative.pdf"]),
                                                          encoding="utf-8")
    sessions = loc.legacy_local / "runtime" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "doc.json").write_text(json.dumps({"version": 1, "source": str(existing), "payload": {"dirty": True}}), encoding="utf-8")
    (sessions / "future.json").write_text(json.dumps({"version": 9}), encoding="utf-8")
    for sub in ("cache", "temp", "logs"):
        (loc.legacy_local / "runtime" / sub).mkdir(parents=True)
        (loc.legacy_local / "runtime" / sub / "x.bin").write_bytes(b"x")


@pytest.fixture
def no_override(monkeypatch):
    for name in ("USER_DATA_DIR", "NO_LEGACY_MIGRATION", "RUNTIME_DIR"):
        monkeypatch.delenv("MONOGRAPH_PDF_" + name, raising=False)
        monkeypatch.delenv("PDFEDITOR_" + name, raising=False)


def test_migration_copies_settings_recent_files_and_sessions(tmp_path, no_override):
    loc = _locations(tmp_path)
    doc = tmp_path / "docs" / "report.pdf"
    doc.parent.mkdir()
    doc.write_bytes(b"%PDF-1.7")
    _plant_legacy(loc, doc)
    runtime = loc.local / "runtime"
    res = lm.migrate(loc, runtime_dir=runtime)
    assert res.ran and not res.errors, res
    assert json.loads((loc.roaming / "preferences.json").read_text(encoding="utf-8"))["theme"] == "dark"
    assert json.loads((loc.roaming / "recent_files.json").read_text(encoding="utf-8")) == [str(doc)]
    assert (runtime / "sessions" / "doc.json").is_file()
    assert not (runtime / "sessions" / "future.json").exists()  # unknown format stays where it was
    for sub in ("cache", "temp", "logs"):
        assert not (runtime / sub / "x.bin").exists(), sub  # never carried over
    record = json.loads((loc.roaming / lm.MARKER_NAME).read_text(encoding="utf-8"))
    assert record["from"] == "PDF Editor" and record["to"] == "Monograph PDF"
    assert record["legacy_roaming"] == str(loc.legacy_roaming)
    # PDF Editor's data is never changed or deleted
    assert (loc.legacy_roaming / "preferences.json").is_file() and (loc.legacy_local / "runtime" / "sessions" / "doc.json").is_file()
    assert (loc.legacy_local / "runtime" / "cache" / "x.bin").is_file()


def test_migration_runs_once_and_never_overwrites_monograph_settings(tmp_path, no_override):
    loc = _locations(tmp_path)
    _plant_legacy(loc, tmp_path / "missing.pdf")
    loc.roaming.mkdir(parents=True)
    (loc.roaming / "preferences.json").write_text('{"theme": "light"}', encoding="utf-8")
    res = lm.migrate(loc)
    assert res.ran and "preferences.json (Monograph PDF already has settings)" in res.skipped
    assert json.loads((loc.roaming / "preferences.json").read_text(encoding="utf-8"))["theme"] == "light"
    again = lm.migrate(loc)
    assert not again.ran and again.reason == "already migrated"


def test_migration_without_legacy_data_does_nothing(tmp_path, no_override):
    loc = _locations(tmp_path)
    res = lm.migrate(loc)
    assert not res.ran and res.reason == "no PDF Editor data" and not loc.roaming.exists()


def test_migration_is_skipped_when_redirected_or_disabled(tmp_path, monkeypatch, no_override):
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "ud"))
    assert lm.migrate().reason == "user-data folder redirected"
    monkeypatch.delenv("MONOGRAPH_PDF_USER_DATA_DIR")
    monkeypatch.setenv("MONOGRAPH_PDF_NO_LEGACY_MIGRATION", "1")
    assert lm.migrate(_locations(tmp_path)).reason == "disabled"


def test_migration_ignores_damaged_files(tmp_path, no_override):
    loc = _locations(tmp_path)
    loc.legacy_roaming.mkdir(parents=True)
    (loc.legacy_roaming / "preferences.json").write_text("{not json", encoding="utf-8")
    (loc.legacy_roaming / "recent_files.json").write_text('{"a": 1}', encoding="utf-8")
    res = lm.migrate(loc)
    assert res.ran and len(res.errors) == 2
    assert not (loc.roaming / "preferences.json").exists() and not (loc.roaming / "recent_files.json").exists()
    assert (loc.roaming / lm.MARKER_NAME).is_file()


def test_migration_never_follows_a_linked_legacy_folder(tmp_path, no_override):
    loc = _locations(tmp_path)
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "preferences.json").write_text("{}", encoding="utf-8")
    loc.legacy_roaming.parent.mkdir(parents=True)
    try:
        loc.legacy_roaming.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links not permitted here")
    res = lm.migrate(loc)
    assert not res.ran and "link" in res.reason


def test_startup_runs_the_migration_before_settings_are_read():
    text = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8")
    assert text.index("migrate_at_startup()") < text.index("UserPreferences.load()")
    smoke = (ROOT / "app" / "smoke_test.py").read_text(encoding="utf-8")
    assert "migrate" not in smoke  # the installer's self-check never touches user data


# ----------------------------------------------------------------- installer: identity and upgrade


def test_installer_keeps_the_pdf_editor_appid():
    assert "AppId={{64FC0D97-5E17-405F-9461-D6C075E1B467}" in ISS
    assert "Uninstall\\{64FC0D97-5E17-405F-9461-D6C075E1B467}_is1" in ISS


def test_installer_identity_is_monograph_pdf():
    for line in ('#define AppName "Monograph PDF"', '#define AppExe "MonographPDF.exe"', '#define ProgIdPdf "MonographPDF.Document"',
                 '#define ProgIdOther "MonographPDF.Convertible"', '#define AppRegKey "Software\\Monograph PDF"',
                 "OutputBaseFilename=MonographPDF_{#AppVersion}_Setup", "DefaultDirName={autopf}\\{#AppName}",
                 "SetupIconFile={#Root}\\resources\\icons\\windows\\monograph_pdf.ico", "UninstallDisplayIcon={app}\\{#AppExe}",
                 "UninstallDisplayName={#AppName}", "UsePreviousGroup=no", 'PayloadDir Root + "\\dist\\MonographPDF"'):
        assert line in ISS, line
    tasks = _section("Tasks")
    assert "Register Monograph PDF for &PDF files" in tasks and "Add Monograph PDF to Open with" in tasks
    icons = _section("Icons")
    assert '"{group}\\{#AppName} User Guide"' in icons and '"{autodesktop}\\{#AppName}"' in icons


def test_installer_never_makes_itself_the_default_pdf_app():
    reg = _section("Registry").lower()
    assert "userchoice" not in reg and "\\.pdf\"; valuetype: string; valuename: \"\"" not in reg
    assert "ms-settings:defaultapps" in _section("Run")


def test_installer_recognises_pdf_editor_installations():
    code = _section("Code")
    assert '#define LegacyExe "PDF_editor.exe"' in ISS and '#define LegacyName "PDF Editor"' in ISS
    assert "FileExists(AddBackslash(Dir) + '{#AppExe}') or FileExists(AddBackslash(Dir) + '{#LegacyExe}')" in code
    assert "AppPathsDirFor(HKCU, '{#LegacyExe}')" in code  # App Paths
    assert "ExpandConstant('{pf}\\{#LegacyName}')" in code  # C:\Program Files\PDF Editor
    assert "ExpandConstant('{localappdata}\\Programs\\{#LegacyName}')" in code  # per-user default
    assert "{userprograms}\\{#LegacyName}\\{#LegacyName}.lnk" in code  # verified Start menu fallback
    assert "Name = ''{#LegacyExe}''" in code  # a running PDF_editor.exe blocks Setup
    assert 'Type: files; Name: "{app}\\{#LegacyExe}"' in _section("InstallDelete")
    assert "RemoveOwnedRelUnder(Base, '{#LegacyExe}')" in code


def test_upgrade_page_wording():
    code = _section("Code")
    assert "'Existing installation found'" in code
    assert "'An existing installation was found at:'" in code
    assert "has been renamed" not in code  # no product-history wording in Setup
    assert "preserving your settings and documents" in code
    assert "'Upgrade using the existing installation location (" in code
    assert "and remove the previous application" in code
    assert "'Cancel — Go back'" in code


def test_move_to_renamed_folder_only_after_the_new_install_is_validated():
    code = _section("Code")
    clean = code[code.index("procedure CleanPreviousLocationIfMoved"):]
    clean = clean[: clean.index("end;\n\n")]
    assert "(not NewInstallLooksValid()) or (not SmokeTestPassed)" in clean
    post = code[code.index("if CurStep = ssPostInstall then"):]
    assert post.index("RunSmokeTest();") < post.index("CleanPreviousLocationIfMoved();") < post.index("RemoveLegacyRegistrations();")
    renamed = code[code.index("function RenamedLegacyDir"):]
    assert "'{#LegacyName}') <> 0" in renamed[:800] and "already exists" in renamed[:1200]


def test_legacy_registrations_are_removed_only_when_their_program_is_gone():
    code = _section("Code")
    assert "function IsRemovedLegacyExe" in code and "not FileExists(Exe)" in code
    for key in ("App Paths\\{#LegacyExe}", "Applications\\{#LegacyExe}", "{#LegacyProgIdPdf}", "{#LegacyProgIdOther}",
                "{#LegacyRegKey}\\Capabilities"):
        assert key in code, key
    assert "RegDeleteValue(AppRoot(), 'Software\\RegisteredApplications', '{#LegacyName}')" in code
    assert "RemoveLegacyOpenWith('.pdf', '{#LegacyProgIdPdf}')" in code
    shortcuts = code[code.index("procedure RemoveLegacyShortcuts"):]
    assert "{autoprograms}\\{#LegacyName}" in shortcuts and "{autodesktop}\\{#LegacyName}.lnk" in shortcuts


def test_silent_policy_and_migrate_switch():
    code = _section("Code")
    assert "CmdHasSwitch('/MIGRATEINSTALL')" in code
    assert "LegacyUpgrade and MigrateInstallFlag and (not CmdHasDir()) and (RenamedDir <> '')" in code
    assert "(pass /MIGRATEINSTALL to move)" in code


def test_uninstall_cleans_pdf_editor_data_only_with_proven_provenance():
    code = _section("Code")
    tail = code[code.index("procedure CurUninstallStepChanged"):]
    assert "LegacyMigrationRecord) and" in tail and "not LegacyAppStillPresent()" in tail
    assert "if LegacyDataAllowed then\n      ClearHistoryIn(LegacyDataFolderName);" in tail
    assert "/REMOVEUSERDATA" in code and "MB_DEFBUTTON2" in tail


# ----------------------------------------------------------------- frozen PDF Editor 0.1.5 release


def _check_release():
    sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
    try:
        import check_release

        return check_release
    finally:
        sys.path.pop(0)


def _release(folder: Path, product: str, version: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "Setup.exe").write_bytes(b"MZ setup " + version.encode())
    (folder / "SHA256SUMS.txt").write_text(f"{product} {version} - SHA-256 checksums\n\nABC  Setup.exe\n", encoding="utf-8")
    return folder


def test_frozen_release_folder_is_never_overwritten_unless_archived(tmp_path, capsys):
    cr = _check_release()
    release = _release(tmp_path / "installer" / "release", "PDF Editor", "0.1.5")
    archive = tmp_path / "releases"
    assert cr.guard_frozen(release, "0.2.0", archive) == 1
    assert "not archived" in capsys.readouterr().err
    copy = archive / "PDFEditor_0.1.5" / "release"
    copy.mkdir(parents=True)
    for f in release.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())
    assert cr.guard_frozen(release, "0.2.0", archive) == 0
    (copy / "Setup.exe").write_bytes(b"changed")
    assert cr.guard_frozen(release, "0.2.0", archive) == 1  # a copy that differs does not count


def test_same_version_or_empty_release_folder_may_be_rebuilt(tmp_path):
    cr = _check_release()
    assert cr.guard_frozen(tmp_path / "none", "0.2.0", tmp_path / "releases") == 0
    release = _release(tmp_path / "release", "Monograph PDF", "0.2.0")
    assert cr.guard_frozen(release, "0.2.0", tmp_path / "releases") == 0


def test_frozen_pdf_editor_artifacts_are_excluded_from_source_and_git():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/releases/" in gitignore and "installer/*.zip" in gitignore
    sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
    try:
        import make_source_archive as msa
    finally:
        sys.path.pop(0)
    assert "releases" not in msa.SOURCE_TOP


def test_historical_changelog_entries_are_kept():
    from core.versioning import get_version

    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Root CHANGELOG tracks the Windows public line; Linux/macOS notes live under docs/releases/.
    ver = get_version("windows")
    assert re.search(rf"^## \[{re.escape(ver)}\] — (Unreleased|\d{{4}}-\d{{2}}-\d{{2}})$", log, re.M)
    assert "## Internal development history" in log
    assert "### [0.1.5] — 2026-10-15" in log and "### [0.1.4] — 2026-10-08" in log
    assert "[0.1.6]" not in log  # folded into the 0.2.x public line, never released
    assert log.index(f"## [{ver}]") < log.index("## Internal development history") < log.index("### [0.1.5]")
    public = log[: log.index("## Internal development history")]
    assert "PDF Editor" not in public  # the public entry presents a standalone product


# ----------------------------------------------------------------- branding scan


def test_no_stale_pdf_editor_branding_remains():
    """Every remaining 'PDF Editor' / 'PDF_editor' reference is history or migration compatibility."""
    sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
    try:
        import branding_scan
    finally:
        sys.path.pop(0)
    hits = branding_scan.scan(ROOT)
    stale = [f"{h['file']}:{h['line']}: {h['text']}" for h in hits if h["class"] == "INCORRECT-STALE-BRANDING"]
    assert not stale, "\n".join(stale)
    assert any(h["class"] == "EXPECTED-MIGRATION-COMPATIBILITY" for h in hits)  # the scan does find the legacy code


def test_migration_accepts_files_with_a_byte_order_mark(tmp_path, no_override):
    """PDF Editor data edited by hand (Notepad / PowerShell) may start with a UTF-8 BOM."""
    loc = _locations(tmp_path)
    doc = tmp_path / "a.pdf"
    doc.write_bytes(b"%PDF-1.7")
    loc.legacy_roaming.mkdir(parents=True)
    bom = b"\xef\xbb\xbf"
    (loc.legacy_roaming / "preferences.json").write_bytes(bom + b'{"theme": "dark"}')
    (loc.legacy_roaming / "recent_files.json").write_bytes(bom + json.dumps([str(doc)]).encode())
    sessions = loc.legacy_local / "runtime" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "s.json").write_bytes(bom + json.dumps({"version": 1, "payload": {}}).encode())
    runtime = loc.local / "runtime"
    res = lm.migrate(loc, runtime_dir=runtime)
    assert not res.errors, res.errors
    assert json.loads((loc.roaming / "preferences.json").read_text(encoding="utf-8"))["theme"] == "dark"
    assert json.loads((loc.roaming / "recent_files.json").read_text(encoding="utf-8")) == [str(doc)]
    # the copied session is plain UTF-8 JSON that the session store reads
    assert json.loads((runtime / "sessions" / "s.json").read_text(encoding="utf-8"))["version"] == 1
