"""Choosing the installation to update, verified staging and the hand-off to the update helper."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest

from core.updates import install_target, manager, staging
from core.updates.install_target import Registration
from core.updates.manifest import parse_and_verify
from tests.fixtures.update_fixtures import make_config, manifest_bytes, setup_bytes, signed_fields

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Windows installer registration / MonographPDF.exe update hand-off",
)


@pytest.fixture(autouse=True)
def updates_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / "Updates"))


def _install(folder: Path, *, helper: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "MonographPDF.exe").write_bytes(b"MZ app")
    (folder / "unins000.exe").write_bytes(b"MZ uninst")
    if helper:
        (folder / staging.HELPER_NAME).write_bytes(b"MZ helper")
    return folder / "MonographPDF.exe"


@pytest.mark.parametrize("name", [
    "Monograph PDF", "Applications/Monograph PDF", "ソフトウェア/Monograph PDF", "张伟的程序/Monograph PDF",
    "김민수/Monograph PDF", "Prüfung (x86)/Monograph PDF",
])
def test_registered_installation_is_found_in_its_hive(tmp_path, name):
    exe = _install(tmp_path / name)
    folder = str(exe.parent) + "\\"  # Inno Setup stores InstallLocation with a trailing separator
    for hive, mode in (("HKCU", "user"), ("HKLM64", "machine"), ("HKLM32", "machine")):
        t = install_target.detect(exe, lambda: [Registration(hive, folder, "0.3.0", "startmenu,assocpdf")])
        assert t.ok and t.mode == mode and t.install_dir == exe.parent and t.version == "0.3.0"
        assert t.tasks == "startmenu,assocpdf" and t.exe == exe


def test_other_registered_copies_are_reported_but_not_targeted(tmp_path):
    exe = _install(tmp_path / "per-user" / "Monograph PDF")
    regs = [Registration("HKCU", str(exe.parent), "0.3.0", ""),
            Registration("HKLM64", str(tmp_path / "Program Files" / "Monograph PDF"), "0.2.2", "")]
    t = install_target.detect(exe, lambda: regs)
    assert t.ok and t.mode == "user" and t.others == [str(tmp_path / "Program Files" / "Monograph PDF")]


def test_unregistered_portable_source_and_ambiguous_copies_are_refused(tmp_path):
    exe = _install(tmp_path / "copy")
    t = install_target.detect(exe, lambda: [Registration("HKCU", str(tmp_path / "elsewhere"), "0.3.0", "")])
    assert not t.ok and "not the installation registered" in t.reason
    both = [Registration("HKCU", str(exe.parent), "0.3.0", ""), Registration("HKLM64", str(exe.parent), "0.3.0", "")]
    t = install_target.detect(exe, lambda: both)
    assert not t.ok and "ambiguous" in t.reason
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / "MonographPDF.exe").write_bytes(b"MZ")
    t = install_target.detect(portable / "MonographPDF.exe", lambda: [Registration("HKCU", str(portable), "0.3.0", "")])
    assert not t.ok and "not installed with Setup" in t.reason
    assert not install_target.detect(tmp_path / "python.exe", lambda: []).ok
    assert not install_target.detect(registrations=lambda: []).ok  # running from source


def _release(version="0.3.1", data=None, **kw):
    data = setup_bytes(version) if data is None else data
    return parse_and_verify(manifest_bytes(signed_fields(version, data=data, **kw)), make_config()), data


def _fake_downloader(data: bytes, *, fail=None):
    def download(cfg, url, dest, size, cancel, progress=None):
        if fail:
            raise fail
        with open(dest, "xb") as fh:
            fh.write(data)
        if progress:
            progress(type("P", (), {"received": len(data), "total": size})())
    return download


def _target(tmp_path, version="0.3.0", mode="user"):
    exe = _install(tmp_path / "インストール先" / "Monograph PDF")
    return install_target.InstallTarget(True, "", exe.parent, mode, version, "startmenu")


def test_download_is_verified_before_it_is_kept(tmp_path):
    rel, data = _release()
    sd = manager.download_and_verify(make_config(), rel, _target(tmp_path), threading.Event(),
                                     downloader=_fake_downloader(data))
    assert sd.installer.read_bytes() == data and not sd.partial.exists()
    marker = staging.read_marker(sd.path)
    assert marker["state"] == "verified" and marker["sha256"] == rel.artifact.sha256


@pytest.mark.parametrize("bad", ["modified", "short", "not_exe"])
def test_modified_or_damaged_downloads_are_deleted(tmp_path, bad):
    rel, data = _release()
    served = {"modified": data[:-1] + b"!", "short": data[:-10], "not_exe": b"ZZ" + data[2:]}[bad]
    if bad == "not_exe":  # a non-program with a signed checksum (manifest says so) is still refused
        rel, _ = _release(data=served)
    with pytest.raises(manager.UpdateError) as e:
        manager.download_and_verify(make_config(), rel, _target(tmp_path), threading.Event(),
                                    downloader=_fake_downloader(served))
    assert e.value.code == "verify"
    assert list(staging.staging_root().iterdir()) == []  # nothing left behind


def test_interrupted_and_cancelled_downloads_leave_nothing(tmp_path):
    from core.updates import net

    rel, data = _release()
    for err, code in ((net.NetworkError("cut", "network"), "network"), (net.Cancelled(), "cancelled"),
                      (net.NetworkError("slow", "timeout"), "timeout")):
        with pytest.raises(manager.UpdateError) as e:
            manager.download_and_verify(make_config(), rel, _target(tmp_path), threading.Event(),
                                        downloader=_fake_downloader(data, fail=err))
        assert e.value.code == code
    assert list(staging.staging_root().iterdir()) == []


def test_insufficient_disk_space_stops_before_downloading(tmp_path, monkeypatch):
    rel, data = _release()
    monkeypatch.setattr(staging, "has_space", lambda folder, needed: False)
    calls = []
    with pytest.raises(manager.UpdateError) as e:
        manager.download_and_verify(make_config(), rel, _target(tmp_path), threading.Event(),
                                    downloader=lambda *a, **k: calls.append(a))
    assert e.value.code == "disk_space" and calls == []


class _FakeProc:
    pid = 4242


def test_hand_off_writes_a_narrow_record_and_starts_the_staged_helper(tmp_path):
    rel, data = _release()
    target = _target(tmp_path)
    sd = manager.download_and_verify(make_config(), rel, target, threading.Event(), downloader=_fake_downloader(data))
    lock = staging.UpdateLock()
    assert lock.acquire()
    started = []

    def popen(args, **kw):
        started.append((args, kw))
        return _FakeProc()

    pid = manager.hand_off(sd, rel, target, lock, app_pid=777, popen=popen)
    assert pid == 4242
    args, kw = started[0]
    assert args == [str(sd.path / staging.HELPER_NAME), "--handoff", str(sd.path / "handoff.json")]
    assert "shell" not in kw and kw["cwd"] == str(sd.path)
    assert (sd.path / staging.HELPER_NAME).read_bytes() == (target.install_dir / staging.HELPER_NAME).read_bytes()
    h = json.loads((sd.path / "handoff.json").read_text(encoding="utf-8"))
    assert h["install_dir"] == str(target.install_dir) and "インストール先" in h["install_dir"]
    assert h["app_exe"] == str(target.install_dir / "MonographPDF.exe")
    assert h["install_mode"] == "user" and h["expected_version"] == "0.3.1" and h["previous_version"] == "0.3.0"
    assert h["installer_sha256"] == hashlib.sha256(data).hexdigest() and h["app_pid"] == 777
    assert Path(h["installer"]).parent == sd.path and Path(h["setup_log"]).parent == sd.path
    assert Path(h["result"]).parent == staging.updates_root()
    # only the fields the helper needs: no user data, no document names, no environment
    assert set(h) == {"schema", "update_id", "app_pid", "install_dir", "app_exe", "install_mode", "previous_version",
                      "expected_version", "installer", "installer_sha256", "installer_size", "staging_dir", "result",
                      "setup_log", "relaunch", "created"}
    assert staging.read_marker(sd.path)["state"] == "handed_off"
    assert json.loads(lock.path.read_text(encoding="utf-8"))["pid"] == 4242


def test_setup_is_run_with_the_existing_mode_and_folder():
    h = {"install_mode": "user", "install_dir": r"D:\ソフトウェア\Monograph PDF", "setup_log": r"C:\x\setup.log"}
    args = manager.setup_arguments(h)
    assert args == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER",
                    r"/DIR=D:\ソフトウェア\Monograph PDF", r"/LOG=C:\x\setup.log"]
    assert "/ALLUSERS" in manager.setup_arguments({**h, "install_mode": "machine"})


def test_helper_applies_the_same_switches():
    """The C# helper and manager.setup_arguments must agree (the helper is what really runs Setup)."""
    cs = (ROOT / "installer" / "update_helper.cs").read_text(encoding="utf-8")
    for switch in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", "/ALLUSERS",
                   '"/DIR=" + h.InstallDir', '"/LOG=" + h.SetupLog'):
        assert switch in cs
    # the helper never elevates itself, never uses a shell command line and verifies before running
    assert "runas" not in cs.lower() and "cmd.exe" not in cs.lower() and "powershell" not in cs.lower()
    assert cs.index("FileShare.Read") < cs.index("var setup = Process.Start(psi)")
    assert "SHA256.Create()" in cs and "RegisteredLocations(h.Mode)" in cs
    assert "Directory.Delete(h.StagingDir" not in cs  # never removes the staging folder recursively


