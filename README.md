# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

[![Windows CI](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml/badge.svg)](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml)

**A free, open-source PDF editor for Windows 10 and 11, designed for privacy and fully offline
operation.** Current release: **0.3.0**.

Monograph PDF lets you view, edit, annotate, organize, convert and protect PDF documents on your own
computer. It needs no account or internet connection and has no function that uploads your files.
Opening a PDF does not change the file: your edits are written only when you save, and exports and
conversions are written to new files.

<p align="center">
  <img src="docs/images/monograph-pdf-ui.png" alt="Monograph PDF with a document open: bookmarks on the left, the page in the middle and document properties on the right" width="100%">
</p>

## What you can do

| | |
| :--- | :--- |
| **View** | Search, zoom, page thumbnails, editable bookmarks, attachments, printing with preview |
| **Edit** | Edit text; add text boxes, pictures, shapes, comments and stamps; highlight, underline, squiggly-underline or strike through text, and remove these marks with the Eraser; a Comments panel — with Undo / Redo |
| **Forms** | Fill in forms, design new fields and flatten finished forms |
| **Organize** | Merge, split, insert, delete, rotate, crop and reorder pages; change page size |
| **Page design** | Headers, footers, page numbers, Bates numbers, watermarks and backgrounds |
| **Convert** | PDF to Word, Excel, PowerPoint (keeping page sizes) and images; images to PDF; Office files to PDF with Microsoft Office or LibreOffice; batch conversion |
| **Compress** | Lossless, balanced or smallest file, or an exact maximum size (for example 956 KB), measured before saving |
| **OCR** | Offline text recognition for English and Japanese (optional verified language packs); make scans searchable or editable; recognize an area, extract and correct text, scanned PDF to Word |
| **Protect** | AES-256 passwords and permissions, redaction that removes the marked content, removal of hidden information, visual signatures |

Complete list: [Features](docs/FEATURES.md) · How to use each tool: [User Guide](docs/USER_GUIDE.md) (also **F1** in the app)

### Feature status in 0.3.0

| Status | Features |
| :--- | :--- |
| **Included** | Everything in the table above unless listed below; covered by the automated tests on Windows |
| **Needs another application** | Office files to PDF and Office round trips need Microsoft Office or LibreOffice installed (tested with Microsoft 365 and LibreOffice 24.2 only) |
| **Limited** | PDF to Word, Excel or PowerPoint is best-effort for complex or scanned layouts. Optional OCR language packs (Chinese, Korean, vertical Japanese, German, French, Spanish) are installed only from a file you supply that matches the pinned SHA-256; their recognition quality has not been tested. Editing Japanese vertical text is not fully supported |
| **Built in, switched off** | Update checks and automatic upgrades; sending problem reports. They stay off until a production update-signing key and a reporting service exist and have been verified |
| **Not supported** | Certificate-based digital signatures (signatures are visual); macOS, Android and iOS; Windows on ARM has not been tested |

## Screenshots

<p align="center">
  <img src="docs/images/monograph-pdf-editing-comments.png" alt="Review markup on a document: highlighted and underlined text, a rectangle with an arrow, a text-box comment and a sticky note" width="49%">
  <img src="docs/images/monograph-pdf-forms.png" alt="A form being filled in, with its fillable fields highlighted" width="49%">
</p>
<p align="center">
  <img src="docs/images/monograph-pdf-start-dark.png" alt="Start page in the dark theme with the Open PDF button and common tools" width="49%">
  <img src="docs/images/monograph-pdf-viewer-dark.png" alt="A document open in the dark theme" width="49%">
</p>

