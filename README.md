# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

**Offline, privacy-first PDF editor for Windows.**

Monograph PDF is the successor to PDF Editor beginning with version 0.2.0. PDF Editor 0.1.5 was the final release under the old name; an installed PDF Editor is upgraded by Monograph PDF Setup, keeping your settings and documents.

Monograph PDF itself makes no network connections, does not upload documents, and does not collect usage data. Opening a PDF never changes it — edits are written only when you save. Optional Microsoft Office or LibreOffice conversion: Monograph PDF does not upload the document; conversion uses the locally installed suite, which follows its own settings and remote-content behavior.

Current development version: **0.2.0 — Unreleased** (latest release: PDF Editor 0.1.5)

| Platform | Status |
| :--- | :--- |
| Windows 10/11 x64 | Supported / primary |
| macOS | Planned |
| Android | Future |
| iOS | Not currently planned |

---

## Screenshot

![Monograph PDF showing a PDF in the viewer, with the page thumbnails, the toolbar and the document panel](docs/images/monograph-pdf-ui.png)

*Monograph PDF 0.2.0: viewer and editor with page thumbnails, toolbar and document properties.*

---

## Overview

* Read, search and print PDFs
* Fill in and design PDF forms
* Edit text, add text boxes, images, shapes and comments
* Merge, split, rotate and rearrange pages
* Convert PDF to Word and back; images or Office files to PDF
* Protect PDFs with a password and permissions, or unlock them
* Watermarks, headers, footers, page numbers and visual signatures
* Offline OCR (English and Japanese)

Details: [User Guide](docs/USER_GUIDE.md) · [Features](docs/FEATURES.md)

---

## Download

A Monograph PDF release consists of:

* `Setup.exe` — the installer (recommended); built as `installer\MonographPDF_{version}_Setup.exe`
* `MonographPDF_{version}_Installer.zip` — the installer together with end-user documentation
* `MonographPDF_{version}_Source.zip` — corresponding Monograph PDF release source (application, build, installer, documentation and release tests) plus corresponding source of the bundled AGPL, GPL and LGPL components; local personal-document validation utilities are excluded
* `SHA256SUMS.txt` — checksums of `Setup.exe`, `MonographPDF.exe` and the source archive

Version 0.2.0 has not been released yet. Installer binaries are build outputs; they are not committed to the source repository.

---

## Quick Start

1. Run `Setup.exe`.
2. Keep **Register Monograph PDF for PDF files** selected if you want it in **Open with**.
3. Start **Monograph PDF** from the Start menu (**Monograph PDF** folder) or the desktop shortcut. The program is `MonographPDF.exe`.
4. Open a PDF with **File ▸ Open…** (Ctrl+O), or drag a file onto the window.
5. Use the start-screen tools or the menus; press **Ctrl+S** to save.

To make Monograph PDF your default PDF app: **Help ▸ Make Monograph PDF the Default PDF App…**

Upgrading from PDF Editor: run the new `Setup.exe`; see [Upgrading from PDF Editor](INSTALLATION.md#upgrading-from-pdf-editor).

---

## Known Limitations

* Windows 10 or 11 (64-bit) only (validated release platform). macOS support is planned; it is not available yet.
* Word, Excel and PowerPoint to PDF requires Microsoft Office or LibreOffice on the computer.
* PDF to Word is high-fidelity for most documents; complex layouts, unusual fonts, or scanned pages may need manual adjustment.
* Signatures are visual only — certificate-based digital signatures are not included.
* Windows does not allow any program to make itself the default PDF app silently. If PDF Editor was your default PDF app, choose Monograph PDF once in Windows Settings after upgrading.
* The build is not code-signed; check `SHA256SUMS.txt` before trusting SmartScreen “Run anyway”.

---

## Privacy

Monograph PDF does not upload documents, collect usage data, show advertising, use online OCR, or download code, plugins, OCR models or updates at runtime. Settings and the recent-files list: `%APPDATA%\Monograph PDF`. Temporary files, logs and recovery sessions: `%LOCALAPPDATA%\Monograph PDF` (cleaned automatically; no recovery copy for password-protected PDFs; nothing written into the installation folder). Settings of PDF Editor (`%APPDATA%\PDF Editor`) are copied once, at the first start. See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md).

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
