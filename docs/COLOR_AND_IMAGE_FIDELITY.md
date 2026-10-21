# Colour and image fidelity

## On screen

Pages are rendered by MuPDF, the engine in PyMuPDF 1.25.3, with **ICC colour management on**, which is MuPDF's default.

- **CMYK, ICC-based and calibrated colours** are converted to sRGB for display. This was measured: the same CMYK picture renders as RGB (241, 94, 67) with colour management and as (255, 55, 55) without it.
- **Output intents and monitor profiles** are not applied. The screen is treated as sRGB.

## What saving changes

Saving, with or without edits, never re-encodes or converts existing content. This is checked by `tests/integration/test_page_sizes_and_save_fidelity.py`:

- **Pictures.** The pixel size, encoding (JPEG stays JPEG), colour space and soft masks of every picture are unchanged. CMYK pictures stay CMYK.
- **Vector colours.** Vector fill and stroke values are kept exactly. For example, the fill (0, 0.5, 1) is still (0, 0.5, 1) after saving.
- **Appearance.** Pages without edits render pixel-identically after saving.
- **Text, annotations and page boxes.** Text, annotations and page boxes are unchanged.

Only objects you add are written new. Text boxes, shapes and stamps are vector content. Placed pictures are embedded as you supplied them; pictures with opacity, cropping or rotation are re-encoded as PNG, which is lossless.

## Exports and conversions

| Output | Colour |
|---|---|
| Save as PDF (from the print dialog), Save a Copy, Selected Pages | exact (PDF pages copied, nothing rasterised) |
| PDF to Images | sRGB rendering at the chosen dpi |
| PDF to PowerPoint, layout mode | sRGB page pictures at 150/200/300 dpi |
| Compress PDF | only lossy modes re-encode pictures; grey stays grey, ICC colour spaces are kept, CMYK pictures are never touched — see [PDF_COMPRESSION.md](PDF_COMPRESSION.md) |

## Printing

Printing sends rendered pages to the printer at a resolution matched to the printed size. Grayscale and true black-and-white are applied to the rendered page, never to the document. See [PRINTING_AND_PRINT_PREVIEW.md](PRINTING_AND_PRINT_PREVIEW.md).
