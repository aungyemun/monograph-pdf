# Build and runtime

## Prerequisites (developers)

- Windows 10 or 11 (64-bit)
- Host Python **3.11** used only to create `./env` (release builds use Python 3.11; the source is also 3.12-compatible)
- Inno Setup 6 in `tools\inno\` (or a normal installation) for the installer; the C# compiler of .NET Framework 4, included in Windows, for `uninstall.exe`
- End users need no Python, Qt or Tesseract (qpdf — still a reserved optional integration; not used or shipped in v0.2.0)

## One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1
```

Creates `./env` and installs `requirements.txt`, caching wheels under `./packages/wheels` when possible.

## Development launch

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev_launch.ps1
```

Equivalent: `.\env\Scripts\python.exe -m app`

### Command-line options

| Option | Purpose |
| :--- | :--- |
| `<file>` | Open a PDF, image or Office file at startup |
| `--user-guide` | Show only the User Guide window (used by the Start menu shortcut) |
| `--smoke-test [--runtime-dir <dir>] [--report <file.json>]` | Offline self-check without a window (used by the build and by Setup); exit code 0 when every required check passed |

## Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

Artifacts go under `tests/outputs/` only. See [TESTING.md](TESTING.md).

## Produce `MonographPDF.exe`

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

- Intermediates: `build/`
- PyInstaller output: `dist/MonographPDF/` (`MonographPDF.exe` + `_internal/`) — **onedir** for fast cold start (no onefile temp extraction)
- A copy is also placed at the project root: `./MonographPDF.exe` plus `./_internal/` (a stale `./PDF_editor.exe` from an earlier internal build is removed)
- Application icon: `resources/icons/windows/monograph_pdf.ico` (16, 24, 32, 48, 64, 128 and 256 px; embedded via `--icon`). `scripts/generate_branding_icons.py` makes it, the window/taskbar/About PNGs and the Setup wizard images from the canonical artwork `resources/icons/source/Monograph_PDF_logo.png` (the icon uses the emblem without the wordmark, scaled uniformly with Lanczos resampling, transparency kept); `scripts/prepare_logo.py` imports a new version of the artwork from the Downloads folder (Windows known folder) without changing the original
- Windows file properties: `build/version_info.txt` from `scripts/make_version_info.py` + `core.product_meta.version_resource_strings()` — ProductName / FileDescription **Monograph PDF**, InternalName **MonographPDF**, OriginalFilename **MonographPDF.exe**, ProductVersion / FileVersion from `VERSION`, LegalCopyright **© 2026 Aung Ye Mun**; the release build compares the built exe with these values
- After PyInstaller, `scripts/packaging/check_release.py prune` removes bundled parts Monograph PDF never uses — Qt Network and its TLS / network-information / TUIO plugins, Qt Quick / QML and the virtual keyboard, Qt PDF, OpenCV's FFmpeg video plugin, software OpenGL (`opengl32sw.dll`) and Python's SSL module — and fails the build if a remaining DLL still imports one of them (checked with `pefile`)

Version embedded in the app is always read from `VERSION` at runtime (bundled as data). Branding assets under `resources/icons/` are bundled offline (no downloads).

## Release build (installer)

```bat
installer\build_release.bat
```

(or `scripts\build_release.ps1 [-SkipTests] [-SkipExe]`). Steps:

1. Unit and UI tests.
2. `MonographPDF.exe` (PyInstaller onedir) in `dist\MonographPDF\`; its version resource is checked against `core.product_meta`.
3. Copies `engines\ocr` and `models\tessdata` beside the exe, as Setup installs them, and checks the release contents (`check_release.py check`: every `.exe` / `.dll` / `.pyd` belongs to a component named in `THIRD_PARTY_NOTICES.md`, nothing the build removes is present, no keys, secrets, environment files, development folders or private paths; inventory in `build\installer\release_inventory.json`). No file of the earlier internal build (`PDF_editor.exe`, its logo or icons) may be present. Then runs `MonographPDF.exe --smoke-test` (PDF engine, rendering, encryption, PDF to Word, OCR, main window, every bundled module imports, no network use). The build stops if a check fails; each program started by the build has a time limit.
4. Builds `uninstall.exe` from `installer\uninstall_launcher.cs` with `csc.exe` and checks that it runs.
5. Compiles `installer\MonographPDF.iss` with Inno Setup into `installer\MonographPDF_{version}_Setup.exe`.
6. Builds the source archive `installer\MonographPDF_{version}_Source.zip` (`scripts\packaging\make_source_archive.py`; Monograph PDF's own source in the `monograph-pdf/` folder of the archive): corresponding Monograph PDF release source, including application, build, installer, documentation and release tests (without caches, environments, build output, generated test files, or local personal-document validation utilities that embed private/machine-local paths; scanned for secrets and private paths), the license texts, and the corresponding source of every bundled AGPL / GPL / LGPL component listed in `scripts\packaging\third_party_sources.json` — upstream archives downloaded once into `packages\sources` and verified against their SHA-256 (Qt archives also against Qt's published SHA-256 and MD5 lists); the OCR engine's GPL/LGPL libraries come as the MSYS2 source packages of exactly the shipped binary packages (from `repo.msys2.org`, or an MSYS2 archive mirror for versions no longer on it). `check_release.py check-source` then verifies every archive's hash, that the OCR DLLs in the release are the ones the source packages belong to (recorded SHA-256), and that each release file whose license requires corresponding source is covered (`REQUIRES_SOURCE`); the build stops otherwise.
7. Writes `installer\release\` (Setup.exe, the source archive, license texts and `SHA256SUMS.txt` for `Setup.exe`, `MonographPDF.exe` and the source archive), checks the release folder, then writes `installer\MonographPDF_{version}_Installer.zip` (the release folder without the source archive) and `installer\build_release_summary.txt` (sizes and SHA-256 hashes of `Setup.exe`, the installer ZIP, the source archive and `MonographPDF.exe`). `scripts\packaging\branding_scan.py --layout` then checks the application and the release folder for stale branding of an earlier internal build (only release history and migration notes may name earlier internal builds). Before anything is written there, `check_release.py guard-frozen` stops the build if `installer\release\` still holds another version's release that is not kept, byte for byte, under `releases\` (the frozen internal build 0.1.5 is in `releases\PDFEditor_0.1.5\`).

The first build on a computer needs internet access for the third-party source archives (about 300 MB); later builds use the cache (`--offline` makes a missing archive an error instead of a download). Adding or upgrading a GPL/LGPL/AGPL component requires a matching entry in `third_party_sources.json` (run `make_source_archive.py --pin` once to record the SHA-256 of a new archive).

The build is **not code-signed**; the summary and `SHA256SUMS.txt` say so.

### Release folder layout

```text
installer\release\
  Setup.exe
  MonographPDF_{version}_Source.zip
  SHA256SUMS.txt                 Setup.exe, MonographPDF.exe, source archive
  README.md, INSTALLATION.md, LICENSE.md, THIRD_PARTY_NOTICES.md,
  SECURITY.md, CITATION.cff, CHANGELOG.md
  docs\USER_GUIDE.md
  licenses\                      GPL / LGPL / MPL / GCC exception texts
  runtime\ocr\TESSERACT_NOTICE.txt, runtime\fonts\OFL.txt
