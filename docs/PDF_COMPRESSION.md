# PDF compression

**File ▸ Compress PDF…** makes a file smaller. It compresses the document as shown, unsaved changes included, after the Save / Save As… / Cancel decision. It works in memory, measures the result, shows it, and writes only when you choose where.

## Units

- 1 KB = 1,000 bytes
- 1 MB = 1,000,000 bytes
- 1 GB = 1,000,000,000 bytes

All comparisons are made in bytes. A target typed as `956 KB` means at most 956,000 bytes, and `1.99 MB` means at most 1,990,000 bytes.

Values are rounded **down** when converted, so rounding can never let a file exceed the limit. Windows Explorer shows sizes in binary units, where its "KB" is 1,024 bytes. Binary units (KiB, MiB, GiB) are accepted by the size parser, but the dialog's KB/MB/GB are decimal; when an upload limit is stated in binary units, enter the byte equivalent.

## How to compress

The dialog asks one question — *How do you want to compress it?* — with five answers, each explained
in one line. Only the settings of the chosen answer are shown. A green box states what is always kept
exactly as it is (text, also text you added, fonts, comments, form fields, drawings, links, bookmarks
and the page layout).

| Choice in the dialog | What changes | Lossy |
|---|---|---|
| **Best quality (lossless)** | Identical objects are merged, unused objects removed, and uncompressed content, font and image streams deflated. Objects are packed into object streams, which needs PDF 1.5 (2003) or later. | no |
| **Balanced (recommended)** | Lossless, plus pictures shown above 150 ppi are reduced to 150 ppi and re-encoded as JPEG quality 75. | pictures only |
| **Smallest file** | Pictures are reduced to 110 ppi (scanned pages 150 ppi) and re-encoded as JPEG quality 55. | pictures only |
| **Fit a size limit** | Lossless first. Pictures are then reduced only as far as needed (see below). | only if needed |
| **My own picture settings** | Pictures above the resolution you choose (100–600 ppi) are reduced to it and re-encoded at the JPEG quality you choose (40–95); scanned pages stay at 150 ppi or more. | pictures only |

**Fit a size limit** offers common limits — *E-mail attachment (10 MB)* and *Online form upload
(2 MB)* — or *My own limit*, typed in KB, MB or GB or set with the slider. Real limits differ between
sites, so check the requirement you need to meet.

## What is never changed

- **Content.** Text stays text and vector drawings stay vectors. Nothing is rasterised.
- **Document structure.** Fonts, annotations, form fields and values, bookmarks, links, page labels, page sizes and boxes, and document metadata are kept. Compression and the deliberate *Remove Hidden Information* command are separate.
- **Pictures that would suffer:**
  - 1-bit images, such as black-and-white scans, barcodes and QR codes (usually CCITT or JBIG2 already);
  - image masks;
  - images with a custom decode array or a colour-key mask;
  - CMYK and other special colour spaces;
  - images under 64 px.
- **Quality floors.** Pictures never go below 100 ppi (150 ppi when a picture fills a page, i.e. a scanned page, so small print stays readable). JPEG quality never goes below 40. Grey images stay grey and ICC colour spaces are kept.
- **Password protection.** Protection is kept.

A picture's density is measured at the size it is **shown** on the page. A 1600 px picture shown 6 inches wide is 267 ppi.

## Target-size search

1. The document is analysed: pages, page sizes, text, images (pixel size, shown size, encoding, colour space), fonts, annotations, forms, scanned pages and signatures.
2. The lossless candidate is measured. If it is within the target, the search stops and nothing lossy is done.
3. If no picture can be reduced, the result says that the target cannot be met. Text and vectors are already stored at their smallest.
4. The floor settings (100 ppi, JPEG 40) are measured. If even they are too large, the target is **reported as not achievable without unacceptable quality loss**. The smallest acceptable result is offered, and you are asked whether to keep it. It is never reported as a success.
5. Otherwise, a binary search over a ladder of eleven settings finds the best-quality rung that fits, from 300 ppi / JPEG 90 down to 100 ppi / JPEG 40.
6. Three refinement steps then look between that rung and the next better one, so the result lands close below the target.
7. The search is bounded: at most 1 lossless run, 1 floor run, 4 ladder runs and 3 refinement runs. Results are cached, so the same settings are never compressed twice.
8. An optional **safety margin** (default 1 %) aims that far below the limit. Success is still judged against the exact limit you entered.

Measured examples (tests/unit/test_compress.py, a 3.78 MB PDF with three 1600 × 1200 photographs shown at 267 ppi, safety margin 0):

| Target | Measured result | Status |
|---|---|---|
| 500 KB | ≤ 500,000 bytes (about 470 KB) | achieved |
| 956 KB, 999 KB, 1 MB, 1.1 MB | about 921 KB | achieved |
| 1.99 MB, 2 MB | about 1.88 MB | achieved |
| 5 KB | smallest acceptable ≈ 20 KB | not achievable (reported) |

## Estimate and measured size

- **Estimate.** Before running, the dialog shows an estimate from the analysis alone: typical JPEG bit rates for the reducible pictures, with everything else unchanged. It is labelled as an estimate.
- **Preview.** **Preview** runs the real compression and shows the measured size in bytes, the reduction, the settings used, how many pictures changed and any notes. It also shows the original and compressed versions side by side for the page with the most picture data, at a small size; you can pick another page.
- **Compress and Save As…** uses the same measured result and asks where to save the smaller copy.

## Output

You choose the file name and folder:

- **Another name or folder, or the same name in another folder.** Writing an existing file asks for confirmation first.
- **Replacing the open document.** This needs a second, explicit confirmation.

Every write follows the same steps:

1. The result is validated: it must open as a PDF with the same page count, and every page must render.
2. It is written to a temporary file in the destination folder and flushed to disk.
3. It is swapped in.

If the disk is full, permission is denied, the folder is invalid or the write is cancelled, no file is changed and no partial file is left behind.

**Stop** cancels a running compression, and nothing is written. Compression runs in a worker thread, so the window stays responsive.

## Digitally signed documents

A compressed copy is a rewritten file, so an existing digital signature is no longer valid. The dialog says so and asks before compressing a signed document.

## PDF version

Lossless output uses object streams (PDF 1.5). Higher PDF versions do not mean better image quality; quality depends on the content and the encoding. Monograph PDF does not offer a choice of PDF version, because downgrading could remove transparency, encryption or forms.
