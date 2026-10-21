# Printing and print preview

**File ▸ Print…** (Ctrl+P) opens Monograph PDF's own print dialog.

## Options

| Option | Values |
|---|---|
| Printer | the printers Windows reports, including Microsoft Print to PDF; **Save as PDF** (in the application) is always available |
| Paper and orientation | the printer's paper sizes; Auto picks portrait or landscape per page |
| Pages | all, current, a range (`1-3, 5`) or the selected pages; printed front to back |
| Scaling | Fit to printable area · Actual size · Shrink oversized pages · Custom percentage (centred) |
| Pages per sheet | 1, 2, 4, 6, 9, in reading order, each page keeping its proportions |
| Colour | Color · Grayscale (shades of grey) · Black and white (only black and white pixels, Floyd–Steinberg dithering so photos and charts stay recognisable; text and thin lines stay solid) |
| Copies | 1–999, collated or not |
| Two-sided | offered only when the printer driver reports duplex support |
| Comments | include or leave out annotations |

**Colour availability.** Colour is disabled for printers that report only monochrome output.

**Scaling and the preview.** The page placement uses one function for both the preview and the print job, so the preview shows what is printed.

## Preview

The preview shows each sheet as it will print: paper, scaling, pages per sheet, colour mode and orientation. You can step through every sheet.

The preview and the printout include **unsaved edits**, because both use the document as shown. The source file is never changed.

## How pages are printed

- **Rendering resolution.** Pages are rendered at a resolution matched to the size they are printed at. The base is the chosen dpi; a page shrunk onto smaller paper or printed several per sheet needs fewer pixels.
- **Floor and cap.** Every page is rendered at no less than 72 dpi of its printed size. The render is capped at 120 megapixels, so an A0 poster cannot exhaust memory.
- **Raster output.** Text is therefore printed as a high-resolution image, not as printer fonts.
- **Save as PDF.** Use **Save as PDF** to keep the text as text. It copies the chosen pages as PDF pages, so nothing is rasterised, and writes the file atomically. Paper, scaling, colour and pages per sheet do not apply to it.

## Errors and cancelling

- **Progress and cancelling.** A progress dialog shows the page being printed. **Cancel** stops the job after the current page.
- **Errors.** If the printer does not accept the job (offline or unavailable), you are told so and asked to check the printer or choose another; the document and unsaved changes are kept.
- **No printers.** When no printers are installed, Print is unavailable and Save as PDF still works.

## Verification

`tests/ui/test_printing_options_and_output.py` uses Qt's PDF printer as a real print target. It checks:

- A4 paper with mixed A4, A3, Legal and custom pages;
- proportions and shrinking of an A3 page;
- 2-up output;
- cancelling;
- grayscale against true black-and-white;
- the custom percentage;
- Save as PDF;
- unsaved edits in the output.

**Not verified:** no physical printer was available. Output on physical printers, driver-specific duplex and paper trays has not been verified.
