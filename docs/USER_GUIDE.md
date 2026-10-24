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
3. The start screen also offers Merge PDFs, Word to PDF, Images to PDF, PDF to Word, PDF to PowerPoint, Compress, Rotate Pages, Protect, Unlock, Watermark, Sign and OCR a Scan. In a small window it scrolls.

Images and Office files open as a new unsaved PDF; the original is never changed. Clear recent files: **File ▸ Open Recent ▸ Clear Recent Files**.

**Default PDF app:** **Help ▸ Make Monograph PDF the Default PDF App…**.

**Update:** run the newer Setup. **Uninstall:** **Settings ▸ Apps ▸ Installed apps**, or `uninstall.exe` in the installation folder.

- Uninstalling removes the program, shortcuts, registrations, recent-files list and working files.
- The uninstaller asks whether to also remove your **settings** (theme, window layout and similar preferences).
- Your own documents (PDFs you saved, converted or exported files) are never removed.

## The Monograph PDF window

- **Menu bar:** File · Edit · View · Insert · Forms · Organize · Convert · OCR · Protect · Sign · Help
- **Main toolbar:** Open · Save · Print · Undo · Redo · Select · Text · Image · Shape ▾ · Highlight (+ color) · Eraser · Comment · Fit ▾ · zoom · page · Find · Navigation and Properties panel buttons. In a narrower window the Select, Text, Highlight and Eraser buttons show icons only (their names appear as tooltips) so the rest stays on the toolbar; anything that still does not fit is under the » button at the right end
- The **context toolbar** (second row): font, size, style and arrange tools for the current selection
- **Navigation panel** (F9): Pages, Bookmarks, Search, Comments, Files (Files only when the PDF has attachments). In a narrow panel the tabs show icons, with the current tab’s name
- **Properties panel** (F8): settings for the selection or document
- **Help ▸ Keyboard Shortcuts** (Ctrl+/) · **View ▸ Theme:** System, Light or Dark
- **One window at a time:** starting Monograph PDF again while it is open (from the Start menu, a shortcut, or by opening a PDF in Explorer) does not start a second copy. The open window comes to the front and opens that PDF (asking first if there are unsaved changes), or says that Monograph PDF is already running
- **Memory saving while minimized:** a few seconds after you minimize the window, Monograph PDF releases the page pictures and thumbnails it can draw again and lets Windows run it in efficiency mode, so it uses very little memory in the background (about 30 MB in our tests). A running OCR or conversion is never slowed down. Restoring the window shows the page at once

## Viewing

- Zoom: Fit Width (Ctrl+1), Fit Page (Ctrl+2), Actual Size (Ctrl+0); Ctrl+= / Ctrl+-; Ctrl + mouse wheel zooms around the pointer
- Pages: Page Up/Down, Home/End, **View ▸ Go to Page…** (Ctrl+G)
- **Scroll button**: press the mouse wheel button on a page — a round marker appears. Move the pointer above or below it and the pages scroll that way, faster the further away (sideways too when the page is wider than the window). After a click, scrolling continues until the next click or Esc; while you hold the button, it stops when you release it
- **View ▸ Automatic Scrolling** (Ctrl+Shift+L): the pages scroll at a steady reading speed; ↓ faster, ↑ slower (and back up), Esc or a click stops; it stops at the end of the document
- Find: Ctrl+F; next/previous Enter / Shift+Enter
- **File ▸ Document Properties…** (Ctrl+Alt+D) · full screen F11
- **View ▸ Highlight Fillable Fields** (Ctrl+Shift+H) — screen tint only; never saved

### Bookmarks

The **Bookmarks** tab of the Navigation panel lists the document outline; click a bookmark to go to its page. The buttons above the list (also on the right-click menu) add, rename (F2), point at the current page, move up or down, and delete (Del) bookmarks. **Insert ▸ Bookmark for This Page…** (Ctrl+B) adds one for the page you are viewing, suggesting the first line of the page as its title. Deleting a bookmark also deletes the bookmarks under it (you are asked first). Bookmark changes are undoable and are saved with **File ▸ Save**. Bookmarks that open web pages keep working when you edit others.

