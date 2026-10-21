# Word, Excel and PowerPoint to PDF

**Convert ▸ Word, Excel or PowerPoint to PDF…** uses an office suite **already installed on this computer**.

## Why an office suite is needed

Accurate rendering of an arbitrary `.docx` or `.pptx` requires a full layout engine: text shaping, fonts, tables, charts, SmartArt and section geometry. Libraries that only read and write the OOXML structure (python-docx, python-pptx) cannot render a page. Monograph PDF therefore does not claim to convert Office files without one.

## Backends

| Backend | Status | How it is used |
|---|---|---|
| Microsoft Word / Excel / PowerPoint | **Optional, locally installed** (B) | Detected by its registered COM class. A fixed PowerShell script opens the file read-only, with macros forced off (`AutomationSecurity = 3`), and uses the application's own PDF export. File names are passed in environment variables, never in the script text. |
| LibreOffice 6.4 or later | **Optional, locally installed** (B) | Found only in LibreOffice's own installation folders or its registry entry. It is never taken from `PATH` or the document's folder. It runs headless with a fresh, throw-away profile with macros disabled. |
| Built-in engine | **Unsupported** (C) | None is bundled. |

Nothing is downloaded, and no office suite is installed, bundled or started silently. If neither suite is installed, the command explains what is needed. Viewing, editing, printing and every other PDF feature work without an office suite.

## What is preserved

The installed application decides the layout, using its normal PDF export. With a current Microsoft Office or LibreOffice, that export preserves:

- slide size and orientation;
- section page sizes and orientations (mixed A4 portrait / A3 landscape in one document);
- margins, headers and footers;
- text, images, tables, shapes, charts, colours, transparency and slide order;
- title and author.

Fonts that are not installed are substituted by the office suite.

## Verified behaviour

The following ran in `tests/integration/test_office_round_trip.py` with LibreOffice 24.2 on Linux, and with Microsoft 365 (Word / PowerPoint 16.0.20430) on Windows 11:

- PPTX (custom 7.5 × 10 in portrait slides with text, a filled shape, a picture, a chart and a table) → PDF. Each page was 540 × 720 pt. The text, picture, colour (within 30/255) and title were kept.
- DOCX (an A4 portrait section with header, footer, coloured text, a table and a picture, then an A3 landscape section) → PDF. The page sizes were 595 × 842 and 1191 × 842 pt. The header, footer, table text, picture, title and author were present.

With Word, section sizes come back within 1 pt (Word stores sizes in twips). On a machine with no office suite, these tests are reported as NOT VERIFIED rather than passed.

## Output

The PDF is written to a temporary file beside the destination and swapped in when complete. An existing PDF of the same name is not removed if the conversion fails.
