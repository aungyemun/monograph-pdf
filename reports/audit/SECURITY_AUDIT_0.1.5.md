# Internal development record — 0.1.5 (earlier internal name "PDF Editor") — Security, privacy, dependency and installer audit

This document is durable security evidence for an **internal development freeze**. It is **not** a public Monograph PDF release record, and the earlier internal name was never a public product release.

| | |
| :--- | :--- |
| Version | 0.1.5 (not bumped by this audit) |
| Audit date | 2026-10-15 |
| Internal freeze state | **2026-10-16 FROZEN** (hashes and test counts below); archived under `releases/PDFEditor_0.1.5/` |
| Scope | Application source (`app`, `core`, `engines`, `ui`), PyInstaller build and the packaged Windows build (`dist\PDF_editor`, `Setup.exe`, `installer\release`), Inno Setup script, `uninstall.exe`, build and packaging scripts, bundled libraries, OCR engine and data, documentation |
| Method | Source review; inventory of every `.exe` / `.dll` / `.pyd` in the built tree with file versions and DLL import tables; PyInstaller module list; Windows build, installer/uninstaller test and full UI audit on Windows 11; automated tests on Windows and Linux |

## Verdict: PASS (with the limitations below) — v0.1.5 INTERNAL FREEZE

No Critical or High issue remains open. Two High and four Medium issues were found during the audit and fixed; the fixes were verified on the packaged Windows build. License compliance for that freeze: the build includes `PDFEditor_0.1.5_Source.zip` (corresponding application source, including build, installer, documentation and release tests, plus corresponding third-party sources), checked automatically. The application's license expression is **AGPL-3.0-or-later** (upstream PyMuPDF/MuPDF remain AGPL-3.0). Code signing is not available: the freeze is **unsigned** and is documented as such. After the final hashes below are recorded, **no further v0.1.5 changes** should be made.

## Findings (historical audit) and current status

The table records what the audit found and how each item was fixed. All High and Medium findings are **fixed** in the final 0.1.5 internal freeze; the Status column is the freeze state.

