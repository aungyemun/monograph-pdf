# Build and runtime

## Platform entry points

Use unified `main` for new development. Python 3.11 is the baseline for all platforms.
Windows setup/build details follow below; Linux uses [LINUX.md](../LINUX.md) and macOS uses
[MACOS.md](MACOS.md). Bash setup/launch/test scripts are shared by Linux and macOS; native
OCR staging and packaging remain platform-specific. See the [script map](../scripts/README.md).
Release publication and production signing are separate maintainer operations.

## Windows requirements

* Windows 10 or 11, 64-bit
* Python **3.11** for the development environment in `.\env` (the source is also compatible with 3.12)
* Inno Setup 6 (in `tools\inno\` or installed system-wide; releases are built with 6.7.1) and the
  .NET Framework 4 C# compiler (`csc`, part of Windows) to build the installer and `uninstall.exe`
* For a release build: the OCR engine and language data (see below)

End users need none of these: Python, Qt, Tesseract and the Visual C++ runtime are bundled with the
application. See [Windows Runtime Dependencies](WINDOWS_RUNTIME_DEPENDENCIES.md),
[Prerequisite Management](PREREQUISITE_MANAGEMENT.md) and [Installer Package Contents](INSTALLER_PACKAGE_CONTENTS.md).

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
and self-check → `uninstall.exe` → `MonographPDFUpdater.exe` (the update helper, from
`installer/update_helper.cs`) → Setup → Source.zip → release folder, Installer.zip and summary →
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

The update manifest is signed outside this build, in a separate signing environment (Python 3.11 with
only the hash-pinned packages of a signing bundle made by `scripts/packaging/make_signing_bundle.py`);
the build environment and the application never contain a signing key or the `cryptography` package.
See [Secure updates](SECURE_UPDATES.md#maintainer-tooling).

### Installer and uninstaller design

* Installs for all users or for the current user, with optional Start menu and desktop shortcuts and
  **Open with** registrations.
* Upgrades keep the same AppId, replace only the files Setup owns, and keep unknown files.
* `uninstall.exe` runs Inno Setup's uninstaller, removes the application's working data and asks
  before removing settings.
* `MonographPDFUpdater.exe` finishes an automatic update after the application has closed: it runs
  this Setup silently for the existing folder and mode ([AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md)).
* The bundled `resources/update/update_config.json` defines update trust and allowed hosts;
  Windows development 0.5.0 enables update checks, with automatic checks off by default.
  `resources/diagnostics/reporting.json` keeps report sending disabled.
  `scripts\build_exe.ps1 -UpdateConfig <folder>` replaces the update
  configuration **in test builds only** (synthetic keys, local mock server); `verify_release.py
  --layout` fails if a release carries anything but the repository's files.
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
| `MONOGRAPH_PDF_UPDATES_DIR` | Folder for update status and staging (tests; the update helper only accepts the default `%LOCALAPPDATA%\Monograph PDF\Updates`) |
| `MONOGRAPH_PDF_DIAGNOSTICS_DIR` | Folder for problem-report records (tests) |

## Related

[Architecture](ARCHITECTURE.md) · [Release and Versioning](RELEASE_AND_VERSIONING.md) · [Testing](TESTING.md)
