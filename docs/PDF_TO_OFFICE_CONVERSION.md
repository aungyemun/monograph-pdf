# PDF to PowerPoint, Word and Excel

Monograph PDF writes modern Office Open XML files (`.pptx`, `.docx`, `.xlsx`). Old binary formats (`.ppt`, `.doc`, `.xls`) are never produced. Generating these files needs no office suite; all three converters run offline inside the application.

Every conversion reads the document **as shown**, so unsaved edits are included: text boxes, pictures, shapes, replaced text, annotations, page order and rotation. When the document has unsaved changes, the converter first asks **Save**, **Save As…** or **Cancel**:

- **Save** writes the open file and converts it.
- **Save As…** writes a new file, which becomes the open document, and converts that.
- **Cancel** stops the conversion and keeps every change.

The source file is never overwritten unless you choose Save.

## PDF to PowerPoint (Convert ▸ PDF to PowerPoint…)

### Slide size

A slide is the PDF page as displayed, with `/Rotate` applied. PDF points are converted to EMU at 1 pt = 12,700 EMU.

A page within 2 pt of a standard sheet gets that sheet's exact size. The standard sheets are A3, A4, A5, Letter, Legal and Tabloid, in either orientation. So an A4 portrait PDF becomes 210 × 297 mm slides, and an A3 landscape PDF becomes 420 × 297 mm slides. A PDF never gets PowerPoint's 16:9 default.

PowerPoint limits a slide side to between 1 and 56 inches. A page outside those limits is scaled uniformly, and the report says so.

### Pages of different sizes

A PowerPoint file has only one slide size. When the pages differ, the dialog lists the sizes it found (for example "A4 portrait (3 pages); A3 landscape (1 page)") and offers these policies:

| Policy | Slide size | Pages |
|---|---|---|
| Largest page size — true size (default) | widest × tallest page | each page centred at its true scale; smaller pages get a white margin |
| Largest page size — fitted | widest × tallest page | each page enlarged or reduced to fill the slide as far as its proportions allow |
| First page's size | the first page | other pages fitted into it |
| Chosen slide size | A4, A3, Letter (portrait or landscape), 16:9, 4:3 | every page fitted |
| Separate presentation for each page size | one file per size group, e.g. `report (A4 portrait).pptx` | exact size for every page |

No policy ever stretches or crops a page. Every page keeps its proportions.

### Modes

- **Layout-preserving (recommended).** Each page becomes one picture at its true page size. This is the most faithful result, but the text cannot be edited.
- **Editable text.** The page's graphics, images, table rules and backgrounds become one picture *without the text*. Every text line is added on top as a native text box at the same position, keeping its font name, size, colour, bold, italic, superscript and angle.
  - PowerPoint substitutes any font that is not installed on the computer that opens the file.
  - As a result, line breaks and widths can differ slightly. This mode is never pixel-identical.
  - The fonts used are listed in the conversion report.

**Picture quality** is 150, 200 (default) or 300 dpi. Higher values make larger files.

## PDF to Word (Convert ▸ PDF to Word…)

| Mode | What you get |
|---|---|
| **Keep layout** (default, bundled pdf2docx engine) | Every page is rebuilt as Word content: paragraphs, fonts, sizes, colours, tables and images. Each PDF page becomes a Word section with that page's exact size, and the orientation flag matches its shape, so mixed A4/A3/Legal documents stay mixed. Exact positioning can make heavy re-editing harder. |
| **Microsoft Word reflow** (only when Word is installed) | Word's own PDF Reflow. The text flows naturally for heavy editing, but complex layouts may shift. |
| **Text only (editable)** | Plain paragraphs that reflow freely, with one Word section per page at that page's size and orientation. Pictures and positions are not kept. |

Word lays text out in a flow; a PDF positions everything exactly. No mode offers both an exact layout and unrestricted editing for every PDF.

## PDF tables to Excel

Detected tables become worksheets. An **Info** sheet states that table detection is a best-effort process.

## Document properties (metadata)

python-docx, python-pptx and openpyxl start from templates that carry their own properties: the author "python-docx" or "Steve Canny", the comment "generated using python-pptx", and 2013 dates. Monograph PDF removes all of these.

| PDF | Office file |
|---|---|
| Title, Author, Subject, Keywords | Title, Author, Subject, Keywords (preserved) |
| CreationDate, ModDate | Created, Modified (mapped, converted to UTC) |
| Creator, Producer, XMP extensions, PDF/A identification, custom keys | not carried over (no Office equivalent) |

A property the PDF lacks is left empty. Nothing is invented, and no user name, computer name or path from your computer is written. The Word-reflow engine's own author entry is replaced in the same way.

## Output files

Every converter writes to a temporary file in the destination folder and swaps it in only when it is complete. An existing file of the same name stays intact if the conversion fails.

## Verification

- **Package structure.** The generated files are checked for valid packages: every part has a content type and every internal relationship target exists. See `tests/integration/test_office_round_trip.py`.
- **Opening the files.** Each file was opened and converted back to PDF, and the page or slide sizes, orientation, text, a colour patch and the metadata were compared. This was done in two places:
  - with LibreOffice 24.2 on Linux;
  - with Microsoft 365 (Word and PowerPoint 16.0.20430) on Windows 11.
- **Other computers.** On other machines the test is skipped (reported as NOT VERIFIED) when no office suite is installed. A file is not called Office-compatible just because of its extension.

See [CONVERSION_FIDELITY.md](CONVERSION_FIDELITY.md) for the fidelity matrix and [OFFICE_TO_PDF_CONVERSION.md](OFFICE_TO_PDF_CONVERSION.md) for the reverse direction.
