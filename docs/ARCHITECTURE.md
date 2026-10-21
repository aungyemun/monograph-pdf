# Architecture

Monograph PDF is an offline desktop application for Windows, written in Python 3.11 (the source also
runs on 3.12) with PySide6 (Qt) for the interface, PyMuPDF (MuPDF) for PDF processing and a bundled
Tesseract engine for OCR. End users run `MonographPDF.exe` and need no separate Python, Qt or
Tesseract installation.

## Repository layout

| Path | Contents |
| :--- | :--- |
| `VERSION` | The single source of the product version |
| `app/` | Start-up, file locations and the offline self-check (`--smoke-test`) |
| `core/` | Document model, editing, forms, OCR, conversion, organizing, security and redaction |
| `core/product_meta.py` | Product name, executable name, copyright, branding and license identifiers |
| `engines/` | MuPDF backend, writing edits into the PDF ("baking"), OCR process handling |
| `ui/` | Main window, page canvas, panels, dialogs and themes |
| `resources/` | Icons, logo, styles and fallback fonts |
| `models/tessdata/` | OCR language data (not stored in the repository) |
| `scripts/` | Environment setup, tests, build, packaging and release checks |
| `tests/` | Unit, integration and UI tests with synthetic fixtures |
| `docs/` | User and developer documentation, screenshots and release notes |
| `installer/` | Inno Setup script and uninstaller source |
| `licenses/`, `third_party/` | Dependency inventory and third-party license texts |

Local, untracked folders: `env/` (Python environment), `packages/` (downloaded wheels and source
archives), `runtime/` (working files during development), `build/` and `dist/` (build output).

## Documentation

* Repository root: `README.md`, `INSTALLATION.md`, `LICENSE`, `LICENSE.md`,
  `THIRD_PARTY_NOTICES.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`
* `.github/`: the Windows CI workflow, issue templates and the pull-request template
* `docs/`: `USER_GUIDE`, `FEATURES`, `FILE_FORMATS_AND_COMPATIBILITY`, `ARCHITECTURE`,
  `BUILD_AND_RUNTIME`, `RELEASE_AND_VERSIONING`, `RELEASE_CHECKLIST`, `CODE_SIGNING`,
  `SECURITY_AND_PRIVACY`, `TESTING`; screenshots in `docs/images/`; release notes in
  `docs/releases/`

## Installed layout

```text
{app}\                                  MonographPDF.exe, _internal\, engines\ocr\, models\tessdata\,
                                        docs\, licenses\, uninstall.exe
%APPDATA%\Monograph PDF\                settings and recent files
%LOCALAPPDATA%\Monograph PDF\runtime\   cache, temporary files, logs and recovery sessions
```

Nothing is written to the installation folder `{app}` during normal use.

## How a document flows through the application

1. `MonographPDF.exe` starts, prepares its folders and opens the main window (or runs the self-check
   or the User Guide when started with `--smoke-test` or `--user-guide`).
2. A PDF is opened with MuPDF. Edits such as text boxes, shapes and form entries are kept as
   overlays on an `EditableDocument`, and every change goes through an undoable `CommandStack`.
3. **Save** writes ("bakes") the overlays into the PDF. OCR runs the bundled `tesseract.exe` with the
   bundled language data in a separate process.
4. Page operations change the open document; merge and split always write new files.
5. Page design (`core/convert/page_marks.py`) writes a new file. Each header, footer, watermark or
   background is a Form XObject drawn upright for the displayed page and tagged with
   `/MonographPDFMark` and an optional-content layer, so it can be replaced or removed later.
6. Redaction (`core/redaction/ops.py`) removes the page content under each mark, together with form
   fields, annotations and links that overlap it, and then reports where the marked text still
   occurs elsewhere in the file.

## Platform support

Windows 10 and 11 (64-bit) are the release target. A macOS version is planned and an Android version
may follow; iOS is not planned. The Windows-specific parts are the installer, registry integration and
Office automation through COM.

## Versioning

The version is read from `VERSION` through `core.versioning`; product identity comes from
`core.product_meta`. See [Release and Versioning](RELEASE_AND_VERSIONING.md).

## Related

[Features](FEATURES.md) · [Build and Runtime](BUILD_AND_RUNTIME.md) · [Security and Privacy](SECURITY_AND_PRIVACY.md) ·
[Dependency inventory](../licenses/DEPENDENCY_INVENTORY.md)
