# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Monograph PDF logo" width="160">

[![Windows CI](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml/badge.svg)](https://github.com/aungyemun/monograph-pdf/actions/workflows/windows-ci.yml)

**A free, open-source PDF editor designed for privacy and fully offline operation.**

| Line | Version | Status |
| :--- | :--- | :--- |
| Windows (`main`) | **0.5.0** prepared | Not yet publicly released (draft). Latest **published** Windows: **[0.4.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.4.0)** |
| macOS (`macos`) | **0.1.0** | Published: **[v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)** |
| Linux (`linux`) | **0.1.0** | Source on branch [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux) — **no** published Linux release tag yet |

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
| **View** | Search (also scientific symbols and Greek letters), zoom around the pointer, a scroll button and automatic scrolling, page thumbnails, editable bookmarks, attachments, printing with preview |
| **Edit** | Edit text; add text boxes, pictures (in front of or behind the text), shapes, comments and stamps; highlight, underline, squiggly-underline or strike through text, and remove these marks with the Eraser; a Comments panel — with Undo / Redo |
| **Forms** | Fill in forms, design new fields and flatten finished forms |
| **Organize** | Merge, split, insert, delete, rotate, crop and reorder pages; change page size |
| **Page design** | Headers, footers, page numbers, Bates numbers, watermarks and backgrounds |
| **Convert** | PDF to Word, Excel, PowerPoint (keeping page sizes) and images; images to PDF; Office files to PDF with Microsoft Office or LibreOffice; batch conversion |
| **Compress** | Lossless, balanced or smallest file, or an exact maximum size (for example 956 KB), measured before saving |
| **OCR** | Offline text recognition for English and Japanese, 45 more languages installable on request (verified); make scans searchable or editable; recognize an area, extract and correct text, scanned PDF to Word |
| **Protect** | AES-256 passwords and permissions that are honoured and kept in every copy, redaction that removes the marked content, removal of hidden information, visual signatures |

Complete list: [Features](docs/FEATURES.md) · How to use each tool: [User Guide](docs/USER_GUIDE.md) (also **F1** in the app)

### Feature status

Windows, Linux and macOS share the feature set below. Platform plumbing differs
([LINUX.md](LINUX.md), [docs/MACOS.md](https://github.com/aungyemun/monograph-pdf/blob/macos/docs/MACOS.md)).

| Status | Features |
| :--- | :--- |
| **Included** | Everything in the table above unless listed below; covered by the automated tests on each platform |
| **Needs another application** | Office files to PDF need LibreOffice (Linux/macOS) or Microsoft Office / LibreOffice (Windows; tested with Microsoft 365 and LibreOffice 24.2) |
| **Limited** | PDF to Word, Excel or PowerPoint is best-effort for complex or scanned layouts. 45 optional OCR languages are installed on request (Download and Install, or from a file) and verified against a pinned SHA-256; their recognition quality has not been tested by the project. Editing Japanese vertical text is not fully supported |
| **Built in, switched off** | Sending problem reports; it stays off until a reporting service exists and has been verified. (Windows update checks ship with 0.5.0 when published; Linux/macOS use manual upgrades for now.) |
| **Not supported** | Certificate-based digital signatures (signatures are visual); Android and iOS; Windows on ARM has not been tested |

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
| Windows 10 and 11, 64-bit | Supported — latest **published** **0.4.0**; **0.5.0** prepared (draft) |
| macOS (Apple silicon, 13+) | Supported — first release **0.1.0** ([v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)) |
| Linux x86_64 | Supported from source — **0.1.0** on branch [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux) (no release tag yet) |
| Android | Under consideration |
| iOS | Not planned |

## Download and installation

Platform lines are versioned separately. Prefer the official
[Releases](https://github.com/aungyemun/monograph-pdf/releases) page only. GitHub’s repository-wide
“Latest” badge may point at any platform — always open the **platform-specific** link below.

| Platform | Get it |
| :--- | :--- |
| **Windows (published)** | [v0.4.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.4.0) — `MonographPDF_0.4.0_Setup.exe` |
| **Windows (0.5.0, not public yet)** | Draft only; do not treat GitHub Latest as the Windows channel |
| **macOS** | [v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1) — zip / dmg / pkg |
| **Linux** | Clone [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux) and build from source (no `v0.1.0-linux` tag yet) |

### Windows

1. Download Setup from the Windows tag above (currently **0.4.0** until 0.5.0 is published).
2. Check its SHA-256 checksum in PowerShell against the release notes:

   ```powershell
   Get-FileHash .\MonographPDF_0.4.0_Setup.exe -Algorithm SHA256
   ```

3. Run Setup and choose to install for all users or only for yourself.

### macOS

Download zip, dmg or pkg from [v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)
and verify SHA-256 against that release. Builds are unsigned; use **Right-click → Open** if Gatekeeper blocks them.
Details: [docs/MACOS.md](https://github.com/aungyemun/monograph-pdf/blob/macos/docs/MACOS.md).

### Linux

```bash
git clone -b linux https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

Optional per-user install after a built tree: `bash installer/linux/install.sh /path/to/MonographPDF`.
Details: [LINUX.md](LINUX.md).

> **Unsigned builds.** Windows and macOS packages are currently distributed **without** code signing.
> On Windows, SmartScreen may warn; continue (**More info ▸ Run anyway**) only if the file came from
> the official release page and its checksum matches.
> [Code signing policy](docs/CODE_SIGNING_POLICY.md) · [Verifying a download](docs/OFFICIAL_DOWNLOAD_VERIFICATION.md) ·
> [Privacy policy](docs/PRIVACY_POLICY.md)

Windows releases also provide `MonographPDF_<version>_Installer.zip` and
`MonographPDF_<version>_Source.zip`. The **Source code** archives GitHub adds to every release
contain only the repository at the release tag.

## Privacy and offline operation

* Monograph PDF is designed to operate offline. It requires no account or cloud service and has no
  telemetry, advertising, online OCR or document upload. Viewing, editing, saving, OCR, conversion and
  printing never use the network.
* **Help ▸ Check for Updates…** (Windows, when enabled in a published build) discovers Windows releases
  through the GitHub Releases API and accepts only an Ed25519-signed update manifest for a Windows
  x64 Setup — never macOS/Linux packages and never “GitHub Latest” alone. Nothing is downloaded or
  installed until you click **Update Now**. Automatic checks are optional and **off by default**.
  0.4.0 and earlier cannot update themselves: install newer Windows versions with Setup from the
  Releases page. Problem reports are still not sent:
  [Secure updates](docs/SECURE_UPDATES.md) · [Error reporting](docs/ERROR_REPORTING.md).
* From Windows 0.5.0, an optional OCR language is downloaded only when you click **Download and Install** in
  **OCR ▸ OCR Languages** (from the official Tesseract release; installed only if its SHA-256 matches).
* Qt's network and TLS modules are removed from the release build; only the update, problem-report
  and OCR-language-download code uses Python's HTTPS support. The built-in self-check fails if a network connection is attempted
  while it runs.
* Documents are processed locally. Settings and working files are kept under XDG on Linux
  (`~/.local/share/monograph-pdf`, cache) or in `%APPDATA%\Monograph PDF` /
  `%LOCALAPPDATA%\Monograph PDF` on Windows.
* Converting Office files uses LibreOffice on Linux, or Microsoft Office / LibreOffice on Windows,
  with macros switched off. Those applications run independently and follow their own settings,
  including any network access.

Details and limits: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) · Reporting a
vulnerability: [Security policy](SECURITY.md)

## Building from source

### Linux (0.1.0)

Python **3.11**, LibreOffice (optional, for Office → PDF), and Tesseract (via `scripts/vendor_ocr.sh`).

```bash
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

See [LINUX.md](LINUX.md).

### Windows (0.5.0)

Windows 10 or 11 (64-bit) and Python 3.11. Building the installer also needs Inno Setup 6
and the OCR engine with its language data, which are not stored in the repository.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev_launch.sh
installer\build_release.bat
```

Details: [Build and Runtime](docs/BUILD_AND_RUNTIME.md) ·
[Release and Versioning](docs/RELEASE_AND_VERSIONING.md)

## Testing

```bash
# Linux
bash scripts/run_tests.sh
./env/bin/python -m pytest -m security
./env/bin/python -m app --smoke-test
```

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
.\env\Scripts\python.exe -m pytest -m security
```

Each run ends with a summary per test category: **PASS**, **FAIL**, or **NOT VERIFIED** when every
test in that category was skipped. Environment-dependent tests are skipped when their required
applications, fonts or reference documents are unavailable; they are reported as skipped, never as
passed. Details: [Testing](docs/TESTING.md).

## Known limitations

* Windows 10/11 64-bit, macOS (Apple silicon), and Linux x86_64; Android/iOS not planned.
* Builds are **not code-signed** yet ([Code Signing](docs/CODE_SIGNING.md)); signing is planned later.
* The sending of problem reports is switched off.
* Signatures are visual only; certificate-based digital signatures are not supported.
* Converting PDF to Word, Excel or PowerPoint is best-effort for complex or scanned layouts.
* Converting Office files to PDF requires LibreOffice (Linux/macOS) or Microsoft Office / LibreOffice (Windows).
* OCR includes English and Japanese; 45 more languages can be installed on request (OCR ▸ OCR Languages), verified against a pinned SHA-256.
* Linux and macOS do not yet use the Windows signed-Setup auto-updater.
* Not verified for Windows 0.5.0: Windows 10, localized (Japanese, Chinese, Korean, German, French) Windows,
  Office versions other than Microsoft 365 and LibreOffice 24.2, and printing on a physical printer.

More: [User Guide ▸ Current limitations](docs/USER_GUIDE.md#current-limitations) · [LINUX.md](LINUX.md)

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

> Mun AY. *Monograph PDF*. Version 0.4.0 (Windows published) / 0.1.0 (macOS) / 0.1.0 (Linux source). 2026. https://github.com/aungyemun/monograph-pdf

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
