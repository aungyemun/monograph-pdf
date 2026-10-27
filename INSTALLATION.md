# Installation

Use the official [Releases](https://github.com/aungyemun/monograph-pdf/releases) and select
the platform explicitly. Published Windows is 0.4.0; Windows 0.5.0 remains an unpublished draft.
macOS 0.1.0 is published; Linux 0.1.0 is available from source. Development uses unified `main`.

## Linux

No Linux release tag is published yet. Build from `main`; see [Linux setup](LINUX.md).

```bash
git clone --branch main https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

The optional `installer/linux/install.sh` installs an already built native application tree.
It is not a source-to-package build command. Dependencies and OCR data must be installed before
offline use; Office conversion needs LibreOffice.

## macOS

Published [v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)
provides zip/dmg/pkg assets. Compare their SHA-256 values with the release notes before opening.
See [macOS setup, packaging and signing limitations](docs/MACOS.md). Unified source builds use
`main`, Python 3.11 and native macOS tools. Local ad-hoc signing is not Developer ID or notarization.

## Windows

**Published:** [v0.4.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.4.0).
**Prepared (not public yet):** 0.5.0 (draft). Do not use the repository-wide GitHub “Latest” link
for Windows downloads while it may point at macOS.

Monograph PDF is installed with a standard Windows installer. Everything it needs — including
Python, Qt and the OCR engine — is included, and no internet connection is required.

## System requirements

| | Minimum | Recommended |
| :--- | :--- | :--- |
| Operating system | Windows 10, 64-bit | Windows 11, 64-bit |
| Memory | 4 GB | 8 GB or more |
| Free disk space | 1 GB | 2 GB |
| Screen | 1280 × 720 | 1920 × 1080 or larger |
| Office suite | — | Microsoft Office or LibreOffice, only for converting Office files to PDF |

## Installing

1. Download `MonographPDF_<version>_Setup.exe` from the official **Windows** release tag only
   (currently [v0.4.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.4.0) until 0.5.0
   is published). Do not rely on GitHub’s repository-wide Latest badge.
2. Check the download in PowerShell. The result must equal the SHA-256 value in the release notes
   (also listed in `SHA256SUMS.txt` inside `MonographPDF_<version>_Installer.zip`):

   ```powershell
   Get-FileHash .\MonographPDF_<version>_Setup.exe -Algorithm SHA256
   ```

3. Run Setup. Monograph PDF is currently distributed without a code-signing certificate, so Windows
   SmartScreen may display a warning. Continue (**More info ▸ Run anyway**) only if the file came
   from the official release page and its checksum matches.
4. Choose where to install:
   * **For all users** — `C:\Program Files\Monograph PDF` (needs administrator rights)
   * **Only for me** — `%LOCALAPPDATA%\Programs\Monograph PDF`

Setup copies the program, OCR data, documentation and `uninstall.exe`, registers the file types you
select, and finishes with an offline self-check. Its report is saved as
`%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json`.

### Upgrading

Run the Setup of the newer version. It replaces the program files of the existing installation in
place; your settings and documents are kept.

0.4.0 and earlier cannot update themselves (their update checks are switched off): install the current
version with its Setup from the [Releases](https://github.com/aungyemun/monograph-pdf/releases) page
(0.5.0 is planned as the first public version with update checks; 0.4.1 was prepared but never published). From then on,
**Help ▸ Check for Updates…** can do this for you when a newer signed release exists: **Update Now** downloads and verifies the new Setup, closes Monograph PDF (after you
save or discard open changes), installs the update in the same folder with the same choices and
restarts Monograph PDF. An all-users installation shows Windows' administrator prompt. Details:
[Automatic upgrade](docs/AUTOMATIC_UPGRADE_AND_CLEANUP.md).

### Silent installation (administrators)

Replace `<published-version>` with the version you actually downloaded; the 0.5.0 draft is not public.

```bat
MonographPDF_<published-version>_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
MonographPDF_<published-version>_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="D:\Apps\Monograph PDF" /MIGRATEINSTALL
```

* Installing to the same folder upgrades the existing installation in place.
* A different `/DIR` keeps the existing location unless `/MIGRATEINSTALL` is given, which moves the
  installation to the new folder.
* Setup stops if `MonographPDF.exe` is running.

## File types

| Option | Default |
| :--- | :--- |
| Offer Monograph PDF for `.pdf` files (Open with / Default apps) | On |
| Offer **Open with** for images and Office files | On |

Setup never makes Monograph PDF your default PDF app on its own. To do so, use
**Help ▸ Make Monograph PDF the Default PDF App…** or Windows **Open with ▸ Always**.

## Uninstalling

Use **Settings ▸ Apps ▸ Installed apps ▸ Monograph PDF ▸ Uninstall**, or run `uninstall.exe` in the
installation folder.

Uninstalling removes the program files installed by Setup, the shortcuts, the file registrations,
the recent-files list and the working files in `%LOCALAPPDATA%\Monograph PDF`. You are asked whether
to remove your settings (`%APPDATA%\Monograph PDF`) as well. **Your own documents are never removed.**

Silent uninstall, keeping or removing settings:

```bat
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REMOVEUSERDATA
```

## Checking an installation

On an offline computer: install, open a PDF, fill in a form field, convert a PDF to Word, protect
and unlock a file, run OCR on a scanned page, and uninstall. The self-check report
`install_smoke_test.json` should contain `"passed": true`. Developers can run the automated
installer test, `scripts\test_installer.ps1` ([Testing](docs/TESTING.md#installer-and-uninstaller-test)).

## Troubleshooting

| Problem | What to do |
| :--- | :--- |
| The app does not start | Run Setup again. Check whether your antivirus software quarantined `MonographPDF.exe` or files in `_internal`. |
| You want to check the installation | Run `MonographPDF.exe --smoke-test`, or open `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json`. |
| Office files cannot be converted | Open **Help ▸ About Monograph PDF ▸ Office Integration** to see which Office suite was found. |

---

Developers: [Build and Runtime](docs/BUILD_AND_RUNTIME.md) · [Release and Versioning](docs/RELEASE_AND_VERSIONING.md)

© 2026 Aung Ye Mun · AGPL-3.0-or-later ([LICENSE.md](LICENSE.md)) · Source code: `MonographPDF_<version>_Source.zip`
