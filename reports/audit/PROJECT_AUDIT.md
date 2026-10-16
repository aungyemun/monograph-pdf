# Monograph PDF — Project Audit

Canonical functional audit record (security, privacy, dependencies and licenses of the last internal build: [SECURITY_AUDIT_0.1.5.md](SECURITY_AUDIT_0.1.5.md); release candidate: [SECURITY_AUDIT_0.2.0.md](SECURITY_AUDIT_0.2.0.md)). Update these files in place; do not create FINAL/status variant copies. The 0.1.5 entries below are the record of an internal development build (not a public release).

## 0.2.0 — Unreleased (first public release)

| Field | Value |
|---|---|
| Audit date | 2026-10-16 |
| VERSION | 0.2.0 (Unreleased — not frozen) |
| Canonical exe | `./MonographPDF.exe` (+ `_internal/` onedir payload); `dist/MonographPDF/` |
| Release (build output, not published) | `installer/release/`: `Setup.exe`, `MonographPDF_0.2.0_Source.zip`, `SHA256SUMS.txt`, documentation; `installer/MonographPDF_0.2.0_Installer.zip` |
| Internal development archive | last internal build 0.1.5, kept unchanged in `releases/PDFEditor_0.1.5/` (not a public release) |
| Tests (Windows) | unit + UI + integration suites (`scripts/build_release.ps1`, `pytest tests\unit tests\ui tests\integration`) |
| Installer test | `scripts/test_installer.ps1`, including the internal-compatibility matrix for earlier internal builds (sections 14–21) |
| Branding scan | `scripts/packaging/branding_scan.py` (repository and built application) |

Scope: product identity (name, executable, PE version resource, About, Start page, window and taskbar icon, Help menu), new logo and icon set, Setup (AppId kept, legacy detection, Existing installation found page, in-place and moved upgrades, registry / shortcut / Open with migration, uninstall), per-user data migration, environment-variable aliases, temporary-folder names, source archive and checksums naming, documentation, and the protection of the frozen 0.1.5 release.

Results are recorded in the release review for 0.2.0; 0.2.0 stays Unreleased until the maintainer approves the release freeze.

## 0.1.5 — internal development build (2026-10-15)

| Field | Value |
|---|---|
| Audit date | 2026-10-15 |
| VERSION | 0.1.5 |
| Canonical exe | `./PDF_editor.exe` (+ `_internal/` onedir payload) |
| Release | `installer/release/`: `Setup.exe`, `PDFEditor_0.1.5_Source.zip`, `SHA256SUMS.txt`, documentation; `installer/installer.zip` (kept in `releases/PDFEditor_0.1.5/`) |
| Tests (Windows) | unit + UI suite, all passing (run by `scripts/build_release.ps1`) |
| UI audit | every menu (File, Edit, View, Insert, Forms, Organize, Convert, OCR, Protect, Sign, Help) and toolbar item, alone and in combination: 32 scenarios, 408 checks (`build/deep_ui_audit.py`, not shipped) |
| Installer test | install → use → uninstall → reinstall (`scripts/test_installer.ps1`), all checks passing |

### Method

1. **UI and outputs** — the audit drives the real main window: every menu item and toolbar button, dialogs filled automatically, results opened and checked (text, pages, protection, images, Office files), on-screen text checked for clipping; combinations such as fill + text box + shape + rotate + save + reopen, protect → reopen → fill → save, OCR → find → redact → save, undo/redo of everything. Every step has a time limit.
2. **Static** — `ruff` (pyflakes rules, syntax errors); Python warnings during the test suite.
3. **Release** — release contents check, self-check of the built app, installer test, source archive check (see `docs/TESTING.md`).

### Findings fixed in 0.1.5

| # | Area | Finding | Fix |
|---|---|---|---|
| 1 | Output | Save a Copy, Reduce File Size, Watermark, Header & Footer, Split, Extract / Copy Pages, Protect, Unlock, Remove Metadata and PDF → other formats ignored unsaved edits | They use the document as shown |
| 2 | Output | Saving a password-protected PDF removed the password | Save / Save As keep encryption and permissions |
| 3 | Output | Reduce File Size failed (“'str' object has no attribute 'value'”) | Preset value accepted |
| 4 | Edit | Shapes and images could not be undone | Undo / redo commands |
| 5 | Output | Choosing the open PDF as an export target failed with “file in use” | Explained; another name asked for |
| 6 | Protect | Mark Text for Redaction marked only the page in view | Marks every page |
| 7 | UI | Empty submenus and Insert ▸ Shapes enabled without a document; disabled toolbar arrows looked enabled | Disabled correctly |
| 8 | UI text | Conversion Quality Guide cut off, raw permission / metadata values, About default button | Readable table, plain labels, Close default |
| 9 | Print | Paper defaulted to Letter for A4 documents | Starts on the document's paper |

## Known limitations (unchanged in 0.2.0)

- Signatures are visual only (not certificate-based digital signatures).
- PDF → Excel / PowerPoint are best-effort (tables from ruled lines; slides as page images).
- Fonts in saved form fields and text boxes use standard faces (Helvetica / Times / Courier look-alikes and an embedded Japanese font), not the exact Windows fonts.
- Japanese vertical writing is not laid out.
- Office → PDF takes several seconds per file (Word / Excel / PowerPoint are started in the background).
