# Monograph PDF Installation Guide

Monograph PDF is a self-contained, offline Windows application. It is the successor to PDF Editor (final release 0.1.5). This guide covers system requirements, installation, upgrading from PDF Editor, file-type registration, uninstall, offline install testing and troubleshooting.

## System Requirements

| Requirement | Minimum | Recommended |
| :--- | :--- | :--- |
| OS | Windows 10 64-bit | Windows 11 64-bit |
| RAM | 4 GB | 8 GB or more for large scanned documents |
| Disk | 1 GB free | 2 GB free |
| Display | 1280 × 720 | 1920 × 1080 or higher (high-DPI supported) |
| Office suite | Not required | Microsoft Office or LibreOffice, for Word / Excel / PowerPoint to PDF |
| Internet | Not required | — |

Python, Qt, Tesseract and the other runtime components are bundled. Nothing else needs to be installed for core Monograph PDF features.

## End-User Installation

Run `Setup.exe` (the release copy of `installer\MonographPDF_{version}_Setup.exe`).

Setup offers two install modes:

* **Install for all users** (recommended, needs administrator rights) — installs to `C:\Program Files\Monograph PDF`
* **Install for me only** — installs to `%LOCALAPPDATA%\Programs\Monograph PDF` without administrator rights

Setup.exe does the following:

