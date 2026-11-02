"""Isolated runs never touch the real user profile (0.5.1).

During 0.5.1 acceptance an isolated run of the packaged program (MONOGRAPH_PDF_USER_DATA_DIR and
RUNTIME_DIR redirected) still wrote its crash-detection records to the real
%LOCALAPPDATA%\\Monograph PDF\\Diagnostics, consumed a stale record there, and created the real
%LOCALAPPDATA%\\Monograph PDF\\Updates\\state.json; the build's packaged self-check likewise used the
real Diagnostics folder. Each location had its own override and only the tests set all of them.
Now every per-user location defaults to a folder inside the redirected user-data folder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import app_env

ROOT = Path(__file__).resolve().parents[2]
ENV_NAMES = ("USER_DATA_DIR", "RUNTIME_DIR", "UPDATES_DIR", "DIAGNOSTICS_DIR")


def _clear(monkeypatch):
    for n in ENV_NAMES:
        monkeypatch.delenv("MONOGRAPH_PDF_" + n, raising=False)
        monkeypatch.delenv("PDFEDITOR_" + n, raising=False)


def _locations() -> dict[str, Path]:
    from core.diagnostics.crash import diagnostics_dir
    from core.ocr.language_packs import user_language_dir
    from core.updates.staging import updates_root
    from core.user_prefs import user_cache_dir, user_data_dir

    return {"user data": user_data_dir(), "diagnostics": diagnostics_dir(), "updates": updates_root(),
            "cache": user_cache_dir(), "ocr languages": user_language_dir()}


def test_redirected_user_data_contains_every_per_user_location(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "profile"))
    for name, path in _locations().items():
        assert tmp_path / "profile" in path.parents or path == tmp_path / "profile", (name, path)
    from core.user_prefs import legacy_user_data_dir

    assert legacy_user_data_dir() is None  # no migration from the real PDF Editor folder


def test_a_location_s_own_override_still_wins(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("MONOGRAPH_PDF_DIAGNOSTICS_DIR", str(tmp_path / "diag"))
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / "upd"))
    loc = _locations()
    assert loc["diagnostics"] == tmp_path / "diag" and loc["updates"] == tmp_path / "upd"


def test_installed_program_runtime_folder_follows_the_redirect(monkeypatch, tmp_path):
    import app.paths as paths

    _clear(monkeypatch)
    monkeypatch.setattr(paths, "_PROJECT_LAYOUT", False)
    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "profile"))
    assert paths._resolve_runtime_dir() == tmp_path / "profile" / "runtime"  # noqa: SLF001
    monkeypatch.setenv("MONOGRAPH_PDF_RUNTIME_DIR", str(tmp_path / "rt"))
    assert paths._resolve_runtime_dir() == tmp_path / "rt"  # noqa: SLF001


@pytest.mark.skipif(sys.platform != "win32", reason="Windows profile folders")
def test_normal_use_keeps_the_standard_windows_folders(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    loc = _locations()
    assert loc["user data"] == tmp_path / "Roaming" / "Monograph PDF"
    assert loc["diagnostics"] == tmp_path / "Local" / "Monograph PDF" / "Diagnostics"
    assert loc["updates"] == tmp_path / "Local" / "Monograph PDF" / "Updates"
    assert app_env.profile_subdir("x") is None


def test_this_test_session_points_away_from_the_real_profile():
    from tests.conftest import REAL_PROFILE_ROOTS

    for name, path in _locations().items():
        for real in REAL_PROFILE_ROOTS:
            assert real not in path.resolve().parents and path.resolve() != real, (name, path, real)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows profile folders")
def test_packaged_style_self_check_writes_nothing_into_the_profile(tmp_path):
    """End to end: the real self-check, with APPDATA/LOCALAPPDATA pointed at empty folders and none
    of the isolation variables set except the --runtime-dir the build and Setup pass."""
    import hashlib
    import json

    roaming, local = tmp_path / "Roaming", tmp_path / "Local"
    roaming.mkdir()
    diag = local / "Monograph PDF" / "Diagnostics"
    diag.mkdir(parents=True)
    # the real user's records: a crash from an earlier session and a report waiting to be shown
    (diag / "session-4242.json").write_text(json.dumps({"pid": 4242, "version": "0.5.0", "started": 1,
                                                        "events": []}), encoding="utf-8")
    (diag / "pending-report.json").write_text(json.dumps({"schema": 1, "report_type": "exception"}),
                                              encoding="utf-8")
    planted = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in diag.iterdir()}
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("MONOGRAPH_PDF_", "PDFEDITOR_"))}
    env.update(APPDATA=str(roaming), LOCALAPPDATA=str(local), QT_QPA_PLATFORM="offscreen",
               MONOGRAPH_PDF_DISABLE_OFFICE="1")
    report = tmp_path / "smoke.json"
    r = subprocess.run([sys.executable, "-m", "app", "--runtime-dir", str(tmp_path / "rt"), "--smoke-test",
                        "--report", str(report)], cwd=ROOT, env=env, capture_output=True, timeout=300)
    assert report.is_file(), r.stdout.decode(errors="replace")[-2000:] + r.stderr.decode(errors="replace")[-2000:]
    found = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")
                   if (roaming in p.parents or local in p.parents) and p.is_file())
    assert found == [str(Path("Local", "Monograph PDF", "Diagnostics", n)) for n in sorted(planted)], found
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in diag.iterdir()} == planted
