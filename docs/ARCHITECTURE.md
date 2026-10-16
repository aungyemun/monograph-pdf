# Architecture

Monograph PDF (formerly PDF Editor, final release 0.1.5) is a Windows-first, offline desktop PDF toolkit. Source is Python 3.11/3.12-compatible; the UI uses PySide6 (Qt); PDF rendering/core operations use PyMuPDF; OCR uses vendored Tesseract. qpdf — still a reserved optional integration; not used or shipped in v0.2.0. End users install it with Setup and start `MonographPDF.exe` with no mandatory internet and no user-installed Python, Tesseract, or Qt.

## Layout

| Path | Role |
|---|---|
| `MonographPDF.exe` | Canonical Windows entry (built into project root; onedir with `_internal/`) |
| `VERSION` | Sole authoritative product version |
| `core/product_meta.py` | Canonical product name, copyright, executable name, branding paths, license (`AGPL-3.0-or-later`) |
| `resources/icons/` | Official logo masters + Windows/macOS/Linux icon sets (offline) |
| `app/` | Bootstrap, paths, package entry (`python -m app`), offline smoke-test / network guard |
| `core/` | Document model, page info, render cache, commands, recent files, versioning |
| `core/editing/` | Non-destructive overlays: TextBox, fonts, commands, session store |
| `core/forms/` | AcroForm load/apply, field model, candidate detection |
| `core/tables/` | Table model + line-based detection |
| `core/layout/` | Align/distribute; Preserve vs Smart layout policy |
| `core/ocr/` | Offline Tesseract adapter, page pipeline, Make Editable analysis |
| `core/organize/` | Page ops, merge/combine, split, temp cleanup, page-index remap helpers |
| `core/convert/` | Convert/export, optimize, watermark; Office bridge; capability registry |
| `core/annotations/` | Native MuPDF annotations (markup, ink, shapes, stamps) |
| `core/security/` | Encrypt/decrypt, permissions, metadata, attachments |
| `core/redaction/` | Mark + true `apply_redactions` content removal |
| `core/signatures/` | Visual signature insertion (non-cryptographic) |
| `core/printing/` | Print bake + high-DPI raster helpers (color/grayscale) for Monograph PDF's print dialog with preview |
| `engines/` | `mupdf_backend`, `bake_edits` (+ flatten) + vendored `ocr/` (Tesseract); `qpdf/` placeholder unused in v0.2.0 |
| `ui/` | Main window, PDF canvas, panels, dialogs, theme, About |
| `resources/` | Icons, styles, i18n assets, fallback fonts |
| `runtime/` | Local working files when run from the project folder (`cache/`, `temp/`, `logs/`, `sessions/`) |
| `packages/` | Wheel cache (`packages/wheels`); `packages/sources` = third-party source archive cache |
| `models/` | OCR language data (`tessdata`: eng / jpn / osd) |
| `third_party/` | Third-party license texts and metadata for bundled components (installed into `{app}\licenses` where required) |
| `tools/` | Dev/build helper tools (Inno Setup under `tools/inno`) |
| `scripts/` | Env setup, tests, version bump, exe/release build, packaging |
| `tests/` | unit / integration / ui + fixtures/samples + `outputs/` |
| `reports/` | Audit and release evidence (not end-user documentation) |
| `docs/` | Canonical documentation (exactly eight Markdown files; see Documentation set below) |
| `licenses/` | Dependency inventory (`DEPENDENCY_INVENTORY.md`) |
| `installer/` | Inno Setup script, `uninstall.exe` launcher source, wizard images, release outputs |
| `build/` | Build intermediates only |
| `dist/` | Packaged distributables (`dist/MonographPDF/`) |
| `env/` | Local Python virtual environment (developer) |

Project-contained development/runtime resources stay under `env`, `packages`, `tools`, `runtime`, `engines`, `models`, `resources`, `third_party`. Do not scatter dependencies into arbitrary folders.

### Documentation set

