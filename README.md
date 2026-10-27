# Monograph PDF

<img src="resources/icons/source/monograph_pdf_logo_512.png" alt="Official Monograph PDF logo" width="160">

An open-source desktop PDF editor for Windows, Linux and macOS. View, edit, annotate,
organize, convert and protect documents on your computer, without an account or cloud service.

[Download releases](https://github.com/aungyemun/monograph-pdf/releases) ·
[Installation](INSTALLATION.md) · [User guide](docs/USER_GUIDE.md) ·
[Documentation](docs/README.md) · [Contributing](CONTRIBUTING.md)

![Monograph PDF document workspace with bookmarks and document properties](docs/images/monograph-pdf-ui.png)

## Platforms and releases

The shared application is developed on `main`. Each platform has an independent version and
release schedule. Legacy `linux` and `macos` branches are retained for recovery; start new
development from `main`. A development version is not a published download.

| Platform | Published distribution | Current development line |
| :--- | :--- | :--- |
| Windows 10/11, x64 | [v0.4.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.4.0) | 0.5.0; unpublished draft |
| macOS 13+, Apple silicon | [v0.1.0-macos-1](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1) | 0.1.0; unified source on main |
| Linux, x86_64 | No published Linux release | 0.1.0; build from main |

macOS Intel, Windows ARM and mobile platforms are not verified targets. CI exercises shared
code and offscreen UI behavior; it does not certify native installers, physical printing or
every desktop environment. See [testing and acceptance limits](docs/TESTING.md).

## Features

These describe the current source tree. Published versions can differ; consult their release notes.

| Area | Capabilities |
| :--- | :--- |
| View and annotate | Search, thumbnails, bookmarks, comments, highlights, shapes and print preview |
| Edit and forms | Text and image editing, text boxes, fillable fields, form design and flattening |
| Organize | Merge, split, insert, remove, rotate, crop and reorder pages |
| Page design | Headers, footers, page numbers, Bates numbering, watermarks and backgrounds |
| Convert | PDF to Word, Excel, PowerPoint, images and text; images and Office documents to PDF |
| Compress and OCR | Image compression; offline Tesseract OCR with English/Japanese and optional language packs |
| Protect | Passwords and permissions, redaction, hidden-information removal and visual signatures |

Office-to-PDF conversion needs locally installed Microsoft Office on Windows or LibreOffice
on Windows/Linux/macOS. PDF-to-Office conversion is best-effort for complex layouts. Optional
OCR packs are checked against pinned size and SHA-256 values; recognition quality for all
45 optional languages has not been validated. Signatures are visual, not certificate-based.
Read the [feature guide](docs/FEATURES.md) and [security limitations](docs/SECURITY_AND_PRIVACY.md).

## Screenshots

<p>
  <img src="docs/images/monograph-pdf-editing-comments.png" alt="Annotations and review comments" width="49%">
  <img src="docs/images/monograph-pdf-forms.png" alt="Fillable PDF form" width="49%">
</p>

These repository screenshots illustrate the interface; they are not native acceptance evidence
for every operating system. [More screenshots](docs/FEATURES.md#screenshots).

## Installation

Use only the official [GitHub Releases](https://github.com/aungyemun/monograph-pdf/releases).
Choose a platform-specific release rather than relying on the repository-wide Latest label.
Compare downloaded files with the checksums in that release's notes.

* **Windows:** download the published Setup executable; see [installation and upgrades](INSTALLATION.md#windows).
  0.5.0 is still a draft and is not offered here as a public release.
* **macOS:** use the zip/dmg/pkg from the published macOS release and follow the
  [macOS guide](docs/MACOS.md). Local builds use ad-hoc signing, not Developer ID or notarization.
* **Linux:** follow the [source setup guide](LINUX.md). The per-user installer consumes an
  already built application tree; it does not build a package from Python source.

Windows packages are not Authenticode signed. Verify origin and checksums before deciding to
run any package. [Download verification](docs/OFFICIAL_DOWNLOAD_VERIFICATION.md) ·
[Code signing policy](docs/CODE_SIGNING_POLICY.md).

## Privacy and offline-first operation

Document processing works locally, without telemetry or document uploads. After dependencies,
OCR engines and language data are installed, normal editing and OCR work without a connection.
Source setup and dependency downloads can require internet access.

Windows development 0.5.0 includes signed update checks. Manual checks contact GitHub;
automatic checks are optional and off by default. Installing an update requires **Update Now**.
Published Windows 0.4.0 has update checks disabled. Linux/macOS use manual upgrades.
Optional OCR language downloads require **Download and Install**; **Install from File** works offline.
Problem-report sending remains disabled. External Office suites follow their own network settings.

Settings and working data use Windows AppData, macOS Application Support/Caches, or Linux XDG
locations. See the [privacy policy](docs/PRIVACY_POLICY.md),
[security policy](SECURITY.md) and [platform path map](docs/REPOSITORY_LAYOUT.md#compatibility-boundaries).
Report vulnerabilities [privately](https://github.com/aungyemun/monograph-pdf/security/advisories/new).

## Build and test from source

Use Python 3.11 and start from the unified development branch:

```bash
git clone --branch main https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev_launch.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

Linux/macOS (Bash):

```bash
bash scripts/setup_env.sh
# Optional OCR setup: vendor_ocr.sh on Linux, vendor_ocr_macos.sh on macOS.
bash scripts/dev_launch.sh
bash scripts/run_tests.sh
```

Native packaging needs additional tools. Follow [Build and runtime](docs/BUILD_AND_RUNTIME.md),
[Linux](LINUX.md) or [macOS](docs/MACOS.md). Never use development build commands to publish a release.
Windows, Linux and macOS CI run on pull requests; skipped tests are reported separately from passes.

## Developer documentation and contributions

The [documentation index](docs/README.md) groups user, platform, security and maintainer guides.
The [repository layout](docs/REPOSITORY_LAYOUT.md) defines shared code, platform adapters,
packaging entry points, resources and test ownership without duplicating platform implementations.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report bugs using the
[issue templates](https://github.com/aungyemun/monograph-pdf/issues/new/choose) with synthetic
sample documents; do not attach confidential files.

## License and attribution

© 2026 Aung Ye Mun. Monograph PDF is licensed under the **GNU Affero General Public License,
version 3 or (at your option) any later version** (AGPL-3.0-or-later).
[LICENSE](LICENSE) contains the complete official text; [LICENSE.md](LICENSE.md) provides a summary.
Third-party components retain their own licenses: [notices](THIRD_PARTY_NOTICES.md) and
[dependency inventory](licenses/DEPENDENCY_INVENTORY.md). Use the corresponding Source.zip
listed with a binary release; GitHub's automatic source archives omit third-party source archives.

For research attribution, use [CITATION.cff](CITATION.cff) and record the platform plus the exact
release tag or commit used. [Changelog](CHANGELOG.md).
