# Features

An overview of what Monograph PDF does today, with pointers to the code for developers. For
step-by-step instructions, see the [User Guide](USER_GUIDE.md).

## Application

- Runs offline as `MonographPDF.exe` (or `python -m app` from source); the version comes from `VERSION`.
- Start page, main and context toolbars, Navigation and Properties panels, light and dark themes.
- Every menu item has its own access key, an icon and a tooltip, and no keyboard shortcut is used
  twice (checked by `tests/ui/test_menu_toolbar_inventory.py`; full inventory with
  `scripts/audit/ui_control_inventory.py`).
- **Help ▸ Keyboard Shortcuts** lists every shortcut; **Help ▸ User Guide** (`F1`, or
  `--user-guide`) opens the User Guide.
- Warns before closing a document with unsaved changes; **Save As**; printing with live preview;
  **Document Properties**.
- **One window at a time.** Starting Monograph PDF again (Start menu, shortcut, or opening a PDF in
  Explorer) brings the open window to the front and opens that PDF there; no second copy is started.
- **Memory saving while minimized.** Page pictures and thumbnails are released and Windows efficiency
  mode is used (not while OCR or a conversion runs): about 30 MB in the background. Large zooms are
  drawn as sharp tiles a few at a time, so scrolling stays smooth on ordinary 8 GB PCs
  (`scripts/perf_check.py` measures speed and memory).

## Viewing

- Opening a PDF never changes it; changes are written only when you save.
- Fit width, fit page or any zoom level; page thumbnails, search, bookmarks and attachments.
- **View ▸ Highlight Fillable Fields** tints form fields on screen only.
- **Scroll button.** Press the mouse wheel button on a page: a round marker appears and the pages
  scroll towards the pointer, faster the further away it is (click to keep scrolling, hold to scroll
  until released). **View ▸ Automatic Scrolling** (`Ctrl+Shift+L`) scrolls at a steady, adjustable
  reading speed.
- **Ctrl + mouse wheel** zooms around the pointer; pages are shown scaled while the sharp picture is
  made.
- Bookmark editing in the Navigation panel: add (`Ctrl+B`), rename, point at the current page,
  move and delete (including sub-bookmarks), all undoable. Bookmarks that open web pages or carry
  styles are preserved (`core/organize/bookmarks.py`).

## Editing and comments

- Edits are kept as overlays with **Undo** / **Redo** (`Ctrl+Z` / `Ctrl+Y`), including undo
  while typing or pasting inside a text box. Overlays are written into the PDF on **Save**, and
  unsaved work is kept in a recovery session (not for password-protected PDFs).
- Existing text can be replaced in place (undoable).
- Commands that write a new file (page design, Remove Hidden Information, Protect & Save As,
  conversions) leave the open document unchanged; applying redactions cannot be undone.
- Text boxes (`T`), shapes, pictures; copy and paste of styles.
- Highlight pen that stays on for several strokes, with a color switch; text highlights follow the
  characters, free-area strokes mark pictures, tables and blank areas. **Esc** cancels an unfinished
  stroke. Underline, strikethrough, sticky notes, callouts and stamps. The Eraser removes highlight,
  underline, strikethrough and ink annotations; it never removes original page content. Creating
  and erasing markup can be undone.
- **Edit ▸ Copy Page as Picture** (`Ctrl+Alt+C`) copies the page as shown at 150 dpi.
- **Color picker** for every color: color field and hue strip, current and new color, Hex / color
  name and R G B, standard and recent colors, **Pick from Screen**, and the contrast on white paper for
  text colors.
- **Pictures in front of or behind text.** *Behind Text* lets the page's text and lines show through
  the picture (multiply blending), also on scanned pages; shown on screen exactly as saved.
- **Properties panel.** Text boxes have opacity, letter spacing and rotation; shapes have opacity, rotation and dash style. Objects can be copied, pasted, duplicated and layered.
- **Squiggly underline.** Markup can be drawn as a squiggly underline, and markup opacity can be set.
- **Comments panel.** **View ▸ Comments Panel** lists, selects, edits, moves and deletes notes.
- **Undo for annotations.** Every annotation change can be undone.
- **Stamp library.** Ten standard stamps, plus custom text and picture stamps, all real PDF stamp annotations.
- **Edit Stamp.** Double-click a placed stamp to change its type, text, font, text / border / fill color,
  border, corners, line thickness, opacity and rotation (live preview). Placed signatures can be
  changed the same way.
- **Several boxes at once.** Drag a rectangle or Ctrl+click to select fields and text boxes and change
  their font, size, color and alignment together; shapes have Line and Fill colors.

## Forms, tables and layout

- Fill in forms in Select mode, with rich field formatting.
- Forms mode to add fields, detect fields automatically and flatten forms.
- Detection of ruled tables; align and distribute objects with Preserve Layout or Smart Layout.

## OCR

- Bundled Tesseract with English, Japanese and orientation data (`eng`, `jpn`, `osd`); works offline.
- Recognize a page or the whole document, add a searchable text layer, or make the text editable.
- **Recognize Text in Area**, and **Extract Text** with a correctable preview: copy, or save as UTF-8 .txt or .docx.
- **Scanned PDF to Word.**
- **Rotated scans.** Rotated and upside-down scans are handled, and an existing text layer is never duplicated.
- **45 optional languages** (Arabic, Burmese, Chinese, Dutch, French, German, Greek, Hindi, Korean, Russian, Spanish, Thai, Vietnamese and more), installed on request: **Download and Install** (one click, from the official Tesseract release), **Install from File…**, or files found in the Downloads folder. A file is accepted only if it matches the pinned size and SHA-256, and is ready at once.

