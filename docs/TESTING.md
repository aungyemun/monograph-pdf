# Testing

## Layout

| Path | Purpose |
|---|---|
| `tests/unit/` | Fast pure tests (versioning, imports, paths) |
| `tests/integration/` | Cross-module startup/import checks |
| `tests/ui/` | Qt UI tests (pytest-qt) when applicable |
| `tests/fixtures/` | Static fixtures |
| `tests/samples/` | Sample PDFs/inputs |
| `tests/outputs/` | **All** generated test artifacts |

Output subfolders: `logs/`, `screenshots/`, `junit/`, `coverage/`, `temp/`, `generated/`.

Never place temporary PDFs, screenshots, logs, coverage, or reports in the repository root.

## Running

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

Or: `.\env\Scripts\python.exe -m pytest`

Config: `pytest.ini` (`pythonpath = .`, `qt_api = pyside6`).

## Coverage focus

- Viewer + text editing regression (open/render, wrapping, undo, Unicode/JP, session)
- Forms: AcroForm load/edit, detection without source mutation, value preserve on Save As
- Tables: itinerary grid detection, row/col/merge/split
- Layout: align, distribute, smart-nudge related-only
- OCR: English/Japanese/mixed/rotated/blank/low-res scans, cancellation, searchable save/reopen; outputs under `tests/outputs/generated`
- Organize: ordering, counts, rotation/crop persistence, merge, split modes, encrypted + corrupted inputs; temps under `runtime/`
- Convert/export: images↔PDF, PNG/JPEG/TIFF, extract, text, flatten, copy, DOCX/XLSX/PPTX best-effort, optimize, watermark; **Office→PDF supported when Microsoft Office or LibreOffice is installed locally**, with graceful unsupported-state behavior when neither is detected (Office is never bundled)
- Security/redaction/annotations: password protect/remove (no silent strip), permissions/metadata, true redaction extraction check, visual signatures, print page rasters
- Fixtures: `make_samples.py` + `make_form_samples.py` + `make_ocr_samples.py` + `make_geometry_samples.py` → `tests/samples`
- Form fidelity: field names / XFA SOM paths never painted; `/AP` preferred; hybrid XFA bake must not strip unmodified widgets
- Geometry/quality: mixed page sizes, rotations, render-cache zoom/DPR keys, Lossless vs Balanced optimize, password dialog API
- Documentation / About UI: canonical `docs/` count, User Guide path, structure, wording and links; every **Menu ▸ Item** path in the User Guide exists in the app's menus; Components status labels, Office Integration optional wording (`tests/unit/test_docs_canonical.py`, `tests/unit/test_installer_and_docs.py`, `tests/ui/test_user_guide_menus.py`)
- Menu audit regressions (`tests/ui/test_menu_audit_fixes.py`): exports include unsaved edits, Save keeps password protection, shapes/images undo, no export over the open PDF, Reduce File Size presets and estimate, empty submenus disabled without a document, print paper matches the document
- Full menu/toolbar audit on Windows (manual, not CI): `build\deep_ui_audit.py <out>` drives every menu item and toolbar button with dialogs filled automatically, checks outputs and clipped text, and writes `deep_audit.json`, `audit.log` and screenshots; each step has a deadline so a stuck dialog cannot hang the run
- Installer script rules: `uninstall.exe` installed and registered, no Start menu uninstall shortcut, every registry entry removed on uninstall, running-app check, `/REMOVEUSERDATA`; self-check includes OCR and removes its sample files
- **Local real-PDF validation** (optional, not a CI dependency): `scripts/validate_real_pdfs.py` reads the current user's Downloads known-folder copies of named local PDFs; writes only under `tests/outputs/generated/real_pdf_validation/` and `tests/outputs/screenshots/real_pdf_validation/` — never commits personal PDFs
- **Live real-PDF QA** (MainWindow UI code path): `scripts/run_live_real_pdf_qa.py` or `pytest tests/integration/test_live_real_pdf_qa.py` — records `tests/outputs/generated/live_real_pdf/live_qa.json`
- **UI action matrix**: live QA writes `tests/outputs/generated/ui_action_matrix.json` (menu enabled/invoked/result)
- **Interaction perf log**: Text Box move/resize timings under `tests/outputs/logs/textbox_interaction_perf.log`
- **Shapes + inspector**: `tests/unit/test_shapes_and_inspector.py`; live QA covers shape tools, constraints, Save bake

## Installer and uninstaller test

`scripts\test_installer.ps1` tests a built `Setup.exe` on Windows (per-user install into `%LOCALAPPDATA%\MonographPDFInstallTest`; the app window and the User Guide appear briefly):

