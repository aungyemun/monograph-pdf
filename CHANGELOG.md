# Changelog

All notable changes to Monograph PDF. Versions follow `VERSION` (see `docs/RELEASE_AND_VERSIONING.md`).

## [0.1.0] — 2026-10-25 (Linux)

First **Linux** release (branch `linux`, tag `v0.1.0-linux`, **unsigned**). First **Linux** build. Versioning is independent of the Windows line (Windows remains at 0.5.0).
Feature set mirrors the Windows application; platform integration uses Linux replacements
(single-instance flock, fontconfig, LibreOffice, XDG desktop / default PDF handler, Tesseract +
pinned tessdata).

### Added (Linux)

- `scripts/setup_env.sh`, `dev_launch.sh`, `run_tests.sh`, `vendor_ocr.sh`
- Per-user install helper (`installer/linux/install.sh`)
- Desktop integration (`core/linux_desktop.py`)

---

## [0.5.0] — 2026-10-24

PLACEHOLDER_FOR_TRUNCATION