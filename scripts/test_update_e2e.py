"""Windows end-to-end test of the automatic in-place upgrade, against the current commit.

    env\\Scripts\\python.exe scripts\\test_update_e2e.py --certs <folder> [--old 0.3.0] [--new 0.3.1] [--keep]

What it does (nothing is published; no existing installation, release artifact or setting is changed
for good):

1. Exports the current commit (``git archive HEAD``) twice, sets VERSION to ``--old`` and ``--new``,
   and builds both with ``scripts\\build_exe.ps1 -UpdateConfig`` — a TEST update configuration
   trusting a synthetic Ed25519 key and a local HTTPS mock server (127.0.0.1, test CA from
   ``--certs``: test-ca.pem, server.pem, server-key.pem) — plus uninstall.exe, MonographPDFUpdater.exe
   and Setup.exe for each version (under build\\e2e).
2. Signs a manifest for the new Setup with the synthetic key (stored in %TEMP%, deleted afterwards)
   and serves both from the mock server.
3. Backs up the current user's Monograph PDF settings and working folders, then installs the old
   test version PER USER into ``build\\e2e\\ソフトウェア\\Monograph PDF`` with non-default choices
   (desktop shortcut on, Open-with for other file types off).
4. Adds a user file and an obsolete owned file, starts the installed program, runs the update check,
   download, verification and hand-off exactly as Update Now does (core.updates), closes the program
   and lets the real helper run the real Setup.
5. Verifies: result file, registered and program versions, same folder and mode, no second
   installation, kept choices (desktop shortcut, .pdf registration, no other-type registration),
   kept settings and recent files, kept user file, removed obsolete file, removed installer and
   staging files, relaunch of the new version, and cleanup after the relaunch.
6. Failure paths through the real helper: a signed but modified download (refused before any change),
   an untrusted signature, the server offline, and a signed "installer" that fails (exit code 4):
   the previous version stays installed and is restarted, the installer is kept for a retry.
7. Uninstalls the test installation and restores the backed-up folders and shortcuts.

Results: build\\e2e\\update_e2e_report.json (PASS / FAIL per check).
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import winreg
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.updates import config as update_config  # noqa: E402
from core.updates import install_target, manager, staging  # noqa: E402
from core.updates.manager import UpdateStatus  # noqa: E402
from core.updates.state import UpdateState  # noqa: E402

E2E = ROOT / "build" / "e2e"
PORT = 48443
BASE = f"https://127.0.0.1:{PORT}"
APP_FOLDER = E2E / "ソフトウェア" / "Monograph PDF"
UNINST = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + update_config.INNO_APP_ID + "_is1"
APPDATA = Path(os.environ["APPDATA"]) / "Monograph PDF"
LOCALDATA = Path(os.environ["LOCALAPPDATA"]) / "Monograph PDF"
def _desktop() -> Path:
    # the real Desktop folder (it may be redirected, e.g. to OneDrive)
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    return Path(out) if out else Path(os.environ["USERPROFILE"]) / "Desktop"


DESKTOP_LNK = _desktop() / "Monograph PDF.lnk"
START_GROUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Monograph PDF"

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 3600) -> int:
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, timeout=timeout).returncode


# ------------------------------------------------------------------ build


def _tool(cands: list[Path]) -> Path:
    for c in cands:
        if c.is_file():
            return c
    raise SystemExit(f"missing tool: {cands[0].name}")


def iscc() -> Path:
    return _tool([ROOT / "tools" / "inno" / "ISCC.exe",
                  Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                  Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
                  Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"])


def csc() -> Path:
    win = Path(os.environ["WINDIR"])
    return _tool([win / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
                  win / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe"])


def export_source(version: str) -> Path:
    src = E2E / f"src-{version}"
    if src.exists():
        junction = src / "env"
        if junction.exists():
            os.rmdir(junction)  # removes the junction only
        shutil.rmtree(src)
    src.mkdir(parents=True)
    archive = E2E / f"head-{version}.zip"
    if run(["git", "-C", str(ROOT), "archive", "--format=zip", "-o", str(archive), "HEAD"]) != 0:
        raise SystemExit("git archive failed")
    with zipfile.ZipFile(archive) as z:
        z.extractall(src)
    archive.unlink()
    (src / "VERSION").write_text(version + "\n", encoding="utf-8")
    run(["cmd", "/c", "mklink", "/J", str(src / "env"), str(ROOT / "env")])
    for side in ("engines/ocr", "models/tessdata"):
        dst = src / side
        dst.mkdir(parents=True, exist_ok=True)
        for f in (ROOT / side).iterdir():
            if f.is_file() and f.name != ".gitkeep":
                shutil.copy2(f, dst / f.name)
    return src


def build_version(version: str, config_dir: Path) -> Path:
    src = export_source(version)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.environ["MONOGRAPH_PDF_BUILD_COMMIT"] = head  # the export has no .git folder
    os.environ["SOURCE_DATE_EPOCH"] = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct"],
                                                     capture_output=True, text=True).stdout.strip()
    if run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(src / "scripts" / "build_exe.ps1"),
            "-UpdateConfig", str(config_dir)], cwd=src) != 0:
        raise SystemExit(f"build_exe failed for {version}")
    payload = src / "dist" / "MonographPDF"
    bi = src / "build" / "installer"
    bi.mkdir(parents=True, exist_ok=True)
    numeric = version.split("-")[0] + ".0"
    (bi / "uninstall_buildinfo.cs").write_text(
        f'namespace MonographPdfUninstall {{ internal static class BuildInfo {{ public const string Version = "{numeric}"; '
        f'public const string ProductVersion = "{version}"; }} }}')
    (bi / "updater_buildinfo.cs").write_text(
        f'namespace MonographPdfUpdater {{ internal static class BuildInfo {{ public const string Version = "{numeric}"; '
        f'public const string ProductVersion = "{version}"; }} }}')
    if run([str(csc()), "/nologo", "/target:winexe", "/optimize+", f"/out:{bi / 'uninstall.exe'}",
            "/reference:System.Windows.Forms.dll", str(src / "installer" / "uninstall_launcher.cs"),
            str(bi / "uninstall_buildinfo.cs")]) != 0:
        raise SystemExit("csc uninstall.exe failed")
    if run([str(csc()), "/nologo", "/target:winexe", "/optimize+", f"/out:{bi / 'MonographPDFUpdater.exe'}",
            "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Web.Extensions.dll",
            str(src / "installer" / "update_helper.cs"), str(bi / "updater_buildinfo.cs")]) != 0:
        raise SystemExit("csc MonographPDFUpdater.exe failed")
    py = str(ROOT / "env" / "Scripts" / "python.exe")
    if run([py, str(src / "scripts" / "packaging" / "write_installed_manifest.py"), "--payload", str(payload),
            "--out", str(bi / "installed_files.txt")], cwd=src) != 0:
        raise SystemExit("installed manifest failed")
    shutil.copyfile(src / "LICENSE.md", bi / "LICENSE.txt")
    out = E2E / "out"
    out.mkdir(exist_ok=True)
    if run([str(iscc()), "/Q", f"/DAppVersion={version}", f"/DPayloadDir={payload}", f"/DUninstallExe={bi / 'uninstall.exe'}",
            f"/DUpdaterExe={bi / 'MonographPDFUpdater.exe'}", f"/DInstalledManifest={bi / 'installed_files.txt'}",
            f"/DOutputDirectory={out}", str(src / "installer" / "MonographPDF.iss")]) != 0:
        raise SystemExit("ISCC failed")
    return out / f"MonographPDF_{version}_Setup.exe"


def fake_failing_setup(version: str) -> Path:
    """A tiny program named like Setup that changes nothing and exits with Inno Setup's code 4."""
    cs = E2E / "failing_setup.cs"
    cs.write_text("static class P { static int Main() { return 4; } }", encoding="utf-8")
    # kept apart from the real test builds in out/ (it has no version resource by design)
    (E2E / "fake").mkdir(parents=True, exist_ok=True)
    exe = E2E / "fake" / f"MonographPDF_{version}_Setup.exe"
    if run([str(csc()), "/nologo", "/target:winexe", f"/out:{exe}", str(cs)]) != 0:
        raise SystemExit("csc failing setup failed")
    return exe