More screenshots — page thumbnails, header and footer, password protection and Remove Hidden
Information — are in [Features](docs/FEATURES.md#screenshots).

## Supported platforms

| Platform | Status |
| :--- | :--- |
| Windows 10 and 11, 64-bit | Supported |
| macOS | Planned |
| Android | Under consideration |
| iOS | Not planned |

Only Windows builds are available.

## Download and installation

1. Download `MonographPDF_0.3.0_Setup.exe` from the official
   [latest release](https://github.com/aungyemun/monograph-pdf/releases/latest) page only.
2. Check its SHA-256 checksum in PowerShell and compare it with the value in the release notes:

   ```powershell
   Get-FileHash .\MonographPDF_0.3.0_Setup.exe -Algorithm SHA256
   ```

3. Run Setup and choose to install for all users or only for yourself.

> **Unsigned installer.** Monograph PDF is currently distributed without a code-signing certificate,
> so Windows SmartScreen may display a warning. Continue (**More info ▸ Run anyway**) only if the
> file came from the official release page and its checksum matches.
> [Code signing policy](docs/CODE_SIGNING_POLICY.md) · [Verifying a download](docs/OFFICIAL_DOWNLOAD_VERIFICATION.md) ·
> [Privacy policy](docs/PRIVACY_POLICY.md)

Each release also provides `MonographPDF_<version>_Installer.zip` (Setup with the documentation,
licenses and `SHA256SUMS.txt`) and `MonographPDF_<version>_Source.zip` (the corresponding source of
Monograph PDF and of the bundled AGPL, GPL and LGPL components). The **Source code** archives that
GitHub adds to every release contain only the repository at the release tag. System requirements,
silent installation, upgrading and uninstalling are described in [Installation](INSTALLATION.md).

## Privacy and offline operation

* Monograph PDF is designed to operate offline. It requires no account or cloud service and has no
  telemetry, advertising, online OCR or document upload. Viewing, editing, saving, OCR, conversion and
  printing never use the network.
* Version 0.3.0 contains secure update checks and private problem reports, but **both are switched
  off in this release**: **Help ▸ Check for Updates…** reports "Updates not configured" and
  **Send to Developer** sends nothing. Once enabled in a later release, they contact the network only
  when you ask (or after you switch on automatic update checks):
  [Secure updates](docs/SECURE_UPDATES.md) · [Error reporting](docs/ERROR_REPORTING.md).
* Qt's network and TLS modules are removed from the release build; only the update and problem-report
  code uses Python's HTTPS support. The built-in self-check fails if a network connection is attempted
  while it runs.
* Documents are processed locally. Settings and working files are kept in `%APPDATA%\Monograph PDF`
  and `%LOCALAPPDATA%\Monograph PDF`.
* Converting Office files uses the Microsoft Office or LibreOffice installed on your computer, with
  macros switched off. Those applications run independently and follow their own settings, including
  any network access.

Details and limits: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) · Reporting a
vulnerability: [Security policy](SECURITY.md)

## Building from source

You need Windows 10 or 11 (64-bit) and Python 3.11. Building the installer also needs Inno Setup 6
and the OCR engine with its language data, which are not stored in the repository.

```powershell
# Create the development environment (.\env) with the pinned packages
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# Run the application from source
powershell -ExecutionPolicy Bypass -File scripts\dev_launch.ps1

# Build and validate a release: tests, executable, Setup and archives
installer\build_release.bat
```

Details: [Build and Runtime](docs/BUILD_AND_RUNTIME.md) ·
[Release and Versioning](docs/RELEASE_AND_VERSIONING.md)

## Testing

```powershell
# Unit, integration and UI tests
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1

# One category only, for example the security tests
.\env\Scripts\python.exe -m pytest -m security
```

Each run ends with a summary per test category: **PASS**, **FAIL**, or **NOT VERIFIED** when every
test in that category was skipped. Automated unit, integration, security and supported UI tests run
through GitHub Actions for every change. Environment-dependent tests are skipped when their required
applications, fonts or reference documents are unavailable; they are reported as skipped, never as
passed. Details: [Testing](docs/TESTING.md).

## Known limitations

* Windows 10 and 11 (64-bit) only.
* The installer and program are not code-signed ([Code Signing](docs/CODE_SIGNING.md)).
* Update checks, automatic upgrades and the sending of problem reports are switched off in 0.3.0;
  install new versions from the [Releases](https://github.com/aungyemun/monograph-pdf/releases) page.
* Signatures are visual only; certificate-based digital signatures are not supported.
* Converting PDF to Word, Excel or PowerPoint is best-effort for complex or scanned layouts.
* Converting Office files to PDF requires Microsoft Office or LibreOffice.
* OCR recognizes English and Japanese; other languages need an optional language pack supplied by you (verified against a pinned SHA-256).
* Not verified for 0.3.0: Windows 10, localized (Japanese, Chinese, Korean, German, French) Windows,
  Office versions other than Microsoft 365 and LibreOffice 24.2, and printing on a physical printer.

More: [User Guide ▸ Current limitations](docs/USER_GUIDE.md#current-limitations)

## License

Monograph PDF is free software, © 2026 Aung Ye Mun. It is licensed under the
**GNU Affero General Public License, version 3 or (at your option) any later version**
(AGPL-3.0-or-later). The license text is in [LICENSE](LICENSE); [LICENSE.md](LICENSE.md) adds a
short explanation of what the license means for users and distributors.

## Third-party components

Monograph PDF is built with PyMuPDF/MuPDF (AGPL-3.0), Qt for Python (LGPL-3.0), pdf2docx (GPL-3.0),
Tesseract OCR (Apache-2.0), the Noto fonts (OFL-1.1) and other open-source components. Their
licenses, versions and source locations are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
and [licenses/DEPENDENCY_INVENTORY.md](licenses/DEPENDENCY_INVENTORY.md). Each release's Source.zip
contains the corresponding source code of the bundled AGPL, GPL and LGPL components.

## Citation and acknowledgments

If you use Monograph PDF in research, please cite it as described in [CITATION.cff](CITATION.cff):

> Mun AY. *Monograph PDF*. Version 0.3.0. 2026. https://github.com/aungyemun/monograph-pdf

Design, development, testing, documentation and packaging: **Aung Ye Mun**. With thanks to the
developers of the open-source projects listed in the third-party notices.

## Contributing and reporting issues

* **Bugs and suggestions:** open a [GitHub issue](https://github.com/aungyemun/monograph-pdf/issues/new/choose)
  with the steps to reproduce the problem. Please do not attach confidential documents.
* **Security vulnerabilities:** report them privately through
  [GitHub private vulnerability reporting](https://github.com/aungyemun/monograph-pdf/security/advisories/new)
  or as described in the [Security policy](SECURITY.md), not in a public issue.
* **Code changes:** see [CONTRIBUTING.md](CONTRIBUTING.md). For anything larger than a small fix,
  please open an issue first so the change can be discussed before a pull request.

What changed in each version: [CHANGELOG.md](CHANGELOG.md) ·
[Release notes and downloads](https://github.com/aungyemun/monograph-pdf/releases).
