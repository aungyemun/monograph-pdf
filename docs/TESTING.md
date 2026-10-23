# Testing

## Layout

| Path | Purpose |
|---|---|
| `tests/unit/` | Fast pure tests |
| `tests/integration/` | Cross-module checks |
| `tests/ui/` | Qt UI (pytest-qt) |
| `tests/fixtures/` · `tests/samples/` | Fixtures / samples |
| `tests/outputs/` | All generated artifacts |

Never leave temp PDFs, screenshots, or logs in the repo root.

## Running

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
# or: .\env\Scripts\python.exe -m pytest
```

`pytest.ini`: `pythonpath = .`, `qt_api = pyside6`.

The small sample PDFs in `tests/samples/` are generated, not stored in git: the test session creates
them (`tests/fixtures/make_samples.py`) when they are missing, so a fresh checkout runs as is.

### Process safety

Tests and tools end only processes they started: through the handle or process ID they hold, or
through the Windows Job Object containing exactly their process tree. They never end processes by
program name (all `python.exe`, all PowerShell windows, …), so unrelated programs, scripts and
analyses keep running. To run the suite (or any long command) with a time limit and guaranteed
cleanup of just its own processes:

```powershell
.\env\Scripts\python.exe scripts\run_isolated.py --timeout 1800 -- .\env\Scripts\python.exe -m pytest -q
```

`tests/unit/test_process_safety.py` fails on any kill-by-name pattern in the repository and checks
that `run_isolated.py` ends the whole command tree on timeout while an unrelated process survives.
If a process's ownership cannot be established, it is left running and reported.

## Test categories

Every test is marked with one or more categories (rules in `tests/conftest.py`), and each run ends
with a per-category table. Select with `-m`, for example `-m "not private_fixture"` or `-m gui`.

| Category | Meaning |
|---|---|
| `portable` | Needs nothing beyond the Python requirements |
| `windows` | Needs Windows behaviour (installed fonts, file locking, registry, Windows paths) |
| `gui` | Creates Qt windows (runs offscreen in CI) |
| `external_app` | Needs Microsoft Office or LibreOffice installed |
| `ocr` | Needs the vendored OCR engine and language data (`engines/ocr`, `models/tessdata`) |
| `private_fixture` | Needs maintainer-local PDFs that are not in the repository |
| `security` | Security, privacy and release-integrity regression tests |
| `golden` | Golden documents and template PDFs compared with their manifests |

Status per category: **PASS** (at least one test ran and none failed), **FAIL** (a test failed) or
**NOT VERIFIED** (every test of the category was skipped, for example no private PDFs or no Office on
that machine). Skipped tests are never reported as passed. Set `MONOGRAPH_TEST_CATEGORY_REPORT` to a
file path to also get the table as Markdown.

## Continuous integration

`.github/workflows/windows-ci.yml` runs on pull requests, pushes to `main` and on demand, on a GitHub
Windows runner with Python 3.11.9:

1. install `requirements-ci.txt` (the pinned `requirements.txt` plus `pytest-timeout`) and `pip check`;
2. install Tesseract 5.4.0.20240606 (approved Chocolatey package) and stage it with
   `scripts/ci/stage_ocr_engine.py` only if every file, and the downloaded `eng` / `jpn` / `osd`
   language data, is SHA-256 identical to what the release ships (`scripts/ci/ocr_engine_pins.json`);
   otherwise the OCR tests skip and show as NOT VERIFIED;
3. validate every `docs/releases/v*.md` with `scripts/packaging/validate_release_notes.py`;
4. `pytest tests/unit tests/integration tests/ui` offscreen, with a 900-second per-test timeout;
5. publish the per-category table in the run summary and keep only the JUnit XML and that table
   (14 days).

The workflow has read-only repository permissions, uses no secrets, does not build or publish
releases, and never uploads documents.

CI runs the automated tests its environment supports, not every test. Tests that need Microsoft
Office, Japanese system fonts that the runner does not have, or the maintainer's private reference
PDFs are skipped there (a category whose tests were all skipped shows as **NOT VERIFIED**); run them
locally before a release ([RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)). Modules for private PDFs are
not in the repository at all. The installer test (`scripts\test_installer.ps1`) and physical printing
are not part of CI. Test figures quoted in release notes always name the build or CI run they come
from.

## Coverage focus

* Viewer, text edit / undo, forms, tables, layout, OCR
* Organize, convert/export; **Office→PDF supported when Microsoft Office or LibreOffice is installed locally**
* Security, redaction, annotations, print
* Highlighting: pen toggle, Esc during a stroke, color switching, the eraser, and marks kept across other edits (`tests/ui/test_highlight_round7.py`, `test_highlight_continuous.py`)
* Docs / menus: User Guide menu paths match the app (`test_user_guide_menus.py`)
* Menu audit (`test_menu_audit_fixes.py`); deep harness `scripts\deep_ui_audit.py <out_dir> [step filter]` (manual: triggers every menu command and dialog, flags cut-off labels, buttons, number boxes and options and dialogs too big for 1366 × 768; printing steps need `QT_QPA_PLATFORM=windows` on Windows)
* Small screens and display scaling: `tests/ui/test_small_screen_layout.py` (status bar, responsive toolbar, Navigation panel tabs, Fit Width with mixed page sizes, dialog fit); visual review with `scripts\audit\ui_visual_capture.py <out_dir>` — Qt-made captures of the window, toolbars, panels, menus and context toolbars in light and dark (set `QT_SCALE_FACTOR` to emulate 125 % / 150 % / 200 %)
* Page design: header/footer slots, watermark and background placement on 0/90/180/270° and cropped pages (measured on renders), replace/remove, shared fonts/pictures (`tests/integration/test_page_marks.py`, `tests/ui/test_page_marks_ui.py`)
* Redaction beyond page content: fields/comments/links under marks, whole pages, residue report and removal, checked in raw bytes (`tests/integration/test_redaction_residue.py`, `tests/ui/test_redaction_ui.py`)
* Merge outlines and protected inputs; Images to PDF without photo metadata (`test_merge_outline_and_protection.py`, `test_images_to_pdf_privacy.py`)
* Menus and toolbars: one Alt-letter per menu item, no duplicate shortcuts, icon + tooltip on every command, toolbar commands present in menus (`tests/ui/test_menu_toolbar_inventory.py`); full JSON inventory of every menu item, toolbar control and shortcut: `scripts\audit\ui_control_inventory.py out.json`
* Cut-off text: `scripts\audit\clipped_text_audit.py [--scale 1.5]` opens every dialog the menus reach and the Properties panel for text boxes and shapes, and lists labels, buttons, check boxes and combo boxes whose text does not fit (exit code 1 when any is found)
* Bookmarks (add / rename / move / retarget / delete, undo, save, web-link bookmarks kept), Remove Hidden Information (checked in every decompressed object of the output, including open/automatic actions, bookmark scripts, page and image XMP, XFA, incremental-save history and unreferenced objects), Bates numbers, print odd/even/reverse/without comments, password strength (`test_bookmark_ops.py`, `test_remove_hidden_info.py`, `test_bates_and_print_options.py`, `test_password_strength.py`, `tests/ui/test_acrobat_style_tools_ui.py`)
* Editing and annotations: replaced text, overlay properties saved as shown, annotation undo, stamps, signatures, page undo (`test_native_text_edit.py`, `test_overlay_properties_saved.py`, `test_annotations_store_and_stamps.py`, `test_comments_stamps_signatures_ui.py`, `test_page_undo_and_thumbnail_menu.py`)
* OCR on rotated pages, area OCR, text export, language packs (`test_ocr_area_rotation_and_export.py`, `test_ocr_language_packs.py`, `test_ocr_text_ui.py`)
* Page sizes and save fidelity (A0–A6, US sizes, custom, rotation, boxes, UserUnit, colours, CMYK) (`test_page_sizes_and_save_fidelity.py`); printing with a real PDF print target (`test_printing_options_and_output.py`)
* Conversions: PowerPoint slide geometry and size policies, Word sections, Office metadata (`test_office_metadata_and_pptx_sizes.py`); Office round trips through LibreOffice or Microsoft Office (`test_office_round_trip.py`, category external_app); batch conversion (`test_batch_convert.py`, `test_batch_convert_ui.py`)
* Compression: exact byte targets 500 KB–2 MB, quality floors, honest failure, cancel, atomic writes, Unicode paths, protection kept (`test_compress.py`); dialog, unsaved changes, Save a Copy (`test_compress_and_save_copy_ui.py`)
* Packaging: Windows runtime dependencies and app-local VC++ runtime (`test_windows_runtime_packaging.py`), code-signing readiness and reproducible PE timestamps (`test_code_signing_readiness.py`)
* Installer: `scripts\test_installer.ps1`
* Release tooling: release-note validation, release-set verification, portable Installer ZIP names (`test_release_notes_validation.py`, `test_verify_release.py`), test categories (`test_test_categories.py`), pinned OCR staging and verification (`test_stage_ocr_engine.py`), source-archive contents (`test_source_archive.py`), build-script pitfalls (`test_release_scripts.py`)
* Audit tools (`scripts\audit\`): installed-copy file/registry audit, isolated run of an installed copy (modules, sockets, profile writes), generated inputs and an independent verifier for real-GUI sessions, timing of page design / redaction / merge / Images to PDF
* Checks against the maintainer's own PDFs, when present on that computer (not in the repository)

## Installer and uninstaller test

`scripts\test_installer.ps1` installs Setup, launches the app, checks registrations/shortcuts/self-check, uninstall/reinstall, upgrade and internal-compatibility matrices. The upgrade sections build a Setup of the next patch version from the current payload on every run. Everything is installed for the current user into test folders; the elevated (all-users) case is skipped unless the script runs in an elevated PowerShell. Logs and the backup of your Monograph PDF / PDF Editor settings under `build\installer-test\` (an earlier run's folder is renamed, never deleted); at the end every backed-up settings file is checked by SHA-256 after the restore. Run it from a normal PowerShell window: inside an app package (for example a terminal started by a packaged app) AppData is virtualised, so the script refuses to run there.

Before a release, also install the previous published Setup and upgrade it with the new one (same test folder): settings, documents and unrelated files must be kept, and the self-check must pass.

**Release validation is done by the maintainer on real Windows test computers** (no virtual machines), following [WINDOWS_RELEASE_TEST_CHECKLIST.md](WINDOWS_RELEASE_TEST_CHECKLIST.md). `scripts\windows_release_check.ps1` supports it and only reads (release-file hashes, installed copies and their trusted update keys, the installed program's offline self-check with a temporary settings folder, optional copy of the logs). `scripts\test_installer.ps1` installs, upgrades and uninstalls and backs up and restores the Monograph PDF settings folders, so run it only on a test computer, not on the everyday work account; use test settings with recognizable dummy values. An item that was not done is recorded as **NOT TESTED**, never as passed.

## Updates, problem reports and international tests

* Update security (synthetic keys only): `test_update_crypto.py` (RFC 8032 vectors, OpenSSL
  cross-check), `test_update_manifest.py` (signatures, keys, expiry, replay, channels, identity,
  architecture, downgrade, unreachable sources), `test_update_net.py` (local HTTPS mock server with a
  generated test CA: TLS, redirects, sizes, rate limits, timeouts, interrupted and cancelled downloads),
  `test_update_staging.py` (cleanup rules, links, disk space, lock), `test_update_install.py`
  (installation detection, hand-off record, Setup arguments, helper source checks), `test_update_ui.py`.
* Update-signing tools (synthetic keys only): `test_update_signing_key.py` (encrypted key file,
  console-only passphrases, key generation refusals, self-test), `test_update_signing_key_pkcs8.py`
  (standard PKCS#8 copy, tamper detection, weak-parameter refusal, OpenSSL interoperability; needs
  `cryptography`), `test_update_signing_bundle.py` (stand-alone signing bundle, multi-copy self-test,
  secret scan), `test_update_manifest_release_check.py` (`verify_release.py`'s manifest check).
* Direct upgrades: `test_update_direct_upgrade.py` (skipped versions, long gaps, expiry, key-rotation
  bridge, refused paths with the manual option, interrupted downloads and installations) and
  `test_user_prefs_migration.py` (settings layout migrations, wrong types, newer settings kept,
  unreadable file kept aside, atomic saving).
* Problem reports: `test_diagnostics.py` (privacy filtering, schema, consent, offline sending,
  crash and termination records), `test_report_gateway.py` (validation, limits, injection, GitHub
  permission isolation; GitHub mocked).
* International: `test_international.py` (Unicode folders and file names, temporary folders,
  subprocess arguments, update staging, locale independence; OCR with Unicode paths when the engine
  is installed). These are simulations on the test machine, not verification on localized Windows.
* `cryptography` is needed only by some of these tests (test certificates, OpenSSL cross-check, the
  gateway's token signing); they are skipped where it is not installed. CI installs it
  (`requirements-ci.txt`); the application does not use it.
* Windows end-to-end upgrade: `scripts\test_update_e2e.py --certs <test CA folder>` builds two test
  versions of the current commit, installs the first per user into a Unicode folder, upgrades it
  through the real helper and Setup, checks preserved choices, settings and files, failure paths and
  cleanup, then uninstalls and restores the user's Monograph PDF folders
  ([AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md#testing)).

## Security tests

`tests/unit/test_security_hardening.py`, `tests/ui/test_security_ui.py` — safe paths, full-path process starts, no network, encryption preserved on Save As.

## Related

[BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md) · [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)
