# Performance and rendering

## Viewer

- **Visible pages only.** Only pages in or near the viewport are rendered. Rendering is debounced, so scrolling and window resizing do not queue a render for every step.
- **Rendering path.** Pages are rendered straight to RGB samples for the screen, with no image-file encoding in between.
- **Page cache.** The page cache holds 20 rendered pages, least recently used first out.
- **Large pages.** A page whose rendering would exceed 24 megapixels (`MAX_PAGE_PIXELS`) is shown as a low-resolution base plus sharp 1024-px tiles of the visible area. At most 48 tiles are kept. Memory therefore stays bounded on A0 posters and at high zoom.
- **Thumbnails.** Thumbnails are rendered small, at most 160 px on the long edge.

## Printing

The print render resolution follows the printed size and is capped at 120 megapixels per page. Pages are rendered and sent one at a time, never all at once.

## Long-running jobs

Compression, Office conversion, OCR and batch conversion run in worker threads, behind a dialog with progress and **Stop** or **Cancel**, so the window stays responsive.

- **Batch conversion** processes files one at a time, because PyMuPDF documents are not shared between threads. Each output is written as `.part` and renamed when complete.
- **Compression** keeps one candidate per setting in memory. The target-size search runs at most nine compressions and never repeats a setting.

## Undo memory

- **Page operations.** Page operations are undone from whole-document snapshots of at most 200 MB each, with at most 8 kept.
- **Object edits.** Edits to text boxes, pictures, shapes and annotations store only the changed objects.
