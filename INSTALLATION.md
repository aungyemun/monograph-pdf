# Monograph PDF Installation Guide

Monograph PDF is a self-contained, offline Windows application. This guide covers system requirements, installation, file-type registration, uninstall, offline install testing and troubleshooting.

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

1. If Setup finds an existing Monograph PDF installation, it uses that installation location by default. If you choose a different folder, Setup asks whether to:
   - **Upgrade using the existing installation location** (recommended), or
   - **Install Monograph PDF in the new location and remove the previous application** from the old location.
   User settings and documents are preserved in either case.
2. During an upgrade, Setup removes files belonging to the previous application before installing the new application files (using the previous owned-file list `installed_files.txt` when present, otherwise a conservative allowlist of known application folders and files). Unknown or user-created files in the selected folder are preserved. Settings and the recent-files list are kept on upgrade; your documents are never removed. On a **new** installation (no earlier installation registered) Setup starts with an empty recent-files list and clears leftover working files.
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

### Silent install (administrators)

```bat
MonographPDF_0.2.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
MonographPDF_0.2.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="D:\Apps\Monograph PDF" /MIGRATEINSTALL
```

* Same registered destination (or omit `/DIR`): automatic in-place upgrade.
* Different `/DIR` **without** `/MIGRATEINSTALL`: Setup keeps the existing registered location (no duplicate registered install).
* `/MIGRATEINSTALL` **with** a different `/DIR`: install at the new path, then remove owned application files from the old path after the new install is validated.
* A silent upgrade stops without changes while `MonographPDF.exe` is running.

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
| Working files | Recent-files list; `%LOCALAPPDATA%\Monograph PDF` (cache, logs, recovery sessions, temporary files); Monograph PDF working folders in `%TEMP%` | — |
| Settings (`%APPDATA%\Monograph PDF`: theme, window layout, recently used fonts and colors) | When you answer **Yes** (complete removal) | When you answer **No** (default), for a later installation |
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

Expected result:

* The app starts offline in a few seconds.
* `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` reports `"passed": true`.

Developers can run the automated version of this test with `scripts\test_installer.ps1` (see [Testing](docs/TESTING.md#installer-and-uninstaller-test)).

## Troubleshooting

If Monograph PDF does not start after installation:

1. Run Setup again — it repairs missing files.
2. Check `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` from Setup, or run `"C:\Program Files\Monograph PDF\MonographPDF.exe" --smoke-test` from a Command Prompt and check `%LOCALAPPDATA%\Monograph PDF\runtime\logs\smoke_test.json`.
3. Check `%LOCALAPPDATA%\Monograph PDF\runtime\logs\` for startup logs.
4. Check your antivirus quarantine for `MonographPDF.exe` or files in `_internal`.

If **Word, Excel or PowerPoint to PDF** says no office suite was found, open **Help ▸ About Monograph PDF ▸ Office Integration** to see what was detected. Install Microsoft Office or LibreOffice, or use *Save as PDF* in the application that created the file.

If Monograph PDF does not appear in **Open with**, run Setup again and keep the file-type options checked.

The installer is **not code-signed**; Windows SmartScreen may show a warning. Compare `Setup.exe` with `SHA256SUMS.txt` from the same release before choosing **More info ▸ Run anyway**. Do not disable antivirus software. See [User Guide — Troubleshooting](docs/USER_GUIDE.md#troubleshooting).

## Developers

Source setup, tests, release builds and packaging are documented in [Build and Runtime](docs/BUILD_AND_RUNTIME.md). Release folder rules and versioning: [Release and Versioning](docs/RELEASE_AND_VERSIONING.md).

## License

© 2026–Present Aung Ye Mun. Monograph PDF is licensed under the GNU Affero General Public License v3.0 or later (**AGPL-3.0-or-later**). See [LICENSE.md](LICENSE.md). Corresponding Monograph PDF release source, including application, build, installer, documentation and release tests, together with the corresponding source of the bundled AGPL, GPL and LGPL components, is published as `MonographPDF_{version}_Source.zip` beside the installer. Local personal-document validation utilities are excluded.
