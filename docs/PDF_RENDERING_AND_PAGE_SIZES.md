# PDF rendering and page sizes

## Page boxes and geometry

Each page is shown as its **CropBox** with `/Rotate` applied. The CropBox is the visible page area; it is the MediaBox when no CropBox is set.

- **Other boxes.** MediaBox, BleedBox, TrimBox and ArtBox are read and kept unchanged on save. Editing never changes any page box.
- **UserUnit.** A page with `/UserUnit` (PDF 1.6) is shown at its real size. For example, a 300 × 400 unit page with UserUnit 2 is displayed and measured as 600 × 800 pt.
- **Coordinates.** Overlays (text boxes, pictures, shapes, signatures) are placed in *display space*, i.e. what you see. They are converted to the page's own unrotated coordinates when saved (`core/page_space.py`). An object therefore lands where it was placed on rotated, cropped, offset-origin and UserUnit pages alike.

## Standard and custom sizes

Every size is read exactly as stored. No size is snapped or normalised.

Tested sizes:

- A0–A6
- Letter, Legal, Tabloid, Executive
- B4, B5
- arbitrary custom sizes (for example 333.3 × 777.7 pt)
- landscape pages
- pages rotated by `/Rotate`
- pages with offset boxes
- UserUnit pages

See `tests/integration/test_page_sizes_and_save_fidelity.py`.

## Mixed-size documents

In a document with pages of different sizes, each page keeps its own size and proportions in the viewer. Pages are centred in a column as wide as the widest page. Thumbnails, printing, Save and every export also handle each page at its own size.

## Zoom and high-DPI screens

- **Zoom modes.** Fit Width, Fit Page, Actual Size (100 % = 96 px per inch at 1× scaling) and manual zoom from 10 % to 800 %.
- **Rendering resolution.** Pages are rendered at *zoom × device pixel ratio*, so text and lines stay sharp at 125 %, 150 %, 200 % and higher Windows scaling. The scaling factor is taken from the screen the window is on.
- **Window resizing.** In Fit modes, the zoom is recomputed when the window is resized. The re-render is debounced, so dragging a window edge does not render every intermediate size.

## Large pages

A page rendering would exceed 24 megapixels when an A0 poster is zoomed in. In that case, the view draws a low-resolution base image and renders only the visible part as sharp 1024-px tiles. Up to 48 tiles are kept, oldest first out. Memory therefore stays bounded however large the page or zoom. See [PERFORMANCE_AND_RENDERING.md](PERFORMANCE_AND_RENDERING.md).