## Password-protected PDFs

The **Protected PDF** dialog asks for the password (never stored in recent files, recovery data or logs).

- **Protection is kept.** Save, Save As, every Save a Copy command, Watermark, Header & Footer, Background, Flatten, Redact, Extract Pages, Compress and Make Searchable write PDFs with the same open password, permissions password and permissions as the original. Remove protection only with **Protect ▸ Unlock PDF (Remove Password)…**. Protection is never removed without the correct password.
- **Permissions are honoured.** A PDF can allow or forbid printing, copying its content, changes and page assembly. With the open password alone, an action the author did not allow asks for the **permissions password** (owner password); after it is entered, everything is allowed until you close the document. Converting to Word, PowerPoint, Excel, text or pictures needs *copying*; Print needs *printing*; saving changes and page design need *changes*; extracting, splitting and combining pages need *page assembly*; changing or removing restrictions always needs the permissions password. **Protect ▸ View Permissions** shows what the PDF allows.
- **Digitally signed PDFs.** Save As without changes copies the file exactly, so its signatures stay valid. Saving changes rewrites the file and makes the signatures invalid; Save asks first — keep the signed original and save your changes under a new name. Word, PowerPoint and picture exports show how the signature looks, but they are not digitally signed.
- **Watermarks** are part of the pages and stay in every output. PDF to Word and PDF to PowerPoint can leave out the watermark, header/footer and background added with Monograph PDF; a watermark locked with Protect with Password, and watermarks made by other programs, always stay.

## Saving

- **File ▸ Save** (Ctrl+S) · **File ▸ Save As…** (Ctrl+Shift+S)
- **File ▸ Save a Copy**: Whole Document (Keep Working on This One)…, Selected Pages as PDF…, Flattened PDF…, or Copy with Metadata… — the open document and its unsaved changes stay as they are
- Save As asks before replacing an existing file; every save writes a temporary file first and swaps it in, so a failed save never leaves a half-written file
- Other formats: **Convert** menu. When the document has unsaved changes, a conversion first asks **Save**, **Save As…** or **Cancel** (Cancel keeps every change)
- **File ▸ Compress PDF…** asks *How do you want to compress it?*: **Best quality (lossless)** · **Balanced (recommended)** · **Smallest file** · **Fit a size limit** (E-mail attachment 10 MB, Online form upload 2 MB, or your own exact maximum such as 956 KB or 1.99 MB; 1 KB = 1,000 bytes) · **My own picture settings** (picture resolution 100–600 ppi and JPEG quality 40–95). Only the settings of your choice are shown. Text — also text you added — fonts, comments, form fields, drawings, links and the page layout are always kept exactly as they are; only pictures can be reduced. **Preview** measures the real size; **Compress and Save As…** saves a new file. The dialog shows the current size, an estimate, the measured size after **Preview**, and the original and compressed page side by side. Success is reported only when the saved file is at or below the target; otherwise you are told the smallest acceptable size and asked whether to keep it. See [PDF_COMPRESSION.md](PDF_COMPRESSION.md)

## Editing

Opening a PDF never changes it. Edits are written only when you save.