```

`installer\MonographPDF_{version}_Installer.zip` is the same folder without the source archive (publish the archive beside it). Developer-only docs (`ARCHITECTURE`, `BUILD_AND_RUNTIME`, `FEATURES`, `FILE_FORMATS_AND_COMPATIBILITY`, `RELEASE_AND_VERSIONING`, `TESTING`, `SECURITY_AND_PRIVACY`) stay in the repository / source archive and are not copied into the release ZIP or the installed application.

Outputs and the end-user view of Setup are described in [INSTALLATION.md](../INSTALLATION.md). Test the installer with `scripts\test_installer.ps1` ([TESTING.md](TESTING.md#installer-and-uninstaller-test)).

### Installer and uninstaller design

- **Setup** (Inno Setup, `installer\MonographPDF.iss`): per-machine (`C:\Program Files\Monograph PDF`, administrator) or per-user (`%LOCALAPPDATA%\Programs\Monograph PDF`) install; the AppId of earlier internal builds is kept, so such a build is upgraded (see *Internal compatibility* below); optional Start menu, desktop, `.pdf` and Open-with registrations; offline self-check at the end. `UsePreviousAppDir=yes` reuses the previous install folder when upgrading. Existing installs are detected (same Setup mode first) by AppId uninstall registry → App Paths → known defaults → verified Start Menu shortcut (fallback only). Cross-mode copies (e.g. Program Files while running `/CURRENTUSER`) are logged and left untouched; interactive Setup may still offer the migration dialog for them. Before copying, Setup deletes owned application trees/files (`[InstallDelete]` plus leftover paths from the previous `{app}\installed_files.txt` manifest, or a legacy allowlist). Unknown / user-created files in the folder are preserved — the destination is never wiped wholesale. A new installation (no earlier same-mode version) clears the user's recent-files list and working files; an upgrade keeps settings and recent files. If the user chooses a different folder than the registered install, Setup offers: upgrade in the existing location (recommended), or install in the new location and remove owned application files from the old path **after** the new install is validated (smoke test). Silent Setup: same path upgrades in place; a different `/DIR` without `/MIGRATEINSTALL` keeps the registered same-mode location; `/MIGRATEINSTALL` moves and cleans the old owned files after success. Setup refuses to continue while `MonographPDF.exe` or `PDF_editor.exe` is still running (silent: fails). The owned-file list is produced by `scripts\packaging\write_installed_manifest.py` at build time.
- **uninstall.exe**: Inno Setup always names its uninstaller `unins000.exe`. `uninstall.exe` is a small launcher in the installation folder that starts `unins000.exe` with the same options, waits and returns its exit code. Setup registers it as `UninstallString` / `QuietUninstallString` (`/SILENT`) in the Windows uninstall key, so **Settings ▸ Apps ▸ Uninstall** runs it. While it waits, the launcher moves its own file to `%TEMP%` (a same-drive rename, allowed for running programs) so the installation folder can be removed completely; if the uninstall is cancelled or refused it rewrites `uninstall.exe` from the copy it read into memory at start (never from the parked file, which other programs could change), and it deletes the parked copy afterwards with `cmd.exe` / `PING.EXE` started by full path. In a per-machine installation it first restarts itself as administrator (the single UAC prompt the uninstall needs anyway). There is no Start menu uninstall shortcut (Windows 10/11 practice).
- **Uninstall** removes the installation folder, shortcuts, every registry key and value Setup created (each is flagged `uninsdeletekey` / `uninsdeletevalue` or lies inside such a key), the recent-files list, `%LOCALAPPDATA%\Monograph PDF` (runtime, cache, logs, sessions, Setup's self-check report) and `monographpdf*` / `monograph-pdf-theme` (and the earlier build's `pdfeditor*` / `pdf-editor-theme`) folders in `%TEMP%` of the user who uninstalls. It deletes only folders named `Monograph PDF` inside that user's `%APPDATA%` / `%LOCALAPPDATA%` — and the earlier build's `PDF Editor` folders only when `%APPDATA%\Monograph PDF\legacy_migration.json` shows Monograph PDF migrated them and no earlier internal build program remains — never one that contains the installation folder, and never follows a junction or symbolic link. It asks whether to remove `%APPDATA%\Monograph PDF` (settings) too; `/REMOVEUSERDATA` does so in silent mode. It refuses to run while `MonographPDF.exe` from the installation folder is running (silent: stops and logs), reports anything it could not delete, and never deletes user documents.

### Internal compatibility: earlier internal builds

Monograph PDF Setup keeps the earlier build's AppId `{64FC0D97-5E17-405F-9461-D6C075E1B467}`, so Windows and Setup treat it as the next version of the same application. Keeping the AppId is what makes the upgrade reliable: Inno Setup finds the previous installation, merges its uninstall log, replaces the single Installed apps entry and keeps the user's task choices. Changing it would leave the earlier internal build installed beside Monograph PDF.

- Detection: `MonographPDF.exe` or `PDF_editor.exe` at the AppId's `InstallLocation` / `UninstallString` / `DisplayIcon`, App Paths (`MonographPDF.exe`, then `PDF_editor.exe`), the default folders (`Monograph PDF` and `PDF Editor` in Program Files and `%LOCALAPPDATA%\Programs`), then a verified **Monograph PDF** or **PDF Editor** Start menu shortcut (fallback only).
- A folder named `PDF Editor` may move to the sibling `Monograph PDF` folder (interactive **Existing installation found** page, or silent `/MIGRATEINSTALL` without `/DIR`). The move follows the safe order: check that the earlier internal build is not running → install into the new folder → self-check → only then remove the earlier build's owned files (allowlist including `PDF_editor.exe`, `unins000.*`) from the old folder, keeping unknown files and removing the folder only if empty. Keeping the old physical folder is always available and is the silent default, because it needs no second copy and cannot leave two installations.
- Afterwards Setup removes the earlier build's App Paths entry, `Applications\PDF_editor.exe`, the `PDFEditor.Document` / `PDFEditor.Convertible` ProgIDs and their Open with values, `Software\PDF Editor\Capabilities`, the `PDF Editor` RegisteredApplications value, the **PDF Editor** Start menu folder and desktop shortcut — each only when the `PDF_editor.exe` it points to no longer exists. A Windows default-app choice (UserChoice) cannot be migrated by any installer; users choose Monograph PDF once.
- Per-user data is migrated by the application, not by Setup (Setup runs for one account; each user's first start copies their own data): `core/legacy_migration.py` copies `preferences.json`, `recent_files.json` (existing files only) and version-1 recovery sessions, never the cache, logs or temporary files, never deletes the earlier internal build folders, never follows links, and records the result in `%APPDATA%\Monograph PDF\legacy_migration.json`. It does not run for the self-check, the tests (redirected user-data folder) or with `MONOGRAPH_PDF_NO_LEGACY_MIGRATION=1`.

### Environment variables (development and testing)

| Variable | Purpose |
| :--- | :--- |
| `MONOGRAPH_PDF_RUNTIME_DIR` | Runtime folder (cache, temp, logs, sessions); `--runtime-dir` sets it |
| `MONOGRAPH_PDF_USER_DATA_DIR` | Settings / recent-files folder (self-check and tests) |
| `MONOGRAPH_PDF_HEADLESS` | `1`: no modal dialogs (tests, self-check) |
| `MONOGRAPH_PDF_STARTUP_TIMING` | `0`: no start-up timing log |
| `MONOGRAPH_PDF_DISABLE_OFFICE` | `1`: behave as if no Office suite is installed |
| `MONOGRAPH_PDF_NO_LEGACY_MIGRATION` | `1`: do not copy the earlier internal build data at start |
| `MONOGRAPH_PDF_NO_PAUSE` | `1`: `installer\build_release.bat` does not wait for a key |

Precedence: `MONOGRAPH_PDF_<NAME>` → `PDFEDITOR_<NAME>` → built-in default (`core/app_env.py`). The `PDFEDITOR_*` names of the earlier internal build are **deprecated** aliases kept during the 0.2.x series so older development scripts keep working; they will be removed in a later release.

### Development release script

```powershell
powershell -ExecutionPolicy Bypass -File scripts/prepare_windows_release.ps1
```

Runs offline feature smoke (`scripts/validate_release_smoke.py`), gate tests, one VERSION bump, PyInstaller onedir build, PE metadata checks, and writes `dist/runtime_manifest.json` (`offline_runtime=true`). It does not build the installer; use the release build above for that.

## Offline runtime expectations

- Disconnect network: app must still start and operate on local files
- OCR requires `engines/ocr` (vendored Tesseract + DLLs) and `models/tessdata` (`eng.traineddata`, `jpn.traineddata`, `osd.traineddata`) beside `MonographPDF.exe`; `tesseract.exe` runs without a console window
- Vendor OCR once with `scripts/vendor_ocr.ps1` (dev machine may use network for that step only); runtime OCR never downloads models
- Runtime folder: `./runtime` in the project layout, `%LOCALAPPDATA%\Monograph PDF\runtime` when installed (`MONOGRAPH_PDF_RUNTIME_DIR` or `--runtime-dir` overrides it). Organize/merge/split staging uses `runtime/temp/organize` and `runtime/cache/organize`; abandoned temporary files are cleaned on startup
- Settings and the recent-files list: `%APPDATA%\Monograph PDF` (`MONOGRAPH_PDF_USER_DATA_DIR` overrides it; the self-check and tests use a throw-away folder)
- Temporary folders in `%TEMP%` are named `monographpdf*`; the theme's generated images go to `%TEMP%\monograph-pdf-theme` only when the runtime cache is not writable
- qpdf — still a reserved optional integration; not used or shipped in v0.2.0; probes report its absence without failing startup
- External programs are started by full path only (see [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md#programs-monograph-pdf-starts)); the built app imports Python modules only from its bundle
- Do not download packages or models at application startup

## Dependency lock strategy

1. Pin direct dependencies in `requirements.txt` with `==` versions.
2. Install into `./env` only via `scripts/setup_env.ps1`.
3. Cache wheels under `./packages/wheels` (`pip --cache-dir`) for offline reinstall on the same platform.
4. After setup, optionally freeze the full environment for audit:

   ```powershell
   .\env\Scripts\python.exe -m pip freeze | Out-File -Encoding utf8 packages\pip-freeze.txt
   ```

5. Accept new libraries only after license/redistribution review; record in `licenses/DEPENDENCY_INVENTORY.md` and `core.dependency_audit`.
6. Native engines (Tesseract; qpdf if ever enabled) are tracked by vendored folder metadata when added — not by pip.

## Dependency policy

Before adopting a library: verify license, redistribution, Windows support, offline use, maintenance, and interaction with existing licenses. Record acceptance once in `licenses/DEPENDENCY_INVENTORY.md` (and `core.dependency_audit`). Do not duplicate equivalent libraries.

## Generated and cleanup-safe areas

Safe to delete and regenerate:

* `build\`, `dist\`
* `runtime\cache\`, `runtime\temp\`, `runtime\logs\` (the app also removes temp files older than a day)
* `runtime\sessions\` — recovery drafts (removed after 30 days)
* `tests\outputs\`, `installer\release\`
* `__pycache__\` folders; old `installer\MonographPDF_*_Setup.exe` versions (keep the newest)

Do not delete unless intentionally rebuilding:

* `MonographPDF.exe` and `_internal\` (built app)
* `installer\*_Setup.exe`, `installer\*_Installer.zip`, `installer\*_Source.zip`
* `releases\` — frozen earlier releases (for example `releases\PDFEditor_0.1.5\`, read-only); never rebuilt or changed
* `packages\sources\` (third-party source archives; re-downloaded and re-verified if deleted)
* `engines\ocr\`, `models\tessdata\` (offline OCR; required by Setup)
* `env\`, `tools\` (developer toolchain)

## Key scripts

| Script | Purpose |
| :--- | :--- |
| `scripts\setup_env.ps1` | Create `env\` with pinned packages |
| `scripts\build_exe.ps1` | Build `MonographPDF.exe` (PyInstaller onedir) |
| `scripts\build_release.ps1` | Full release: tests, exe, smoke test, uninstall.exe, Setup, source archive, ZIP |
| `scripts\test_installer.ps1` | Install → launch → uninstall → reinstall, upgrade matrix, earlier internal build (0.1.5) → Monograph PDF migration |
| `scripts\packaging\create_release_zip.ps1` | Release folder, `SHA256SUMS.txt`, `MonographPDF_{version}_Installer.zip` |
| `scripts\packaging\check_release.py` | Prune unused bundled parts; release contents / secrets / source-archive checks |
| `scripts\packaging\make_source_archive.py` | Build `MonographPDF_{version}_Source.zip` |
| `scripts\generate_branding_icons.py`, `scripts\prepare_logo.py` | Icons and wizard images from the logo; import a new logo |
| `scripts\run_tests.ps1`, `scripts\dev_launch.ps1` | Tests and run from source |
| `scripts\vendor_ocr.ps1` | Stage Tesseract and language data |

## Related

- Version bumps: [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- End-user installation: [INSTALLATION.md](../INSTALLATION.md)