# ------------------------------------------------------------------ mock server


class Routes(http.server.BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}

    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        # Releases API pagination appends ?page=&per_page=; match on path only.
        path = self.path.split("?", 1)[0]
        data = self.files.get(path) or self.files.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_server(certs: Path) -> http.server.ThreadingHTTPServer:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Routes)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certs / "server.pem", certs / "server-key.pem")
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_config(certs: Path, key_hex: str) -> Path:
    folder = E2E / "update-config"
    folder.mkdir(parents=True, exist_ok=True)
    pub = bytes.fromhex(key_hex)
    cfg = json.loads((ROOT / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    cfg.update(enabled=True, disabled_reason="", allowed_hosts=["127.0.0.1"],
               stable_manifest_url="",  # discovery uses Releases API only (never Latest)
               releases_api_url=f"{BASE}/api/releases",
               trusted_keys=[{"keyid": update_config.key_id(pub), "public_key": key_hex}], ca_file="test-ca.pem")
    (folder / "update_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    shutil.copyfile(certs / "test-ca.pem", folder / "test-ca.pem")
    return folder


def sign(setup: Path, key_file: Path, sequence: int, out: Path) -> bytes:
    py = str(ROOT / "env" / "Scripts" / "python.exe")
    rc = run([py, str(ROOT / "scripts" / "packaging" / "update_manifest.py"), "make", "--setup", str(setup),
              "--channel", "stable", "--sequence", str(sequence), "--key", str(key_file), "--out", str(out),
              "--download-base", f"{BASE}/download", "--config", str(E2E / "update-config" / "update_config.json")])
    if rc != 0:
        raise SystemExit("manifest signing failed")
    return out.read_bytes()


# ------------------------------------------------------------------ Windows state


def hkcu_registration() -> dict | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST) as k:
            out = {}
            for name in ("InstallLocation", "DisplayVersion", "Inno Setup: Selected Tasks"):
                try:
                    out[name] = winreg.QueryValueEx(k, name)[0]
                except OSError:
                    out[name] = None
            return out
    except OSError:
        return None


def hkcu_key_exists(sub: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub))
        return True
    except OSError:
        return False


def pdf_openwith_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithProgids") as k:
            winreg.QueryValueEx(k, "MonographPDF.Document")
            return True
    except OSError:
        return False


def processes_in(folder: Path) -> list[int]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='MonographPDF.exe'\" | "
          "Select-Object ProcessId, ExecutablePath | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, encoding="utf-8").stdout
    if not out.strip():
        return []
    items = json.loads(out)
    items = items if isinstance(items, list) else [items]
    key = install_target.norm(folder)
    return [i["ProcessId"] for i in items if i.get("ExecutablePath") and install_target.norm(Path(i["ExecutablePath"]).parent) == key]


def uninstaller_running() -> bool:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower()
    return '"_iu' in out or '"unins000.exe"' in out


def file_version(exe: Path) -> str:
    ps = f"(Get-Item -LiteralPath '{exe}').VersionInfo.ProductVersion"
    return subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def close_app(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)  # WM_CLOSE, not /F
    for _ in range(60):
        if not staging.pid_alive(pid):
            return
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def wait_for(pred, timeout: float, step: float = 1.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def backup_user_state(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    saved = {}
    for name, src in (("appdata", APPDATA), ("localdata", LOCALDATA)):
        if src.exists():
            shutil.copytree(src, folder / name, symlinks=True)
            saved[name] = True
    if DESKTOP_LNK.exists():
        shutil.copy2(DESKTOP_LNK, folder / "desktop.lnk")
        saved["desktop"] = True
    saved["start_group_existed"] = START_GROUP.exists()
    return saved


def restore_user_state(folder: Path, saved: dict) -> None:
    for name, dst in (("appdata", APPDATA), ("localdata", LOCALDATA)):
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        if saved.get(name):
            shutil.copytree(folder / name, dst, symlinks=True)
    if saved.get("desktop"):
        shutil.copy2(folder / "desktop.lnk", DESKTOP_LNK)
    elif DESKTOP_LNK.exists():
        DESKTOP_LNK.unlink()


def tree_digest(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()} if folder.exists() else {}


# ------------------------------------------------------------------ the test


def setup_args(setup: Path, log: Path, tasks: str | None = None) -> list[str]:
    args = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER",
            f"/DIR={APP_FOLDER}", f"/LOG={log}"]
    if tasks is not None:
        args.append(f"/TASKS={tasks}")
    return args


HELPERS: list[subprocess.Popen] = []


def quiet_popen(args, **kw):
    proc = subprocess.Popen(list(args) + ["--quiet"], **kw)
    HELPERS.append(proc)
    return proc


def update_once(cfg, app_pid: int, expected: str) -> dict | None:
    state = UpdateState.load()
    res = manager.check(cfg, "stable", hkcu_registration()["DisplayVersion"], state)
    state.save()
    if not check(f"check finds {expected}", res.status == UpdateStatus.AVAILABLE and str(res.release.version) == expected,
                 f"{res.status.value}: {res.message}"):
        return None
    target = install_target.detect(APP_FOLDER / "MonographPDF.exe")
    check("target is the registered per-user installation", target.ok and target.mode == "user"
          and install_target.norm(target.install_dir) == install_target.norm(APP_FOLDER), target.reason)
    lock = staging.UpdateLock()
    check("update lock acquired", lock.acquire())
    sd = manager.download_and_verify(cfg, res.release, target, threading.Event())
    check("download verified in the staging folder", sd.installer.is_file() and
          manager.sha256_file(sd.installer) == res.release.artifact.sha256, str(sd.path.parent))
    helper_pid = manager.hand_off(sd, res.release, target, lock, app_pid=app_pid, popen=quiet_popen)
    check("helper started from the staging folder", helper_pid > 0)
    time.sleep(2)
    close_app(app_pid)  # in the application this is close_for_update()
    # The relaunched program reads and deletes the result file within seconds, so it is polled
    # closely and the helper's exit code (0 installed, 5 failed) is used as well.
    result = staging.updates_root() / f"result-{sd.update_id}.json"
    proc = HELPERS[-1]
    data: dict = {}
    end = time.time() + 900
    while time.time() < end:
        if result.is_file():
            try:
                data = json.loads(result.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if not check("helper finished", proc.poll() is not None, f"exit {proc.returncode}"):
        return None
    if result.is_file():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    check("helper result file written", bool(data), json.dumps(data))
    data["_sd"] = sd
    data["_helper_pid"] = helper_pid
    data["_exit"] = proc.returncode
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--certs", type=Path, required=True)
    ap.add_argument("--old", default="0.3.0")
    ap.add_argument("--new", default="0.3.1")
    ap.add_argument("--fail", default="0.3.2")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the test installation")
    a = ap.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("Windows only")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD"]).returncode != 0:
        print("note: uncommitted changes are NOT part of the test builds (git archive HEAD)")
    if hkcu_registration() is not None:
        raise SystemExit("A per-user Monograph PDF installation is registered for this user; not touching it.")
    E2E.mkdir(parents=True, exist_ok=True)

    keys = Path(tempfile.mkdtemp(prefix="monographpdf-e2e-keys-"))
    py = str(ROOT / "env" / "Scripts" / "python.exe")
    out = subprocess.run([py, str(ROOT / "scripts" / "packaging" / "update_manifest.py"), "keygen", "--plaintext-test-key", "--out", str(keys)],
                         capture_output=True, text=True, check=True).stdout
    key_hex = json.loads(out)["public_key"]
    key_file = keys / "update-signing.key"
    cfg_dir = test_config(a.certs, key_hex)
    cfg = update_config.load(cfg_dir / "update_config.json")

    print("== build", flush=True)
    t0 = time.time()
    if a.skip_build:
        old_setup = E2E / "out" / f"MonographPDF_{a.old}_Setup.exe"
        new_setup = E2E / "out" / f"MonographPDF_{a.new}_Setup.exe"
    else:
        old_setup = build_version(a.old, cfg_dir)
        new_setup = build_version(a.new, cfg_dir)
    failing = fake_failing_setup(a.fail)
    check("test builds ready", old_setup.is_file() and new_setup.is_file(), f"{int(time.time() - t0)} s")

    manifest_new = sign(new_setup, key_file, 10, E2E / "manifest-new.json")
    manifest_fail = sign(failing, key_file, 11, E2E / "manifest-fail.json")
    good = new_setup.read_bytes()
    asset = "MonographPDF_update_manifest.json"

    def listing_for(version: str) -> bytes:
        # Include a macOS "Latest"-style decoy first — Windows discovery must ignore it.
        return json.dumps([
            {"tag_name": "v0.1.0-macos-1", "draft": False, "prerelease": False,
             "assets": [{"name": asset, "browser_download_url": f"{BASE}/download/v0.1.0-macos-1/{asset}"}]},
            {"tag_name": f"v{version}", "draft": False, "prerelease": False,
             "assets": [{"name": asset, "browser_download_url": f"{BASE}/download/v{version}/{asset}"}]},
        ]).encode()

    Routes.files = {
        "/api/releases": listing_for(a.new),
        f"/download/v{a.new}/{asset}": manifest_new,
        f"/download/v{a.new}/{new_setup.name}": good,
        f"/download/v{a.fail}/{failing.name}": failing.read_bytes(),
    }
    httpd = start_server(a.certs)

    backup = E2E / "backup"
    if backup.exists():
        raise SystemExit(f"{backup} exists from an interrupted run: restore it first")
    saved = backup_user_state(backup)
    before = {"appdata": tree_digest(APPDATA), "localdata": tree_digest(LOCALDATA)}
    installed = False
    had_default_user = (Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Monograph PDF" / "MonographPDF.exe").exists()
    try:
        print("== install old version (per user, Unicode folder)", flush=True)
        log1 = E2E / "setup-old.log"
        rc = run(setup_args(old_setup, log1, "startmenu,desktopicon,assocpdf"), timeout=900)
        installed = True
        reg = hkcu_registration()
        check("old version installed per user", rc == 0 and reg and reg["DisplayVersion"] == a.old, f"exit {rc}, {reg}")
        tasks_before = reg and reg["Inno Setup: Selected Tasks"]
        check("desktop shortcut created by the first installation", DESKTOP_LNK.exists(), str(DESKTOP_LNK))
        check("non-default choices recorded", tasks_before is not None and "desktopicon" in tasks_before
              and "assocother" not in tasks_before, str(tasks_before))

        # user data written after the first install (a new install starts with an empty recent list)
        APPDATA.mkdir(parents=True, exist_ok=True)
        prefs = {"theme": "dark", "recent_limit": 7, "highlight_color": "#00ff00", "update_channel": "stable"}
        (APPDATA / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
        sample = E2E / "研究データ" / "実験結果.pdf"
        sample.parent.mkdir(parents=True, exist_ok=True)
        import fitz

        d = fitz.open()
        d.new_page().insert_text((72, 72), "e2e")
        d.save(sample)
        d.close()
        (APPDATA / "recent_files.json").write_text(json.dumps([str(sample)]), encoding="utf-8")
        user_file = APP_FOLDER / "my notes.txt"
        user_file.write_text("keep me", encoding="utf-8")
        obsolete = APP_FOLDER / "docs" / "OBSOLETE_TEST_NOTE.md"
        obsolete.write_text("owned by the previous version", encoding="utf-8")
        with open(APP_FOLDER / "installed_files.txt", "a", encoding="utf-8") as fh:
            fh.write("\ndocs/OBSOLETE_TEST_NOTE.md\n")

        print("== failure paths before the upgrade", flush=True)
        # signed manifest, but the server serves different bytes
        Routes.files[f"/download/v{a.new}/{new_setup.name}"] = good[:-1] + bytes([good[-1] ^ 1])
        res = manager.check(cfg, "stable", a.old, UpdateState())
        if not check("signed manifest accepted by the test configuration", res.release is not None, res.message):
            raise SystemExit("cannot continue without a verified manifest")
        try:
            manager.download_and_verify(cfg, res.release, install_target.detect(APP_FOLDER / "MonographPDF.exe"),
                                        threading.Event())
            check("modified download refused", False)
        except manager.UpdateError as exc:
            check("modified download refused", exc.code == "verify", str(exc))
        check("nothing left in staging after the refused download",
              not staging.staging_root().exists() or not any(staging.staging_root().iterdir()))
        Routes.files[f"/download/v{a.new}/{new_setup.name}"] = good
        # manifest signed by an untrusted key
        other = update_config.UpdateConfig(**{**cfg.__dict__, "trusted_keys": {"0" * 16: bytes(32)}})
        check("untrusted signature refused", manager.check(other, "stable", a.old, UpdateState()).status
              == UpdateStatus.VERIFICATION_FAILED)
        httpd.shutdown()
        httpd.server_close()
        offline = manager.check(cfg, "stable", a.old, UpdateState())
        check("server offline: 'Unable to check', not 'Up to date'", offline.status == UpdateStatus.UNAVAILABLE,
              offline.message)
        httpd = start_server(a.certs)
        check("installed version unchanged by the failures", hkcu_registration()["DisplayVersion"] == a.old)

        print("== upgrade through the update helper", flush=True)
        app = subprocess.Popen([str(APP_FOLDER / "MonographPDF.exe")], cwd=str(APP_FOLDER))
        time.sleep(10)
        check("old version running", app.poll() is None)
        t1 = time.time()
        result = update_once(cfg, app.pid, a.new)
        if result:
            check("helper result: installed (exit 0)", result.get("status") == "installed" and result["_exit"] == 0, json.dumps({k: v for k, v in result.items() if not k.startswith('_')}))
            reg = hkcu_registration()
            check("registered version is the new one", reg["DisplayVersion"] == a.new, reg["DisplayVersion"])
            default_user = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Monograph PDF" / "MonographPDF.exe"
            same_folder = install_target.norm(reg["InstallLocation"]) == install_target.norm(APP_FOLDER)
            no_copy_in_default = had_default_user or not default_user.exists()
            check("same folder and mode (no second installation)", same_folder and no_copy_in_default,
                  reg["InstallLocation"])
            check("program file version is the new one", file_version(APP_FOLDER / "MonographPDF.exe") == a.new)
            check("previous choices kept", reg["Inno Setup: Selected Tasks"] == tasks_before, str(reg["Inno Setup: Selected Tasks"]))
            check("desktop shortcut kept", DESKTOP_LNK.exists())
            check(".pdf Open-with registration kept", pdf_openwith_registered())
            check("other file types still not registered", not hkcu_key_exists(r"Software\Classes\MonographPDF.Convertible"))
            check("user file in the installation folder kept", user_file.read_text(encoding="utf-8") == "keep me")
            check("obsolete owned file removed", not obsolete.exists())
            check("update helper installed", (APP_FOLDER / staging.HELPER_NAME).is_file())
            kept = json.loads((APPDATA / "preferences.json").read_text(encoding="utf-8"))
            check("settings kept", all(kept.get(k) == v for k, v in prefs.items()), json.dumps({k: kept.get(k) for k in prefs}))
            recent = json.loads((APPDATA / "recent_files.json").read_text(encoding="utf-8"))
            check("recent files kept", str(sample) in recent, json.dumps(recent, ensure_ascii=False))
            sd = result["_sd"]
            check("installer and hand-off removed after success",
                  not sd.installer.exists() and not (sd.path / "handoff.json").exists() and not (sd.path / "setup.log").exists())
            check("new version relaunched", result.get("relaunched") is True and wait_for(lambda: processes_in(APP_FOLDER), 60))
            print(f"  upgrade took {int(time.time() - t1)} s", flush=True)
            # the relaunched program removes the helper copy, the marker and the result file
            check("staging folder removed after the relaunch", wait_for(lambda: not sd.path.exists(), 90, 3))
            check("result consumed by the new version", wait_for(
                lambda: not (staging.updates_root() / f"result-{sd.update_id}.json").exists(), 60, 2))
            for pid in processes_in(APP_FOLDER):
                close_app(pid)

            print("== a signed installer that fails", flush=True)
            Routes.files["/api/releases"] = listing_for(a.fail)
            Routes.files[f"/download/v{a.fail}/{asset}"] = manifest_fail
            app = subprocess.Popen([str(APP_FOLDER / "MonographPDF.exe")], cwd=str(APP_FOLDER))
            time.sleep(10)
            failed = update_once(cfg, app.pid, a.fail)
            if failed:
                check("helper result: failed with Setup's exit code (exit 5)", failed.get("status") == "failed"
                      and failed.get("code") == "setup_exit_4" and failed["_exit"] == 5,
                      f"{failed.get('status')} {failed.get('code')} exit {failed['_exit']}")
                check("previous version still installed", hkcu_registration()["DisplayVersion"] == a.new
                      and file_version(APP_FOLDER / "MonographPDF.exe") == a.new)
                fsd = failed["_sd"]
                check("installer and Setup log kept for a retry, hand-off removed",
                      fsd.installer.exists() and not (fsd.path / "handoff.json").exists())
                check("previous version restarted", failed.get("relaunched") is True and wait_for(lambda: processes_in(APP_FOLDER), 60))
                for pid in processes_in(APP_FOLDER):
                    close_app(pid)
    finally:
        httpd.shutdown()
        for pid in processes_in(APP_FOLDER):
            close_app(pid)
        if installed and not a.keep:
            print("== uninstall and restore", flush=True)
            unins = APP_FOLDER / "uninstall.exe"
            if unins.exists():
                ulog = E2E / "uninstall.log"
                ulog.unlink(missing_ok=True)
                rc = run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/REMOVEUSERDATA",
                          f"/LOG={ulog}"], timeout=600)
                # uninstall.exe returns before Inno Setup's second phase (a copy in %TEMP%) has removed
                # this user's data; restoring earlier would be undone by it. Wait for its log to close.
                done = wait_for(lambda: ulog.is_file() and "Log closed." in ulog.read_text(encoding="utf-8", errors="replace"),
                                300, 0.5)
                wait_for(lambda: not uninstaller_running(), 120, 0.5)
                check("test installation uninstalled", hkcu_registration() is None and done, f"exit {rc}")
                check("user file left in place by the uninstaller", (APP_FOLDER / "my notes.txt").exists())
            shutil.rmtree(APP_FOLDER.parent, ignore_errors=True)
        restore_user_state(backup, saved)
        time.sleep(15)  # nothing may remove the restored folders afterwards
        restored = tree_digest(APPDATA) == before["appdata"] and tree_digest(LOCALDATA) == before["localdata"]
        if check("user settings and working files restored exactly (and still there 15 s later)", restored):
            shutil.rmtree(backup, ignore_errors=True)
        else:
            print(f"  the backup is kept at {backup}; restore it before running the test again")
        shutil.rmtree(keys, ignore_errors=True)
        report = E2E / "update_e2e_report.json"
        report.write_text(json.dumps(CHECKS, indent=1, ensure_ascii=False), encoding="utf-8")
    failed_checks = [c for c in CHECKS if c["result"] == "FAIL"]
    print(f"RESULT: {len(CHECKS) - len(failed_checks)} passed, {len(failed_checks)} failed")
    return 1 if failed_checks else 0


if __name__ == "__main__":
    sys.exit(main())