- **Insert ▸ Text Box** (`T`); shapes from the Shape ▾ button
- Tool keys: `V` Select · `T` Text Box · `I` Image · `R` Rectangle · `E` Ellipse · `L` Line · `A` Arrow · `P` Freehand · `H` Highlight · `Shift+E` Eraser · `U` Underline · `K` Strikethrough · `N` Sticky Note
- The **context toolbar** and **Properties panel**: font, size, wrapping, box sizing and color
- The font box lists the fonts installed on your PC plus the fonts that come with Monograph PDF (Noto Sans, Noto Serif, Noto Sans CJK JP). One click opens the list; type a few letters to find a font
- Double-click a text box to type in it. Select a shape to change its **Line** and **Fill** color on the context toolbar
- **Colors**: every color button opens the same color picker — a large color field with hue strip, the current and new color side by side, Hex (or a color name such as *navy*) and R G B values, standard colors, your recent colors, and **Pick from Screen** (click anywhere to take its color; Esc cancels). For text, it shows the contrast against white paper
- **Pictures**: **Insert ▸ Image** (`I`). With a picture selected, **In Front of Text** (it covers what is under it) or **Behind Text** (the page's text and lines show through it, as if printed on the paper beneath them — also on scanned pages) is on the Image toolbar, in **Edit ▸ Selected Image** and in the Properties panel (*Placement*), together with opacity and rotation
- While typing in a text box or field, Ctrl+Z / Ctrl+Y undo and redo typing and paste; after you leave, **Edit ▸ Undo** / **Edit ▸ Redo** cover the session
- Arrange: Ctrl+] / Ctrl+[ · **Edit ▸ Align & Distribute**
- **Edit ▸ Copy Page as Picture** (Ctrl+Alt+C) — the current page as shown, including unsaved changes, at 150 dpi, ready to paste into another program
- Unsaved documents show `*` in the title; recovery copies are kept for unprotected PDFs only

## Forms, tables and layout

- Fill fields in Select mode (click and type; Tab / Shift+Tab). Mixed Japanese and Latin entries are supported.
- Press in a field and drag to select its words; the font, size, bold, italic and color on the toolbar then change only those words.
- To change several boxes at once, drag a rectangle from empty paper (or the grey margin) across the fields and text boxes, or Ctrl+click them; the toolbar's font, size, A+ / A−, bold, italic, color and alignment then apply to every selected box (one **Edit ▸ Undo** step).
- Text boxes, pictures, shapes and fields stay on the page while you drag them or move them with the arrow keys: anything past the page edge would not show in other PDF apps or print.
- Design: **Edit ▸ Workspace Mode ▸ Forms**, **Forms ▸ Add Field**, **Forms ▸ Detect Fields**, **Forms ▸ Flatten Form on Save**
- Signature fields are **visual** signatures, not certificate-based digital signatures.
- **Forms ▸ Tables ▸ Detect Tables** · **Edit ▸ Align & Distribute** (Preserve Layout or Smart Layout)

## OCR (text recognition)

The OCR engine and English / Japanese language data ship with the app and work offline. Other languages are added only when you ask (see OCR Languages below).

- **OCR ▸ Make PDF Editable…** (summary before conversion)
- **OCR ▸ OCR Whole Document…**, **OCR ▸ OCR Current Page…**, **OCR ▸ Make Searchable PDF…** — each saves a searchable copy under a name you choose (the open document is not changed); open the copy to search or select its text
- Low-certainty words are marked in amber; Cancel stops after the current page
- **OCR ▸ Recognize Text in Area…** (drag a rectangle) and **OCR ▸ Extract Text (OCR)…**: the recognised text can be corrected, copied, or saved as a text file or Word document; **OCR ▸ Scanned PDF to Word (OCR)…**
- Rotated and upside-down scans are handled; running OCR again never adds a second text layer
- **OCR ▸ OCR Languages…** — tick the languages printed on your pages (fewer languages recognize faster and more accurately). Under **Add languages**, 45 more languages are listed (Arabic, Burmese, Chinese, Dutch, French, German, Greek, Hindi, Korean, Russian, Spanish, Thai, Vietnamese …): select one and click **Download and Install**, or use **Install from File…** for files you downloaded yourself (the download address is shown by **Copy Address**). Language files already in your Downloads folder are offered for installation. Every file comes from the official Tesseract release used for the included languages and is installed only if its size and SHA-256 match; an installed language is ready at once and is ticked for recognition. Nothing is downloaded unless you click **Download and Install**

## Organize pages

Drag thumbnails in the Navigation panel to reorder. Ctrl/Shift+click to multi-select.

- **Organize ▸ Insert Blank Pages…** (Ctrl+Shift+N) and **Organize ▸ Insert Pages from PDF…** (Ctrl+Shift+I) ask exactly where the pages go: **Before page** or **After page** a number you choose, **At the beginning** or **At the end**. Blank pages can be added several at once and take the size of the page next to them
- **Organize ▸ Move Pages…** moves the selected pages (kept in their order) before or after any page, to the beginning or to the end — the same as dragging them, without dragging. These commands are also on the thumbnails' right-click menu, and every change is undoable

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
- PowerPoint slides and Word sections keep each page's size and orientation. When the pages differ in size, **PDF to PowerPoint** lets you choose: largest page (true size or fitted), first page's size, a chosen slide size, or one presentation per page size. Document properties (title, author, subject, keywords, dates) come from the PDF. See [PDF to Office](PDF_TO_OFFICE_CONVERSION.md)
- **Convert ▸ Batch Convert…** — many files at once to Word, Excel, PowerPoint, text, images, searchable PDF or Word via OCR (or Office files and images to PDF), with a status for each file and Cancel
- With unsaved changes, a conversion first asks **Save**, **Save As…** or **Cancel**
- **Convert ▸ Conversion Quality Guide…**
- Scanned pages: run OCR first. Protected files: enter the password first; unlock only if you want an unprotected copy (**Protect ▸ Unlock PDF (Remove Password)…**)

## Page design

- **Insert ▸ Header, Footer & Page Numbers…** — text at the left, center or right of the top and bottom margins. `{page}`, `{total}`, `{date}` and `{bates}` are replaced on each page; choose the number style and place, the first page number, date style, text size and color, margins and pages. **Add Bates number** puts a fixed-width page identifier such as `CASE-000001` on every page (prefix, first number, number of digits and suffix are yours to choose); it counts through the whole document. Long text is made smaller to fit between the margins.
- **Insert ▸ Watermark…** — text or a picture; size, color, orientation, opacity, position (center, top or bottom), and in front of or behind the page content. A watermark behind the content is hidden where a page has its own opaque background, such as a scanned page.
- **Insert ▸ Background…** — a color and/or a picture behind the page content (fit or stretched), with opacity.
- Each of these dialogs shows a large preview of the page as it will be saved: **◀ ▶** go through the pages, the zoom box (Fit page, Fit width, 100–400 %), **−** / **+** or Ctrl + mouse wheel enlarge it (text stays sharp), and **Larger Preview…** opens it in a window you can resize or maximize. The dialogs remember your last settings, remembers your last settings, and writes a new PDF; the open document is not changed. Marks are placed upright on the page as you see it, also on rotated pages.
- **Replace the one added earlier by Monograph PDF** (in each dialog) swaps a header/footer, watermark or background added before instead of adding a second one. **Insert ▸ Remove Header, Footer, Watermark or Background…** removes them. Only marks added by this version of Monograph PDF can be recognized; text or pictures added by other programs are part of the page and are kept.
- **Insert ▸ Image…** (`I`) · **Edit ▸ Selected Image**

## Protect, redact and sign

- **Protect ▸ Protect with Password…** — open and/or permissions password; Allow printing / copying / changes / comments / forms; AES-256 (or AES-128). **Protect & Save As…** writes a new file.
- While you type a password, a strength rating suggests how hard it is to guess (worked out on your computer; nothing is sent or stored). Use a permissions password that differs from the open password — otherwise anyone who can open the file can also lift the restrictions.
- **Protect ▸ Unlock PDF (Remove Password)…** · **Protect ▸ View Permissions…**
- **Protect ▸ Remove Hidden Information…** — lists what the document carries besides its visible pages (document properties and XMP metadata, attached files, scripts and automatic actions, page thumbnails, private application data, comments, form fields, links, bookmarks, invisible text) and saves a new PDF without the kinds you tick. Comments, fields, links, bookmarks and invisible text are kept unless you choose them; invisible text is usually recognised (OCR) text, and removing it stops scanned pages being searchable. Invisible text lying over visible text is kept so the page never changes. Password-protected files must be unlocked first. Marked redactions are not applied here. Anything that is part of the pages themselves is not removed — including text inside pictures and content on layers that are turned off — so check the result before sharing it.
- Markup under Insert (Comments & markup): **Insert ▸ Highlight Text** (pen + color; click again to leave the tool), **Insert ▸ Eraser** (draw over highlights, underlines, strikethroughs and ink marks to remove everything you cross in one pass; a click removes everything under the pointer; one Undo restores them), **Insert ▸ Underline Text**, **Insert ▸ Strikethrough Text**, **Insert ▸ Squiggly Underline**, **Insert ▸ Sticky Note Comment…**, **Insert ▸ Callout…**, **Insert ▸ Stamp…** (standard stamps, your own text or picture stamps, rotation and opacity; **Customize Look…** before placing) — every change is undoable
- Double-click a placed item to change it: a sticky note or callout asks for its new text; a stamp opens **Edit Stamp** — switch the stamp type (Approved, Rejected, Draft …), change its text and second line, font, text / border / fill color, border (double, single or none), corners (rounded, square or round ends), line thickness, opacity and rotation, with a live preview
- Sticky notes show as a small speech bubble; point at one (or click it) to read the note
- **View ▸ Comments Panel** lists the notes and markup; select one to go to it, edit its text, or delete it
- Highlight: stays on for many strokes; change the color menu for the next stroke only; Esc cancels an unfinished stroke (keeps mode); Esc again (or click Highlight) returns to Select. Free-area strokes mark blank pages, pictures and tables; text strokes mark only the characters the pen touches. Completed marks stay when you add text boxes, shapes, images or fill forms (opaque overlays may cover them on screen without deleting them).
- **Protect ▸ Mark Area for Redaction**, **Protect ▸ Mark Text for Redaction…** (every page is searched) or **Protect ▸ Mark Whole Pages for Redaction…**, then **Protect ▸ Apply Redactions…** — truly removes the content (cannot be undone after Apply). Form fields, comments and links that overlap a mark are removed with it. Whole-page marks also remove content hidden outside the visible page area; the pages themselves stay.
- After applying text marks, Monograph PDF looks for the same text elsewhere in the saved file — comments, form values, bookmarks, document properties and attachments — and lists where it is still found. Choose **Remove These Too** to replace it with “[redacted]” (attachments with the text in their name or description are deleted), or **Keep Them**. Monograph PDF never opens or reads attachments, so their contents are not checked: any attachments are listed for you to review.
- **Sign ▸ Type a Signature…** · **Sign ▸ Draw a Signature…** · **Sign ▸ Signature from Image…** — **visual** signatures only, not certificate-based
- Double-click a placed signature to change it: a typed signature reopens with its name, style and ink; a drawn one can be drawn again; a picture can be replaced. It stays in the same place at the same height

## Printing

**File ▸ Print…** (Ctrl+P) with live preview. Unsaved overlays print as shown; the open file is not changed.

- Pages: all, current, selected or a range — then **Odd pages** / **Even pages** (by page number, for two-sided printing by hand) and **Reverse order**
- **Comments:** **Document and comments**, or **Document only** (notes, highlights, shapes and stamps left out; form fields still print)
- **Scaling:** actual size (the default), fit, shrink oversized pages or a custom percentage; **Pages per sheet:** 1, 2, 4, 6 or 9
- **Two-sided:** **Print on both sides of paper** with **Flip on long edge** (the default) or **Flip on short edge** — switched on whenever the printer reports two-sided printing, unavailable otherwise
- **Color:** Color, Grayscale, or Black and white (only black and white dots)
- **Save as PDF…** writes the chosen pages as a PDF (text stays text) without a printer. See [Printing](PRINTING_AND_PRINT_PREVIEW.md)

## Updates

**Help ▸ Check for Updates…** checks for a newer version; **File ▸ Settings… ▸ Updates** turns on
automatic checks (off by default), sets how often (every day, every 3 days or every week) and the
release channel (stable, or prereleases as well), and shows the last successful check and the status.

A check contacts only the official GitHub Releases page of Monograph PDF and accepts only update
information signed with the project's update-signing key. If the check cannot reach GitHub (for
example offline) or the information cannot be verified, it says so — never "up to date" — nothing is
downloaded, and **Open Releases Page** takes you to the official download page instead. Automatic
checks only check: nothing is downloaded or installed until you click **Update Now**. Versions 0.4.0
and earlier cannot check for updates; install the current version once with its Setup (your settings and
documents are kept).

