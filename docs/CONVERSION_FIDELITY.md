# Conversion fidelity

Conversions between PDF and Office formats can be lossy. This page describes what each direction keeps, what it changes, and how that was measured. Visual fidelity and editability are measured separately. No test requires binary equality.

## Matrix

| | Page / slide size | Orientation | Text | Fonts | Images | Vector graphics | Colour | Editable |
|---|---|---|---|---|---|---|---|---|
| PDF → PPTX, layout | exact (EMU) | exact | as picture | as picture | as picture (dpi chosen) | as picture | rendered sRGB | no (picture) |
| PDF → PPTX, editable | exact | exact | text boxes at original positions | name kept; substituted if missing | in the page picture | in the page picture | text colour exact | text yes |
| PDF → DOCX, keep layout | exact per section | flag matches shape | paragraphs | name, size, colour | yes | partly (simple shapes) | yes | yes, positioned |
| PDF → DOCX, text only | exact per section | flag matches shape | paragraphs | default | no | no | no | fully reflowable |
| PPTX / DOCX → PDF | as the office suite exports | yes | yes | installed fonts | yes | yes | yes | n/a |

## Round trips (tests/integration/test_office_round_trip.py)

All four round trips passed with LibreOffice 24.2 on Linux and with Microsoft 365 (Word / PowerPoint 16.0.20430) on Windows 11.

| Round trip | Compared | Result |
|---|---|---|
| PDF → PPTX → PDF (layout and editable) | page size (A4, ±2 pt), a known colour patch (±30/255), text (editable) | passed |
| PDF → DOCX → PDF (text and keep-layout) | A4 / A3 landscape / Legal sizes (±3 pt) and orientation in order, text of every page, title | passed |
| PPTX → PDF → PPTX | 7.5 × 10 in portrait slide size, slide count, text, picture, colour, title | passed |
| DOCX → PDF → DOCX | section sizes A4 portrait / A3 landscape, header, footer, table text, picture, title and author | passed |

Unit tests (`tests/unit/test_office_metadata_and_pptx_sizes.py`) cover the following:

- PPTX slide geometry for A4 portrait, A3 landscape, Legal, custom sizes and mixed sizes under every size policy;
- the DOCX section geometry for both engines;
- metadata mapping, with no template values and no local user name.

## Known limits

- **Editable PPTX.** Text boxes use the PDF's font names. On a computer without those fonts, PowerPoint substitutes others, and line breaks can move.
- **Vertical Japanese text and complex scripts.** These are kept as pictures in layout mode. In editable mode, each line keeps its angle, but vertical layout is not reconstructed.
- **Keep-layout DOCX.** Complex vector drawings, transparency groups and form fields become pictures or are dropped by the layout engine.
- **Forms, annotations and digital signatures.** These have no Office equivalent. Annotations are visible in the page picture (layout PPTX) but cannot be edited.
- **Opening in Microsoft Office.** This was verified with Microsoft 365 16.0.20430 on Windows 11 (the round trips above). Other Office versions have not been tested. A file is never called compatible on the basis of its extension.
