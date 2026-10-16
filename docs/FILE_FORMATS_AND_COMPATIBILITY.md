# File formats and compatibility

## Primary format

- **PDF** — open, view, edit (non-destructive overlays + bake on Save), organize, convert/export, OCR, annotate, protect, redact, and print locally via PyMuPDF. qpdf — still a reserved optional integration; not used or shipped in v0.2.0.

## Ancillary inputs (shipped)

| Kind | Notes |
|---|---|
| Images (PNG/JPEG/TIFF/BMP/GIF/WebP) | Open as a new PDF; insert as overlays; Images→PDF; page export to PNG/JPEG/TIFF; extract embedded images |
| Plain text | Text boxes / stamps / overlays; PDF→plain text export |
| Fonts | Local system fonts with fallback; substitution noted in the Properties panel when needed |

## Compatibility targets

| Platform | Priority |
|---|---|
| Windows 10/11 (x64) | Supported / primary — the only release target (`MonographPDF.exe`) |
| macOS | Planned — not available yet |
| Android | Future |
| iOS | Not currently planned |
| Linux | Portable architecture; not a release target |

## Engine compatibility

| Engine | Role | State |
|---|---|---|
| PyMuPDF | Open, render, edit bake, text search, metadata, security, redaction, annotations | Active via `engines/mupdf_backend` |
| qpdf | Reserved optional integration | Not used or shipped in v0.2.0 (`engines/qpdf` placeholder may remain) |
| Tesseract | Offline OCR | Vendored `engines/ocr` + `models/tessdata` (`eng`/`jpn`/`osd`) |

## Viewer / document detection (best-effort)

| Signal | Notes |
|---|---|
| Text vs image/scanned page | Heuristic from extracted text length + embedded images |
| AcroForm | Widgets / catalog `/AcroForm`; widget `/AP`, `/V`, `/DA`, `NeedAppearances` |
| XFA | Detected as `none` / `static` / `dynamic` / `hybrid` / `unknown` from AcroForm `/XFA` |
| Encryption | PyMuPDF `is_encrypted` / authenticate |
| Digital signatures | Signature widgets or `/FT /Sig` when present — edit warnings; visual signatures only for insertion |
| Page size / rotation | PDF page rect + `/Rotate` |
| Fonts | Embedded/subset inventory; system + bundled OFL fallbacks for *editing* only |

## Support levels (current)

| Area | Level | Notes |
|---|---|---|
| View / zoom / search | Full | Offline local files; MuPDF page render + widget `/AP` when present |
| Overlay text/image edit | Full | Baked on Save; source untouched until Save |
| Forms (AcroForm) | Partial | Values/geometry editable; per-word formatting saved as rich text (`/RV`, `/DS`) with plain `/V`; justify and vertical position kept in private keys (other readers show left / top); **view never paints field names / XFA SOM paths**; prefers existing `/AP`; does not regenerate appearances on open |
| Forms (XFA) | Partial / unsupported | Hybrid: view AcroForm `/AP` + page content; interactive XFA template editing **unsupported**. Pure dynamic XFA without widgets: editing unsupported; view is best-effort MuPDF |
| Tables | Partial | Detection + row/col tools |
| Fonts (view) | Full (engine) | Embedded PDF fonts/subsets used by MuPDF for page rendering |
| Fonts (edit) | Partial | Resolver: embedded name → local match → bundled Noto (OFL) → warning; lazy inventory (no full scan at startup) |
| OCR | Full (offline) | eng/jpn; no runtime downloads |
| Organize / merge / split | Full | Writes new files; sources preserved |
| Convert Office→PDF (.docx .doc .docm .rtf .odt .txt · .xlsx .xls .xlsm .xlsb .csv .ods · .pptx .ppt .pptm .pps .ppsx .odp) | Supported when Microsoft Office or LibreOffice is installed | Monograph PDF does not upload the document; conversion uses the locally installed suite, which follows its own settings and remote-content behavior; unavailable when neither suite is detected |
| PDF→DOCX | High fidelity (most documents) | Layout engine (pdf2docx): fonts, tables, images, columns, margins; optional Word reflow; text-only fallback; complex/scanned pages may need adjustment |
| PDF→XLSX / PPTX | Best-effort | Tables only / page images as slides — labeled in the dialog |
| Open images / Office files | Supported | Converted to a new unsaved PDF; original untouched |
| Cryptographic signatures | Unsupported | Visual signatures only |
| Japanese vertical (`vertical-rl`) | Not supported (planned) | Text is laid out horizontally |

## Viewing invariant

Opening a PDF with no edits must show the MuPDF page appearance. Editable overlays are not auto-created for every form field. Internal identifiers such as `topmostSubform[0].Page1[0]…` remain metadata (Properties panel / diagnostics only).

## Page geometry

- PDF points (1/72 in) are the coordinate source of truth.
- Pages may differ in size within one document (A0–A6, Letter, Legal, Tabloid/Ledger, Executive, custom).
- Fit Width / Fit Page use the **current** page dimensions; continuous view does not normalize sizes.
- `/Rotate` 0/90/180/270 is honored for layout and hit-testing; view rotation ≠ persistent page rotation.
- The Properties panel may show nominal labels (e.g. `A4 — 210 × 297 mm`) with tolerance matching.

## Encryption

- Password dialog: **Protected PDF** — masked entry, Show password, incorrect-password retry; Cancel leaves the file unopened.
- Passwords are never written to Recent, autosave/session JSON, or logs.
- Protection is never removed silently.

## Save / Save As / Optimize

| Mode | Behavior |
|---|---|
| Save / Save As | Prefer vector/text; keep embedded fonts; do not full-page rasterize; bake only dirty overlays/fields |
| Optimize → Lossless | Garbage/deflate/dedup only — **never** downsample or recompress rasters |
| Optimize → High Quality | Preserve image streams by default |
| Optimize → Standard | Default recommended balance |
| Optimize → Balanced | May recompress/downsample oversized rasters — labeled **lossy**, not lossless |
| Optimize → Minimum | Stronger size reduction — labeled lossy |

Unmodified AcroForm/XFA widgets are not rewritten on Save merely because another overlay changed.

## Related

- Features: [FEATURES.md](FEATURES.md)
- Security: [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)
- User-facing description of these behaviors: [USER_GUIDE.md](USER_GUIDE.md)
