"""Update staging area: ownership markers, cleanup rules, links, disk space, the update lock."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

from core.updates import staging


@pytest.fixture(autouse=True)
def updates_dir(tmp_path, monkeypatch):
    root = tmp_path / "Updates"
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(root))
    return root


def _staged(version="0.3.1", state="verified", age=0.0, files=("installer",), **extra):
    sd = staging.new_staging(version)
    if "installer" in files:
        sd.installer.write_bytes(b"MZ" + b"x" * 100)
    if "part" in files:
        sd.partial.write_bytes(b"MZ")
    if "handoff" in files:
        (sd.path / "handoff.json").write_text("{}", encoding="utf-8")
    if "log" in files:
        (sd.path / "setup.log").write_text("log", encoding="utf-8")
    sd.set_state(state, **extra)
    marker = json.loads((sd.path / staging.MARKER).read_text(encoding="utf-8"))
    marker["updated"] = int(time.time() - age)
    (sd.path / staging.MARKER).write_text(json.dumps(marker), encoding="utf-8")
    return sd


def test_staging_lives_in_the_dedicated_updates_folder(updates_dir):
    sd = staging.new_staging("0.3.1")
    assert sd.path.parent == updates_dir / "Staging"
    assert staging.read_marker(sd.path)["owner"] == staging.OWNER
    assert sd.installer.name == "MonographPDF_0.3.1_Setup.exe"


def test_successful_update_removes_installer_and_folder():
    sd = _staged(state="installed", files=("installer", "handoff", "log"))
    rep = staging.cleanup()
    assert sd.path.name in rep.removed and not sd.path.exists()


def test_abandoned_downloads_are_removed_but_fresh_ones_kept():
    old = _staged(state="downloading", age=2 * 86400, files=("part",))
    fresh = _staged(state="downloading", age=60, files=("part",))
    rep = staging.cleanup()
    assert not old.path.exists() and old.path.name in rep.removed
    assert fresh.path.exists() and fresh.path.name in rep.kept


def test_failed_update_keeps_only_the_newest_installer_for_a_bounded_time():
    older = _staged(state="failed", age=3600, files=("installer", "log", "handoff"))
    newer = _staged(state="failed", age=60, files=("installer", "log", "handoff"))
    expired = _staged(state="failed", age=8 * 86400, files=("installer",))
    staging.cleanup()
    assert not older.path.exists() and not expired.path.exists()
    assert newer.installer.exists() and not (newer.path / "handoff.json").exists()


def test_repeated_updates_do_not_accumulate_packages():
    for v in ("0.3.1", "0.3.2", "0.3.3"):
        _staged(version=v, state="installed", files=("installer", "log"))
    staging.cleanup()
    assert list(staging.staging_root().iterdir()) == []


def test_unknown_files_and_folders_are_preserved(updates_dir):
    root = staging.staging_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "my notes.txt").write_text("keep", encoding="utf-8")
    (root / "not-an-update").mkdir()
    (root / "not-an-update" / "x.pdf").write_bytes(b"%PDF")
    lookalike = root / "0.3.1-0123456789ab"  # right name, but no ownership marker
    lookalike.mkdir()
    (lookalike / "MonographPDF_0.3.1_Setup.exe").write_bytes(b"MZ")
    sd = _staged(state="installed", files=("installer",))
    (sd.path / "user file.docx").write_bytes(b"keep")  # a foreign file inside an owned folder
    rep = staging.cleanup()
    assert (root / "my notes.txt").exists() and (root / "not-an-update" / "x.pdf").exists()
    assert (lookalike / "MonographPDF_0.3.1_Setup.exe").exists()
    assert (sd.path / "user file.docx").exists() and not sd.installer.exists()
    assert "my notes.txt" in rep.skipped_unknown and lookalike.name in rep.skipped_unknown


def test_marker_must_name_its_own_folder():
    sd = _staged(state="installed")
    marker = json.loads((sd.path / staging.MARKER).read_text(encoding="utf-8"))
    marker["id"] = "0.3.1-ffffffffffff"
    (sd.path / staging.MARKER).write_text(json.dumps(marker), encoding="utf-8")
    staging.cleanup()
    assert sd.installer.exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_cleanup_never_follows_links(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "MonographPDF_0.3.1_Setup.exe"
    victim.write_bytes(b"MZ important")
    (outside / staging.MARKER).write_text(json.dumps({"owner": staging.OWNER, "id": "0.3.1-0123456789ab",
                                                       "state": "installed", "updated": 0}), encoding="utf-8")
    root = staging.staging_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, root / "0.3.1-0123456789ab", target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks is not permitted here")
    rep = staging.cleanup()
    assert victim.exists() and "0.3.1-0123456789ab" in rep.skipped_unknown
    # a link inside an owned folder is not deleted through either
    sd = _staged(state="installed", files=())
    os.symlink(victim, sd.path / "MonographPDF_0.3.1_Setup.exe")
    staging.cleanup()
    assert victim.exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_linked_updates_root_is_refused(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    try:
        os.symlink(real, link, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks is not permitted here")
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(link))
    with pytest.raises(OSError):
        staging.new_staging("0.3.1")


def test_active_helper_and_active_attempt_are_left_alone():
    running = _staged(state="handed_off", files=("installer",), helper_pid=os.getpid())
    gone = _staged(state="handed_off", files=("installer",), helper_pid=999999)
    active = _staged(state="verified", age=10 * 86400, files=("installer",))
    staging.cleanup(active_id=active.path.name)
    assert running.installer.exists() and active.installer.exists()
    assert not gone.path.exists()


def test_files_in_use_stay_and_the_folder_is_retried_later(monkeypatch):
    sd = _staged(state="installed", files=("installer",))
    helper = sd.path / staging.HELPER_NAME
    helper.write_bytes(b"MZ")
    real_unlink = type(helper).unlink

    def busy(self, *a, **k):
        if self.name == staging.HELPER_NAME:
            raise PermissionError("in use")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(type(helper), "unlink", busy)
    rep = staging.cleanup()
    assert helper.exists() and sd.path.name in rep.kept and not sd.installer.exists()
    monkeypatch.setattr(type(helper), "unlink", real_unlink)  # the helper has exited
    staging.cleanup()
    assert not sd.path.exists()


def test_size_limit_trims_oldest_first(monkeypatch):
    monkeypatch.setattr(staging, "MAX_STAGING_BYTES", 400)  # one attempt is ~250 bytes
    a = _staged(version="0.3.1", state="verified", age=300)
    b = _staged(version="0.3.2", state="verified", age=10)
    staging.cleanup()
    assert not a.path.exists() and b.path.exists()


def test_disk_space_check(tmp_path, monkeypatch):
    assert staging.has_space(tmp_path, 1)
    assert not staging.has_space(tmp_path, 10**18)
    # a folder that does not exist yet is measured on its drive
    assert staging.has_space(tmp_path / "does-not-exist" / "x", 1)


def test_one_update_at_a_time():
    a, b = staging.UpdateLock(), staging.UpdateLock()
    assert a.acquire()
    assert not b.acquire()
    a.release()
    assert b.acquire()
    b.release()


def test_stale_lock_of_a_dead_process_is_replaced():
    lock = staging.UpdateLock()
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text(json.dumps({"pid": 999999, "time": int(time.time())}), encoding="utf-8")
    assert lock.acquire()
    lock.release()


@pytest.mark.parametrize("name", ["研究データ", "实验报告", "연구자료", "Ünïcödé Folder"])
def test_unicode_updates_folder(tmp_path, monkeypatch, name):
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / name / "Updates"))
    sd = _staged(state="installed", files=("installer", "log"))
    assert name in str(sd.path)
    staging.cleanup()
    assert not sd.path.exists()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows default location")
def test_default_location_is_local_appdata(monkeypatch):
    # normal use: no redirect at all (a redirected user-data folder would contain it, 0.5.1)
    monkeypatch.delenv("MONOGRAPH_PDF_UPDATES_DIR")
    monkeypatch.delenv("MONOGRAPH_PDF_USER_DATA_DIR", raising=False)
    root = staging.updates_root()
    assert root.parts[-2:] == ("Monograph PDF", "Updates")
    assert "Local" in root.parts or os.environ.get("LOCALAPPDATA", "") in str(root)
