# Website kit

Monograph PDF · © 2026 Aung Ye Mun

Ready-to-use text and pictures for a Monograph PDF website, a GitHub Pages site or a project
profile. The pages are written for people who have never used a PDF editor: short sentences,
no technical terms where an everyday word works. Copy them as they are or shorten them.

The technical documentation stays in the [documentation index](../README.md). If a website page
and a technical guide disagree, the technical guide is right, so correct the website page.

## Pages

| Page | Use it as |
| :--- | :--- |
| [HOME.md](HOME.md) | Start page: what Monograph PDF is, who it is for, three reasons to use it |
| [FEATURES.md](FEATURES.md) | Features in plain language, each with a picture |
| [DOWNLOAD.md](DOWNLOAD.md) | How to download, check and install safely (including the SmartScreen warning) |
| [PRIVACY.md](PRIVACY.md) | Privacy in plain language; links to the full privacy policy |
| [FAQ.md](FAQ.md) | Frequently asked questions |
| [SCREENSHOTS.md](SCREENSHOTS.md) | Picture gallery with captions |
| [CITE.md](CITE.md) | How to cite Monograph PDF in research |
| [BRAND.md](BRAND.md) | Name, logo, colours and fonts, and how to use them |

## Pictures

All pictures in [`images/`](images/) are made from the real program window by
`scripts/make_showcase_screenshots.py`, using **fictional sample documents** (the "Lumen Bay
Environmental Laboratory", invented people, numbers and addresses). No real document, user name or
folder appears in them. They are drawn by Qt's off-screen renderer at 1.5× scale, so the interface
font can differ slightly from what you see on your own screen. The plain screenshots without a frame are in [`../images/`](../images/).

| File | Size (px) | Headline in the picture | Alternative text (for `alt=`) |
| :--- | :--- | :--- | :--- |
| `monograph-pdf-ui-framed.png` | 2400 × 1600 | Everything on your own computer | Monograph PDF showing a report with its chapter list on the left and document details on the right |
| `monograph-pdf-select-text-framed.png` | 2400 × 1600 | Copy text straight from the page | Two paragraphs of a report selected with the Select Text tool; the status bar says the text was copied |
| `monograph-pdf-select-text-japanese-framed.png` | 2400 × 1600 | Works with Japanese too | A Japanese paragraph selected and copied in Monograph PDF |
| `monograph-pdf-editing-comments-framed.png` | 2400 × 1600 | Review documents together | A report page with highlighted text, sticky notes and a callout; all comments listed on the left |
| `monograph-pdf-forms-framed.png` | 2400 × 1600 | Fill in forms without printing | A registration form being filled in: text fields, a drop-down list and ticked boxes |
| `monograph-pdf-page-thumbnails-framed.png` | 2400 × 1600 | See every page at a glance | Small pictures of all pages beside a page with a bar chart |
| `monograph-pdf-redaction-framed.png` | 2400 × 1600 | Remove private information for good | A contract with a name, an address, an account number and a phone number marked for redaction |
| `monograph-pdf-password-protect-framed.png` | 2400 × 1600 | Protect a PDF with a password | The Encrypt with a password window with password fields and permission choices |
| `monograph-pdf-header-footer-framed.png` | 2400 × 1600 | Add page numbers and headers | The header, footer and page numbers window with a preview of the page |
| `monograph-pdf-viewer-dark-framed.png` | 2400 × 1600 | Easy on the eyes, day and night | Monograph PDF in the dark theme showing the cover of a report |
| `monograph-pdf-start-dark-framed.png` | 2400 × 1600 | Start in seconds | The start page with an Open PDF button and buttons for common tasks |
| `monograph-pdf-social-preview.png` | 1280 × 640 | (card) | Monograph PDF: offline, privacy-first PDF editor for Windows, open source |

Use the framed pictures on web pages and in slides, and the plain screenshots in technical
documentation. On GitHub, the social preview is set by hand under **Settings ▸ General ▸ Social
preview** (upload `monograph-pdf-social-preview.png`).

To make the pictures again after the program's look changes (Windows, from the project folder):

```text
env\Scripts\python.exe scripts\make_showcase_screenshots.py
```

Look at every new picture before you commit it.

## Rules for website text

* **Only true statements.** Every claim must match the technical documentation. Do not write
  "100 % secure", "works with every PDF" or "compatible with Adobe Acrobat" unless such a claim has
  been tested and documented.
* **Versions.** Features differ between Windows, Linux and macOS, and between versions. Name the
  version when a feature is new (for example *Select Text: Windows 0.6.0 and later*), and link to the
  [Releases page](https://github.com/aungyemun/monograph-pdf/releases) for what is currently
  available. Never describe an unpublished version as released.
* **Downloads only from GitHub Releases.** Do not host copies of the installer elsewhere, and
  always show where to find the SHA-256 checksum.
* **No tracking.** The project collects no data, so a project website should not either: no
  analytics, advertising or third-party trackers, and fonts and scripts served from the site itself.
* **Pictures** show fictional documents only. Do not add screenshots of real documents, e-mail or
  folders.
