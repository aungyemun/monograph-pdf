"""Locale-independent version parsing and comparison (Semantic Versioning 2.0.0 precedence).

Monograph PDF releases use ``X.Y.Z``; prerelease builds may use ``X.Y.Z-label.N``
(``0.3.0-rc.1``). Build metadata (``+...``) is not accepted. Only ASCII digits count as digits, so
the result never depends on the Windows display language or regional settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RE = re.compile(
    r"^(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})"
    r"(?:-((?:0|[1-9][0-9]{0,8}|[0-9]*[A-Za-z-][0-9A-Za-z-]{0,31})"
    r"(?:\.(?:0|[1-9][0-9]{0,8}|[0-9]*[A-Za-z-][0-9A-Za-z-]{0,31})){0,7}))?$",
    re.ASCII,
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple = ()

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def _key(self):
        # A release sorts after all of its prereleases; numeric identifiers sort before alphanumeric
        pre = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.prerelease)
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, pre)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __le__(self, other: "Version") -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def __ge__(self, other: "Version") -> bool:
        return self._key() >= other._key()

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return core + ("-" + ".".join(self.prerelease) if self.prerelease else "")


def parse(text: str) -> Version:
    """Parse ``X.Y.Z`` or ``X.Y.Z-pre``; a leading ``v`` (Git tags) is accepted. Raises ValueError."""
    if not isinstance(text, str):
        raise ValueError("version must be a string")
    s = text[1:] if text[:1] in ("v", "V") else text
    m = _RE.match(s)
    if not m:
        raise ValueError(f"invalid version: {text!r}")
    pre = tuple(m.group(4).split(".")) if m.group(4) else ()
    return Version(int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)


def is_valid(text: str) -> bool:
    try:
        parse(text)
        return True
    except ValueError:
        return False
