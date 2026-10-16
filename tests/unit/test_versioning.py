"""Unit tests for VERSION single-source helpers."""

from __future__ import annotations

from core.versioning import bump_patch, get_version, parse_version


def test_get_version_matches_file():
    version = get_version()
    major, minor, patch = parse_version(version)
    assert major >= 0
    assert minor >= 0
    assert patch >= 0
    assert version == f"{major}.{minor}.{patch}"


def test_bump_patch_rollover():
    assert bump_patch("0.0.1") == "0.0.2"
    assert bump_patch("0.0.99") == "0.1.0"
    assert bump_patch("0.1.99") == "0.2.0"
