# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

**Offline PDF editor for Windows.**

**Monograph PDF 0.2.0** is a desktop application for viewing, editing, annotating, organizing, converting, protecting, and managing PDF documents. It performs its core PDF operations locally on your computer, without requiring a cloud service. The application combines PDF viewing, text and object editing, form handling, page management, conversion, OCR, password protection, annotations, signatures, and other document workflow tools in one desktop interface.

Monograph PDF itself makes no network connections, does not upload documents, and does not collect usage data. Opening a PDF never changes it — edits are written only when you save. Optional Microsoft Office or LibreOffice conversion is performed through the locally installed suite, which follows its own settings and remote-content behavior.

Monograph PDF is the successor to PDF Editor; PDF Editor 0.1.5 was the final release under the old name. Running Monograph PDF Setup on a computer with PDF Editor upgrades it and keeps your settings and documents.

Current development version: **0.2.0 — Unreleased** (latest release: PDF Editor 0.1.5)

| Platform | Status |
| :--- | :--- |
| Windows 10/11 x64 | Supported / primary |
| macOS | Planned |
| Android | Future |
| iOS | Not currently planned |

---

## Interface

<p align="center">
  <img src="docs/images/monograph-pdf-ui.png"
       alt="Monograph PDF desktop application interface"
       width="100%">
</p>

<p align="center">
  <em>Monograph PDF desktop interface (light theme).</em>
</p>

<p align="center">
  <img src="docs/images/monograph-pdf-start-dark.png"
       alt="Monograph PDF start page in the dark theme"
       width="49%">
  <img src="docs/images/monograph-pdf-viewer-dark.png"
       alt="Monograph PDF viewer with a PDF open in the dark theme"
       width="49%">
</p>

<p align="center">
  <em>Start page and document view in the dark theme.</em>
</p>

---

## Overview

* View, search, navigate, and print PDF documents
* Edit existing text and add text boxes
* Add images, shapes, annotations, and comments
* Fill, edit, and design PDF forms
* Merge, split, rotate, extract, and rearrange pages
* Convert PDF to Word and create PDFs from images or Office documents
* Protect PDFs with passwords and permissions, or remove supported protection when authorized
* Add watermarks, headers, footers, and page numbers
* Add visual signatures
* Perform offline OCR in English and Japanese

Details: [User Guide](docs/USER_GUIDE.md) · [Features](docs/FEATURES.md)

---

## Download

A Monograph PDF release includes:

* `MonographPDF_{version}_Setup.exe` — Windows installer (recommended)
* `MonographPDF_{version}_Installer.zip` — installer together with end-user documentation
* `MonographPDF_{version}_Source.zip` — corresponding application source, build and installer scripts, documentation, release tests, and required corresponding source for bundled AGPL, GPL, and LGPL components
* `SHA256SUMS.txt` — SHA-256 checksums for release artifacts

Version 0.2.0 is currently under development and has not yet been released.

Generated installers, binaries, release archives, local validation outputs, private test material, and personal-document validation utilities are not committed to the source repository.

---

## Quick Start

1. Run `MonographPDF_{version}_Setup.exe`.
2. Keep **Register Monograph PDF for PDF files** selected if you want Monograph PDF to appear in **Open with**.
3. Start **Monograph PDF** from the Start menu (**Monograph PDF** folder) or the desktop shortcut. The program is `MonographPDF.exe`.
4. Open a PDF with **File ▸ Open…** (`Ctrl+O`), or drag a PDF into the application window.
5. Use the toolbar, menus, inspector, or start-page tools to work with the document.
6. Press **Ctrl+S** to save your changes.

To make Monograph PDF your default PDF application, use **Help ▸ Make Monograph PDF the Default PDF App…** and complete the selection in Windows Settings.

Upgrading from PDF Editor: run the new Setup; see [Upgrading from PDF Editor](INSTALLATION.md#upgrading-from-pdf-editor).

---

## Known Limitations

* Windows 10 or 11 (64-bit) is currently the validated release platform.
* macOS support is planned but is not yet available.
* Android support is planned for a future version.
* Word, Excel, and PowerPoint to PDF conversion requires Microsoft Office or LibreOffice to be installed locally.
* PDF to Word conversion is designed for high fidelity, but complex layouts, unusual fonts, or scanned pages may require manual adjustment.
* Signatures are visual only; certificate-based digital signatures are not currently included.
* Windows does not allow applications to silently make themselves the default PDF viewer. Choose Monograph PDF manually in Windows Settings if you want it as the default; this includes the case where PDF Editor was your default PDF app before upgrading.
* Windows builds are currently unsigned, so Microsoft SmartScreen may display a warning. Verify downloaded release files against the published `SHA256SUMS.txt` before running them.

---

## Privacy

Monograph PDF does not upload documents, collect usage data, show advertising, use online OCR, or download executable code, plugins, OCR models, or updates at runtime.

Settings and the recent-files list are stored under:

```text
%APPDATA%\Monograph PDF
```

Temporary files, logs, and recovery sessions are stored under:

```text
%LOCALAPPDATA%\Monograph PDF
```

These working files are cleaned up automatically. No recovery copy is kept for password-protected PDFs, and nothing is written into the installation folder. After an upgrade, the settings of the previous PDF Editor (`%APPDATA%\PDF Editor`) are migrated by copying them once, at the first start. See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md).

---

## Documentation

For users (also in the installer package / the installed app where noted):

* [User Guide](docs/USER_GUIDE.md) — **Help ▸ User Guide** (F1) and the **Monograph PDF User Guide** Start menu entry
* [Installation Guide](INSTALLATION.md) — in the downloadable release package
* [Changelog](CHANGELOG.md)
* [Security Policy](SECURITY.md)

For developers (repository `monograph-pdf` / source archive):

* [Features](docs/FEATURES.md)
* [File Formats and Compatibility](docs/FILE_FORMATS_AND_COMPATIBILITY.md)
* [Architecture](docs/ARCHITECTURE.md)
* [Build and Runtime](docs/BUILD_AND_RUNTIME.md)
* [Release and Versioning](docs/RELEASE_AND_VERSIONING.md)
* [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
* [Testing](docs/TESTING.md)

---

## Uninstallation

**Settings ▸ Apps ▸ Installed apps** → **Monograph PDF** → **Uninstall** (or run `uninstall.exe` in the installation folder).

Removes the application, shortcuts, file-type registrations, recent-files list and working files (cache, logs, temporary files). Asks whether to remove settings. Your documents are never removed. Details: [Installation Guide — Uninstallation](INSTALLATION.md#uninstallation).

---

## Citation

Mun AY. **Monograph PDF: An offline desktop application for viewing, editing, organizing, converting, protecting and signing PDF documents.** Version 0.2.0 (unreleased). 2026. Previously distributed as PDF Editor through version 0.1.5.

The citation will name the release date once 0.2.0 is released. See also `CITATION.cff`.

---

## Author

Design, development, testing, packaging and maintenance: **Aung Ye Mun**

---

## License

© 2026–Present Aung Ye Mun.

Monograph PDF is free software under the **GNU Affero General Public License v3.0 or later** (**AGPL-3.0-or-later**). Its PDF engine (PyMuPDF / MuPDF) is under upstream AGPL-3.0; other bundled components keep their own licenses (see `THIRD_PARTY_NOTICES.md`). The new product name does not change any license. Each release includes `MonographPDF_{version}_Source.zip` beside the installer.

See `LICENSE.md` for full details.
