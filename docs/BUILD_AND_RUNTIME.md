# Build and runtime

## Prerequisites

* Windows 10/11 x64
* Python **3.11** for `./env` (3.12-compatible source)
* Inno Setup 6 (`tools\inno\` or system install); .NET Framework 4 `csc` for `uninstall.exe`

End users need no Python, Qt, or Tesseract. qpdf is reserved and not shipped.

## Setup and run

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1
powershell -ExecutionPolicy Bypass -File scripts/dev_launch.ps1
# or: .\env\Scripts\python.exe -m app
```

| Option | Purpose |
| :--- | :--- |
| `<file>` | Open at startup |
| `--user-guide` | User Guide only (Start menu shortcut) |
| `--smoke-test` | Offline self-check (build / Setup) |

Tests: `scripts/run_tests.ps1` → artifacts under `tests/outputs/`. See [TESTING.md](TESTING.md).

## Build exe

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

Output: `dist/MonographPDF/` (onedir) and root `MonographPDF.exe` + `_internal/`. Version from `VERSION`. `check_release.py prune` removes unused network/Qt/SSL bits.

## Release build

```bat
installer\build_release.bat
```

Flow: tests → exe → OCR copy → contents/smoke checks → `uninstall.exe` → Setup → Source.zip → `installer\release\` + Installer.zip + summary. First build may download third-party sources into `packages\sources` (~300 MB); later builds use the cache.

```text
installer\release\
  Setup.exe
  MonographPDF_{version}_Source.zip
  SHA256SUMS.txt
  README.md, INSTALLATION.md, LICENSE.md, THIRD_PARTY_NOTICES.md,
  SECURITY.md, CITATION.cff, CHANGELOG.md, docs\USER_GUIDE.md, licenses\
```

### Installer and uninstaller design

* Per-machine or per-user; optional Start menu / desktop / Open with.
* Upgrades reuse AppId; owned-file cleanup; unknown files kept.
* `uninstall.exe` wraps Inno `unins000.exe`; removes app data; settings optional.
* Internal compatibility with earlier `PDF Editor` / `PDF_editor.exe` installs (migration only).

### Environment variables (development and testing)

| Variable | Purpose |
| :--- | :--- |
| `MONOGRAPH_PDF_RUNTIME_DIR` | Cache / temp / logs / sessions |
| `MONOGRAPH_PDF_USER_DATA_DIR` | Settings / recent files |
| `MONOGRAPH_PDF_HEADLESS` | No modal dialogs |
| `MONOGRAPH_PDF_DISABLE_OFFICE` | Pretend no Office suite |
| `MONOGRAPH_PDF_NO_LEGACY_MIGRATION` | Skip first-start migration |
| `MONOGRAPH_PDF_STARTUP_TIMING` | `0` turns off the startup-timing file (20 newest kept) |
| `MONOGRAPH_PDF_PERF_LOG` | `1` lets an installed copy write the text-box drag timing log (always on in a source checkout; capped at 256 KB) |
| `MONOGRAPH_PDF_NO_PAUSE` | Skip pause in `build_release.bat` |

## Related

[ARCHITECTURE.md](ARCHITECTURE.md) · [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md) · [TESTING.md](TESTING.md)
