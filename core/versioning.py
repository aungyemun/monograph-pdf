"""Single-source version helpers. All product metadata must derive from VERSION."""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def version_file() -> Path:
    return project_root() / "VERSION"


def get_version() -> str:
    text = version_file().read_text(encoding="utf-8").strip()
    if not _VERSION_RE.match(text):
        raise ValueError(f"Invalid VERSION contents: {text!r}")
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


def write_version(version: str) -> None:
    if not _VERSION_RE.match(version):
        raise ValueError(f"Invalid version: {version!r}")
    version_file().write_text(version + "\n", encoding="utf-8")
