# File formats and compatibility

## Supported formats

| Format | What Monograph PDF does with it |
| :--- | :--- |
| **PDF** | View, edit, organize, convert, recognize text (OCR), annotate, protect, redact and print |
| **Images** (PNG, JPEG, TIFF, BMP, GIF, WebP) | Open as a new PDF, or place on a page as a picture |
| **Word, Excel, PowerPoint** | Open as a new, unsaved PDF when Microsoft Office or LibreOffice is installed |

## Platforms

| Platform | Status |
| :--- | :--- |
| Windows 10 and 11, 64-bit | Supported |
| macOS | Planned |
| Android | Under consideration |
| iOS | Not planned |

## Engines

| Engine | Used for |
| :--- | :--- |
| PyMuPDF (MuPDF) | Rendering, editing, annotations, encryption and most conversions |
| pdf2docx | Layout-preserving PDF to Word conversion |
| Tesseract | Offline OCR with English, Japanese and orientation data (`eng`, `jpn`, `osd`) |

## Level of support

| Area | Support |
| :--- | :--- |
| Viewing, search and zoom | Full |
| Editing (text boxes, shapes, pictures, comments) | Full; written into the PDF when you save |
| Interactive forms (AcroForm) | Partial: filling in, rich text formatting and field design |
| XFA forms | Hybrid forms with an AcroForm part can be viewed; XFA templates cannot be edited |
| Tables | Partial: tables with ruled lines are detected |
| OCR | Offline, English and Japanese; optional verified language packs (Chinese, Korean, vertical Japanese, German, French, Spanish); accuracy has been measured on a small synthetic set only |
| Organize, merge and split | Full |
| Office to PDF | When Microsoft Office or LibreOffice is installed |
| PDF to Word, Excel and PowerPoint | Best-effort; complex layouts may need manual correction. Page size and orientation are kept (per Word section; PowerPoint size policies for mixed sizes); see [PDF to Office](PDF_TO_OFFICE_CONVERSION.md) and [Conversion Fidelity](CONVERSION_FIDELITY.md) |
| Digital (certificate) signatures | Not supported; signatures are visual only |
| Japanese vertical text | Not supported for editing |

A PDF that is opened but not edited is displayed exactly as MuPDF renders it. Passwords are kept in
memory only — never in recent files, recovery data or logs. Encrypted PDFs are processed locally, and
protection is never removed without the correct password.

## Saving and compressing

| Option | Effect |
| :--- | :--- |
| **Save** / **Save As** / **Save a Copy** | Writes your edits; keeps fonts; never turns pages into images; replacing a file is atomic ([Save As and Export](SAVE_AS_AND_EXPORT.md)) |
| **Lossless** (File ▸ Compress PDF…) | Optimizes the file structure only; pictures are not changed |
| **Balanced**, **Smallest file** | Pictures are reduced and re-encoded (lossy for pictures only); text and vectors are unchanged |
| **Target size** | An exact maximum in bytes (1 KB = 1,000 bytes); reported as achieved only when the saved file is at or below it ([PDF Compression](PDF_COMPRESSION.md)) |

## Related

[Features](FEATURES.md) · [Security and Privacy](SECURITY_AND_PRIVACY.md) · [User Guide](USER_GUIDE.md)
