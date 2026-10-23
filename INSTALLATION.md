# Installation

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

1. Download `MonographPDF_<version>_Setup.exe` from the official
   [latest release](https://github.com/aungyemun/monograph-pdf/releases/latest) page only.
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

In 0.4.0 (as in 0.3.0) update checks and automatic upgrades are built in but **switched off** (no production
update-signing key exists yet): **Help ▸ Check for Updates…** reports "Updates not configured".
Download new versions from the [Releases](https://github.com/aungyemun/monograph-pdf/releases) page.
Once updates are enabled in a later release, **Help ▸ Check for Updates…** can do this for you: **Update Now** downloads and verifies the new Setup, closes Monograph PDF (after you
save or discard open changes), installs the update in the same folder with the same choices and
restarts Monograph PDF. An all-users installation shows Windows' administrator prompt. Details:
[Automatic upgrade](docs/AUTOMATIC_UPGRADE_AND_CLEANUP.md).

### Silent installation (administrators)

```bat
MonographPDF_0.4.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
MonographPDF_0.4.0_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="D:\Apps\Monograph PDF" /MIGRATEINSTALL
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
