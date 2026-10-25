"""Update checks, verified downloads and the hand-off to the update helper (no Qt here).

Flow after the user clicks Update Now::

    detect target installation -> download to the staging folder -> verify size + SHA-256 against
    the signed manifest (+ Authenticode when required) -> write handoff.json -> start the helper
    (a copy of MonographPDFUpdater.exe in the staging folder) -> the application exits.

The helper (installer/update_helper.cs) waits for the application to exit, verifies the installer
again while holding it locked, runs the existing Setup silently in upgrade mode for the same folder
and install mode, verifies the installed version, removes the staging files and starts the new
version. The running application never replaces its own files.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core.updates import authenticode, messages, net, staging
from core.updates.config import UpdateConfig
from core.updates.install_target import InstallTarget
from core.updates.manifest import ManifestError, ReleaseInfo, parse_and_verify
from core.updates.semver import parse as parse_version
from core.updates.state import UpdateState

DEFAULT_INSTALLED_SIZE = 700 * 1024**2


class UpdateStatus(str, enum.Enum):
    NOT_CONFIGURED = "not_configured"
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    UNAVAILABLE = "unable_to_check"
    VERIFICATION_FAILED = "verification_failed"

    @property
    def label(self) -> str:
        return {
            "not_configured": "Updates not configured",
            "checking": "Checking for updates…",
            "up_to_date": "Up to date",
            "available": "Update available",
            "unable_to_check": "Unable to check",
            "verification_failed": "Verification failed",
        }[self.value]


@dataclass
class CheckResult:
    status: UpdateStatus
    message: str
    installed: str
    release: ReleaseInfo | None = None
    checked_at: int = 0
    reason: str = ""   # why a check failed (messages.CHECK_REASONS key); "" otherwise
    detail: str = ""   # technical detail for diagnostics; not shown in the dialogs

    @property
    def title(self) -> str:
        from core.updates import messages

        return messages.check_text(self.reason)[0] if self.reason else self.status.label


class UpdateError(Exception):
    def __init__(self, message: str, code: str = "update_failed") -> None:
        super().__init__(message)
        self.code = code


# Platform-suffixed tags (v0.1.0-macos-1, v0.1.0-linux, …) are other OS lines in this repository.
# They must never be selected as Windows update candidates even if GitHub marks them Latest.
_PLATFORM_PRE_PREFIXES = ("macos", "linux", "darwin", "osx", "windows-arm", "win-arm")


def _tag_is_windows_line(tag_name: str, *, allow_prerelease: bool) -> bool:
    """True when ``tag_name`` is a Windows product-line version (not macOS/Linux)."""
    try:
        version = parse_version(str(tag_name))
    except ValueError:
        return False
    for part in version.prerelease:
        low = str(part).lower()
        if any(low == p or low.startswith(p + "-") or low.startswith(p + ".") for p in _PLATFORM_PRE_PREFIXES):
            return False
    if not allow_prerelease and version.is_prerelease:
        return False
    return True


def _manifest_url_from_release(config: UpdateConfig, rel: dict) -> str | None:
    for asset in rel.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("name") != config.manifest_asset:
            continue
        url = asset.get("browser_download_url")
        if isinstance(url, str) and config.host_allowed(url):
            return url
    return None


def _choose_from_listing(config: UpdateConfig, data: bytes, *, channel: str) -> str:
    """Newest non-draft GitHub release that publishes our Windows update manifest asset.

    The listing is only a discovery hint: authenticity comes from the Ed25519-signed manifest
    fetched next. GitHub's repository-wide Latest badge is never used (it may point at macOS or
    Linux). Drafts are ignored. Stable skips GitHub prereleases and platform-suffixed tags;
    the prerelease channel allows SemVer prereleases on the Windows line only.
    """
    try:
        releases = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise net.NetworkError("the release list could not be read", "http") from None
    if not isinstance(releases, list):
        raise net.NetworkError("the release list could not be read", "http")
    allow_pre = channel == "prerelease"
    best = None
    for rel in releases[:100]:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        if not allow_pre and rel.get("prerelease"):
            continue
        tag = str(rel.get("tag_name", ""))
        if not _tag_is_windows_line(tag, allow_prerelease=allow_pre):
            continue
        try:
            version = parse_version(tag)
        except ValueError:
            continue
        url = _manifest_url_from_release(config, rel)
        if url is None:
            continue
        if best is None or version > best[0]:
            best = (version, url)
    if best is None:
        raise net.NetworkError("no release with update information was found", "not_found")
    return best[1]


def check(config: UpdateConfig, channel: str, installed: str, state: UpdateState, *,
          fetch: Callable[..., bytes] = net.fetch_bytes, now: datetime | None = None) -> CheckResult:
    """One update check. Never reports "up to date" unless a verified manifest said so."""
    stamp = int(time.time())
    if not config.usable:
        return CheckResult(UpdateStatus.NOT_CONFIGURED, config.disabled_reason or
                           "Automatic updates are not configured for this build.", installed, checked_at=stamp)
    try:
        listing = fetch(config, config.releases_api_url, config.max_listing_bytes, "application/vnd.github+json")
        url = _choose_from_listing(config, listing, channel=channel)
        data = fetch(config, url, config.max_manifest_bytes)
    except net.NetworkError as exc:
        state.last_check, state.last_status = stamp, UpdateStatus.UNAVAILABLE.value
        return CheckResult(UpdateStatus.UNAVAILABLE, messages.check_text(exc.kind)[1], installed, checked_at=stamp,
                           reason=exc.kind, detail=str(exc))
    try:
        release = parse_and_verify(data, config, now=now)
        if channel != "prerelease" and release.channel != "stable":
            raise ManifestError("a prerelease was offered on the stable channel", "channel")
        seen = int(state.sequence.get(release.channel, 0) or 0)
        if release.sequence < seen:
            raise ManifestError("the update information is older than information already seen "
                                "(possible replay of outdated metadata)", "rollback")
    except ManifestError as exc:
        state.last_check, state.last_status = stamp, UpdateStatus.VERIFICATION_FAILED.value
        return CheckResult(UpdateStatus.VERIFICATION_FAILED, messages.check_text(exc.code)[1], installed,
                           checked_at=stamp, reason=exc.code, detail=str(exc))
    state.sequence[release.channel] = max(seen, release.sequence)
    state.last_check = state.last_success = stamp
    state.latest_version = str(release.version)
    if release.version > parse_version(installed):
        state.last_status = UpdateStatus.AVAILABLE.value
        return CheckResult(UpdateStatus.AVAILABLE, f"Monograph PDF {release.version} is available.",
                           installed, release, stamp)
    state.last_status = UpdateStatus.UP_TO_DATE.value
    return CheckResult(UpdateStatus.UP_TO_DATE, f"Monograph PDF {installed} is the newest version. No update is "
                       "available.", installed, release, stamp)


def install_permitted(release: ReleaseInfo, installed: str) -> str:
    """'' when an automatic upgrade from ``installed`` to ``release`` is allowed, else the reason."""
    current = parse_version(installed)
    if not release.version > current:
        return "The offered version is not newer than the installed version (downgrades are refused)."
    if release.min_upgrade_from is not None and current < release.min_upgrade_from:
        return (f"Version {release.version} cannot be installed automatically over {installed}; "
                "install it with Setup from the release page.")
    return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download_and_verify(config: UpdateConfig, release: ReleaseInfo, target: InstallTarget, cancel: threading.Event,
                        progress: Callable[[str, int, int], None] | None = None, *,
                        downloader: Callable[..., None] = net.download) -> staging.StagingDir:
    """Download Setup into a new staging folder and verify it. On any failure the partial files
    are removed and UpdateError is raised; the installed application is untouched."""
    a = release.artifact
    if not staging.has_space(staging.updates_root(), a.size):
        raise UpdateError("There is not enough free disk space to download the update.", "disk_space")
    if target.install_dir is not None and not staging.has_space(target.install_dir, release.installed_size or DEFAULT_INSTALLED_SIZE):
        raise UpdateError("There is not enough free disk space on the installation drive for the update.", "disk_space")
    sd = staging.new_staging(str(release.version))
    try:
        sd.set_state("downloading")
        report = (lambda p: progress("downloading", p.received, p.total)) if progress else None
        downloader(config, a.url, sd.partial, a.size, cancel, report)
        if progress:
            progress("verifying", a.size, a.size)
        if cancel.is_set():
            raise net.Cancelled()
        if sd.partial.stat().st_size != a.size or sha256_file(sd.partial) != a.sha256:
            raise UpdateError("The downloaded installer does not match the signed update information "
                              "(it may be damaged or modified). It was deleted.", "verify")
        with open(sd.partial, "rb") as fh:
            if fh.read(2) != b"MZ":
                raise UpdateError("The downloaded file is not a Windows program. It was deleted.", "verify")
        os.replace(sd.partial, sd.installer)
        sig = authenticode.check(sd.installer)
        if config.require_authenticode and sig != authenticode.VALID:
            raise UpdateError(f"The installer's Windows signature check failed ({sig}). It was deleted.", "verify")
        sd.set_state("verified", sha256=a.sha256, authenticode=sig)
        return sd
    except net.Cancelled:
        staging.remove_staging(sd.path)
        raise UpdateError("The update was cancelled.", "cancelled") from None
    except net.NetworkError as exc:
        staging.remove_staging(sd.path)
        raise UpdateError(f"The download failed: {exc}.", exc.kind) from None
    except UpdateError:
        staging.remove_staging(sd.path)
        raise
    except OSError as exc:
        staging.remove_staging(sd.path)
        raise UpdateError(f"The update could not be saved ({type(exc).__name__}).", "io") from None


def build_handoff(sd: staging.StagingDir, release: ReleaseInfo, target: InstallTarget, app_pid: int) -> dict:
    return {
        "schema": 1,
        "update_id": sd.update_id,
        "app_pid": app_pid,
        "install_dir": str(target.install_dir),
        "app_exe": str(target.exe),
        "install_mode": target.mode,
        "previous_version": target.version,
        "expected_version": str(release.version),
        "installer": str(sd.installer),
        "installer_sha256": release.artifact.sha256,
        "installer_size": release.artifact.size,
        "staging_dir": str(sd.path),
        "result": str(staging.updates_root() / f"result-{sd.update_id}.json"),
        "setup_log": str(sd.path / "setup.log"),
        "relaunch": True,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def setup_arguments(handoff: dict) -> list[str]:
    """The documented Inno Setup upgrade switches the helper uses (kept here for tests and docs).

    /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- : unattended, no restart without the user
    /CURRENTUSER or /ALLUSERS                     : the existing installation's mode
    /DIR=<folder>                                 : the existing installation folder
    /LOG=<file>                                   : Setup's log in the staging folder
    Previously chosen tasks (shortcuts, file types) are kept by Setup (UsePreviousTasks=yes).
    """
    mode = "/CURRENTUSER" if handoff["install_mode"] == "user" else "/ALLUSERS"
    return ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", mode,
            f"/DIR={handoff['install_dir']}", f"/LOG={handoff['setup_log']}"]


def hand_off(sd: staging.StagingDir, release: ReleaseInfo, target: InstallTarget, lock: staging.UpdateLock, *,
             app_pid: int | None = None, popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> int:
    """Copy the helper into the staging folder, write handoff.json and start the helper.

    Returns the helper's process id. The caller must then exit the application.
    """
    if not target.ok or target.install_dir is None:
        raise UpdateError(target.reason or "No installation to update.", "target")
    reason = install_permitted(release, target.version or "0.0.0")
    if reason:
        raise UpdateError(reason, "not_permitted")
    source = target.install_dir / staging.HELPER_NAME
    if not source.is_file():
        raise UpdateError("The update helper is missing from this installation; reinstall Monograph PDF "
                          "with Setup from the release page.", "helper_missing")
    helper = sd.path / staging.HELPER_NAME
    shutil.copyfile(source, helper)
    if sha256_file(helper) != sha256_file(source):
        raise UpdateError("The update helper could not be prepared.", "helper_copy")
    if sha256_file(sd.installer) != release.artifact.sha256:
        raise UpdateError("The staged installer changed after verification; the update was stopped.", "verify")
    handoff = build_handoff(sd, release, target, os.getpid() if app_pid is None else app_pid)
    path = sd.path / "handoff.json"
    path.write_text(json.dumps(handoff, indent=1, ensure_ascii=False), encoding="utf-8")
    flags = 0
    if sys.platform.startswith("win"):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
    try:
        proc = popen([str(helper), "--handoff", str(path)], cwd=str(sd.path), close_fds=True, creationflags=flags)
    except OSError:
        try:
            proc = popen([str(helper), "--handoff", str(path)], cwd=str(sd.path), close_fds=True,
                         creationflags=flags & ~0x01000000)
        except OSError as exc:
            raise UpdateError(f"The update helper could not be started ({type(exc).__name__}).", "helper_start") from None
    sd.set_state("handed_off", helper_pid=proc.pid)
    lock.transfer_to(proc.pid)
    return proc.pid


def read_results() -> list[dict]:
    """Results the helper wrote since the user last saw them (newest last)."""
    out = []
    root = staging.updates_root()
    for f in sorted(root.glob("result-*.json")):
        if staging.is_link(f):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("schema") == 1:
            data["_file"] = f.name
            out.append(data)
    return out
