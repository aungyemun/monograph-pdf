# Security and privacy

How Monograph PDF protects documents and the PC. Reporting: [SECURITY.md](../SECURITY.md). Audit: [SECURITY_AUDIT_0.2.0.md](../reports/audit/SECURITY_AUDIT_0.2.0.md).

## Offline by design

* Local processing only — no accounts, telemetry, online OCR, or runtime downloads.
* Optional Office conversion uses a locally installed suite only (Monograph PDF does not upload the file).
* Qt network/TLS and Python SSL are stripped from the release; the self-check fails on any connect attempt.

## Untrusted input

* MuPDF parses PDFs; malformed files fail without writing the source.
* PDF JavaScript, actions, and links are never run; attachments are listed only.
* Office macros are forced off; programs start by full system/install path only.

## Photos

**Images to PDF** does not copy JPEG metadata (EXIF with GPS location, camera and date; XMP; IPTC; comments) into the PDF. The picture data is copied unchanged and the EXIF orientation is applied as page rotation; the ICC color profile is kept. Other formats are re-encoded, so their metadata is not copied either.

## Redaction

* Applying redactions removes the page content under each mark (text, image pixels, vector graphics) **and** any form field, annotation or link overlapping a mark. The result is written to a new file.
* Whole-page marks cover the full MediaBox, so content hidden outside the visible (cropped) area is removed as well.
* Redaction acts on pages. For text marked by search, the saved file is then searched for the same text in comments, form values, bookmarks, document properties (Info and XMP) and attachment names/descriptions; every place found is listed, and nothing there is changed unless you choose **Remove These Too**. Attachment contents are never read (attachments are listed, not opened), so attachments are listed as "not checked" for you to review.
* Not covered: text inside images (OCR first), text drawn as vector outlines, and other hidden data such as content outside the visible area on pages that were only area-redacted. Check the result before sharing it.

## Hidden information

**Protect ▸ Remove Hidden Information…** (`core/security/sanitize.py`) scans the document and writes a cleaned copy:

* Removable: document properties (all Info entries, including custom ones) and XMP metadata of the document, its pages and its images; embedded files and file-attachment comments (deleted by name; their contents are never read); scripts and automatic actions — document JavaScript, an open action that does more than show a page (JavaScript, web address, program launch, form submission), document and page automatic actions (`AA`), JavaScript in comments, fields and bookmarks (the bookmark itself stays); embedded page thumbnails; private application data (`PieceInfo`); comments, form fields (including XFA form data), links, bookmarks and invisible text.
* Defaults remove what a reader never needs (metadata, attachments, scripts, thumbnails, private data); comments, fields, links, bookmarks and invisible text are removed only when chosen.
* Invisible text is removed glyph by glyph and the page's visible text is compared before and after; if it would change, the invisible text is kept and the report says so.
* The copy is re-scanned and the before/after counts are shown. Pending redaction marks are reported, never applied here. Password-protected files are refused, because the copy would have to be written unencrypted.
* The copy is always a new, fully rewritten file: earlier revisions kept by incremental saves and unreferenced objects of the original are not carried over (checked in tests by searching every object and decompressed stream of the output).
* Not covered — review these yourself before sharing:
  * anything that is part of the page content: visible text and pictures, content outside the visible (cropped) page area, and content in **layers that are turned off** (optional content), which is neither reported nor removed;
  * text inside pictures, and data hidden inside picture or font data;
  * accessibility structure, including alternate text of figures (kept on purpose), and rarely used catalog data such as web-capture information (`SpiderInfo`);
  * the contents of attachments when attachments are kept (they are never opened);
  * links and web-link bookmarks when those are kept: they are visible, user-triggered navigation, not hidden actions.

## Passwords

Passwords stay in memory while the document is open for Save. They are never written to logs, settings, recent files, or recovery data. **Save** / **Save As** keep encryption. Unlock needs the correct password.

The password strength rating in **Protect with Password** is computed locally (length, character variety, common passwords and patterns); nothing is sent or stored. Encrypted PDFs are handled locally by PyMuPDF (AES-256, or AES-128 when chosen). Permissions passwords are policy for readers, not a cryptographic boundary. No recovery copy for password-protected PDFs.

## Data on disk

| Kind | Location | Uninstall |
| :--- | :--- | :--- |
| App | Install folder | Always |
| Settings | `%APPDATA%\Monograph PDF` | Optional |
| Recent / runtime / sessions / Setup log | `%LOCALAPPDATA%\Monograph PDF` | Always |
| Your documents | Wherever you saved them | Never |

Nothing is written into the install folder at runtime. No startup tasks, services, or extra registry beyond Setup’s registrations.

Diagnostics: each launch keeps a small startup-timing file in the runtime `logs` folder (phase durations only — no document names or content); only the 20 newest are kept. An installed copy writes no other diagnostics unless `MONOGRAPH_PDF_PERF_LOG=1` is set.

## Installer

Upgrades replace owned files only; unknown files stay. Setup never sets the default PDF app. `uninstall.exe` removes the app and working data; settings only with consent / `/REMOVEUSERDATA`.

## Release integrity

`check_release.py` gates contents and source archives. Publish with `SHA256SUMS.txt`. Builds are **not code-signed** — verify hashes before run.

## Related

[ARCHITECTURE.md](ARCHITECTURE.md) · [TESTING.md](TESTING.md#security-tests) · [SECURITY.md](../SECURITY.md)
