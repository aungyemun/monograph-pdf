# Build and runtime

## Requirements

* Windows 10 or 11, 64-bit
* Python **3.11** for the development environment in `.\env` (the source is also compatible with 3.12)
* Inno Setup 6 (in `tools\inno\` or installed system-wide; releases are built with 6.7.1) and the
  .NET Framework 4 C# compiler (`csc`, part of Windows) to build the installer and `uninstall.exe`
* For a release build: the OCR engine and language data (see below)

End users need none of these: Python, Qt and Tesseract are bundled with the application.

## Setting up and running from source

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1    # create .\env with the pinned packages
powershell -ExecutionPolicy Bypass -File scripts\dev_launch.ps1   # start the app
# or: .\env\Scripts\python.exe -m app
```

| Command-line option | Purpose |
| :--- | :--- |
| `<file>` | Open this file at start-up |
| `--user-guide` | Open only the User Guide (used by the Start menu shortcut) |
| `--smoke-test` | Run the offline self-check (used by the build and by Setup) |

Tests: `scripts\run_tests.ps1`; results go to `tests\outputs\`. See [Testing](TESTING.md).

## Building the executable

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The output is `dist\MonographPDF\` (a PyInstaller one-folder build), copied to `MonographPDF.exe`
and `_internal\` in the project root. The version comes from `VERSION`. The build then runs
`check_release.py prune`, which removes components the application never uses (networking and TLS
modules, unused Qt plugins and similar) and checks that nothing still depends on them.

## OCR engine and language data

The OCR engine (`engines\ocr\`) and the `eng`, `jpn` and `osd` language data (`models\tessdata\`) are
not stored in the repository. Releases ship Tesseract 5.4.0.20240606 (Windows x64) and the
tessdata_fast 4.1.0 language data; every file is pinned by SHA-256 in `scripts/ci/ocr_engine_pins.json`.

```powershell
# 1. Install exactly that Tesseract version (approved Chocolatey package, also used by CI)
choco install tesseract --version 5.4.0.20240606 -y

# 2. Copy it and download the language data, only if every file matches the pins
powershell -ExecutionPolicy Bypass -File scripts\vendor_ocr.ps1
```

`vendor_ocr.ps1` changes nothing when any file differs. The release build checks the folders against
the pins again (`scripts\ci\stage_ocr_engine.py --verify`) and stops on a missing, different or extra
file. The OCR tests are skipped when the engine is absent. After an intentional engine update, record
the new files with `stage_ocr_engine.py --write-pins` and update the notices and source archives.

## Release build

```bat
installer\build_release.bat
```

The release build runs these steps in order: tests → executable → OCR engine copy → contents check
and self-check → `uninstall.exe` → Setup → Source.zip → release folder, Installer.zip and summary →
release-set verification. The first build downloads the third-party source archives into
`packages\sources\` (about 300 MB); later builds use that cache.

```text
installer\
  MonographPDF_<version>_Setup.exe
  MonographPDF_<version>_Installer.zip
  MonographPDF_<version>_Source.zip
  build_release_summary.txt
  release\
    Setup.exe, MonographPDF_<version>_Source.zip, SHA256SUMS.txt,
    README.md, INSTALLATION.md, LICENSE.md, THIRD_PARTY_NOTICES.md, SECURITY.md,
    CITATION.cff, CHANGELOG.md, docs\USER_GUIDE.md, licenses\, runtime\
```

`MonographPDF_<version>_Source.zip` is made from the committed files (`HEAD`) with their committed
bytes, never from untracked files or uncommitted edits; the build stops if selected files have
uncommitted changes (`make_source_archive.py --allow-dirty` only for a development archive). The
archive is reproducible: the same commit and the same cached third-party archives give the same ZIP
bytes, whatever the checkout's line-ending setting (fixed order, dates from the commit time,
attributes and compression; the same Python version is assumed for zlib).

Publishing a release is a separate, manual step: see the [Release checklist](RELEASE_CHECKLIST.md).

### Installer and uninstaller design

* Installs for all users or for the current user, with optional Start menu and desktop shortcuts and
  **Open with** registrations.
* Upgrades keep the same AppId, replace only the files Setup owns, and keep unknown files.
* `uninstall.exe` runs Inno Setup's uninstaller, removes the application's working data and asks
  before removing settings.
* Earlier internal builds (installed as `PDF Editor` / `PDF_editor.exe`) are recognized so that
  they can be upgraded and their settings migrated; this is the only reason the old name appears.

### Environment variables for development and testing

| Variable | Purpose |
| :--- | :--- |
| `MONOGRAPH_PDF_RUNTIME_DIR` | Folder for cache, temporary files, logs and sessions |
| `MONOGRAPH_PDF_USER_DATA_DIR` | Folder for settings and recent files |
| `MONOGRAPH_PDF_HEADLESS` | Never show modal dialogs (automated tests) |
| `MONOGRAPH_PDF_DISABLE_OFFICE` | Behave as if no Office suite were installed |
| `MONOGRAPH_PDF_NO_LEGACY_MIGRATION` | Skip the one-time settings migration at first start |
| `MONOGRAPH_PDF_STARTUP_TIMING` | `0` turns off the start-up timing file (the 20 newest are kept) |
| `MONOGRAPH_PDF_PERF_LOG` | `1` lets an installed copy write the text-box drag timing log (always on when running from source; at most 256 KB) |
| `MONOGRAPH_PDF_NO_PAUSE` | Skip the final pause of `build_release.bat` |

## Related

[Architecture](ARCHITECTURE.md) · [Release and Versioning](RELEASE_AND_VERSIONING.md) · [Testing](TESTING.md)
