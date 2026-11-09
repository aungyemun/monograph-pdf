# Name, logo and colours

## Name

Write **Monograph PDF**: two words, capital M, "PDF" in capitals. Do not write MonographPDF,
Monograph-PDF or monograph pdf in running text. (`MonographPDF` appears only in file names such as
`MonographPDF.exe`.)

Short description: *A free, open-source PDF editor that keeps your documents on your own
computer.*

## Logo

| File | Use |
| :--- | :--- |
| [`resources/icons/source/monograph_pdf_logo_512.png`](../../resources/icons/source/monograph_pdf_logo_512.png) | Full logo (emblem and wordmark) for web pages and documents |
| [`resources/icons/source/monograph_pdf_icon_1024.png`](../../resources/icons/source/monograph_pdf_icon_1024.png) | Square emblem for app icons, favicons and small spaces |
| [`resources/icons/source/Monograph_PDF_logo.png`](../../resources/icons/source/Monograph_PDF_logo.png) | Canonical artwork; the other files are generated from it |

* Use the files as they are: do not recolour, stretch, rotate or add effects.
* Leave free space around the logo of at least a quarter of its width.
* The logo is designed for light backgrounds. On dark backgrounds, place it on a white or light
  rounded tile.
* Logo files of the predecessor product ("PDF Editor") must not be used.

## Colours

Taken from the program's own light and dark themes, so the website matches the program.

| Name | Hex | Use |
| :--- | :--- | :--- |
| Teal (primary) | `#0F766E` | Buttons, links, highlights on light backgrounds |
| Teal light | `#2BB3A5` | Accent on dark backgrounds |
| Teal tint | `#E7F4F2` | Selected or hovered items on light backgrounds |
| Ink | `#1F2937` | Body text on light backgrounds |
| Slate | `#5F6B7A` | Secondary text |
| Line grey | `#E2E5EA` | Borders and dividers |
| Night | `#15181D` | Dark-theme window background |
| Night panel | `#1C2027` | Dark-theme panels and fields |
| White | `#FFFFFF` | Light background |

Keep body text at a contrast of at least 4.5 : 1 against its background. Ink on White (about
14.7 : 1), White on Teal (about 5.5 : 1) and Teal light on Night (about 6.9 : 1) meet this.

## Fonts

The program uses the standard interface font of each platform. For a website, use the
visitor's system fonts and do not load fonts from third-party services:

```css
font-family: "Segoe UI", system-ui, -apple-system, "Noto Sans", "Noto Sans JP", sans-serif;
```

## Pictures

Use the illustrations in [`images/`](images/) (see the [website kit](README.md#pictures) for
alternative texts). They show fictional documents only. When making new pictures, use
`scripts/make_showcase_screenshots.py` or other fictional documents. Never use real documents,
e-mail or folder names.
