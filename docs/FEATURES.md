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

## Viewing

- Opening a PDF never changes it; changes are written only when you save.
- Fit width, fit page or any zoom level; page thumbnails, search, bookmarks and attachments.
- **View ▸ Highlight Fillable Fields** tints form fields on screen only.
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

## Forms, tables and layout

- Fill in forms in Select mode, with rich field formatting.
- Forms mode to add fields, detect fields automatically and flatten forms.
- Detection of ruled tables; align and distribute objects with Preserve Layout or Smart Layout.

## OCR

- Bundled Tesseract with English, Japanese and orientation data (`eng`, `jpn`, `osd`); nothing is
  downloaded.
- Recognize a page or the whole document, add a searchable text layer, or make the text editable.

## Organizing and converting

- Insert, delete, rotate, crop, merge and split pages; change the page size.
- PDF to Word, Excel and PowerPoint (best-effort); images to PDF and PDF to images; Office files to
  PDF through a locally installed Office suite.
- File size reduction with several presets.
- Page design: headers and footers in six positions with `{page}`, `{total}`, `{date}` and
  `{bates}`; page numbers; Bates numbers (prefix, first number, digits, suffix); text or picture
  watermarks in front of or behind the content; color or picture backgrounds. Each dialog has a
  live preview and remembers its settings. Marks are placed upright on rotated pages and are tagged
  so they can be replaced or removed later (`core/convert/page_marks.py`).

## Protecting, redacting, signing and printing

- AES-256 encryption with an open password and permissions; unlocking only with the password; an
  offline password-strength rating and a warning when the permissions password equals the open
  password.
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
  without comments.

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
