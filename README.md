# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

**Offline PDF editor for Windows.**

**Monograph PDF 0.2.0** is a desktop application for viewing, editing, annotating, organizing, converting, protecting, and managing PDF documents. It performs its core PDF operations locally on your computer, without requiring a cloud service. The application combines PDF viewing, text and object editing, form handling, page management, conversion, OCR, password protection, annotations, signatures, and other document workflow tools in one desktop interface.

Monograph PDF itself makes no network connections, does not upload documents, and does not collect usage data. Opening a PDF never changes it — edits are written only when you save. Optional Microsoft Office or LibreOffice conversion is performed through the locally installed suite, which follows its own settings and remote-content behavior.

Current development version: **0.2.0 — Unreleased**

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
* Perform offline OCR on scanned PDFs and images containing English or Japanese text

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
3. Start **Monograph PDF** from the Start menu or desktop shortcut.
4. Open a PDF with **File ▸ Open…** (`Ctrl+O`), or drag a PDF into the application window.
5. Use the toolbar, menus, inspector, or start-page tools to work with the document.
6. Press **Ctrl+S** to save your changes.

To make Monograph PDF your default PDF application, use **Help ▸ Make Monograph PDF the Default PDF App…** and complete the selection in Windows Settings.

---

## Known Limitations

* Windows 10 or 11 (64-bit) is currently the validated release platform.
* macOS support is planned but is not yet available.
* Android support is planned for a future version.
* Word, Excel, and PowerPoint to PDF conversion requires Microsoft Office or LibreOffice to be installed locally.
* PDF to Word conversion is designed for high fidelity, but complex layouts, unusual fonts, or scanned pages may require manual adjustment.
* Signatures are visual only; certificate-based digital signatures are not currently included.
* Windows does not allow applications to silently make themselves the default PDF viewer. Choose Monograph PDF manually in Windows Settings if you want it as the default.
* Windows builds are currently unsigned, so Microsoft SmartScreen may display a warning. Verify downloaded release files against the published `SHA256SUMS.txt` before running them.

---

## Privacy

Monograph PDF does not upload documents, collect usage data, show advertising, use online OCR, or download executable code, plugins, OCR models, or updates at runtime.

Application settings and recent-file information are stored locally on your computer. Temporary files, logs, and recovery sessions are also handled locally and cleaned up automatically.

No recovery copy is kept for password-protected PDFs, and Monograph PDF does not write working data into the installation folder.

See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) for detailed information about local storage, temporary data, recovery behavior, and security-related design.

---

## Documentation

For users:

* [User Guide](docs/USER_GUIDE.md) — also available in the application through **Help ▸ User Guide** (`F1`)
* [Installation Guide](INSTALLATION.md)
* [Changelog](CHANGELOG.md)
* [Security Policy](SECURITY.md)

For developers:

* [Features](docs/FEATURES.md)
* [File Formats and Compatibility](docs/FILE_FORMATS_AND_COMPATIBILITY.md)
* [Architecture](docs/ARCHITECTURE.md)
* [Build and Runtime](docs/BUILD_AND_RUNTIME.md)
* [Release and Versioning](docs/RELEASE_AND_VERSIONING.md)
* [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
* [Testing](docs/TESTING.md)

---

## Uninstallation

**Settings ▸ Apps ▸ Installed apps** → **Monograph PDF** → **Uninstall**

You can also run the uninstaller from the Monograph PDF installation directory.

Uninstallation removes the application, shortcuts, file registrations, recent-file information, and application working files such as cache, logs, and temporary files.

You can choose whether to remove saved settings.

Your PDF documents and other user-created files are never removed.

See [Installation Guide — Uninstallation](INSTALLATION.md#uninstallation) for details.

---

## Citation

Mun AY. **Monograph PDF: An offline desktop application for viewing, editing, organizing, converting, protecting, and signing PDF documents.** Version 0.2.0. 2026. Unreleased.

The citation will include the release date once version 0.2.0 is released.

See also [`CITATION.cff`](CITATION.cff).

---

## Author

**Aung Ye Mun**

Design, development, testing, documentation, packaging, and maintenance.

---

## License

© 2026 Aung Ye Mun.

Monograph PDF is free software licensed under the **GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`).

The PDF engine, PyMuPDF / MuPDF, is distributed under its upstream AGPL-3.0 terms. Other bundled components retain their respective licenses.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for third-party component and license information.

Each release includes the corresponding:

`MonographPDF_{version}_Source.zip`

See [`LICENSE.md`](LICENSE.md) for full licensing information.
