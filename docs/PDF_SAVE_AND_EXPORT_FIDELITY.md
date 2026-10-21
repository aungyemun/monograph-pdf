# PDF save and export fidelity

The test cycle is: open → (modify) → save → reopen → compare. It is run by `tests/integration/test_page_sizes_and_save_fidelity.py` on a fixture containing:

- A0–A6, Letter, Legal, Tabloid, Executive, B4 and B5 pages, plus a custom size;
- a landscape page and a `/Rotate 90` page;
- a page with offset CropBox, TrimBox, BleedBox and ArtBox;
- RGB JPEG, CMYK JPEG and grey-with-alpha pictures;
- a note annotation;
- Japanese and mathematical text;
- a UserUnit page.

## Save without changes

| Compared | Result |
|---|---|
| Page boxes, rotation, UserUnit | identical |
| Text of every page | identical |
| Pictures: pixel size, encoding, colour space, soft mask | identical (JPEG stays JPEG, CMYK stays CMYK) |
| Annotations | identical |
| Rendered appearance (sample pages) | pixel-identical |
| Vector fill colour values | exact |

## Save with an edit

A text box was added to one page:

- That page changes.
- Every other page renders pixel-identically.
- Page geometry is unchanged.
- The text box lands where it was placed on A0, Legal, rotated, cropped and UserUnit pages, within a few points.

## Writing the file

- **Save.** The edits are baked into a temporary copy. The open file is then released, because Windows cannot replace an open file, and replaced atomically. If another program holds the file, Save retries for about 4.5 s, then reports it and keeps your edits.
- **Save As, Save a Copy and exports.** Replacing an existing file is atomic. A new file is removed if writing fails.
- **Password protection.** Protection is kept by Save and Save As.

See [SAVE_AS_AND_EXPORT.md](SAVE_AS_AND_EXPORT.md) for the commands and [COLOR_AND_IMAGE_FIDELITY.md](COLOR_AND_IMAGE_FIDELITY.md) for colour.
