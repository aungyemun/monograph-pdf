# Features

This document is the developer-facing feature map of Monograph PDF. How to use each feature is described in the [User Guide](USER_GUIDE.md); this map does not repeat it.

## Shipped

### Platform shell
- Offline desktop app (`MonographPDF.exe` / `python -m app`)
- Version from `VERSION` (About / diagnostics); title bar shows product name / filename only
- Start screen with recent files and one-click tools; icon toolbar + context toolbar (second row); Navigation panel (left) and Properties panel (right), both collapsible
- Unified light/dark design system (`ui/theme.py` palette → stylesheet, icons, canvas); Fusion style for consistent UI rendering across supported environments
- Drawn, theme-aware icon set (100+ icons) across toolbar and menus; tooltips show shortcuts
- Complete keyboard map (tool letters, navigation, arrange, pages) + searchable **Help ▸ Keyboard Shortcuts**; offline **Help ▸ User Guide** (also `MonographPDF.exe --user-guide`, used by the Start menu shortcut)
- Draw-to-place for markup, stamps, callouts, redaction areas and signatures; text markup snaps to words
- Unsaved-changes guard on open/close; Save As continues on the new file; Print dialog with live preview; Document Properties
- Official logo in window/taskbar/exe icon + About; centered footer copyright
- Project-contained env/packages/engines/models layout; deferred startup warmup after first paint

### Document core + viewer
- Open local PDF (File ▸ Open…, drag/drop, Open Recent, command line); password only when required
- Opening never modifies the source file
- Continuous canvas; zoom toolbar **Fit ▾ / − / % / +** synced with View menu and footer
- Thumbnails, search, bookmarks, attachments; document properties; Highlight Fillable Fields (UI-only)
- High-DPI aware rendering; nearby-page cache

### Editing (non-destructive overlays)
- Editable document model + command Undo/Redo (Ctrl+Z / Ctrl+Y)
- Selection, handles, move, resize, delete, copy/paste, duplicate, layer order
- Alignment guides / snapping; keyboard nudge; multi-select (Ctrl)
- **Text Box** tool (toolbar / `T`): click or drag create, caret + immediate typing; Esc / Ctrl+Enter → Select
- Overlay-only move/resize (native page pixmap stays cached during drag)
- Box sizing: Grow to fit text (default), Size to text, Shrink text to fit, Fixed size (+ overflow warning)
- Contextual font toolbar: family, size, −/+, B/I/U, align, color
- Properties panel switches automatically (text / form field / shape / image / document)
- Shape overlays: Rectangle, Ellipse/Circle, Line, Arrow, Freehand — Shift constraints; stroke/fill/opacity
- Padding, H/V align, colors, border, opacity, rotation, tracking, leading
- Horizontal writing; Japanese vertical writing (`vertical-rl`) planned
- Unicode / Japanese / English; font fallback with substitution notice
- Copy Style / Paste Style; Auto Match Nearby Text (basic)
- Existing-text: span extract; safe replace or undoable redaction+reinsertion
- Save / Save As bake overlays; dirty `*` state; local session autosave/recovery

### Forms / tables / layout
- **Direct fill in Select mode** (click field → type; Tab order; checkbox/radio/dropdown) — Forms mode not required for filling
- Field formatting from the field toolbar: font, size (A− / A+), bold, italic, color, UPPER / lower case, alignment left / center / right / **justify** and top / middle / bottom, wrap; for the whole entry or for **selected words** (saved as rich text: `/RV` + `/DS`, plain text in `/V`, custom appearance stream); justify and vertical position are stored in private PDF field keys whose names are kept stable so documents remain readable across versions
- Fields shown in several places (same name) receive the entry and formatting in every place
- **View ▸ Highlight Fillable Fields** (UI-only; never written into saved files)
- Read & edit AcroForm: text, multiline, checkbox, radio, dropdown, date-style, signature (**visual only** — not cryptographic)
- Auto font size (0) preserved as Auto; dirty overlays fit text without replacing Auto permanently until set
- **View fidelity:** page render + widget `/AP`; field names / XFA SOM paths are never painted as content; empty fields stay empty
- XFA detected (none/static/dynamic/hybrid); interactive XFA editing is **not** claimed — hybrid forms use AcroForm appearances for viewing
- Forms mode (Edit ▸ Workspace Mode ▸ Forms) for design: create/move/resize fields, Detect Fields (candidates for review with Keep / Discard; detection never alters the PDF), Flatten Form on Save
- Line-based table detection (only tables detected with high confidence are offered); row/col add/delete; merge/split where structure allows; cell text/borders
- Layout mode: align, distribute, snap; **Preserve Layout** (default) vs **Smart Layout** (basic: moves related objects only — no silent reflow)
- Font resolver for new/edited text: subset-prefix aware, Japanese/Latin fallbacks, optional bundled OFL Noto fonts; lazy font inventory

### Offline OCR
- Vendored Tesseract under `engines/ocr` + local `models/tessdata` (`eng`, `jpn`, `osd`) — **no runtime model downloads**
- Detect image-only/scanned pages; OCR document / current page / region pass
- Invisible searchable text layer (preserves original scan visually unless reconstruction is chosen later)
- Recognized text + bounding boxes exposed as editable overlays; confidence metadata; low-confidence review indicators
- Orientation/script detection via OSD where supported; mixed Japanese/English (`eng+jpn`)
- **Make PDF Editable** analysis: inspect native text, forms, field/table candidates, images, scanned regions, OCR need — summarize before conversion
- Skips native-text pages; page-by-page progress/cancel; bounded memory; fully offline

