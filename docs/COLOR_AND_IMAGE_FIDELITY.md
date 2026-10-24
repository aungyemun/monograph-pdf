# Colour and image fidelity

## On screen

Pages are rendered by MuPDF, the engine in PyMuPDF 1.25.3, with **ICC colour management on**, which is MuPDF's default.

- **CMYK, ICC-based and calibrated colours** are converted to sRGB for display. This was measured: the same CMYK picture renders as RGB (241, 94, 67) with colour management and as (255, 55, 55) without it; a CMYK fill 0/1/1/0 renders as (237, 28, 36), not (255, 0, 0) (`tests/ui/test_display_color.py`). Spot (Separation/DeviceN) colours use their alternate colour space.
- **Monitor profile** (from 0.5.0): when Windows assigns the display a colour profile that is not sRGB (a wide-gamut monitor calibrated with a Display P3 or Adobe RGB profile), rendered pages, page thumbnails, the print preview, edited text boxes and shapes, and placed pictures are converted from sRGB to that profile, so colours are not shown over-saturated. On an sRGB monitor nothing is converted. **View ▸ Match Colors to Monitor Profile** turns it off. Only the pixels on screen are converted: documents, exports and printing are not changed.
- **Placed pictures with their own profile** (Adobe RGB, Display P3 …) are shown converted to sRGB (then to the monitor profile) instead of their raw values.
- Not applied: the document's output intent (shown as sRGB), overprint simulation, and per-monitor profiles on multi-monitor systems (the primary display's profile is used). Word colours inside a text box being edited are drawn unconverted.

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