Root: `README.md`, `INSTALLATION.md`, `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `SECURITY.md`, `CHANGELOG.md`, `CITATION.cff`.  
`docs/`: `USER_GUIDE.md`, `FEATURES.md`, `FILE_FORMATS_AND_COMPATIBILITY.md`, `ARCHITECTURE.md`, `BUILD_AND_RUNTIME.md`, `RELEASE_AND_VERSIONING.md`, `SECURITY_AND_PRIVACY.md`, `TESTING.md`.

### Installed layout (end user)

```text
{app}\                          C:\Program Files\Monograph PDF  or  %LOCALAPPDATA%\Programs\Monograph PDF
  MonographPDF.exe, _internal\, engines\ocr\, models\tessdata\
  docs\USER_GUIDE.md
  licenses\                     GPL / LGPL / MPL / GCC exception texts
  README.md, LICENSE.md, THIRD_PARTY_NOTICES.md, SECURITY.md, CHANGELOG.md
  uninstall.exe, unins000.exe, installed_files.txt

%APPDATA%\Monograph PDF\              Settings, recent-files list, legacy_migration.json
%LOCALAPPDATA%\Monograph PDF\runtime\  Cache, temp, logs, recovery sessions
%LOCALAPPDATA%\Monograph PDF\logs\     Setup self-check report

%APPDATA%\PDF Editor\, %LOCALAPPDATA%\PDF Editor\   PDF Editor (<= 0.1.5) data: read once by the
                                first start (core/legacy_migration.py), never changed
```

Nothing is written into `{app}` during normal use. User documents are never stored under the installation folder.

## Process model

1. User starts `MonographPDF.exe` (or `python -m app` in a populated `./env` for development).
2. `app.bootstrap.main` ensures runtime folder layout, copies a PDF Editor user's settings once (`core.legacy_migration`), creates `QApplication`, shows `ui.main_window.MainWindow` (or, with `--smoke-test`, runs the offline self-check; with `--user-guide`, shows only the User Guide).
3. Open/view flows use `core.document.open_document` → `engines.mupdf_backend.MuPdfBackend` (PyMuPDF). Source files are never modified on open.
4. `EditableDocument` holds overlay objects in PDF coordinates; the canvas paints them in real time. Commands on `CommandStack` provide Undo/Redo.
5. Save / Save As call `engines.bake_edits.bake_via_backend` to write overlays into a PDF file. Session JSON under `runtime/sessions/` enables crash recovery without touching the original until Save.
6. `ui.pdf_canvas` renders visible/nearby pages via `core.render_cache`; thumbnails stay background/cancellable.
7. Engine probes report local availability only — never over the network.
8. OCR uses vendored `engines/ocr/tesseract.exe` with `models/tessdata` (`eng`/`jpn`/`osd`). `TESSDATA_PREFIX` points at the local tessdata folder; no network downloads. Page-by-page pipeline exposes words/boxes and can bake an invisible searchable layer.
9. Page organize mutates the live MuPDF document in memory; overlays remap via `EditableDocument.remap_page_indices`. Bake prefers the live document so structural edits survive Save. Merge/split write only new files under user-chosen paths; staging uses `runtime/temp/organize`.

## Portability

**Windows 10/11 x64** is the validated release platform. Paths are resolved via `pathlib` from the repository root (`app.paths`). Native binaries are placed under `engines/` with OS-specific subfolders as they are vendored. Portable architecture may later support macOS/Linux with adapted launcher/engine binaries; those platforms are **not** validated releases in v0.2.0.

Platform status: Windows 10/11 x64 supported (primary); macOS planned; Android future; iOS not planned. Preparation without a structural rewrite: product identity, data-folder names and environment overrides are platform-neutral (`core.product_meta`, `core.app_env`, `core.user_prefs` already resolve macOS *Application Support* and XDG folders); Windows-only code stays at the edges (`installer/`, Windows registry and COM use in `core/convert/office_bridge.py`, `core/safe_paths.windows_tool`, Windows packaging scripts). New platform-specific code should go into `platform/<os>/` and `packaging/<os>/` folders when a second platform is started, not into `core/`.

## Versioning

All product **version** metadata must read `VERSION` through `core.versioning` / `app.read_version`. Product **name, executable name, PE version strings, copyright, data-folder names, branding paths and the predecessor's (PDF Editor's) names** come from `core.product_meta` (do not duplicate). See [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md).

## Related docs

- Features roadmap: [FEATURES.md](FEATURES.md)
- Build/runtime: [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md)
- Security/privacy: [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)
- Licenses: `../licenses/DEPENDENCY_INVENTORY.md`