When an update is available you see the installed and available versions, the release date, the
release notes and the download size. **Update Now** downloads the update, verifies it, asks you to
save or discard unsaved changes, closes Monograph PDF, installs the update in the same place and
restarts it; your settings, shortcuts and file-type choices are kept. **Remind Me Later** postpones
it. An installation for all users shows Windows' administrator prompt.

* **Skipped versions.** You do not need to install every version: an older copy (0.5.0 or later)
  updates straight to the newest release, even after months or years.
* **When a check fails** the message names the reason — for example *No internet connection*,
  *GitHub is temporarily unavailable*, *Update information has expired* or *Invalid digital
  signature* — and nothing is downloaded or installed. Try again later or use **Open Releases Page**
  and run the new Setup yourself; Setup always upgrades in place and keeps your settings and
  documents. Monograph PDF itself keeps working normally, online or offline.
* **Expiry.** Each release's update information is valid for two years from its publication. If no
  newer release appears in that time, checks report that it has expired until the next release; the
  application is not affected.

## Problem reports

If something unexpected goes wrong, Monograph PDF can show a problem report — limited technical
information such as the version, Windows version and language, the failing operation and where in
Monograph PDF's code it failed. It never contains your documents, file names, folder paths, user name
or typed text. The full report is shown before you decide: **Don't Send** discards it; **Send to
Developer** sends exactly that report. Nothing is sent without your click. **In this version sending
is switched off:** the dialog then shows **Copy Report** and **Open Issues Page** instead. If you
want to help, copy the report, open the issues page and paste it into a new issue; **Close**
discards it. The app itself sends nothing.

