# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

[![Windows CI](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml/badge.svg)](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml)

**An offline PDF editor for Windows 10/11.** Current release: **0.2.3**.

Monograph PDF views, edits, annotates, organizes, converts and protects PDF documents entirely on
your own computer. It needs no account and no internet connection, and it never uploads your files.
Opening a PDF never changes it; changes are written only when you save.

## Main capabilities

* **View:** search, zoom, page thumbnails, editable bookmarks, attachments, print with preview
* **Edit:** text, text boxes, images, shapes, comments, highlight and eraser, with undo
* **Forms:** fill in, design and flatten forms
* **Organize:** merge, split, insert, delete, rotate, crop, reorder pages, change page size
* **Page design:** headers, footers, page and Bates numbers, watermarks, backgrounds
* **Convert:** PDF to Word, Excel, PowerPoint and images; images to PDF; Office files to PDF when
  Microsoft Office or LibreOffice is installed
* **OCR:** offline text recognition for English and Japanese
* **Protect:** AES-256 password encryption and permissions, true redaction, Remove Hidden
  Information, visual signatures

Full list: [Features](docs/FEATURES.md) · How to use it: [User Guide](docs/USER_GUIDE.md) (`F1` in the app)

## Supported platforms

| Platform | Status |
| :--- | :--- |
| Windows 10/11, 64-bit | Supported |
| macOS | Planned |
| Android | Future |
| iOS | Not planned |

## Download and installation

1. Download `MonographPDF_0.2.3_Setup.exe` from the
   [latest release](https://github.com/aungyemun/monograph-pdf/releases/latest).
2. Check its SHA-256 checksum against the value on the release page:
   `Get-FileHash .\MonographPDF_0.2.3_Setup.exe` in PowerShell.
3. Run Setup and choose an installation for all users or only for you. Windows SmartScreen may warn
   because the installer is not code-signed; **More info ▸ Run anyway** continues.

Each release also offers `MonographPDF_<version>_Installer.zip` (Setup with the documentation,
licenses and `SHA256SUMS.txt`) and `MonographPDF_<version>_Source.zip` (the complete corresponding
source). Requirements, silent installation, upgrading and uninstalling: [Installation](INSTALLATION.md).

## Screenshots

<p align="center">
  <img src="docs/images/monograph-pdf-ui.png" alt="Monograph PDF with a document open: bookmarks on the left, the page in the middle and document properties on the right" width="100%">
</p>

<p align="center">
  <img src="docs/images/monograph-pdf-start-dark.png" alt="Start page in the dark theme with recent files and common tools" width="49%">
  <img src="docs/images/monograph-pdf-viewer-dark.png" alt="A document open in the dark theme" width="49%">
</p>

More screenshots (page thumbnails, header and footer, password protection, Remove Hidden
Information): [Features](docs/FEATURES.md#screenshots).

## Privacy and offline operation

* Monograph PDF makes no network connections: no telemetry, advertising, online OCR or downloads at
  run time. The network and TLS components are removed from the release build.
* Documents are processed locally. Settings and working files stay in `%APPDATA%\Monograph PDF` and
  `%LOCALAPPDATA%\Monograph PDF`.
* Office conversion uses a locally installed Office suite with macros turned off.

Details and limits: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) · Reporting a vulnerability: [SECURITY.md](SECURITY.md)

## Building from source

Requires Windows 10/11 64-bit, Python 3.11 and, for the installer, Inno Setup 6.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1    # create .\env with the pinned packages
powershell -ExecutionPolicy Bypass -File scripts\dev_launch.ps1   # run the app from source
installer\build_release.bat                                       # tests, executable, Setup and archives
```

The OCR engine and language data are not stored in the repository; see
[Build and Runtime](docs/BUILD_AND_RUNTIME.md) and [Release and Versioning](docs/RELEASE_AND_VERSIONING.md).

## Testing

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1   # unit, integration and UI tests
.\env\Scripts\python.exe -m pytest -m security                   # one category
```

Every run ends with a per-category summary (PASS, FAIL or NOT VERIFIED when all tests of a category
were skipped). The same tests run on GitHub Actions for every push and pull request. Details:
[Testing](docs/TESTING.md).

## Known limitations

* Windows 10/11 64-bit only.
* The installer and program are not code-signed ([Code Signing](docs/CODE_SIGNING.md)).
* Signatures are visual only, not certificate-based digital signatures.
* PDF to Word, Excel and PowerPoint is best-effort on complex or scanned layouts.
* Office to PDF needs Microsoft Office or LibreOffice installed.
* OCR recognizes English and Japanese only.

More: [User Guide ▸ Current limitations](docs/USER_GUIDE.md#current-limitations).

## License

Monograph PDF is free software, © 2026 Aung Ye Mun, licensed under the
**GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later). See [LICENSE.md](LICENSE.md).

## Third-party notices

Monograph PDF builds on PyMuPDF/MuPDF (AGPL-3.0), Qt for Python (LGPL-3.0), pdf2docx (GPL-3.0),
Tesseract OCR (Apache-2.0), the Noto fonts (OFL-1.1) and other components. Their licenses, versions
and source locations are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[licenses/DEPENDENCY_INVENTORY.md](licenses/DEPENDENCY_INVENTORY.md); each release's Source.zip
contains the corresponding source.

## Citation and acknowledgments

If you use Monograph PDF in research, please cite it — see [CITATION.cff](CITATION.cff):

> Mun AY. *Monograph PDF*. Version 0.2.3. 2026. https://github.com/aungyemun/monograph-pdf

Design, development, testing, documentation and packaging: **Aung Ye Mun**. Thanks to the
developers of the open-source projects listed in the third-party notices.

## Contributing and reporting issues

* Bugs and suggestions: [GitHub Issues](https://github.com/aungyemun/monograph-pdf/issues). Please
  describe the steps to reproduce and do not attach confidential documents.
* Security vulnerabilities: report privately as described in [SECURITY.md](SECURITY.md), not in a
  public issue.
* For larger changes, please open an issue to discuss them before a pull request.

Changes in each version: [CHANGELOG.md](CHANGELOG.md).