def test_hand_off_refuses_downgrades_missing_helper_and_changed_installer(tmp_path):
    rel, data = _release()
    target = _target(tmp_path, version="0.3.1")
    sd = manager.download_and_verify(make_config(), rel, target, threading.Event(), downloader=_fake_downloader(data))
    lock = staging.UpdateLock()
    with pytest.raises(manager.UpdateError) as e:
        manager.hand_off(sd, rel, target, lock, popen=lambda *a, **k: _FakeProc())
    assert e.value.code == "not_permitted"
    target = _target(tmp_path, version="0.3.0")
    (target.install_dir / staging.HELPER_NAME).unlink()
    with pytest.raises(manager.UpdateError) as e:
        manager.hand_off(sd, rel, target, lock, popen=lambda *a, **k: _FakeProc())
    assert e.value.code == "helper_missing"
    (target.install_dir / staging.HELPER_NAME).write_bytes(b"MZ helper")
    sd.installer.write_bytes(b"MZ swapped after verification")
    with pytest.raises(manager.UpdateError) as e:
        manager.hand_off(sd, rel, target, lock, popen=lambda *a, **k: _FakeProc())
    assert e.value.code == "verify"
    bad_target = install_target.InstallTarget(False, "ambiguous")
    with pytest.raises(manager.UpdateError):
        manager.hand_off(sd, rel, bad_target, lock, popen=lambda *a, **k: _FakeProc())


def test_helper_results_are_read_from_the_updates_folder():
    root = staging.updates_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "result-0.3.1-0123456789ab.json").write_text(json.dumps({"schema": 1, "status": "installed",
                                                                    "expected_version": "0.3.1"}), encoding="utf-8")
    (root / "result-bad.json").write_text("{", encoding="utf-8")
    res = manager.read_results()
    assert [r["status"] for r in res] == ["installed"]
