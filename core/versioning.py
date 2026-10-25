"""Platform-aware version helpers (Option B: independent Windows / Linux / macOS lines).

Each platform keeps its own SemVer in ``versions/<platform>.txt``. The root ``VERSION``
file mirrors the **Windows** line for backward-compatible packaging tools that still
read it; runtime code should call :func:`get_version` (current host) or
:func:`get_version` with an explicit platform.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PLATFORMS = ("windows", "linux", "macos")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def versions_dir() -> Path:
    return project_root() / "versions"


def version_file(platform: str | None = None) -> Path:
    """Path of the authoritative version file for ``platform`` (default: host OS).

    Windows packaging still consults root ``VERSION`` as a mirror of ``versions/windows.txt``.
    """
    plat = platform or current_platform()
    if plat not in _PLATFORMS:
        raise ValueError(f"Unknown platform: {plat!r}")
    return versions_dir() / f"{plat}.txt"


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def get_version(platform: str | None = None) -> str:
    """Return ``X.Y.Z`` for ``platform`` (default: the host operating system)."""
    plat = platform or current_platform()
    path = version_file(plat)
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
    elif plat == "windows":
        # Legacy checkouts / frozen Windows installs that only ship root VERSION
        legacy = project_root() / "VERSION"
        text = legacy.read_text(encoding="utf-8").strip() if legacy.is_file() else ""
    else:
        text = ""
    if not _VERSION_RE.match(text):
        raise ValueError(f"Invalid version for {plat}: {text!r} ({path})")
    return text


def parse_version(version: str | None = None) -> tuple[int, int, int]:
    version = get_version() if version is None else version.strip()
    match = _VERSION_RE.match(version)
    if not match:
        raise ValueError(f"Invalid version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_patch(version: str | None = None) -> str:
    """Increment patch with rollover: 0.0.99 -> 0.1.0, 0.1.99 -> 0.2.0."""
    major, minor, patch = parse_version(version)
    if patch >= 99:
        minor += 1
        patch = 0
        if minor > 99:
            major += 1
            minor = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def write_version(version: str, platform: str | None = None) -> None:
    """Write ``version`` for ``platform`` and keep root ``VERSION`` mirrored for Windows."""
    if not _VERSION_RE.match(version):
        raise ValueError(f"Invalid version: {version!r}")
    plat = platform or current_platform()
    if plat not in _PLATFORMS:
        raise ValueError(f"Unknown platform: {plat!r}")
    versions_dir().mkdir(parents=True, exist_ok=True)
    version_file(plat).write_text(version + "\n", encoding="utf-8")
    if plat == "windows":
        (project_root() / "VERSION").write_text(version + "\n", encoding="utf-8")


def all_platform_versions() -> dict[str, str]:
    return {p: get_version(p) for p in _PLATFORMS}
