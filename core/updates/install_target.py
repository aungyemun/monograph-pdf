"""Which installation an automatic update may modify — decided before anything is downloaded.

The running program must be the installation Setup registered: its folder must hold Setup's
uninstaller and must equal the ``InstallLocation`` of Monograph PDF's uninstall entry (Inno Setup
AppId) in exactly one registry hive. HKCU means a per-user installation (no administrator rights);
HKLM means an all-users installation (Windows asks for administrator approval). Anything else —
a portable or development copy, an unregistered copy, or the same folder registered twice — is
ambiguous, and automatic installation stops with an explanation instead of guessing.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.product_meta import WINDOWS_EXECUTABLE_NAME
from core.updates.config import INNO_APP_ID

UNINSTALL_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + INNO_APP_ID + "_is1"


@dataclass(frozen=True)
class Registration:
    hive: str             # "HKCU" | "HKLM64" | "HKLM32"
    install_dir: str
    version: str
    tasks: str


@dataclass
class InstallTarget:
    ok: bool
    reason: str = ""
    install_dir: Path | None = None
    mode: str = ""        # "user" | "machine"
    version: str = ""
    tasks: str = ""
    others: list = field(default_factory=list)  # other registered installations (left alone)

    @property
    def exe(self) -> Path | None:
        # Windows Setup installs always use the .exe name, even when this module is imported on Linux CI.
        return self.install_dir / WINDOWS_EXECUTABLE_NAME if self.install_dir else None


def norm(path: str | os.PathLike) -> str:
    """Comparison key for Windows paths: absolute, normalised separators, case-folded."""
    text = os.path.normpath(os.path.abspath(str(path)))
    return os.path.normcase(text).rstrip("\\/").casefold()


def read_registrations() -> list[Registration]:  # pragma: no cover - Windows registry
    import winreg

    out = []
    views = [("HKCU", winreg.HKEY_CURRENT_USER, 0),
             ("HKLM64", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
             ("HKLM32", winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)]
    for name, root, view in views:
        try:
            with winreg.OpenKey(root, UNINSTALL_SUBKEY, 0, winreg.KEY_READ | view) as key:
                def value(n: str) -> str:
                    try:
                        v, _ = winreg.QueryValueEx(key, n)
                        return str(v)
                    except OSError:
                        return ""

                loc = value("InstallLocation") or value("Inno Setup: App Path")
                out.append(Registration(name, loc, value("DisplayVersion"), value("Inno Setup: Selected Tasks")))
        except OSError:
            continue
    # HKLM64 and HKLM32 are the same key on a 32-bit system; keep one of identical entries
    seen, unique = set(), []
    for r in out:
        k = (r.hive[:4], norm(r.install_dir) if r.install_dir else "", r.version)
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique


def detect(exe: Path | None = None,
           registrations: Callable[[], list[Registration]] | None = None) -> InstallTarget:
    if exe is None:
        if not getattr(sys, "frozen", False):
            return InstallTarget(False, "This copy runs from source code; automatic installation is only "
                                        "available in a copy installed with Setup.")
        exe = Path(sys.executable)
    exe = Path(exe)
    if exe.name.lower() != WINDOWS_EXECUTABLE_NAME.lower():
        return InstallTarget(False, "This is not the Monograph PDF program file.")
    folder = exe.resolve().parent if exe.exists() else exe.parent
    if not any(folder.glob("unins*.exe")):
        return InstallTarget(False, "This copy of Monograph PDF was not installed with Setup (portable or "
                                    "development copy), so it cannot be updated automatically.")
    regs = (registrations or read_registrations)()
    matches = [r for r in regs if r.install_dir and norm(r.install_dir) == norm(folder)]
    others = [r.install_dir for r in regs if r not in matches and r.install_dir]
    if not matches:
        return InstallTarget(False, "This copy of Monograph PDF is not the installation registered in Windows "
                                    "(Settings > Apps). To avoid changing the wrong copy, install the update "
                                    "with Setup from the release page.", others=others)
    hives = {r.hive[:4] for r in matches}
    if len(hives) > 1:
        return InstallTarget(False, "This folder is registered both for the current user and for all users; "
                                    "the installation to update is ambiguous. Install the update with Setup "
                                    "from the release page.", others=others)
    reg = matches[0]
    return InstallTarget(True, "", folder, "user" if reg.hive == "HKCU" else "machine", reg.version, reg.tasks, others)