1. Clean install with every task: files, no `logs` folder in the installation folder, no startup entries, scheduled tasks or services, `uninstall.exe` and its version information, `MonographPDF.exe` version resource (Monograph PDF / MonographPDF / MonographPDF.exe / version / © 2026–Present Aung Ye Mun), `DisplayIcon` → `MonographPDF.exe`, no PDF Editor file installed, **Installed apps** entry (`UninstallString` / `QuietUninstallString` → `uninstall.exe`), file-type and Open-with registrations, Start menu (**Monograph PDF**, **Monograph PDF User Guide** with `--user-guide`, no uninstall shortcut), desktop shortcut, Setup's self-check (including OCR, every bundled module importing and no network use; report in `%LOCALAPPDATA%\Monograph PDF\logs`), no development paths in the installed User Guide.
2. Launch Monograph PDF with a document and the User Guide window; nothing is written into the installation folder, working files go to `%LOCALAPPDATA%\Monograph PDF`.
3. A silent uninstall while Monograph PDF is running is refused and leaves the installation intact.
4. Complete uninstall (`/REMOVEUSERDATA`) with a working file locked: the locked item is logged, user documents are untouched.
5. Reinstall and complete uninstall: no installation folder, shortcuts, registrations, `%APPDATA%\Monograph PDF`, `%LOCALAPPDATA%\Monograph PDF` or `%TEMP%\monographpdf*` / `%TEMP%\pdfeditor*` folders remain.
6. Reinstall and uninstall keeping settings: `preferences.json` is kept, the recent-files list and working files are removed.
7. **Upgrade / migration matrix** (builds a next-version test Setup into `build\installer\` only — does not overwrite frozen `installer\release` artifacts):
   - same-folder upgrade: obsolete owned files removed; unrelated notes/nested folders preserved; AppData preferences/recent-files and LOCALAPPDATA runtime kept
   - silent upgrade fails while Monograph PDF is running; install into a non-empty folder keeps pre-existing unrelated files
   - same path with trailing slash treated as in-place upgrade
   - silent different `/DIR` without `/MIGRATEINSTALL` keeps the registered location (no duplicate install)
   - registered install authoritative; unregistered second folder left untouched
   - silent `/MIGRATEINSTALL`: new location installed and validated; old owned files removed; unknown files and AppData preserved; registry/App Paths/Start Menu point at the new path
8. **PDF Editor 0.1.5 → Monograph PDF matrix** (sections 14–21), using the frozen PDF Editor 0.1.5 Setup from `releases\PDFEditor_0.1.5\` (checked against its released SHA-256; only run, never changed):
   - PDF Editor 0.1.5 installed per-user in its default `%LOCALAPPDATA%\Programs\PDF Editor`, with planted settings, recent files (one existing, one missing), a recovery session, an unknown-format session, cache and temporary files, and an unknown file in the install folder
   - a running `PDF_editor.exe` stops the silent upgrade without changes
   - silent in-place upgrade: `MonographPDF.exe` replaces `PDF_editor.exe`, unknown file kept, one Installed apps entry (now Monograph PDF, `DisplayIcon` / `UninstallString` updated), new App Paths / ProgIDs / Open with / Default apps registrations, every PDF Editor registration, Start menu folder and desktop shortcut removed, new shortcuts present, PDF Editor data untouched by Setup
   - first start: preferences, existing recent files and the version-1 session migrated; unknown session format, cache and temporary files not; migration record written; PDF Editor folders kept
   - complete uninstall after migration: Monograph PDF data and the migrated PDF Editor data removed, unknown install-folder file kept, no registrations or Start menu folders left
   - silent `/MIGRATEINSTALL` without `/DIR`: installed in `%LOCALAPPDATA%\Programs\Monograph PDF`, PDF Editor's files removed from the old folder (unknown file kept), InstallLocation / App Paths / ProgID / Start menu point at the new folder, an unregistered second PDF Editor copy elsewhere left untouched
   - Start menu fallback: a PDF Editor in a custom folder whose registration is gone is found through its verified Start menu shortcut and upgraded there
   - per-machine `C:\Program Files\PDF Editor` → `C:\Program Files\Monograph PDF` when the test runs elevated (reported as skipped otherwise)
   Use `-SkipUpgradeTests` / `-SkipLegacyTests` to omit; `-UpgradeSetup` / `-LegacySetup` for other Setup files. Interactive folder-choice dialog wording is covered in `INSTALLATION.md` (automated tests use the silent policy equivalents).

The current user's `%APPDATA%` / `%LOCALAPPDATA%` `Monograph PDF` and `PDF Editor` folders and desktop shortcuts are backed up first and restored afterwards; logs go to `build\installer-test\`. The exit code is the number of failed checks. Setup, the uninstaller and the app each have a time limit, so a stuck process cannot hang the test. The interactive prompts (close Monograph PDF; remove settings?; **Upgrade to Monograph PDF** page) use the same code paths as the silent options tested here.

## Product identity and PDF Editor migration tests

- `tests/unit/test_product_meta.py`: canonical identity (Monograph PDF, MonographPDF.exe, `monograph-pdf`, AGPL-3.0-or-later, version 0.2.0), PE version strings and `make_version_info.py`, the new icon (every ICO size 16–256 with transparency, emblem scaled without distortion or cropping), no old PDF Editor logo or icon as an active resource.
- `tests/unit/test_monograph_migration.py`: `MONOGRAPH_PDF_*` overrides win over the deprecated `PDFEDITOR_*` aliases; new temporary-folder names; AppData migration (preferences, existing recent files, version-1 sessions; never cache, temp or logs; never deletes or overwrites; once only; ignores damaged files and links; skipped for the self-check and tests); installer identity (AppId kept, names, ProgIDs, Start menu, never the default app), PDF Editor detection (uninstall entry, App Paths, default folders, Start menu fallback, running `PDF_editor.exe`), Upgrade page wording, move only after validation, legacy registrations removed only when their program is gone, silent `/MIGRATEINSTALL`, uninstall of PDF Editor data only with proven provenance; the frozen-release guard; changelog history kept.
- `tests/ui/test_branding_ui.py`: window and application icon from `monograph_pdf.ico`, About shows Monograph PDF, version, description, history note, Components / Office Integration tabs and License / Third-Party Notices buttons.
- `tests/unit/test_source_archive.py`: `MonographPDF_<version>_Source.zip` with `monograph-pdf/`, `SHA256SUMS.txt` naming `MonographPDF.exe`, installer package `MonographPDF_<version>_Installer.zip`.
- Branding scan (release review): search the repository and the built output for `PDF Editor`, `PDF_editor`, `PDFEditor_`, `PDF_logo.png`, `pdf_editor.ico` and the old AppData / Program Files paths; every remaining match must be historical, migration compatibility or file-format compatibility (`check_release.py check` already fails on old program or icon files in the release).

`tests\unit\test_installed_manifest.py` checks that `write_installed_manifest.py` rejects unsafe relative paths and lists only application-owned install paths.

## Security tests

- `tests/unit/test_security_hardening.py`: safe output names (no `..`, folder parts or reserved names; never replacing existing files) for Split, PDF to Images and Extract Images; every external program started by full path, no `shell=True` or dynamic code; Office scripts force macros off before opening and receive file names only in environment variables; LibreOffice profile disables macros and `soffice.exe` is never taken from the current folder or `PATH`; PDF JavaScript (field calculation / format scripts, `OpenAction`) is never run, also not when saving; malformed and truncated PDFs fail safely without changing the file; no network code in the app and the offline guard refuses and records connections; the built app does not import modules from its folder; an installed copy keeps working files in `%LOCALAPPDATA%` and never probes the installation folder; the installer creates no persistence (Run keys, services, tasks, firewall rules) and only the documented registrations; uninstall removal is limited to Monograph PDF's own folders (and PDF Editor's only with a migration record) and never follows links; `uninstall.exe` starts its clean-up by full path and restores itself from memory; the release check rejects unknown program files, removed network parts, keys, secrets, environment files, test folders and private paths; every shipped component is named in `THIRD_PARTY_NOTICES.md` and every pinned package in `licenses/DEPENDENCY_INVENTORY.md`.
- `tests/ui/test_security_ui.py`: passwords and the contents of a protected PDF are never written to working files, settings or the recent-files list (no recovery copy for protected PDFs; unprotected PDFs still get one); **Save As** keeps encryption, password and permissions; opening, editing, converting and saving use no network.
- On Windows, the installer's self-check (`no_network`, `bundle_imports`) and `scripts\test_installer.ps1` cover the packaged release.

## Source archive and license tests

- `tests/unit/test_source_archive.py` (no network; third-party archives replaced by small stand-ins): every release file whose license requires corresponding source (Monograph PDF, PyMuPDF / MuPDF, pdf2docx, Qt / PySide6, the OCR engine's GPL / LGPL libraries) is covered by a component of `scripts/packaging/third_party_sources.json`, and dropping any component is reported; the manifest lists a license, download address and hash for every archive, and every OCR library names its MSYS2 binary and source package with the SHA-256 of each DLL; the GPL / LGPL / MPL license texts are shipped and `THIRD_PARTY_NOTICES.md` points to the source archive instead of an on-request offer; Monograph PDF's source selection leaves out caches, environments, build output, generated test files and the personal-document validation scripts, and contains no secrets or private paths; a built archive has the documented layout and passes `check_release.py check-source`, which rejects tampered, incomplete or leaking archives and a release whose OCR DLLs differ from the recorded ones; an offline build without cached archives fails.
- The release build runs `make_source_archive.py` and `check_release.py check-source` on the real archive and fails on any gap.

## Reports policy

Routine successful runs write machine-readable/junit/log output under `tests/outputs`. Do not create Markdown “success reports” for green runs. Human `reports/` Markdown is reserved for audits, release notes, or compatibility investigations when necessary — update an existing canonical report instead of creating `FINAL2`/`latest` copies.

## Related

- Build: [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md)
- Release gating: [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md)
