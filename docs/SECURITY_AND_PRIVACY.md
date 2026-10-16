# Security and privacy

This document is the technical reference for how Monograph PDF protects documents and the computer it runs on. The user-facing summary is in the [User Guide](USER_GUIDE.md#troubleshooting); the release-candidate audit is in [SECURITY_AUDIT_0.2.0.md](../reports/audit/SECURITY_AUDIT_0.2.0.md).

## Offline by design

- All Monograph PDF processing is local. No account, login, cloud API, online OCR, telemetry, analytics, advertising, update check or remote document processing.
- Monograph PDF does not upload documents, file names, contents, metadata, passwords, usage information or personal information, and it does not listen for network connections.
- No code, plugins, OCR models, updates or dependencies are downloaded at runtime. Monograph PDF runs only its installed components and explicitly supported locally installed applications.
- Optional Microsoft Office / LibreOffice: Monograph PDF does not upload the document. Conversion uses the locally installed suite, which follows its own settings and remote-content behavior.

### Network-capable code in the release

| Component | Network capability | Why it is there | Status in the release |
| :--- | :--- | :--- | :--- |
| Python standard library (`socket`, `urllib`, `http`, …) | Can open connections | Part of the Python runtime; imported by some libraries | Not used by Monograph PDF. The bundled Python runtime has no SSL/TLS support used by Monograph PDF (`_ssl.pyd` and `libssl` are removed). The self-check refuses and reports any connection attempt or host-name lookup |
| Qt Network, TLS backends, network information, TUIO touch (UDP) | Sockets, TLS, UDP listener | Collected automatically by PyInstaller's Qt hooks | Removed from the build (`check_release.py prune`) |
| OpenCV FFmpeg video plugin | Network streams | Part of the OpenCV wheel | Removed from the build |
| Tesseract OCR | URL input when built with libcurl | OCR engine | This build has no libcurl; it is started only with local file paths |
| `scripts\fetch_fallback_fonts.py` | Downloads fonts | Development-time font fetch | Not part of the release |
| `ms-settings:` links, `explorer.exe` | Open Windows Settings or File Explorer | **Help ▸ Set as Default PDF App**, **Show in Folder** | Local Windows features; no network |

The release check (`scripts\packaging\check_release.py`) fails a build that contains the removed parts or any program file not listed in `THIRD_PARTY_NOTICES.md`.

## Untrusted input

PDFs, Office documents, images, fonts, metadata, attachments and OCR input are treated as untrusted.

- **PDF parsing** is done by MuPDF. A malformed file fails with an error message; it never changes the file on disk.
- **PDF JavaScript, actions and links are never run.** MuPDF's JavaScript support is not enabled (form calculations, `OpenAction` and field scripts are ignored), links are not followed, and launch actions are not executed.
- **Attachments** are only listed (name and size); Monograph PDF never extracts or opens them.
- **File types** are chosen by extension and checked by the engine that opens them: PDFs by MuPDF, images by Pillow/MuPDF, Office files only by an installed office suite.
- **Office macros** are never enabled by Monograph PDF: Microsoft Office is driven with `AutomationSecurity = 3` (macros forced off) and files are opened read-only; LibreOffice runs headless with a throw-away profile that sets Very High macro security and disables macro execution. File names are passed to PowerShell in environment variables, never pasted into script text.
- **Names written to disk**: files written into a folder the user chose (Split, PDF to Images, Extract Images) get plain names made from page numbers, bookmark titles or the document name, with folder parts, `..`, reserved names and invalid characters removed; an existing file is never replaced (`name (2).pdf` is used instead).

## Programs Monograph PDF starts

| Program | When | How |
| :--- | :--- | :--- |
| `engines\ocr\tesseract.exe` | OCR, About box version | Full path inside the installation, argument list (no shell), fixed options, hidden window, time limit |
| `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` | Office → PDF and Word reflow with Microsoft Office | Full path, `-NoProfile -NonInteractive -Command` with a fixed script; no execution-policy change |
| LibreOffice `soffice.exe` | Office → PDF with LibreOffice | Only from `Program Files\LibreOffice\program` or the path LibreOffice registered; argument list; throw-away profile |
| `%SystemRoot%\explorer.exe` | **Show in Folder** | Full path, argument list |
| `%SystemRoot%\System32\rundll32.exe printui.dll` | **Printing preferences…** | Full path |

Programs are always started by full path, so a same-named program in the current folder (for example a downloaded `explorer.exe` next to a PDF) is never run. The built app loads Python modules only from inside its bundle, and its DLLs from its own folder (PyInstaller restricts the DLL search path).

## Passwords and sensitive data

- Passwords are typed into masked fields (shown only after **Show password** is selected) and kept in memory while the document is open, so that **Save** can keep the protection. They are never written to logs, settings, the recent-files list, recovery data or reports.
- **Save** and **Save As** keep a protected PDF's encryption, passwords and permissions. Protection is removed only by **Protect ▸ Unlock PDF (Remove Password)…** after the correct password is entered.
- No recovery copy is kept for a password-protected PDF (recovery copies are not encrypted).
- Printing, copies and conversions of a protected PDF use a short-lived unencrypted working copy in `%LOCALAPPDATA%\Monograph PDF\runtime\temp`, deleted as soon as the job ends (and at the next start after a crash, once older than a day).
- Logs contain timings and self-check results only — no document contents, form values, signatures or clipboard data.

Encrypted PDFs are handled locally by PyMuPDF (AES-256, or AES-128 when chosen). Permissions passwords are enforced by PDF readers, not by cryptography; treat them as a policy rather than a security boundary.

## Data stored on the computer

| Kind | Location | Contents | Removed by uninstall |
| :--- | :--- | :--- | :--- |
| Application files | Installation folder (`C:\Program Files\Monograph PDF`, or `%LOCALAPPDATA%\Programs\Monograph PDF` for a current-user installation) | Program, libraries, OCR engine and data, documentation, uninstaller — nothing else | Always |
| Settings | `%APPDATA%\Monograph PDF\preferences.json` | Theme, window layout, recently used fonts and colors | With complete removal (or `/REMOVEUSERDATA`) |
| Recent files | `%APPDATA%\Monograph PDF\recent_files.json` | Paths of recently opened files (never passwords) | Always |
| Working files | `%LOCALAPPDATA%\Monograph PDF\runtime` (`cache`, `temp`, `logs`) | Page cache, temporary copies, timing logs | Always |
| Recovery copies | `%LOCALAPPDATA%\Monograph PDF\runtime\sessions` | Unsaved text boxes, form entries and other edits of unprotected PDFs | Always |
| Setup self-check report | `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` | Results of Setup's self-check (no user data) | Always |
| Short-lived work folders | `%TEMP%\monographpdf*`, `%TEMP%\monograph-pdf-theme` | Conversion and OCR scratch files, theme images | Always (skipped while Monograph PDF is running) |
| Registry | Open with, file types, Default apps, App Paths, Installed apps | Created by Setup only | Always |
| Your documents | Wherever you save or export them | Saved PDFs, copies, conversions, images | **Never** |

Monograph PDF writes nothing into its installation folder while it runs, creates no startup entries, scheduled tasks, services, firewall rules or browser extensions, and writes no other registry values. A per-machine installation in Program Files is read-only for standard users; a current-user installation lives in the user's own profile, like other per-user applications.

## Installer and uninstaller

- Setup asks for administrator rights only for an all-users installation (it offers a current-user installation without them), installs program files only into the installation folder, and registers only the documented file types (`.pdf`, plus Open with for images and Office files) and the Default apps entry.
- During an upgrade, Setup removes files belonging to the previous installation (previous `{app}\installed_files.txt` when present, otherwise a conservative allowlist) before installing the new files. Unknown or user-created files in the selected folder are preserved. The destination folder is never deleted wholesale; paths are validated (no `..`, no drive roots, no profile/system roots, no reparse-point follow). When migrating to a new folder, owned files at the old path are removed only after the new install passes its offline self-check; settings (`%APPDATA%\Monograph PDF`) and documents are never removed merely because the install directory changed. Unregistered look-alike folders are not deleted. Setup refuses to proceed while `MonographPDF.exe` from the relevant installation is running.
- Setup never sets the default PDF app (Windows protects that choice) and never copies or deletes user data.
- **Internal compatibility** (not user-facing): Setup keeps a stable AppId so an earlier *internal* development build on the same machine is recognised and upgraded in place (one *Installed apps* entry). At first start, settings, recent files and recovery sessions may be copied from that earlier build's folders if present (`core/legacy_migration.py`: no deletion, no link following; cache, temporary files and logs never copied; a path-only record is written under `%APPDATA%\Monograph PDF`). The uninstaller removes those earlier folders only with proven provenance and only when no program of that build remains. Deprecated environment-variable aliases from earlier internal builds are documented in [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md).
- Setup's self-check runs the installed program with a working folder inside Setup's own temporary folder.
- The uninstaller removes the program, shortcuts, file-type and Default apps registrations, the Installed apps entry, the recent-files list and working files; settings only with consent (complete removal) or `/REMOVEUSERDATA`. It never removes user documents.
- Removal is bounded: it deletes only folders named `Monograph PDF` inside the user's `%APPDATA%` or `%LOCALAPPDATA%` — never a folder that contains the installation folder, never a junction or symbolic link, and only `%TEMP%` folders whose names start with `monographpdf` (or are `monograph-pdf-theme`).
- `uninstall.exe` starts the Inno Setup uninstaller and waits for it. It moves itself to `%TEMP%` while waiting (so the installation folder can be removed); if the uninstall is cancelled, it restores itself from the copy it read into memory at start, never from the file in `%TEMP%`, and it starts its clean-up commands by full path.

## Release integrity

- `scripts\packaging\check_release.py` checks the built application and the release folder: only known components, nothing the build removes, no keys, secrets, environment files, development folders or private paths.
- `installer\release\SHA256SUMS.txt` lists the SHA-256 of `Setup.exe`, `MonographPDF.exe` and `MonographPDF_<version>_Source.zip`; the source archive is checked like the release (hashes of every third-party archive, no development files, secrets or private paths in Monograph PDF's source); a released version is frozen — the release build will not overwrite another version's unarchived release folder; `installer\build_release_summary.txt` records version, build time, test and self-check results.
- **The build is not code-signed.** Windows SmartScreen may warn about an unrecognized app; compare the SHA-256 checksum with the published one, then choose **More info ▸ Run anyway** only for a file you trust. Never turn off Microsoft Defender, SmartScreen or other security software to install Monograph PDF.

## Dependency and license risk

See `licenses/DEPENDENCY_INVENTORY.md` and `THIRD_PARTY_NOTICES.md`. The AGPL (Monograph PDF, PyMuPDF/MuPDF), GPL (pdf2docx, JBIG-KIT) and LGPL (Qt/PySide6, the OCR engine's GLib, Pango, cairo and others) require the corresponding source with binary releases: every release is published with `MonographPDF_<version>_Source.zip`, and the release build fails if a release file needing source is not covered by it. The third-party source archives are downloaded only by the build (into `packages\sources`) and verified by SHA-256; Monograph PDF itself never downloads anything.

## Development overrides

`MONOGRAPH_PDF_RUNTIME_DIR`, `MONOGRAPH_PDF_USER_DATA_DIR` and the other `MONOGRAPH_PDF_*` variables (see [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md#environment-variables-development-and-testing)) only redirect folders or switch off dialogs for development, tests and Setup's self-check; none enables network access or weakens a protection.

## Secure coding rules

- Start external programs by full path with argument lists; never `shell=True`, never a program name looked up in the current folder or `PATH` on Windows.
- Pass file names to scripts in environment variables or arguments, never inside script text.
- Write generated names with `core.safe_paths.safe_child`; write only inside the user's chosen folder or Monograph PDF's working folders.
- Never enable MuPDF JavaScript or follow PDF actions.
- No network code; the offline guard (`app/offline_guard.py`) must stay green in the self-check and tests.
- Test artifacts must not escape into the repository root or the user's real settings.

## Related

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Testing: [TESTING.md](TESTING.md#security-tests)
- Security policy (reporting): [../SECURITY.md](../SECURITY.md)