## Organizing and converting

- Insert, delete, rotate, crop, merge and split pages; change the page size.
- **Exact page positions.** Insert blank pages (several at once) or the pages of another PDF, or move
  the selected pages, before or after any page, at the beginning or at the end.
- PDF to Word, Excel and PowerPoint (best-effort); images to PDF and PDF to images; Office files to
  PDF through a locally installed Office suite.
- **Compress PDF.** Best quality (lossless), Balanced, Smallest file, Fit a size limit (an exact maximum in bytes) or My own picture settings (resolution and JPEG quality); text, fonts, comments, forms and drawings are never changed, with an estimate, the measured size and a preview. See [PDF Compression](PDF_COMPRESSION.md).
- **Batch conversion.** Converts many files to Word, Excel, PowerPoint, text, images, a searchable PDF, or Word via OCR.
- **Page sizes in conversions.** PowerPoint and Word files keep each page's size and orientation, with policies for mixed sizes. Document properties come from the PDF. See [PDF to Office](PDF_TO_OFFICE_CONVERSION.md) and [Conversion Fidelity](CONVERSION_FIDELITY.md).
- **Save a Copy ▸ Whole Document** keeps working on the open document. Overwriting files is atomic. See [Save As and Export](SAVE_AS_AND_EXPORT.md).
- Page design: headers and footers in six positions with `{page}`, `{total}`, `{date}` and
  `{bates}`; page numbers; Bates numbers (prefix, first number, digits, suffix); text or picture
  watermarks in front of or behind the content; color or picture backgrounds. Each dialog has a
  live preview and remembers its settings. Marks are placed upright on rotated pages and are tagged
  so they can be replaced or removed later (`core/convert/page_marks.py`).

## Protecting, redacting, signing and printing

- AES-256 encryption with an open password and permissions; unlocking only with the password; an
  offline password-strength rating and a warning when the permissions password equals the open
  password.
- **Protected, signed and watermarked PDFs** are handled consistently: every PDF written from a
  protected PDF keeps its passwords and permissions; the permissions are honoured (the permissions
  password unlocks the rest); unchanged signed PDFs are copied byte for byte; watermarks stay in every
  output. See [Protected, signed and watermarked PDFs](PROTECTED_SIGNED_WATERMARKED_PDFS.md).
- **Remove Hidden Information** finds and selectively removes: document, page and picture metadata
  (including XMP); attachments; scripts and automatic actions (document JavaScript, open actions that
  run something, document and page automatic actions, scripts in comments, fields and bookmarks);
  page thumbnails; private application data; comments; form fields (including XFA data); links;
  bookmarks; and invisible (OCR) text. The result is written to a new, fully rewritten file with no
  earlier revisions, then scanned again. Password-protected files must be unlocked first. Limits are
  listed in [Security and Privacy](SECURITY_AND_PRIVACY.md#hidden-information)
  (`core/security/sanitize.py`).
- Redaction by area, by text search or by whole page, which removes the marked content rather than
  covering it. Form fields, annotations and links under
  a mark are removed with it, and other places where the marked text still occurs (comments, form
  values, bookmarks, document properties, attachments) are listed and can be removed.
- Visual signatures (typed, drawn or from a picture); certificate-based signatures are not supported.
- Printing with preview, including unsaved changes; odd or even pages, reverse order, and printing
  without comments. Two-sided printing (flip on long edge by default); Actual size and All pages are
  the defaults.
- **Colour modes.** Colour, grayscale or true black-and-white.
- **Scaling.** Custom scale, and 2, 4, 6 or 9 pages per sheet.
- **Save as PDF** from the print dialog, with progress and Cancel. See [Printing](PRINTING_AND_PRINT_PREVIEW.md).

## Installer

- Inno Setup installer for all users or the current user, with an offline self-check and a
  dedicated `uninstall.exe`. See
  [Build and Runtime](BUILD_AND_RUNTIME.md#installer-and-uninstaller-design).

## Screenshots

Captured from the application with synthetic sample documents (`scripts/make_readme_screenshots.py`).

<p>
  <img src="images/monograph-pdf-editing-comments.png" alt="Review markup on a document: highlighted and underlined text, a rectangle with an arrow, a text-box comment and a sticky note" width="49%">
  <img src="images/monograph-pdf-forms.png" alt="A form being filled in, with its fillable fields highlighted" width="49%">
</p>

<img src="images/monograph-pdf-page-thumbnails.png" alt="Navigation panel showing page thumbnails beside the open document" width="100%">

<p>
  <img src="images/monograph-pdf-header-footer.png" alt="Header, footer and page numbers dialog with a live preview of the page" width="56%">
  <img src="images/monograph-pdf-password-protect.png" alt="Encrypt with a password dialog: open password, permissions and AES-256 encryption" width="36%">
</p>

<img src="images/monograph-pdf-remove-hidden.png" alt="Remove hidden information dialog listing what was found in the document" width="50%">

## Planned

- Editing Japanese vertical text
- Improved Smart Layout
- Rebuilding the visual layout of recognized (OCR) pages
- Certificate-based digital signatures

## Not planned

- Cloud services, online OCR or any feature that requires an internet connection
- Requiring users to install Python, Qt or Tesseract separately

## See also

[Architecture](ARCHITECTURE.md) · [File formats and compatibility](FILE_FORMATS_AND_COMPATIBILITY.md) · [User Guide](USER_GUIDE.md)