| # | Severity | Finding (historical) | Status (final 0.1.5) |
| :--- | :--- | :--- | :--- |
| H1 | High | `uninstall.exe` runs from `%TEMP%` while it waits and started `cmd.exe` **by name** with no working folder. Windows searches the program's own folder first, so a `cmd.exe` planted in the user's `%TEMP%` could run — with administrator rights during a per-machine uninstall. A cancelled uninstall also moved the parked copy back from `%TEMP%` into the protected installation folder without checking it (a same-user process could swap it, and the swapped file would later run elevated). | **Fixed:** `cmd.exe` and `PING.EXE` by full path from the system folder, system folder as working folder; on cancel `uninstall.exe` is rewritten from the bytes read into memory at start. |
| H2 | High | Programs started by bare name from the app: `explorer` (**Show in Folder**), `rundll32.exe` (**Printing preferences…**), `powershell.exe` (Office conversions), and `soffice` looked up with `shutil.which` (current folder and `PATH`). On Windows the current folder is searched, so a program with the same name next to a document (for example in Downloads) could be started by PDF Editor. | **Fixed:** `core.safe_paths.windows_tool` gives full system paths; LibreOffice is taken only from its installation folder or its registered path. Test fails if any program is started by bare name. |
| M1 | Medium | Recovery copies of **password-protected** PDFs were written unencrypted to `%LOCALAPPDATA%\PDF Editor\runtime\sessions` (unsaved text boxes and form entries readable without the password). | **Fixed:** no recovery copy for protected PDFs (User Guide says so). |
| M2 | Medium | Network-capable components shipped although unused: Qt Network with TLS (OpenSSL / Schannel) backends, network-information plugin, TUIO touch plugin (UDP listener when enabled), Qt Quick/QML/virtual keyboard, Qt PDF, OpenCV's FFmpeg plugin (network streams), Python's `_ssl` / `libssl`. `THIRD_PARTY_NOTICES.md` wrongly stated that FFmpeg was not included. | **Fixed:** removed after PyInstaller (`check_release.py prune`, verified with each remaining DLL's import table); `_internal` 309.4 MB → 242.5 MB, Setup 139.5 MB → 120.4 MB. The self-check now refuses and reports network use and checks that every bundled module loads. |
| M3 | Medium | No release-contents gate: an undocumented library, test file, key or private path could enter a release unnoticed. Notices were incomplete (OpenSSL, OpenBLAS, MSVC runtime, libffi, colorama, typing_extensions, the 40+ libraries of the OCR engine, including LGPL and GPL-2.0-or-later ones) and listed qpdf, which was never shipped. | **Fixed:** `check_release.py check` runs on the built app and the release folder (unknown program files, removed parts, keys, secrets, `.env`, development folders, private paths); notices and `licenses/DEPENDENCY_INVENTORY.md` rewritten from the actual release. **qpdf is not shipped.** |
| M4 | Medium | Split, PDF to Images and Extract Images silently replaced same-named files in the chosen folder; the image extension came from the PDF unchecked. | **Fixed:** `safe_child` (plain names only, inside the chosen folder, `name (2).ext` instead of replacing); extension reduced to letters/digits. Bookmark titles were already sanitized. |
| L1 | Low | Setup wrote its self-check report into `{app}\logs` (the installation folder). | **Fixed:** `%LOCALAPPDATA%\PDF Editor\logs`; removed on uninstall. Installation folder holds only application/runtime/OCR/docs/licenses/uninstaller files. |
| L2 | Low | Uninstall removal guards relied on fixed paths only. | **Hardened:** removes only folders named `PDF Editor` inside the user's `%APPDATA%` / `%LOCALAPPDATA%`, never a junction or symbolic link, never a folder containing `{app}`; `%TEMP%` links skipped. |
| L3 | Low | LibreOffice conversions used LibreOffice's default macro security (High) in a fresh profile; Office conversions passed `-ExecutionPolicy Bypass` (process scope, not needed for `-Command`). | **Hardened:** profile sets Very High security and `DisableMacrosExecution`; execution-policy argument removed (Office conversions keep `AutomationSecurity = 3`). |
| L4 | Low | The built app put its own folder first on `sys.path`, and a portable/dist copy created developer folders (`packages`, `engines\qpdf`, `runtime`) beside `PDF_editor.exe` — also while running the self-check. | **Fixed:** frozen app imports only bundled modules; no developer folders and no probe of the exe folder when the working folder is set elsewhere. |
| L5 | Low | `scripts\test_installer.ps1` and `build_release.ps1` waited on Setup, the uninstaller and the self-check without a time limit; the installer test could check before the uninstaller's second phase finished. | **Fixed:** time limits on every started program; waits for the uninstaller log to close. |
| I1 | Info | `--runtime-dir` / `PDFEDITOR_RUNTIME_DIR` / `PDFEDITOR_USER_DATA_DIR` move working files. | By design (Setup and tests); same-user control only. |
| I2 | Info | Per-user installation (`%LOCALAPPDATA%\Programs\PDF Editor`) is writable by the user. | Normal for per-user Windows apps; documented. Per-machine installation in Program Files is read-only for standard users. |

Already correct (verified, no change needed): MuPDF JavaScript is never enabled (field calculate/format scripts and `OpenAction` do not run, also not on save); links and launch actions are not followed; attachments are listed only; passwords are masked unless **Show password** is chosen and never written to logs, settings, recent files or reports; Office automation forces macros off before opening files read-only and passes file names in environment variables; Tesseract is started by full path with fixed arguments and has no network support (no libcurl); no telemetry, ads, analytics, update checks, startup entries, services, scheduled tasks or firewall rules; Save / Save As keep encryption (fixed earlier in 0.1.5).

### Obsolete compliance wording (removed)

Earlier drafts referred to corresponding source as “available on request” or as an owner-confirmation / source-offer step. That model is **not** used for 0.1.5. The freeze packages `PDFEditor_<version>_Source.zip` beside the installer; the build fails if corresponding source is missing or incomplete. No separate owner confirmation is required for source availability.

## Fixes performed (files)

- `core/safe_paths.py` (new), `app/offline_guard.py` (new), `app/smoke_test.py` (checks `bundle_imports`, `no_network`), `app/bootstrap.py`, `app/paths.py`, `core/convert/office_bridge.py`, `core/convert/pdf_to_images.py`, `core/convert/extract_images.py`, `core/organize/split.py`, `core/ocr/paths.py`, `ui/main_window.py`, `ui/print_dialog.py`
- `installer/PDFEditor.iss`, `installer/uninstall_launcher.cs`
- `scripts/packaging/check_release.py` (new), `scripts/build_exe.ps1`, `scripts/build_release.ps1`, `scripts/packaging/create_release_zip.ps1` (`SHA256SUMS.txt`), `scripts/test_installer.ps1`
- `tests/unit/test_security_hardening.py`, `tests/ui/test_security_ui.py` (new)
- `THIRD_PARTY_NOTICES.md`, `licenses/DEPENDENCY_INVENTORY.md`, `docs/SECURITY_AND_PRIVACY.md` (`licenses/NOTICE.md` removed: it duplicated these two files), `SECURITY.md`, `docs/BUILD_AND_RUNTIME.md`, `docs/TESTING.md`, `docs/USER_GUIDE.md`, `README.md`, `INSTALLATION.md`, `CHANGELOG.md` (later documentation consolidation removed `DIRECTORY_STRUCTURE.md`; layout lives in `docs/ARCHITECTURE.md` / `docs/BUILD_AND_RUNTIME.md`)

## Network / offline audit

Application code contains no networking imports (test-enforced). Network-capable code in the release and its status is tabulated in `docs/SECURITY_AND_PRIVACY.md`: the Python standard-library networking modules remain (part of the runtime, unused; the bundled Python runtime has no SSL/TLS support used by PDF Editor), every Qt/OpenCV network component is removed, Tesseract has no URL support. The packaged self-check ran with all socket connects and name lookups refused: **no attempts** (Setup and build self-check, Windows). The UI test opens, edits, converts (text, flattened PDF, Word) and saves under the same guard: no attempts.

Residual: Microsoft Office or LibreOffice, once started for a conversion, follow their own settings — an Office document can reference remote images or templates that the office suite may fetch. This is outside PDF Editor's control and documented.

## Privacy / storage audit

| Kind | Location | Verified |
| :--- | :--- | :--- |
| Application files | `{app}` | Installer test: using the app (open a document, User Guide) adds no file to `{app}`; no `logs` folder in the installation directory |
| Settings, recent files | `%APPDATA%\PDF Editor` | Paths only; password never present (UI test scans every file) |
| Working files, recovery, logs | `%LOCALAPPDATA%\PDF Editor\runtime`, `…\logs` | No recovery copy for protected PDFs; removed on uninstall |
| Temporary | `%TEMP%\pdfeditor*`, `%TEMP%\pdf-editor-theme` | Removed on uninstall (not while running) |
| User documents | wherever saved | Never touched by uninstall (installer test) |

Residual: printing, copying or converting a protected PDF uses a short-lived unencrypted working copy in `%LOCALAPPDATA%\PDF Editor\runtime\temp`, deleted after the job; after a crash it is removed at the next start once older than a day.

## Installer / uninstaller audit

`scripts\test_installer.ps1` on the final 0.1.5 Setup.exe: **87 checks passed, 0 failed** — install with every task; files, `uninstall.exe` version, Installed apps entry; file-type, Open-with, App Paths and Default apps registrations; Start menu and desktop shortcuts; no `logs` folder in `{app}`; installed license texts present; no Run/RunOnce entries, scheduled tasks, services or Startup shortcuts; Setup self-check passed including OCR, `bundle_imports` and `no_network`; app launched with a document and the User Guide; nothing written into `{app}`; silent uninstall refused while running; complete uninstall with a locked working file (reported, user document untouched); reinstall and complete uninstall leave no folder, shortcut, registration, settings or `%TEMP%` folder; reinstall and uninstall keeping settings.

Administrator rights are requested only for an all-users installation (current-user installation offered in the dialog). Registrations are limited to `.pdf` (ProgID, Open with, Default apps capability) and Open with for images and Office files; every key and value is removed on uninstall.

## Dependency / third-party audit

Inventory taken from the built release (file versions and import tables) and the PyInstaller module list, compared with `requirements.txt` and `pip freeze`:

| Component (release check) | Files | Size |
| :--- | ---: | ---: |
| PDF Editor launcher (PyInstaller bootloader) | 1 | 10.8 MB |
| Python runtime | 18 | 8.0 MB |
| OpenSSL libcrypto (Python hashlib) | 1 | 5.0 MB |
| Microsoft Visual C++ / Universal C runtime | 52 | 4.4 MB |
| Qt 6 / PySide6 / Shiboken6 | 28 | 41.8 MB |
| PyMuPDF 1.25.3 / MuPDF 1.25.4 | 3 | 33.8 MB |
| OpenCV | 1 | 70.8 MB |
| NumPy + OpenBLAS | 14 | 25.9 MB |
| Pillow | 6 | 4.9 MB |
| lxml | 7 | 6.4 MB |
| fontTools | 2 | 0.5 MB |
| Tesseract OCR and its libraries | 52 | 159.7 MB |

Every component is named in `THIRD_PARTY_NOTICES.md` (test-enforced) and every pinned package in `licenses/DEPENDENCY_INVENTORY.md` (test-enforced). Python packages are pinned; pure-Python packages bundled additionally (colorama, typing_extensions, et_xmlfile, XlsxWriter) are listed. No dependency is downloaded at runtime. `scripts\fetch_fallback_fonts.py` (development only) is the only code that downloads anything and is not packaged. **qpdf is not shipped.**

License obligations: PDF Editor **AGPL-3.0-or-later**; PyMuPDF/MuPDF upstream **AGPL-3.0**; GPL-3.0 (pdf2docx); LGPL (Qt / PySide6; GLib, Pango, cairo, FriBidi, libthai, libdatrie, Graphite2, libiconv, gettext in the OCR engine); GPL-2.0-or-later (JBIG-KIT). These require corresponding source with binary releases and are met by publishing `PDFEditor_0.1.5_Source.zip` with every release (next section). Exempt: PyInstaller bootloader (bootloader exception), GCC runtime libraries (GCC Runtime Library Exception). The GPL, LGPL and MPL license texts are installed in `{app}\licenses` and included in the release folder.

## Source archive (license compliance)

Every 0.1.5 release includes `PDFEditor_0.1.5_Source.zip`, built by `scripts\packaging\make_source_archive.py` and checked by `check_release.py check-source`:

- `pdf-editor/`: corresponding PDF Editor release source, including application, build, installer, documentation and release tests. Caches, environments, build output and generated test files are left out. Local personal-document validation utilities that embed private or machine-local paths are intentionally excluded (they are development-only and are not part of corresponding-source coverage). The tree is scanned for keys, secrets and private paths.
- `third-party/`: unmodified upstream source archives of PyMuPDF 1.25.3 and MuPDF 1.25.4 (the MuPDF release PyMuPDF 1.25.3 builds), pdf2docx 0.5.8, PySide6 / Shiboken6 6.8.1.1 and Qt 6.8.1 (qtbase, qtsvg, qtimageformats — the modules shipped); every archive verified by SHA-256 (Qt: also against Qt's published SHA-256 and MD5 lists).
- `third-party/ocr-engine/`: for the ten GPL / LGPL libraries of the OCR engine, the MSYS2 source packages of the exact binary packages. Verified: each of the 16 DLLs is byte-identical to the DLL in its MSYS2 binary package; each source package's PKGBUILD is identical to the MSYS2 MINGW-packages commit of the build date; every file inside matches a SHA-256 recorded in that PKGBUILD. Old packages no longer on `repo.msys2.org` were fetched from an MSYS2 archive mirror and checked the same way. The DLL hashes are recorded in `third_party_sources.json`; `check-source` compares them with the release.
- `LICENSES/`, `README_SOURCE.md` (layout, build instructions, which binaries each source covers), `SOURCE_MANIFEST.json` (license, covered release files, source files with SHA-256 and origin).

The automated check fails the release if any release file whose license requires corresponding source (`REQUIRES_SOURCE`, defined independently of the manifest) is not covered, if an archive is missing or altered, or if PDF Editor's source part contains development files, secrets or private paths. Source-archive audit for the final 0.1.5 build: **passed** (17 third-party archives, 16 OCR DLL hashes; every AGPL / GPL / LGPL release file covered).

## Release integrity

Final 0.1.5 freeze build (2026-10-16; Python 3.11.9, PyInstaller 6.11.1, Inno Setup 6.7.1). Clean rebuild of `PDF_editor.exe` / `_internal`, Setup.exe, source archive and `installer.zip` from the frozen documentation/source tree (AGPL-3.0-or-later metadata synchronized into the bundled executable). Because `reports/audit/` is included in the source archive, the **authoritative** SHA-256 for `PDFEditor_0.1.5_Source.zip` is the value in `installer\release\SHA256SUMS.txt` after the final packaging pass (embedding that hash inside this report would change the archive hash). Setup.exe and `PDF_editor.exe` hashes below are fixed for this freeze binary.

| Artifact | Size | SHA-256 |
| :--- | ---: | :--- |
| `PDFEditor_0.1.5_Setup.exe` (`installer\release\Setup.exe`) | 126,222,272 bytes | `6EF9072C9B4B909E9E750EF119EDE45E9465B7A6E648CA1A2B6E76303C22A891` |
| `PDF_editor.exe` | 11,332,932 bytes | `E5D05760E1EBB6BB8C986F1DD05EBDB7025760D96CC06DF5974989DEB9FAB3E7` |
| `PDFEditor_0.1.5_Source.zip` | (see final `SHA256SUMS.txt`) | **Authoritative:** `installer\release\SHA256SUMS.txt` |

`installer\release\SHA256SUMS.txt` lists **Setup.exe**, **PDF_editor.exe** and **PDFEditor_0.1.5_Source.zip** for this build. (`installer.zip` is an optional download package that holds the installer only; its hash is recorded in `installer\build_release_summary.txt` and is not required in `SHA256SUMS.txt`.)

The release contents check passed on `dist\PDF_editor` and on `installer\release` (no development files, secrets, keys or private paths; `build_release_summary.txt`, which names the build machine, stays out of the release), and the source archive check passed. **Not code-signed**; SmartScreen guidance in the User Guide asks users to compare the checksum and never to turn off security software. qpdf remains reserved optional integration — not used or shipped. No `DIRECTORY_STRUCTURE.md` in the release or installed application.

## Security test results (final 0.1.5 freeze)

| Run | Result |
| :--- | :--- |
| Windows, `pytest tests\unit tests\ui` | **416 passed** |
| Windows release build: prune + dependency check, contents check (app and release folder), self-check (9 checks incl. `bundle_imports`, `no_network`), source archive build and `check-source` (17 third-party archives, 16 OCR DLL hashes) | passed |
| Windows installer / uninstaller test (includes installed license texts; About/license AGPL-3.0-or-later; no logs in `{app}`) | **87 passed, 0 failed** |
| Windows UI audit (`build\deep_ui_audit.py`: prior freeze cycle; runtime/license-meta rebuild does not change menu/command behavior) | Prior result retained: 408 checks, harness-only failure then re-pass 11/11 including Office→PDF |

## Remaining risks and limitations

- Unsigned build (SmartScreen warnings; integrity relies on the published SHA-256).
- Office suites run outside PDF Editor's control after launch (remote content in Office documents).
- Short-lived unencrypted working copies of protected PDFs during print/export (see storage audit).
- MuPDF, Pillow, Qt and the OCR libraries parse untrusted files; their security depends on keeping these pinned versions updated (PyMuPDF 1.25.3 / MuPDF 1.25.4; PyMuPDF is pinned by pdf2docx 0.5.8).
- Inno Setup's `DelTree` is relied on not to follow links below the top-level folders it removes (top levels are checked).
- Per-user installations are writable by the user (normal Windows behavior).
- Each release must be published with its source archive (`installer\release\` contains Setup.exe, PDF_editor.exe hashes via `SHA256SUMS.txt`, and `PDFEditor_0.1.5_Source.zip`; `installer.zip` holds the installer only, to keep downloads small).
- The source archive intentionally excludes local personal-document validation utilities; corresponding-source coverage for the product and bundled AGPL/GPL/LGPL components remains complete.