## Keyboard shortcuts

| Area | Keys |
| :--- | :--- |
| File | Ctrl+O · Ctrl+S · Ctrl+Shift+S · Ctrl+W · Ctrl+P · Ctrl+, (Settings) · Ctrl+Q |
| Edit | Ctrl+Z · Ctrl+Y · Ctrl+X/C/V · Del · Ctrl+A · Ctrl+Alt+C (copy page as picture) |
| Insert | Ctrl+B (bookmark for this page) |
| View | Ctrl+1 / 2 / 0 · Ctrl+= / − · Ctrl+F · F8 · F9 · F11 · Ctrl+Shift+L (automatic scrolling) · mouse wheel button (scroll button) · Ctrl+/ |
| Tools | V Select · T Text · H Highlight · Shift+E Eraser · I Image · … |

Full list: **Help ▸ Keyboard Shortcuts**.

## Current limitations

- Windows 10 and Windows 11 (64-bit) only
- Japanese vertical writing is not fully supported for editing
- Office to PDF needs a local suite; PDF to Word / Excel / PowerPoint is best-effort on complex layouts
- Signatures are visual only
- Builds are not code-signed — verify `SHA256SUMS.txt`; SmartScreen may warn
- Sending problem reports is switched off in this version (reports can be copied and passed on)
- Optional OCR languages (other than English and Japanese) have not been tested by the project for recognition quality

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
