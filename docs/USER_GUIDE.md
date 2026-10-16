# Monograph PDF User Guide

Monograph PDF views, edits, organizes, converts, protects and signs PDF documents on your computer.

**Privacy.** Monograph PDF itself makes no network connections, does not upload your documents, and does not collect usage data (telemetry). There is no advertising, online OCR or runtime download of code or models. Optional Word, Excel and PowerPoint conversion: Monograph PDF does not upload the document; conversion uses the locally installed Microsoft Office or LibreOffice application, which follows its own settings and remote-content behavior.

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
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Current limitations](#current-limitations)
- [Troubleshooting](#troubleshooting)
- [Additional documentation](#additional-documentation)

## Getting started

### Opening files

1. Start **Monograph PDF** from the Start menu or the desktop shortcut.
2. Open a file in any of these ways:
   - **File ▸ Open…** (Ctrl+O)
   - drag a file onto the window
   - choose a file under **File ▸ Open Recent** or in the start screen's **Recent files** list
   - in File Explorer, right-click a PDF and choose **Open with ▸ Monograph PDF**
3. The start screen also offers one-click tools: **Merge PDFs**, **Word to PDF**, **Images to PDF**, **PDF to Word**, **Rotate Pages**, **Protect**, **Unlock**, **Watermark**, **Sign** and **OCR a Scan**.

Monograph PDF opens PDFs directly. Images (PNG, JPEG, TIFF, BMP, GIF, WebP) and Word, Excel or PowerPoint files are first converted to a new, unsaved PDF; the original file is never changed. **Save** then asks where to store the new PDF.

To clear the recent-files list, choose **File ▸ Open Recent ▸ Clear Recent Files**.

### Making Monograph PDF your default PDF app

Choose **Help ▸ Make Monograph PDF the Default PDF App…**. Windows asks you to confirm the choice in Settings.

### Updating and uninstalling

- **Update:** run the Setup program of the newer version. Your settings and recent files are kept.
- **Uninstall:** open **Settings ▸ Apps ▸ Installed apps**, find **Monograph PDF** and choose **Uninstall**. You can also run `uninstall.exe` in the Monograph PDF installation folder.
  - Uninstalling removes the program, its shortcuts, its file-type registrations, its recent-files list and its working files (cache and temporary files).
  - The uninstaller asks whether to also remove your **settings** (theme, window layout and similar preferences). Choose **Yes** to leave nothing of Monograph PDF behind.
  - Your own documents (PDFs you saved, converted or exported files) are never removed.
  - If Monograph PDF is still running, the uninstaller asks you to close it first.

## The Monograph PDF window

- **Menu bar:** File · Edit · View · Insert · Forms · Organize · Convert · OCR · Protect · Sign · Help
- **Main toolbar:** Open · Save · Print │ Undo · Redo │ Select · Text · Image · Shape ▾ · Highlight · Comment │ Fit ▾ · − · zoom % · + │ ‹ page box / total › │ Find box │ panel buttons
- **Context toolbar** (second row): changes with the selection, for example font, size, bold/italic/underline, alignment and color for text, or arrange and delete for shapes and images.
- **Navigation panel** (left, F9): tabs for **Pages** (thumbnails), **Bookmarks**, **Search** and **Files** (attachments).
- **Properties panel** (right, F8): see [Editing](#editing).
- Each button's tooltip shows its keyboard shortcut. **Help ▸ Keyboard Shortcuts** (Ctrl+/) lists every shortcut, with a filter box.
- **View ▸ Theme:** System, Light or Dark. Icons, pages and dialogs all follow the theme.

## Viewing

- **Zoom:** use the toolbar's **Fit ▾** (Width, Page or Actual Size), **−**, the zoom percentage (you can type a value) and **+**. You can also use the **View** menu or Ctrl+mouse wheel.
  - Fit Width: Ctrl+1 · Fit Page: Ctrl+2 · Actual Size: Ctrl+0
  - Zoom In: Ctrl+= (or Ctrl++) · Zoom Out: Ctrl+-
- **Move between pages:** Page Up / Page Down, Home / End (first / last page), **View ▸ Go to Page…** (Ctrl+G), or type a page number in the toolbar's page box.
- **Find:** Ctrl+F moves to the toolbar's find box. Enter or F3 goes to the next match, Shift+Enter or Shift+F3 to the previous one, and Esc clears the search. The **Search** tab in the Navigation panel lists the matches on each page.
- **Document properties:** **File ▸ Document Properties…** (Ctrl+Alt+D) shows the title, author, dates, page size, encryption and forms.
- **Full screen:** F11.
- **Properties panel** (F8): document details, paper size (with **Change Page Size…**) and the properties of the selected object.
- **View ▸ Highlight Fillable Fields** (Ctrl+Shift+H): tints form fields on screen so they are easy to find. The tint is never written into saved files.
- Forms show the page as designed; internal field names are not drawn on the page.
- Viewing always uses the fonts embedded in the PDF. If a font you choose for *new* text is not installed, Monograph PDF uses a similar font and notes this in the Properties panel.

## Password-protected PDFs

When a file needs a password, the **Protected PDF** dialog asks for it. The password is hidden as you type; select **Show password** to see it.

- A wrong password keeps the dialog open so you can try again.
- **Cancel** leaves the document closed.
- The password is never stored in the recent-files list or in recovery data, and is never written to log files.
- **Save** and **Save As** keep the file's password protection (same passwords and permissions). To remove it, use **Protect ▸ Unlock PDF (Remove Password)…**.

## Saving

- **File ▸ Save** (Ctrl+S) writes your changes to the PDF.
- **File ▸ Save As…** (Ctrl+Shift+S) suggests `<name>-copy.pdf` and then continues with the new file.
- If you close the document or open another file with unsaved changes, Monograph PDF asks: **Save**, **Don't Save** or **Cancel**.
- **File ▸ Save a Copy** saves **Selected Pages as PDF…**, a **Flattened PDF…** or a **Copy with Metadata…**. The open document stays as it is.
- To save in other formats (Word, Excel, PowerPoint, images, text), use the **Convert** menu.
- Copies, conversions, page extracts, watermarks, headers and footers and **Reduce File Size** use the document **as shown**, including changes you have not saved yet; the open file itself is not changed.
- A copy or conversion cannot replace the PDF that is open in Monograph PDF; choose another name, or use **File ▸ Save** for the open document.
- Save dialogs suggest a file name next to the open document, for example `report-optimized.pdf`.
- **File ▸ Reduce File Size…** offers these levels:

| Level | Result |
| :--- | :--- |
| **Lossless** | Structural cleanup only; images are never downsampled |
| **High Quality** | Keeps images as they are |
| **Standard** (recommended) | Default balance of size and quality |
| **Balanced** | Recompresses images; image quality may drop |
| **Minimum file size** | Smallest file; lossy |

Balanced and Minimum file size recompress images and are lossy; Lossless never changes image quality. The dialog estimates the new size for the level you choose.

## Editing

Opening a PDF never changes it. Your edits are written only to the file you save.

### Tools

- **Text** tool (Insert ▸ Text Box, or press `T`): click, or drag a box. The caret appears and your typing shows immediately.
- **Tool keys:** `V` Select · `T` Text · `I` Image · `R` Rectangle · `E` Ellipse · `L` Line · `A` Arrow · `P` Freehand · `H` Highlight · `U` Underline · `K` Strikethrough · `N` Sticky note. While you type in a text box, letters go into the text, not to the tools.
- **Shape ▾** on the toolbar: Rectangle, Circle, Ellipse, Line, Arrow and Freehand. Hold Shift to draw a square or circle, or to keep lines at fixed angles.

### Text boxes

- Text boxes work like a word processor: click inside to place the caret, drag or use Shift+arrow keys to select text, and double-click a box to edit it again.
- Esc, Ctrl+Enter or a click outside the box finishes editing.
- The **context toolbar** for a selected text box offers: Font · Size · − / + · Bold / Italic / Underline · alignment (left, center, right; top, middle, bottom) · **Wrap Text** · Color. Size, alignment and style apply to all the text in the box, also while you are typing.
- **Finding a font:** click the Font box and type a few letters. Every installed font containing them is listed; for example, `go` finds Gothic, MS Gothic and Yu Gothic. Pick one, or type a full name and press Enter. Nothing changes until you pick a font.
- **Wrap Text** (toolbar or Properties panel): long lines continue on the next line inside the box. Turn it off to keep each line on one line.
- **Box sizing:** **Grow to fit text** (default), **Size to text**, **Shrink text to fit** or **Fixed size**.
- Double-click existing PDF text to replace it. The replacement can be undone.

### Properties panel

The Properties panel (F8) shows the settings of whatever is selected: Text, Form Field, Shape, Image or Document. For text boxes it has three groups:

- **Text:** font, size, bold / italic / underline, color and wrap
- **Paragraph:** alignment and spacing
- **Box:** position, size, box sizing, rotation, opacity, padding, border and background

To hide the panel, click the **×** in its top-right corner or press F8. Press F8 again, or choose **View ▸ Properties Panel**, to show it.

### Selecting and arranging

- In Select mode you can move and resize added objects; the page itself is not redrawn. Ctrl+click selects several objects, and the arrow keys nudge them (1 pt; with Shift, 10 pt).
- Ctrl+A selects all objects on the page; Ctrl+Shift+A selects nothing. Delete removes the selection.
- Ctrl+] / Ctrl+[ bring an object forward / send it backward; Ctrl+Shift+] / Ctrl+Shift+[ bring it to the front / send it to the back.
- Ctrl+Shift+C / Ctrl+Shift+V copy and paste an object's style.
- Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z.

### Unsaved changes and recovery

A document with unsaved changes shows `*` in the window title. Monograph PDF keeps a recovery copy of the session in its working folder, so your edits are not lost if the app closes unexpectedly. No recovery copy is kept for a password-protected PDF, because the copy would not be protected; save often.

## Forms, tables and layout

### Filling in forms

- Fill in existing fields in **Select** mode: click a field and type. Tab / Shift+Tab moves to the next / previous field. You do not need Forms mode to fill in a form.
- A text field behaves like a normal text box: select text with the mouse, double-click a word, use Shift+arrow keys or Ctrl+A, copy and paste, and undo with Ctrl+Z.
- Enter (in single-line fields) or Esc finishes the entry.
- Fields accept any mix of letters, numbers and Japanese, for example `山田 Taro 123-4567`, or full-width `ＡＢＣ１２３` typed with the Japanese IME. Mixed entries are saved with an embedded Unicode font, so they look the same in every PDF reader and stay searchable.
- Checkboxes and radio buttons toggle when clicked (or with Space when selected). Drop-down fields open a list of choices.
- To deselect a field, press Esc (twice while typing) or click blank paper or the gray area around the page.

### Formatting a field's entry

- **Field size:** drag the white handles around a selected field to enlarge it for longer entries.
- **Field toolbar** (above the page): font (type to search), size (**A−** / **A+**), **Bold**, **Italic**, alignment, **Wrap Text** and color.
  - Alignment: left, center, right or **justify**, and top, middle or bottom.
  - **Justify** needs Wrap Text. Other PDF apps show justified fields as left-aligned, because PDF fields only support left, center and right.
  - **Auto** font size (size 0 in the PDF) is kept and shown as Auto.
- **ABC / abc** change the entry, or a selected text box, to UPPERCASE or lowercase.
- Changes show at once, also while you are typing, and are written into the PDF when you save.
- A red **!** in a field's top-right corner means part of the entry does not fit the box at its font size; that part will not be printed or shown in other PDF apps (point at the field for a tip). Make the text smaller (**A−**) or enlarge the box.

### Formatting only some words

1. While typing in a field, select the words (with the mouse or Shift+arrow keys).
2. Use the same field toolbar. For example, set one word in Times New Roman 8 pt and the next in Arial 10 pt bold.

The toolbar shows the format of the text at the caret. Fields with formatted words open in Adobe Acrobat as rich-text fields.

The Properties panel shows a field's type, name and value.

### Designing forms

- **Forms mode** (**Edit ▸ Workspace Mode ▸ Forms**) is for creating, moving and resizing fields and editing their properties. Add fields with **Forms ▸ Add Field**: text, multi-line text, checkbox, radio button, drop-down list, date or signature field.
- **Forms ▸ Detect Fields** suggests fields for review only and does not change the PDF. Keep the suggestions with **Keep Detected Fields** or remove them with **Discard Detected Fields**.
- Signature fields are **visual placeholders**, not certificate-based digital signatures.
- **Forms ▸ Flatten Form on Save** turns fields into ordinary page content when you save (optional).

### Tables

**Forms ▸ Tables ▸ Detect Tables** marks tables only where Monograph PDF is confident it found one. Once a table is detected, you can add or delete rows and columns.

### Aligning objects

**Edit ▸ Align & Distribute** aligns and distributes the selected objects. Choose how other content is treated:

- **Preserve Layout** (default, most reliable): nothing else moves.
- **Smart Layout** (basic): moves only objects that are clearly related.

## OCR (text recognition)

OCR turns scanned pages into searchable, selectable text. The OCR engine (Tesseract) and the English, Japanese and page-orientation language data are installed with Monograph PDF. Nothing is downloaded.

- **OCR ▸ Make PDF Editable…** first examines the document and shows a summary of its text, forms, tables, images and the pages that need OCR, before anything is converted.
- **OCR ▸ OCR Whole Document…**, **OCR Current Page…** and **Make Searchable PDF…** add a searchable text layer. The scanned appearance is kept.
- Words recognized with low certainty are marked in amber for you to review and correct.
- **Cancel** stops processing after the current page.

## Organize pages

The **Organize** menu merges, splits, inserts (blank pages or pages from a PDF), deletes, duplicates, replaces, rotates, crops and extracts pages, copies or moves pages to another PDF, and changes the page size.

### Working with thumbnails

- Drag thumbnails in the Navigation panel to reorder pages.
- Ctrl+click or Shift+click thumbnails to select several pages for one action.
- With the thumbnails focused, Delete removes the selected pages and Ctrl+A selects all pages.

### Rotate

**Organize ▸ Rotate Pages…** rotates all pages, the current page, the selected thumbnails, odd or even pages, or a range such as `1-3, 7` by 90° clockwise, 90° counterclockwise or 180°. Ctrl+R / Ctrl+Shift+R rotate the current (or selected) pages at once.

### Change page size

**Organize ▸ Change Page Size…** (also on the page toolbar, or in the Properties panel when nothing is selected) converts pages to A3, A4, A5, A6, B4 / B5 (JIS or ISO), Letter, Legal, Tabloid, Executive, Japanese postcard or a custom size.

- **Orientation:** same as each page, portrait or landscape.
- **Fit:** **Fit to page** (keeps proportions; recommended), **Fill page** (keeps proportions; edges may be cut off), **Stretch**, or **Keep original size**.
- Optional margin and page selection.

Text stays selectable, and form fields, links and comments move with the content. The result is saved as a new PDF.

### Crop

**Organize ▸ Crop Page…** asks how much to trim from each edge, in millimeters, and shows the resulting page size.

### Copy or move pages to another PDF

**Copy Pages to Another PDF…** and **Move Pages to Another PDF…** save a new target file. The source document is changed only when you save it.

### Merge and split

- **Organize ▸ Merge PDFs…** (Ctrl+Shift+M): add several PDFs from your computer, put them in order, set page ranges and combine them into a new file. The source files are never changed. Password-protected PDFs ask for their password, and a warning appears when a source file contains signatures.
- **Organize ▸ Split PDF…**: split by page ranges, by selected pages, into single pages, every N pages, or by bookmarks. Only new files are written.
- Long merge and split jobs show their progress and can be canceled. Working files are removed automatically.

## Convert

All conversions run on your computer. Monograph PDF does not upload documents for conversion.

### Create PDF

- **Convert ▸ Word, Excel or PowerPoint to PDF…** converts:
  - Word: `.docx`, `.doc`, `.docm`, `.rtf`, `.odt`, `.txt`
  - Excel: `.xlsx`, `.xls`, `.xlsm`, `.xlsb`, `.csv`, `.ods`
  - PowerPoint: `.pptx`, `.ppt`, `.pptm`, `.pps`, `.ppsx`, `.odp`

  Monograph PDF does not upload the document. Conversion uses the locally installed Microsoft Office or LibreOffice application, which follows its own settings and remote-content behavior, so the layout is kept as closely as that application normally keeps it. Office or LibreOffice must already be installed, and macros are never run by Monograph PDF. **Help ▸ About Monograph PDF ▸ Office Integration** shows which suite was found.
- **Convert ▸ Images to PDF…**: one page per image (PNG, JPEG, TIFF, BMP, GIF, WebP), in the order you choose.

When you open an Office file or an image with **File ▸ Open…**, **Open with** or drag and drop, Monograph PDF converts it to a new PDF and the title shows, for example, *(from DOCX — not saved yet)*. Edit as usual; **Save** asks where to store the PDF. The original file is never changed.

### Convert PDF to other formats

- **Convert ▸ PDF to Word…** creates an editable `.docx` that closely reproduces most documents. Complex layouts, unusual fonts or scanned pages may need manual adjustment. Choose a method:
  - **Keep layout** (recommended): rebuilds text, fonts, tables, images, columns and page margins.
  - **Microsoft Word**: uses Word's own PDF conversion (only when Word is installed); good for flowing text.
  - **Text only**: plain paragraphs for quick reuse.

  You can convert all pages, the current page or a range, and open the result in Word when it is ready.
- **PDF Tables to Excel…**, **PDF to PowerPoint…**, **PDF to Images…** (PNG, JPEG or TIFF at 72–600 dpi), **PDF to Text…** and **Extract Images…**. Files written into a folder never replace files already there; a number is added instead, for example `page_0001 (2).png`.
- **Conversion Quality Guide…** lists each conversion with its expected quality (High, Best effort or Not available) and what to expect, in plain language.

Tips:

- Scanned PDFs contain no text to convert. Run [OCR](#ocr-text-recognition) first.
- Fonts that are not installed on your computer may be replaced by similar fonts in Word. Installing the original fonts gives the closest match.
- Open the password-protected PDF and enter its password before converting. You do not need to remove its protection unless you specifically want an unprotected copy (**Protect ▸ Unlock PDF (Remove Password)…**).

## Page design

- **Insert ▸ Watermark…**: text, font size, color, orientation, opacity and pages.
- **Insert ▸ Header, Footer & Page Numbers…**: text, size, number style (such as "Page 1 of 12") and pages.
- Both write a new PDF.
- **Insert ▸ Image…** (`I`) places an image from your computer that you can move and resize. Replace it or save it as a file with **Edit ▸ Selected Image** or the context toolbar.

## Protect, redact and sign

### Protect with a password

Choose **Protect ▸ Protect with Password…**:

| Setting | Meaning |
| :--- | :--- |
| **Open password** (optional, entered twice) | Needed to open the PDF at all. |
| **Permissions password** (optional) | Needed to change the permissions. With only this password, anyone can open the file but the restrictions apply. If it is empty, the open password also gives full rights. |
| **Allow printing** / **High-quality printing** | Whether readers can print, and at full resolution. |
| **Allow copying text and images** | Selecting and copying content. |
| **Allow changes to the document** | Editing content. |
| **Allow inserting, rotating and deleting pages** | Page assembly. |
| **Allow comments** | Adding or changing comments and markup. |
| **Allow filling in form fields** | Typing into form fields. |
| **Encryption** | AES-256 (recommended), or AES-128 for older readers. |

Choose **Protect & Save As…** to write a protected copy; the open document is not changed. Encryption is done on your computer.

**Protect ▸ Unlock PDF (Remove Password)…**: enter the current password once and save an unprotected copy. Forms, bookmarks and metadata are kept. Protection is never removed without the correct password.

**Document information:** **Protect ▸ View Permissions…**, **View Metadata…** and **View Attachments…** show the document's details; **Remove Metadata…** removes its metadata.

### Comments and markup

- Highlight, Underline, Strikethrough, Callout, Stamp, redaction areas and signatures are placed by **dragging a box on the page** (or clicking for a default size). Text markup snaps to the words under the box. Esc cancels.
- **Insert ▸ Comments & markup:** **Highlight Text** (`H`), **Underline Text** (`U`), **Strikethrough Text** (`K`), **Sticky Note Comment…** (`N`, click where it goes), **Callout…** and **Stamp…** (built-in stamps).

### Redaction

1. Mark content with **Protect ▸ Mark Area for Redaction** or **Mark Text for Redaction…**. Mark Text finds the text on every page.
2. Check the number of marks with **Count Marked Redactions**.
3. Choose **Apply Redactions…**.

Redaction truly removes the content; it does not just cover it with a black box. After you save, removed content cannot be recovered by copying or searching.

### Visual signatures

**Sign ▸ Type a Signature…**, **Draw a Signature…** or **Signature from Image…**: drag a box on the page; you can move or resize the signature afterwards.

These are **visual** signatures, not certificate-based digital signatures. Monograph PDF warns you when a PDF already contains signature fields.

## Printing

**File ▸ Print…** (Ctrl+P or Ctrl+Shift+P) opens Monograph PDF's print dialog with a **live preview** of every printed sheet (use ‹ › to step through the sheets). You can choose:

- the printer, number of copies and collation
- pages: all, the current page, the selected thumbnails or a range such as `1-3, 5`
- paper size and orientation (**Auto** turns the paper for landscape pages); the dialog starts with the paper that matches the document, for example A4
- scaling: **Fit to paper**, **Actual size** or **Shrink large pages only**
- color or black and white, and two-sided printing when the printer supports it

**Printing preferences…** opens the printer's own settings for trays, quality and finishing.

Text boxes, typed form entries, shapes and other added content print as shown on screen, including changes you have not saved yet, at full resolution and with the page proportions kept. Printing never saves or changes your file.

## Keyboard shortcuts

| Area | Keys |
| :--- | :--- |
| File | Ctrl+O open · Ctrl+S save · Ctrl+Shift+S save as · Ctrl+W close · Ctrl+P print (with preview) · Ctrl+Alt+D document properties · Ctrl+Q exit |
| Edit | Ctrl+Z undo · Ctrl+Y or Ctrl+Shift+Z redo · Ctrl+X / Ctrl+C / Ctrl+V cut, copy, paste · Ctrl+D duplicate · Del delete · Ctrl+A select all · Ctrl+Shift+A deselect all · Ctrl+Shift+C / Ctrl+Shift+V copy / paste style |
| Arrange | Ctrl+] forward · Ctrl+[ backward · Ctrl+Shift+] to front · Ctrl+Shift+[ to back |
| Tools | V select · T text · I image · R rectangle · E ellipse · L line · A arrow · P freehand · H highlight · U underline · K strikethrough · N sticky note |
| Find | Ctrl+F find · F3 / Shift+F3 next / previous |
| View | Ctrl+= / Ctrl+- zoom in / out · Ctrl+0 actual size · Ctrl+1 fit width · Ctrl+2 fit page · Home / End first / last page · Page Up / Page Down · Ctrl+G go to page · F9 Navigation panel · F8 Properties panel · Ctrl+Shift+H highlight fillable fields · F11 full screen |
| Pages | Ctrl+Shift+N blank page · Ctrl+Shift+I insert PDF pages · Ctrl+Shift+Del delete pages · Ctrl+R / Ctrl+Shift+R rotate · Ctrl+Shift+E extract · Ctrl+Shift+M merge |
| Help | F1 User Guide · Ctrl+/ keyboard shortcuts |

On the page: the arrow keys nudge the selection by 1 pt (with Shift, 10 pt); Shift while drawing constrains the shape; Tab moves between form fields; Ctrl+Enter or Esc finishes typing.

## Current limitations

- **PDF to Word** closely reproduces most documents, but complex magazine-style layouts, unusual fonts or scanned pages may need adjustment in Word.
- **Japanese vertical writing** is not supported yet; text is laid out horizontally.
- **Certificate-based digital signatures** are not supported. Signatures are visual only.
- **Word, Excel and PowerPoint to PDF** needs Microsoft Office or LibreOffice installed on your computer; neither is included.
- **Justified form fields** appear left-aligned in other PDF apps.
- **Supported systems:** Windows 10 and Windows 11 (64-bit). Other operating systems are not supported in this release.

## Troubleshooting

### Security software and SmartScreen

Monograph PDF follows standard desktop practice and does not require weakening your system's security.

- You do **not** need to disable antivirus software or add exclusions.
- Monograph PDF is not code-signed, so Windows SmartScreen may show "Windows protected your PC" for the installer. Check the installer against `SHA256SUMS.txt` from the same release, then choose **More info ▸ Run anyway** only if you obtained the installer from a trusted source.
- If antivirus software quarantines a Monograph PDF file, restore it from quarantine, report the false positive to the antivirus vendor if appropriate, and run Setup again.

### What Monograph PDF does and does not do

- Your documents and usage data are never sent anywhere by Monograph PDF.
- Opening a PDF never changes it. Files are written only when you save, save as, or run a conversion that creates a new file.
- Office conversions: Monograph PDF does not upload the document; conversion uses the locally installed suite (macros disabled by Monograph PDF), which follows its own settings and remote-content behavior.
- Monograph PDF does not bypass security software, inject code into other programs, run JavaScript embedded in PDFs, enable Office macros, start automatically when you sign in, send telemetry, or remove passwords without the correct password.

### Working files

Working files (cache, temporary files and recovery data) are kept in `%LOCALAPPDATA%\Monograph PDF\runtime` and cleaned up automatically. Your settings and recent-files list are kept in `%APPDATA%\Monograph PDF`.

### Installation self-check

At the end of installation, Setup runs a short offline self-check of Monograph PDF (PDF engine, rendering, encryption, PDF to Word, OCR and the main window). It uses a sample page it creates itself, never opens your documents and does not connect to the network. If it reports a problem, run Setup again; if the problem continues, check your antivirus quarantine. The report is saved as `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json`.

## Additional documentation

These files are installed in the Monograph PDF installation folder (by default `C:\Program Files\Monograph PDF`):

- **README.md**: product overview
- **CHANGELOG.md**: what changed in each version
- **SECURITY.md**: how to report a security issue
- **LICENSE.md** and **THIRD_PARTY_NOTICES.md**: license terms of Monograph PDF and the components it includes

**Help ▸ About Monograph PDF** shows the version, the included components and the Office integration status. **Help ▸ Keyboard Shortcuts** (Ctrl+/) lists every shortcut.