### PDF organization
- Insert PDF pages / blank page; delete; duplicate; replace; drag/drop reorder (thumbnails); rotate (Rotate Pages dialog: all / current / selected / odd / even / range, 90° either way or 180°); crop; extract
- Move/copy pages between opened documents (target saved as new file); page range selection; **Change Page Size** — A3–A6, B4/B5 (JIS and ISO), Letter, Legal, Tabloid, Executive, postcard or custom; fit / fill / stretch / original size; orientation; margin; page scope. Content is scaled as vector (no rasterizing) and form fields, links and annotations are transformed with it
- **Merge / Combine** workspace: add local PDFs, thumbnails list, reorder, include/exclude pages, combine to new PDF; sources preserved; encrypted inputs with password; signature consequence warnings
- **Split**: ranges, selected pages, every page, every N pages, bookmarks when available
- Batch merge/split on background workers (UI stays responsive); temps under `runtime/temp/organize` (never project root); abandoned temp cleanup on startup

### Convert (offline)
- **PDF → Word (DOCX):** high-fidelity reconstruction for most documents via bundled layout engine (pdf2docx, GPL-3.0); complex layouts, unusual fonts, or scanned pages may require manual adjustment. Optional Microsoft Word PDF-reflow when Word is installed; text-only fallback. Background worker with progress; page range supported
- **Word / Excel / PowerPoint / RTF / ODF → PDF:** Monograph PDF does not upload the document. Conversion uses the locally installed Microsoft Office or LibreOffice application (COM automation or headless), which follows its own settings and remote-content behavior, to preserve layout as closely as that application normally does. Neither suite is bundled; when neither is present the command explains what is needed
- **Open with:** images and Office files open as a new unsaved PDF (converted in place); Save routes to Save As beside the original
- **Also:** images→PDF; PDF pages→PNG/JPEG/TIFF; extract embedded images; PDF→plain text; scanned→searchable (OCR); tables→XLSX; PDF→PPTX (page images as slides); selected pages→PDF; flattened PDF; metadata-preserving copy
- **Images:** add/replace/move/resize/crop/rotate/opacity/arrange/export as overlays; baked on Save
- **Optimize:** Lossless / High Quality / Standard / Balanced / Minimum; Lossless never downsamples images; Balanced/Minimum labeled lossy; garbage cleanup; optional metadata removal; size before/after + reduction %
- **Watermark** (text, size, color, rotation, opacity, page scope) / **header / footer / page numbers**; every script (Japanese included) via embedded fonts

### Annotations
- Highlight, underline, strikeout, text comment, callout, freehand, lines/arrows, rectangle/ellipse
- Built-in MuPDF stamps (Approved/Draft/Confidential/…) — no third-party stamp artwork

### Security
- AES-256 (or AES-128) password protection with an optional separate permissions password and individual permissions: print, high-quality print, copy, modify, assemble pages, comments, form filling; inspect permissions/metadata/attachments
- **Unlock PDF**: remove protection **only** with a valid password (never silent); forms, outlines and metadata are preserved
- Metadata removal writes a new file; does not strip encryption as a side effect

### Redaction
- Mark region/text (preview annots); **Apply True Redaction** uses `apply_redactions()` — not opaque covers
- Verification: redacted strings are not recoverable by normal text extraction

### Installer

- Inno Setup installer (per-machine or per-user), Start menu / desktop shortcuts, `.pdf` and Open-with registrations, offline self-check including OCR
- `uninstall.exe` registered with **Settings ▸ Apps**; removes application, shortcuts, registrations, recent files and working files; optional complete removal of settings (`/REMOVEUSERDATA` when silent); see [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md#installer-and-uninstaller-design)

### Signatures
- Visual typed / drawn / image signatures only; clearly labeled non-cryptographic
- Cryptographic certificate signing not packaged; signed-PDF edit warnings

### Printing
- Monograph PDF's own print dialog with live sheet preview: printer, copies/collation, page range or selected thumbnails, paper, orientation (Auto per page), scaling (Fit / Actual size / Shrink large pages), color or black & white, two-sided; **Printing preferences…** opens the printer driver's settings
- Unsaved overlays (text boxes, typed form values, shapes, images, tables) are included via a temporary bake — source PDF untouched
- High-resolution page rasters with aspect ratio preserved (no stretch/bend)
- Printing is optional — PDF export does not require a printer

## Planned (later stages — not implemented now)

| Area | Intent |
|---|---|
| Full Japanese vertical glyph layout | Complete `vertical-rl` renderer |
| Richer Smart Layout constraints | Group/locked constraints beyond edge-related nudge |
| OCR visual reconstruction | Optional redraw of glyphs instead of preserving scan pixels |
| Cryptographic digital signatures | Local certificate workflow if later accepted for packaging |

## Explicit non-goals

- Cloud APIs, accounts, login, telemetry
- Online OCR or remote document processing
- Mandatory internet for any core feature
- Requiring end users to install Python, Tesseract, or Qt (qpdf — still a reserved optional integration; not used or shipped in v0.2.0)

## Cross-references

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Formats: [FILE_FORMATS_AND_COMPATIBILITY.md](FILE_FORMATS_AND_COMPATIBILITY.md)
- User-facing usage: [USER_GUIDE.md](USER_GUIDE.md)
