# Installer package contents

A release consists of three files, each listed in `SHA256SUMS.txt`:

| File | What it is | For |
|---|---|---|
| `MonographPDF_<version>_Setup.exe` | the self-contained installer | installing (everything needed is inside) |
| `MonographPDF_<version>_Installer.zip` | the same `Setup.exe`, plus licences, notices and the user guide | people who want the documents next to the installer |
| `MonographPDF_<version>_Source.zip` | the source code at the release commit (AGPL-3.0 corresponding source) | building from source; **not** an installer |

There is no portable (unzip-and-run) edition.

## Setup.exe

Setup.exe is an Inno Setup 6 installer. It needs no internet access and installs no prerequisite (see [PREREQUISITE_MANAGEMENT.md](PREREQUISITE_MANAGEMENT.md)). It installs:

| Part | Content |
|---|---|
| `MonographPDF.exe` | the program (PyInstaller launcher), x64 |
| `_internal\` | Python 3.11 runtime, Qt 6.8 / PySide6 with the `qwindows` platform plugin, MuPDF, Pillow, NumPy, OpenCV, lxml, the conversion libraries, the Visual C++ runtime DLLs, the application's resources (icons, logo, OCR language-pack pins, update and reporting configuration, build provenance) |
| `engines\ocr\` | Tesseract OCR 5.4.0 and its libraries |
| `models\tessdata\` | `eng`, `jpn`, `osd` language data (tessdata_fast 4.1.0) |
| `uninstall.exe`, `MonographPDFUpdater.exe` | the uninstaller and the update helper |
| licences and notices | `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `licenses\`, the OCR and font notices |

### How the contents are checked

The release build verifies the following, and stops on any failure (`scripts/build_release.ps1`):

- **Installed-files list.** The build writes the list of every file the installer places, `build\installer\installed_files.json` (500 paths for 0.3.0 and 0.4.0). It is shipped as `installed_files.txt`; when upgrading, Setup removes only files on that list that the new version no longer has.
- **Release-set check** (`scripts/packaging/check_release.py`):
  - the required components are present;
  - OCR engine and data match the SHA-256 pins, with no extra files;
  - no stale branding;
  - size per component.
- **Release-set verification** (`scripts/packaging/verify_release.py`):
  - artifact names and checksums, and ZIP entry names;
  - notices and version consistency;
  - privacy scan, OCR presence and update-trust configuration (equal to the committed files);
  - provenance (the program names the commit the source archive was made from).
- **Runtime-dependency check** (`scripts/packaging/runtime_dependencies.py --check`).
- **`MonographPDF.exe --smoke-test`.**

The package checks of the 0.4.1 release build found the same layout expectations as 0.4.0
(tag `v0.4.0`, commit fc411e2) and 0.3.0 (tag `v0.3.0`, commit 96c36b9):

- Hundreds of files in the installation layout (exact count is recorded in
  `build\installer\installed_files.json` for that build).
- Present: the program, the Python DLL, the Qt platform plugin, MuPDF, the VC++ and UCRT DLLs,
  Tesseract, the three language files, the icon and logo, and the update configuration.
- No test or build-tool files.
- The `Setup.exe` inside the Installer ZIP is byte-identical to the standalone `Setup.exe`.

`scripts/test_installer.ps1` then installs the real Setup.exe into a test folder and checks the files,
registrations, shortcuts and self-check, launches the program, uninstalls, and tests upgrades. Whether
that suite was run for a given release is stated in that release's notes
([docs/releases/](releases/)).

## Installer ZIP

The published `MonographPDF_0.4.1_Installer.zip` (same layout as 0.4.0 and 0.3.0) contains these
entries and nothing else:

```
Setup.exe                     (identical to MonographPDF_0.4.1_Setup.exe)
README.md  INSTALLATION.md  CHANGELOG.md  SECURITY.md  CITATION.cff
LICENSE.md  THIRD_PARTY_NOTICES.md  SHA256SUMS.txt  docs/USER_GUIDE.md
licenses/GPL-2.0.txt  licenses/GPL-3.0.txt  licenses/LGPL-2.1.txt  licenses/LGPL-3.0.txt
licenses/MPL-1.1.txt  licenses/GCC-exception-3.1.txt
runtime/fonts/OFL.txt  runtime/ocr/TESSERACT_NOTICE.txt
```

The ZIP contains no older versions, no build artifacts and no prerequisite installers. Application files are not duplicated outside `Setup.exe`.
