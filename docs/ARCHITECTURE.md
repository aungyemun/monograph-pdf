# Architecture

Windows-first offline PDF app: Python 3.11/3.12, PySide6, PyMuPDF, vendored Tesseract. End users run `MonographPDF.exe` with no separate Python/Qt/Tesseract. qpdf is reserved and not shipped.

## Layout

| Path | Role |
|---|---|
| `VERSION` | Sole product version |
| `core/product_meta.py` | Name, exe, copyright, branding, license |
| `app/` | Bootstrap, paths, smoke-test |
| `core/` | Document, editing, forms, OCR, convert, security, … |
| `engines/` | MuPDF backend, bake, OCR; `qpdf/` unused |
| `ui/` | Main window, canvas, dialogs, theme |
| `resources/` | Icons, styles, fonts |
| `models/tessdata` | OCR language data |
| `scripts/` | Env, tests, build, packaging |
| `tests/` | unit / integration / ui |
| `docs/` | Eight canonical Markdown files |
| `installer/` | Inno Setup + release outputs |
| `env/` · `packages/` · `runtime/` | Dev env, wheel/source cache, local working files |

### Documentation set

Root: `README.md`, `INSTALLATION.md`, `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `SECURITY.md`, `CHANGELOG.md`, `CITATION.cff`.  
`docs/`: `USER_GUIDE`, `FEATURES`, `FILE_FORMATS_AND_COMPATIBILITY`, `ARCHITECTURE`, `BUILD_AND_RUNTIME`, `RELEASE_AND_VERSIONING`, `SECURITY_AND_PRIVACY`, `TESTING`.

### Installed layout

```text
{app}\  MonographPDF.exe, _internal\, engines\ocr\, models\tessdata\, docs\, licenses\, uninstall.exe
%APPDATA%\Monograph PDF\              settings, recent files
%LOCALAPPDATA%\Monograph PDF\runtime\ cache, temp, logs, sessions
```

Nothing is written into `{app}` during normal use.

## Process

1. Start exe → bootstrap → MainWindow (or `--smoke-test` / `--user-guide`).
2. Open via MuPDF; overlays on `EditableDocument` + `CommandStack`.
3. Save bakes overlays; OCR uses local `tesseract.exe` + tessdata.
4. Organize mutates the live doc; merge/split write new files only.
5. Page design (`core/convert/page_marks.py`) writes a new file: each header/footer, watermark or background is a Form XObject drawn upright for the displayed page, tagged with `/MonographPDFMark` and an optional-content layer so it can be replaced or removed later.
6. Redaction (`core/redaction/ops.py`) removes page content plus form fields, annotations and links under each mark, then reports the marked text found elsewhere in the file.

## Portability

**Windows 10/11 x64** is the release target. macOS planned; Android future; iOS not planned. Windows-only edges: installer, registry, Office COM.

## Versioning

`VERSION` via `core.versioning`. Identity via `core.product_meta`. See [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md).

## Related

[FEATURES.md](FEATURES.md) · [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md) · [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) · `../licenses/DEPENDENCY_INVENTORY.md`
