# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

**Offline PDF editor for Windows 10/11.**

Monograph PDF **0.2.2** views, edits, annotates, organizes, converts, protects, and signs PDFs locally. No cloud, no uploads, no telemetry. Opening a PDF never changes it — edits are written only when you save.

| Platform | Status |
| :--- | :--- |
| Windows 10/11 x64 | Supported |
| macOS | Planned |
| Android | Future |
| iOS | Not planned |

---

## Interface

<p align="center">
  <img src="docs/images/monograph-pdf-ui.png" alt="Monograph PDF desktop interface" width="100%">
</p>

<p align="center">
  <img src="docs/images/monograph-pdf-start-dark.png" alt="Start page, dark theme" width="49%">
  <img src="docs/images/monograph-pdf-viewer-dark.png" alt="Viewer, dark theme" width="49%">
</p>

---

## Features

* View, search, navigate; edit bookmarks; print (odd/even pages, reverse order, with or without comments)
* Edit text; add text boxes, images, shapes, comments; continuous Highlight (toggle / colour switch) and Eraser
* Fill and design forms
* Merge, split, rotate, extract, rearrange pages
* Headers, footers, page and Bates numbers, watermarks, backgrounds
* PDF ↔ Word / images; Office → PDF when Microsoft Office or LibreOffice is installed
* Passwords (with strength rating), permissions, true redaction, removal of hidden information (metadata, attachments, scripts, …), visual signatures
* Offline OCR (English and Japanese)

[User Guide](docs/USER_GUIDE.md) · [Features](docs/FEATURES.md)

---

## Install

1. Run `MonographPDF_{version}_Setup.exe`.
2. Optionally register for PDF **Open with**.
3. Open a PDF (`Ctrl+O` or drag-and-drop) and save with `Ctrl+S`.

Release package: Setup.exe, Installer.zip, Source.zip, `SHA256SUMS.txt`. Builds are unsigned — verify checksums before running. Default PDF app: **Help ▸ Make Monograph PDF the Default PDF App…**.

---

## Limits

* Windows x64 only (validated)
* Office → PDF needs a local Office suite
* PDF → Word / Excel / PowerPoint are best-effort on complex or scanned pages
* Signatures are visual only (not certificate-based)
* SmartScreen may warn on unsigned builds

---

## Privacy

No network use by Monograph PDF, no advertising, no online OCR, no runtime downloads. Settings and working files stay under `%APPDATA%` / `%LOCALAPPDATA%\Monograph PDF`. Details: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md).

---

## Docs

**Users:** [User Guide](docs/USER_GUIDE.md) (`F1`) · [Installation](INSTALLATION.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

**Developers:** [Features](docs/FEATURES.md) · [Formats](docs/FILE_FORMATS_AND_COMPATIBILITY.md) · [Architecture](docs/ARCHITECTURE.md) · [Build](docs/BUILD_AND_RUNTIME.md) · [Release](docs/RELEASE_AND_VERSIONING.md) · [Security/Privacy](docs/SECURITY_AND_PRIVACY.md) · [Testing](docs/TESTING.md)

---

## Uninstall

**Settings ▸ Apps ▸ Installed apps** → **Monograph PDF** → **Uninstall** (or `uninstall.exe`). Removes the app, shortcuts, and working files; settings optional. Your documents are never removed. See [Installation](INSTALLATION.md#uninstallation).

---

## Citation · Author · License

Mun AY. **Monograph PDF.** Version 0.2.2. 2026. See [`CITATION.cff`](CITATION.cff).

**Aung Ye Mun** — design, development, testing, documentation, packaging.

© 2026 Aung Ye Mun. **AGPL-3.0-or-later**. See [`LICENSE.md`](LICENSE.md) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Each release ships `MonographPDF_{version}_Source.zip`.