1. If Setup finds an existing Monograph PDF installation, it uses that installation location by default. If it finds **PDF Editor**, it shows **Upgrade to Monograph PDF** (see [Upgrading from PDF Editor](#upgrading-from-pdf-editor)). If you choose a different folder, Setup asks whether to:
   - **Upgrade using the existing installation location** (recommended), or
   - **Install Monograph PDF in the new location and remove the previous application** from the old location.
   User settings and documents are preserved in either case.
2. During an upgrade, Setup removes files belonging to the previous application before installing the new application files (using the previous owned-file list `installed_files.txt` when present, otherwise a conservative allowlist of known application folders and files such as `PDF_editor.exe`). Unknown or user-created files in the selected folder are preserved. Settings and the recent-files list are kept on upgrade; your documents are never removed. On a **new** installation (no earlier installation registered) Setup starts with an empty recent-files list and clears leftover working files.
3. Copies `MonographPDF.exe` and its `_internal` runtime folder.
4. Copies the offline OCR engine (`engines\ocr`) and language data (`models\tessdata`).
5. Copies the license, third-party notices, changelog, User Guide (`docs\USER_GUIDE.md`), security policy, license texts (`licenses\`) and `uninstall.exe`.
6. Registers Monograph PDF with Windows for the selected file types (see below) and in **Settings ▸ Apps ▸ Installed apps**.
7. Runs a short offline self-check (`MonographPDF.exe --smoke-test`) of the PDF engine, rendering, encryption, PDF to Word conversion, OCR and the main window. The report is saved as `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` (the installation folder holds only Monograph PDF's own files — no user documents or logs).
8. Creates Start menu shortcuts in the **Monograph PDF** folder if **Create Start Menu shortcuts** is checked (checked by default): **Monograph PDF** and **Monograph PDF User Guide** (opens the guide in Monograph PDF's own viewer). Creates a desktop shortcut if **Create a Desktop shortcut** is checked.

### Choosing a different installation folder

If Monograph PDF is already installed and you pick another folder, Setup shows a clear choice:

* **Upgrade using the existing installation location** (recommended) — keeps Monograph PDF where it already is and replaces the previous version. Settings and documents are preserved; nothing is left in the folder you briefly selected.
* **Install Monograph PDF in the new location and remove the previous application** — installs into the new folder, verifies the new copy, then removes only the previous application files from the old folder. Unknown or user-created files in the old folder stay. Settings (`%APPDATA%\Monograph PDF`) and documents are preserved.
* **Go back** — return to the folder page without changes.

Upgrading in the same folder removes owned application files first, then installs the new version, and replaces shortcuts (or removes them if their task is now unchecked).

## Upgrading from PDF Editor

PDF Editor has been renamed to Monograph PDF. Version 0.1.5 was the final PDF Editor release; Monograph PDF 0.2.0 is its successor and upgrades it — you do not need to uninstall PDF Editor first, and only one installed application remains afterwards.

When Setup finds PDF Editor (through its Installed apps entry, `InstallLocation`, uninstall command, App Paths entry, the default folders `C:\Program Files\PDF Editor` / `%LOCALAPPDATA%\Programs\PDF Editor`, or — as a last resort — a verified **PDF Editor** Start menu shortcut), it shows **Upgrade to Monograph PDF**:

> PDF Editor has been renamed to Monograph PDF.
>
> An existing PDF Editor installation was found at: *OLD_PATH*
>
> Monograph PDF can upgrade your existing installation while preserving your settings and documents.

* When PDF Editor is in a folder named **PDF Editor** (the default), the recommended choice is **Install Monograph PDF in …\Monograph PDF and remove the previous PDF Editor application**. Setup installs Monograph PDF in the renamed folder (for example `C:\Program Files\Monograph PDF`), checks that it works, and only then removes PDF Editor's application files from the old folder. Files you added to the old folder are kept; the old folder is removed only if it is then empty. If the new folder already exists with other content, this choice is not offered.
* **Upgrade using the existing installation location** keeps the current folder: `PDF_editor.exe` is replaced by `MonographPDF.exe` in place. This is the only choice for a PDF Editor folder with another name.
* **Back** returns to the previous page without changes.

In both cases Setup:

* refuses to continue while `PDF_editor.exe` (or `MonographPDF.exe`) is running;
* replaces the Installed apps entry (same application ID, now **Monograph PDF**, icon `MonographPDF.exe`, `uninstall.exe` as uninstall command), the App Paths entry, **Open with** and Default apps registrations, and the Start menu and desktop shortcuts. PDF Editor's entries (`PDF_editor.exe`, `PDFEditor.Document`, `PDFEditor.Convertible`, the **PDF Editor** Start menu folder and desktop shortcut) are removed once its program is gone;
* leaves an unregistered second PDF Editor copy elsewhere untouched (it is only noted in the Setup log).

Your settings move with you. The first time each Windows user starts Monograph PDF, it copies that user's PDF Editor settings (`%APPDATA%\PDF Editor\preferences.json`), the recent-files list (entries that still exist) and any unsaved-edit recovery sessions into the Monograph PDF folders. Cache, logs and temporary files are not carried over. The PDF Editor folders are left unchanged; uninstalling Monograph PDF later removes them as well, but only for a user whose data Monograph PDF migrated and only when no PDF Editor program remains.

If you had chosen PDF Editor as your default PDF app, Windows asks you once to pick the app again (Windows does not let Setup make that choice for you) — choose **Monograph PDF**, or use **Help ▸ Make Monograph PDF the Default PDF App…**.

### Silent install (administrators)

```bat
MonographPDF_0.2.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
MonographPDF_0.2.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /MIGRATEINSTALL
MonographPDF_0.2.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="D:\Apps\Monograph PDF" /MIGRATEINSTALL
```

* Same registered destination (or omit `/DIR`): automatic in-place upgrade — also for PDF Editor, which keeps its folder.
* Different `/DIR` **without** `/MIGRATEINSTALL`: Setup keeps the existing registered location (no duplicate registered install).
* `/MIGRATEINSTALL` **with** a different `/DIR`: install at the new path, then remove owned application files from the old path after the new install is validated.
* `/MIGRATEINSTALL` **without** `/DIR`, upgrading PDF Editor in a folder named `PDF Editor`: install in the renamed `Monograph PDF` folder next to it, then remove PDF Editor's files from the old folder.
* A silent upgrade stops without changes while `PDF_editor.exe` or `MonographPDF.exe` is running.

No internet connection is required during installation or for core Monograph PDF use. Optional Office conversion uses a suite already installed on the computer; Monograph PDF does not upload the document, but that suite follows its own settings and remote-content behavior.

## File Types And Default App

Setup's **File types** page offers:

| Option | Default | What it does |
| :--- | :--- | :--- |
| Register Monograph PDF for PDF files (.pdf) | Checked | Adds Monograph PDF to **Open with** for `.pdf`, and to **Settings ▸ Apps ▸ Default apps** |
| Add Monograph PDF to Open with for images and Word, Excel and PowerPoint files | Checked | `.png .jpg .jpeg .tif .tiff .bmp .gif .webp`, `.docx .doc .rtf .odt`, `.xlsx .xls .csv .ods`, `.pptx .ppt .odp` — these open as a new PDF |

Windows 10 and 11 do not let an installer silently replace your default PDF app, and Setup never tries. To make Monograph PDF the default:

* Tick **Make Monograph PDF the default PDF app** on Setup's last page, or
* In Monograph PDF choose **Help ▸ Make Monograph PDF the Default PDF App…**, or
* Right-click any PDF ▸ **Open with ▸ Choose another app** ▸ **Monograph PDF** ▸ **Always**.

## Uninstallation

Open **Settings ▸ Apps ▸ Installed apps**, find **Monograph PDF** and choose **Uninstall**. You can also run `uninstall.exe` in the installation folder. (Following current Windows practice, Setup does not add an uninstall shortcut to the Start menu.)

If Monograph PDF is running, the uninstaller asks you to close it first. After you confirm, it asks whether to **also remove your settings**.

| | Removed | Kept |
| :--- | :--- | :--- |
| Application | Installation folder: `MonographPDF.exe`, `_internal`, OCR engine and language data, documentation, licenses, `uninstall.exe` | Files you added to the installation folder |
| Windows integration | Start menu and desktop shortcuts; **Open with**, file-type, Default apps and Installed apps registrations | — |
| Working files | Recent-files list; `%LOCALAPPDATA%\Monograph PDF` (cache, logs, recovery sessions, temporary files); Monograph PDF and PDF Editor folders in `%TEMP%` | — |
| Settings (`%APPDATA%\Monograph PDF`: theme, window layout, recently used fonts and colors) | When you answer **Yes** (complete removal) | When you answer **No** (default), for a later installation |
| PDF Editor data migrated by Monograph PDF (`%APPDATA%\PDF Editor`, `%LOCALAPPDATA%\PDF Editor`) | Working files always; settings when you answer **Yes** — only if Monograph PDF migrated them for you and no PDF Editor program remains | Otherwise |
| Your documents | Never | PDFs you saved, converted or exported files, and all other files |

Notes:

* Per-user data is removed for the Windows user who runs the uninstaller. Other user accounts on the same computer keep their own settings.
* If a file is in use and cannot be deleted, the uninstaller lists it so you can delete it later.
* Folders that are links (junctions or symbolic links) are never followed.
* No antivirus or security setting needs to be changed to uninstall.

### Silent uninstallation (administrators)

```bat
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REMOVEUSERDATA
```

The first command keeps the user's settings; `/REMOVEUSERDATA` removes them too. A silent uninstall stops without changes if Monograph PDF is running. `uninstall.exe` passes all options to the Inno Setup uninstaller (`unins000.exe`), waits for it and returns its exit code.

## Offline Installation Test

Use this procedure before sending a release to another computer.

Test machine requirements:

* Windows 10/11 x64
* No internet connection
* No Python, Qt or developer tools installed

Procedure:

1. Copy `Setup.exe` (or `MonographPDF_{version}_Installer.zip`) to the test machine.
2. Run Setup and complete it with the default options.
3. Confirm Setup finishes without a self-check warning.
4. Start Monograph PDF from the Start menu; the start screen shows no recent files.
5. Open **Monograph PDF User Guide** from the Start menu.
6. Right-click a PDF in File Explorer ▸ **Open with** and confirm **Monograph PDF** is listed.
7. Open a PDF, fill in a form field, add a text box and save.
8. **Convert ▸ PDF to Word…** and open the result.
9. **Protect ▸ Protect with Password…**, then reopen the file and unlock it.
10. **OCR ▸ OCR Current Page…** on a scanned page.
11. Uninstall from **Settings ▸ Apps** and choose **Yes** to remove settings; then confirm that the installation folder, the Start menu folder, `%APPDATA%\Monograph PDF` and `%LOCALAPPDATA%\Monograph PDF` are gone and **Open with** no longer lists Monograph PDF.
12. Install again and confirm Monograph PDF starts with default settings.
13. On a computer with PDF Editor 0.1.5 installed: run Setup, accept **Upgrade to Monograph PDF**, and confirm the theme and recent files carried over, the Start menu shows only **Monograph PDF**, and **Installed apps** lists only **Monograph PDF**.

Expected result:

* The app starts offline in a few seconds.
* `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` reports `"passed": true`.

Developers can run the automated version of this test, including the PDF Editor 0.1.5 upgrade matrix, with `scripts\test_installer.ps1` (see [Testing](docs/TESTING.md#installer-and-uninstaller-test)).

## Troubleshooting

If Monograph PDF does not start after installation:

1. Run Setup again — it repairs missing files.
2. Check `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` from Setup, or run `"C:\Program Files\Monograph PDF\MonographPDF.exe" --smoke-test` from a Command Prompt and check `%LOCALAPPDATA%\Monograph PDF\runtime\logs\smoke_test.json`.
3. Check `%LOCALAPPDATA%\Monograph PDF\runtime\logs\` for startup logs.
4. Check your antivirus quarantine for `MonographPDF.exe` or files in `_internal`.

If your PDF Editor settings did not carry over, start Monograph PDF once as the same Windows user; the copy is recorded in `%APPDATA%\Monograph PDF\legacy_migration.json`.

If **Word, Excel or PowerPoint to PDF** says no office suite was found, open **Help ▸ About Monograph PDF ▸ Office Integration** to see what was detected. Install Microsoft Office or LibreOffice, or use *Save as PDF* in the application that created the file.

If Monograph PDF does not appear in **Open with**, run Setup again and keep the file-type options checked.

The installer is **not code-signed**; Windows SmartScreen may show a warning. Compare `Setup.exe` with `SHA256SUMS.txt` from the same release before choosing **More info ▸ Run anyway**. Do not disable antivirus software. See [User Guide — Troubleshooting](docs/USER_GUIDE.md#troubleshooting).

## Developers

Source setup, tests, release builds and packaging are documented in [Build and Runtime](docs/BUILD_AND_RUNTIME.md). Release folder rules and versioning: [Release and Versioning](docs/RELEASE_AND_VERSIONING.md).

## License

© 2026–Present Aung Ye Mun. Monograph PDF is licensed under the GNU Affero General Public License v3.0 or later (**AGPL-3.0-or-later**). See [LICENSE.md](LICENSE.md). Corresponding Monograph PDF release source, including application, build, installer, documentation and release tests, together with the corresponding source of the bundled AGPL, GPL and LGPL components, is published as `MonographPDF_{version}_Source.zip` beside the installer. Local personal-document validation utilities are excluded.
