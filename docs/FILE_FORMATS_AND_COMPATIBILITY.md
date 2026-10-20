# File formats and compatibility

## Formats

* **PDF** — view, edit (overlays + bake), organize, convert, OCR, annotate, protect, redact, print (PyMuPDF). qpdf reserved, not shipped.
* **Images** — PNG/JPEG/TIFF/BMP/GIF/WebP open as PDF or as overlays.
* **Office** — Word/Excel/PowerPoint open as new unsaved PDF when a local suite is present.

## Platforms

| Platform | Status |
|---|---|
| Windows 10/11 x64 | Supported |
| macOS | Planned |
| Android | Future |
| iOS | Not planned |

## Engines

| Engine | Role |
|---|---|
| PyMuPDF | Render, edit, security, annotations |
| Tesseract | Offline OCR (`eng`/`jpn`/`osd`) |

## Support levels

| Area | Level |
|---|---|
| View / search / zoom | Full |
| Overlay edit | Full (bake on Save) |
| AcroForm | Partial (rich text; no painted field names) |
| XFA | View hybrid AcroForm only; template editing unsupported |
| Tables | Partial (ruled lines) |
| OCR | Offline, English and Japanese; accuracy measured on a small synthetic set only |
| Organize / merge / split | Full |
| Office → PDF | When Microsoft Office or LibreOffice is installed |
| PDF → DOCX / XLSX / PPTX | Best-effort |
| Cryptographic signatures | Unsupported (visual only) |
| Japanese vertical | Not supported |

Opening without edits shows the MuPDF page. Passwords stay in memory only — never in recent files, sessions, or logs. Encrypted PDFs are handled locally; protection is never removed silently.

## Save / optimize

| Mode | Behavior |
|---|---|
| Save / Save As | Bake dirty overlays; keep fonts; no full-page rasterize |
| Lossless | Structure only — no image downsample |
| Standard / Balanced / Minimum | Increasing size reduction; Balanced+ are lossy |

## Related

[FEATURES.md](FEATURES.md) · [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) · [USER_GUIDE.md](USER_GUIDE.md)
