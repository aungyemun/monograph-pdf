# Monograph PDF User Guide

Monograph PDF views, edits, organizes, converts, protects and signs PDF documents on your computer.

**Privacy.** Monograph PDF does not upload your documents and does not collect usage data (telemetry); opening, editing, saving, OCR, conversion and printing never use the network. It connects only when you check for updates (or switch on automatic checks) and when you choose to send a problem report — see [Updates](#updates) and [Problem reports](#problem-reports). There is no advertising, online OCR or runtime download of code or models. Optional Word, Excel and PowerPoint conversion: Monograph PDF does not upload the document; conversion uses the locally installed Microsoft Office or LibreOffice application, which follows its own settings and remote-content behavior.

## Contents

- [Getting started](#getting-started)
- [The Monograph PDF window](#the-monograph-pdf-window)
- [Viewing](#viewing)
- [Password-protected PDFs](#password-protected-pdfs)
- [Saving](#saving)
- [Editing](#editing)
- [Forms, tables and layout](#forms-tables-and-layout)
- [OCR (text recognition)](#ocr-text-recognition)
- [Organize pages](#organize-pages)
- [Convert](#convert)
- [Page design](#page-design)
- [Protect, redact and sign](#protect-redact-and-sign)
- [Printing](#printing)
- [Updates](#updates)
- [Problem reports](#problem-reports)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Current limitations](#current-limitations)
- [Troubleshooting](#troubleshooting)
- [Additional documentation](#additional-documentation)

## Getting started

1. Start **Monograph PDF** from the Start menu or the desktop shortcut.
2. Open a file: **File ▸ Open…** (Ctrl+O), drag onto the window, **File ▸ Open Recent**, or in File Explorer right-click **Open with ▸ Monograph PDF**.
3. The start screen also offers Merge PDFs, Word to PDF, Images to PDF, PDF to Word, Rotate Pages, Protect, Unlock, Watermark, Sign and OCR a Scan.

Images and Office files open as a new unsaved PDF; the original is never changed. Clear recent files: **File ▸ Open Recent ▸ Clear Recent Files**.

**Default PDF app:** **Help ▸ Make Monograph PDF the Default PDF App…**.

**Update:** run the newer Setup. **Uninstall:** **Settings ▸ Apps ▸ Installed apps**, or `uninstall.exe` in the installation folder.

- Uninstalling removes the program, shortcuts, registrations, recent-files list and working files.
- The uninstaller asks whether to also remove your **settings** (theme, window layout and similar preferences).
- Your own documents (PDFs you saved, converted or exported files) are never removed.

## The Monograph PDF window

- **Menu bar:** File · Edit · View · Insert · Forms · Organize · Convert · OCR · Protect · Sign · Help
- **Main toolbar:** Open · Save · Print · Undo · Redo · Select · Text · Image · Shape ▾ · Highlight (+ color) · Comment · zoom · page · Find
- The **context toolbar** (second row): font, size, style and arrange tools for the current selection
- **Navigation panel** (F9): Pages, Bookmarks, Search, Files
- **Properties panel** (F8): settings for the selection or document
- **Help ▸ Keyboard Shortcuts** (Ctrl+/) · **View ▸ Theme:** System, Light or Dark

## Viewing

- Zoom: Fit Width (Ctrl+1), Fit Page (Ctrl+2), Actual Size (Ctrl+0); Ctrl+= / Ctrl+-
- Pages: Page Up/Down, Home/End, **View ▸ Go to Page…** (Ctrl+G)
- Find: Ctrl+F; next/previous Enter / Shift+Enter
- **File ▸ Document Properties…** (Ctrl+Alt+D) · full screen F11
- **View ▸ Highlight Fillable Fields** (Ctrl+Shift+H) — screen tint only; never saved

### Bookmarks

The **Bookmarks** tab of the Navigation panel lists the document outline; click a bookmark to go to its page. The buttons above the list (also on the right-click menu) add, rename (F2), point at the current page, move up or down, and delete (Del) bookmarks. **Insert ▸ Bookmark for This Page…** (Ctrl+B) adds one for the page you are viewing, suggesting the first line of the page as its title. Deleting a bookmark also deletes the bookmarks under it (you are asked first). Bookmark changes are undoable and are saved with **File ▸ Save**. Bookmarks that open web pages keep working when you edit others.

## Password-protected PDFs

The **Protected PDF** dialog asks for the password (never stored in recent files, recovery data or logs). **Save** and **Save As** keep protection. Remove it only with **Protect ▸ Unlock PDF (Remove Password)…**. Protection is never removed without the correct password.

## Saving

- **File ▸ Save** (Ctrl+S) · **File ▸ Save As…** (Ctrl+Shift+S)
- **File ▸ Save a Copy**: Selected Pages as PDF…, Flattened PDF…, or Copy with Metadata…
- Other formats: **Convert** menu
- **File ▸ Reduce File Size…**: Lossless · High Quality · Standard · Balanced · Minimum (Balanced and Minimum are lossy)

## Editing

Opening a PDF never changes it. Edits are written only when you save.

- **Insert ▸ Text Box** (`T`); shapes from the Shape ▾ button
- Tool keys: `V` Select · `T` Text Box · `I` Image · `R` Rectangle · `E` Ellipse · `L` Line · `A` Arrow · `P` Freehand · `H` Highlight · `Shift+E` Eraser · `U` Underline · `K` Strikethrough · `N` Sticky Note
- The **context toolbar** and **Properties panel**: font, size, wrapping, box sizing and color
- While typing in a text box or field, Ctrl+Z / Ctrl+Y undo and redo typing and paste; after you leave, **Edit ▸ Undo** / **Edit ▸ Redo** cover the session
- Arrange: Ctrl+] / Ctrl+[ · **Edit ▸ Align & Distribute**
- **Edit ▸ Copy Page as Picture** (Ctrl+Alt+C) — the current page as shown, including unsaved changes, at 150 dpi, ready to paste into another program
- Unsaved documents show `*` in the title; recovery copies are kept for unprotected PDFs only

## Forms, tables and layout

- Fill fields in Select mode (click and type; Tab / Shift+Tab). Mixed Japanese and Latin entries are supported.
- Design: **Edit ▸ Workspace Mode ▸ Forms**, **Forms ▸ Add Field**, **Forms ▸ Detect Fields**, **Forms ▸ Flatten Form on Save**
- Signature fields are **visual** signatures, not certificate-based digital signatures.
- **Forms ▸ Tables ▸ Detect Tables** · **Edit ▸ Align & Distribute** (Preserve Layout or Smart Layout)

## OCR (text recognition)

The OCR engine and English / Japanese language data ship with the app. Nothing is downloaded.

- **OCR ▸ Make PDF Editable…** (summary before conversion)
- **OCR ▸ OCR Whole Document…**, **OCR ▸ OCR Current Page…**, **OCR ▸ Make Searchable PDF…**
- Low-certainty words are marked in amber; Cancel stops after the current page

## Organize pages

Drag thumbnails in the Navigation panel to reorder. Ctrl/Shift+click to multi-select.

- **Organize ▸ Rotate Pages…** (Ctrl+R / Ctrl+Shift+R) — undoable; signed documents ask first
- **Organize ▸ Change Page Size…** · **Organize ▸ Crop Page…**
- **Organize ▸ Copy Pages to Another PDF…** · **Organize ▸ Move Pages to Another PDF…**
- **Organize ▸ Merge PDFs…** (Ctrl+Shift+M) · **Organize ▸ Split PDF…**
- Merging keeps each file's bookmarks, pointing to the right pages. If a file is password-protected, enter its password; the merged PDF is not protected until you use **Protect ▸ Protect with Password…**.
- Also: insert, delete, duplicate, replace, extract pages

## Convert

All conversions run on your computer.

- **Convert ▸ Word, Excel or PowerPoint to PDF…** — uses locally installed Office or LibreOffice; macros are never run by Monograph PDF. Status: **Help ▸ About Monograph PDF ▸ Office Integration**
- **Convert ▸ Images to PDF…** — one page per picture at its own size; photos keep their orientation. Photo details stored in JPEG files (location, camera, date) are not copied into the PDF.
- **Convert ▸ PDF to Word…** (Keep layout / Microsoft Word / Text only)
- **Convert ▸ PDF Tables to Excel…** · **Convert ▸ PDF to PowerPoint…** · **Convert ▸ PDF to Images…** · **Convert ▸ PDF to Text…** · **Convert ▸ Extract Images…**
- **Convert ▸ Conversion Quality Guide…**
- Scanned pages: run OCR first. Protected files: enter the password first; unlock only if you want an unprotected copy (**Protect ▸ Unlock PDF (Remove Password)…**)

## Page design

- **Insert ▸ Header, Footer & Page Numbers…** — text at the left, center or right of the top and bottom margins. `{page}`, `{total}`, `{date}` and `{bates}` are replaced on each page; choose the number style and place, the first page number, date style, text size and color, margins and pages. **Add Bates number** puts a fixed-width page identifier such as `CASE-000001` on every page (prefix, first number, number of digits and suffix are yours to choose); it counts through the whole document. Long text is made smaller to fit between the margins.
- **Insert ▸ Watermark…** — text or a picture; size, color, orientation, opacity, position (center, top or bottom), and in front of or behind the page content. A watermark behind the content is hidden where a page has its own opaque background, such as a scanned page.
- **Insert ▸ Background…** — a color and/or a picture behind the page content (fit or stretched), with opacity.
- Each of these dialogs shows a preview of the current page as it will be saved, remembers your last settings, and writes a new PDF; the open document is not changed. Marks are placed upright on the page as you see it, also on rotated pages.
- **Replace the one added earlier by Monograph PDF** (in each dialog) swaps a header/footer, watermark or background added before instead of adding a second one. **Insert ▸ Remove Header, Footer, Watermark or Background…** removes them. Only marks added by this version of Monograph PDF can be recognized; text or pictures added by other programs are part of the page and are kept.
- **Insert ▸ Image…** (`I`) · **Edit ▸ Selected Image**

## Protect, redact and sign

- **Protect ▸ Protect with Password…** — open and/or permissions password; Allow printing / copying / changes / comments / forms; AES-256 (or AES-128). **Protect & Save As…** writes a new file.
- While you type a password, a strength rating suggests how hard it is to guess (worked out on your computer; nothing is sent or stored). Use a permissions password that differs from the open password — otherwise anyone who can open the file can also lift the restrictions.
- **Protect ▸ Unlock PDF (Remove Password)…** · **Protect ▸ View Permissions…**
- **Protect ▸ Remove Hidden Information…** — lists what the document carries besides its visible pages (document properties and XMP metadata, attached files, scripts and automatic actions, page thumbnails, private application data, comments, form fields, links, bookmarks, invisible text) and saves a new PDF without the kinds you tick. Comments, fields, links, bookmarks and invisible text are kept unless you choose them; invisible text is usually recognised (OCR) text, and removing it stops scanned pages being searchable. Invisible text lying over visible text is kept so the page never changes. Password-protected files must be unlocked first. Marked redactions are not applied here. Anything that is part of the pages themselves is not removed — including text inside pictures and content on layers that are turned off — so check the result before sharing it.
- Markup under Insert (Comments & markup): **Insert ▸ Highlight Text** (pen + color; click again to leave the tool), **Insert ▸ Eraser** (click a highlight or ink mark to remove it), **Insert ▸ Underline Text**, **Insert ▸ Strikethrough Text**, **Insert ▸ Sticky Note Comment…**, **Insert ▸ Callout…**, **Insert ▸ Stamp…** — creation and erase are undoable
- Highlight: stays on for many strokes; change the color menu for the next stroke only; Esc cancels an unfinished stroke (keeps mode); Esc again (or click Highlight) returns to Select. Free-area strokes mark blank pages, pictures and tables; text strokes mark only the characters the pen touches. Completed marks stay when you add text boxes, shapes, images or fill forms (opaque overlays may cover them on screen without deleting them).
- **Protect ▸ Mark Area for Redaction**, **Protect ▸ Mark Text for Redaction…** (every page is searched) or **Protect ▸ Mark Whole Pages for Redaction…**, then **Protect ▸ Apply Redactions…** — truly removes the content (cannot be undone after Apply). Form fields, comments and links that overlap a mark are removed with it. Whole-page marks also remove content hidden outside the visible page area; the pages themselves stay.
- After applying text marks, Monograph PDF looks for the same text elsewhere in the saved file — comments, form values, bookmarks, document properties and attachments — and lists where it is still found. Choose **Remove These Too** to replace it with “[redacted]” (attachments with the text in their name or description are deleted), or **Keep Them**. Monograph PDF never opens or reads attachments, so their contents are not checked: any attachments are listed for you to review.
- **Sign ▸ Type a Signature…** · **Sign ▸ Draw a Signature…** · **Sign ▸ Signature from Image…** — **visual** signatures only, not certificate-based

## Printing

**File ▸ Print…** (Ctrl+P) with live preview. Unsaved overlays print as shown; the open file is not changed.

- Pages: all, current, selected or a range — then **Odd pages** / **Even pages** (by page number, for two-sided printing by hand) and **Reverse order**
- **Comments:** **Document and comments**, or **Document only** (notes, highlights, shapes and stamps left out; form fields still print)

## Updates

**Help ▸ Check for Updates…** checks for a newer version; **File ▸ Settings… ▸ Updates** turns on
automatic checks (off by default), sets how often (every day, every 3 days or every week) and the
release channel (stable, or prereleases as well), and shows the last successful check and the status.
In builds where updates are not yet enabled, the check says so instead of reporting "up to date".

When an update is available you see the installed and available versions, the release date, the
release notes and the download size. **Update Now** downloads the update, verifies it, asks you to
save or discard unsaved changes, closes Monograph PDF, installs the update in the same place and
restarts it; your settings, shortcuts and file-type choices are kept. **Remind Me Later** postpones
it. An installation for all users shows Windows' administrator prompt.

## Problem reports

If something unexpected goes wrong, Monograph PDF can show a problem report — limited technical
information such as the version, Windows version and language, the failing operation and where in
Monograph PDF's code it failed. It never contains your documents, file names, folder paths, user name
or typed text. The full report is shown before you decide: **Don't Send** discards it; **Send to
Developer** sends exactly that report. Nothing is sent without your click. (Sending is not yet enabled
in development builds; the dialog says so.)

## Keyboard shortcuts

| Area | Keys |
| :--- | :--- |
| File | Ctrl+O · Ctrl+S · Ctrl+Shift+S · Ctrl+W · Ctrl+P · Ctrl+, (Settings) · Ctrl+Q |
| Edit | Ctrl+Z · Ctrl+Y · Ctrl+X/C/V · Del · Ctrl+A · Ctrl+Alt+C (copy page as picture) |
| Insert | Ctrl+B (bookmark for this page) |
| View | Ctrl+1 / 2 / 0 · Ctrl+= / − · Ctrl+F · F8 · F9 · F11 · Ctrl+/ |
| Tools | V Select · T Text · H Highlight · Shift+E Eraser · I Image · … |

Full list: **Help ▸ Keyboard Shortcuts**.

## Current limitations

- Windows 10 and Windows 11 (64-bit) only
- Japanese vertical writing is not fully supported for editing
- Office to PDF needs a local suite; PDF to Word / Excel / PowerPoint is best-effort on complex layouts
- Signatures are visual only
- Builds are not code-signed — verify `SHA256SUMS.txt`; SmartScreen may warn

## Troubleshooting

- App will not start: re-run Setup; check antivirus quarantine. You do **not** need to disable antivirus software or add exclusions.
- SmartScreen “Windows protected your PC”: compare Setup with `SHA256SUMS.txt`, then **More info ▸ Run anyway** only for a trusted copy.
- Office conversion missing: **Help ▸ About Monograph PDF ▸ Office Integration**
- Working files: `%LOCALAPPDATA%\Monograph PDF\runtime`; settings: `%APPDATA%\Monograph PDF`; update downloads: `%LOCALAPPDATA%\Monograph PDF\Updates` (removed after a successful update)
- An update could not be installed: the previous version stays installed; run the Setup of the new version from the release page
- Setup ends with an offline self-check; report at `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json`

Opening a PDF never changes it. Your documents and usage data are never sent by Monograph PDF.

## Additional documentation

Installed with Monograph PDF:

- **README.md** — overview
- **CHANGELOG.md** — version history
- **SECURITY.md** — how to report a security issue
- **LICENSE.md** and **THIRD_PARTY_NOTICES.md** — licenses
- **INSTALLATION.md** — install and uninstall

**Help ▸ About Monograph PDF** shows the version and components. **Help ▸ Keyboard Shortcuts** (Ctrl+/) lists every shortcut.
