# Changelog

All notable changes to Monograph PDF. Versions follow `VERSION` (see `docs/RELEASE_AND_VERSIONING.md`).

## [0.2.0] — Unreleased

First public release of Monograph PDF, in preparation. It has not been released yet.

### Features

- View, search, navigate and print PDF documents; opening a document never changes it, edits are written only when you save.
- Edit existing text and add text boxes, images, shapes, annotations and comments.
- Fill, edit and design PDF forms.
- Merge, split, rotate, extract and rearrange pages.
- Convert PDF to Word and create PDFs from images or Word, Excel and PowerPoint documents (Microsoft Office or LibreOffice is used for Office files).
- Protect PDFs with passwords and permissions, or remove supported protection when authorized.
- Add watermarks, headers, footers and page numbers; add visual signatures; apply redactions.
- Perform offline OCR on scanned PDFs and images containing English or Japanese text.
- Light and dark themes, a start page, a built-in User Guide.

### Windows installer

- Per-machine (`C:\Program Files\Monograph PDF`) or per-user (`%LOCALAPPDATA%\Programs\Monograph PDF`) installation; optional Start menu and desktop shortcuts, **Open with** and `.pdf` registrations. Setup never makes itself the default PDF app; use **Help ▸ Make Monograph PDF the Default PDF App…**.
- Reinstalling over an existing Monograph PDF installation replaces only files Setup installed (owned-file list `installed_files.txt`, otherwise a conservative allowlist); unknown or user-created files are preserved. Choosing a different folder offers an in-place upgrade or a move that removes the old files only after the new installation passes its self-check. Silent Setup keeps the registered location unless `/MIGRATEINSTALL` is given.
- Setup refuses to continue while `MonographPDF.exe` is running; it ends with an offline self-check (PDF engine, rendering, encryption, PDF to Word, OCR, main window, no network use).
- The uninstaller removes the installation, shortcuts, registrations, recent files and working files, optionally the settings, and never user documents.
- Windows builds are not code-signed; verify downloads against `SHA256SUMS.txt`.

### Security

- Monograph PDF makes no network connections: the release build leaves out Qt's network and TLS plugins and Python's SSL module, and the self-check fails if anything tries to connect.
- PDF JavaScript, actions and launch commands are never run; external programs are started by full path only; Office conversions run with macros disabled.
- No recovery copy is kept for password-protected PDFs.
- Release-candidate audit: `reports/audit/SECURITY_AUDIT_0.2.0.md` (no blocker; one MEDIUM dependency finding, Pillow 11.1.0, open).
- Exporting a placed picture reads only PNG, JPEG, BMP, GIF, TIFF and WEBP files, so Pillow's rarely used decoders (PSD, FITS, JPEG 2000, …) are never run on a user-supplied file.
- A printer whose name contains a quotation mark is never passed to the printer-preferences command line.

### Testing

- Unit, UI, integration and installer tests, a packaged-application smoke test, a release-content check and a branding scan; see `docs/TESTING.md`.
- Security audit of the release candidate: `reports/audit/SECURITY_AUDIT_0.2.0.md`.

## Internal development history

Versions before 0.2.0 were internal development builds and were not public releases. Their entries are kept below as the development record; they describe the product under its earlier internal name, and nothing in them is a published release.

### Internal compatibility notes for 0.2.0

These describe behaviour kept only so that machines that ran an earlier internal build keep working; it is not user-facing functionality.

#### Product identity

- PDF Editor has been renamed to Monograph PDF.
- v0.1.5 remains the final release under the PDF Editor name.
- New executable: MonographPDF.exe.
- New product branding and application icon.
- Existing PDF Editor installations can be migrated during Setup.

Details:

- Program `MonographPDF.exe` (PE version resource: Monograph PDF / MonographPDF / MonographPDF.exe, © 2026–Present Aung Ye Mun), built into `dist\MonographPDF\`; release files `MonographPDF_<version>_Setup.exe`, `MonographPDF_<version>_Installer.zip` and `MonographPDF_<version>_Source.zip` (source folder `monograph-pdf/`). `SHA256SUMS.txt` lists `MonographPDF.exe`.
- New logo (open book with “M”, PDF page and pen) from `resources/icons/source/Monograph_PDF_logo.png`; `scripts/generate_branding_icons.py` makes `monograph_pdf.ico` (16–256 px), the window, taskbar, Start page and About icons and the Setup wizard images from it. The PDF Editor logo is no longer an application resource.
- Default folders `C:\Program Files\Monograph PDF` / `%LOCALAPPDATA%\Programs\Monograph PDF`; data in `%APPDATA%\Monograph PDF` and `%LOCALAPPDATA%\Monograph PDF`; Start menu folder **Monograph PDF** with **Monograph PDF** and **Monograph PDF User Guide**.
- Windows registration uses `MonographPDF.exe`, ProgIDs `MonographPDF.Document` / `MonographPDF.Convertible` and the Default apps name **Monograph PDF**; Setup still never makes itself the default PDF app. Help menu: **Make Monograph PDF the Default PDF App…**.
- About shows Monograph PDF, its version, description, author, license and privacy information.
- The license is unchanged: Monograph PDF is AGPL-3.0-or-later and every bundled component keeps its license and version.

#### Upgrade from PDF Editor

- Setup keeps PDF Editor's application ID, so it recognises PDF Editor ≤ 0.1.5 (uninstall entry, `InstallLocation`, `UninstallString`, `DisplayIcon`, App Paths, the default `PDF Editor` folders, and a verified Start menu shortcut as a last resort) and replaces it: one installed application remains.
- **Existing installation found** page: for a folder named `PDF Editor` the recommended choice installs into the renamed `Monograph PDF` folder, checks the new installation and only then removes PDF Editor's application files from the old folder (files you added are kept; the folder is removed only if empty); the alternative upgrades in the existing location. Silent Setup keeps the location unless `/MIGRATEINSTALL` is given.
- After the upgrade, PDF Editor's App Paths entry, ProgIDs, Open with entries, Default apps capability, Start menu folder and desktop shortcut are removed once `PDF_editor.exe` is gone; an unregistered second PDF Editor copy is left untouched. A running `PDF_editor.exe` stops Setup.
- On its first start for each Windows user, Monograph PDF copies that user's PDF Editor preferences, recent files (existing files only) and recovery sessions; cache, logs and temporary files are not carried over and the PDF Editor folders are left unchanged (`%APPDATA%\Monograph PDF\legacy_migration.json` records the copy). Uninstalling Monograph PDF also cleans those PDF Editor folders, only for a user whose data was migrated and only when no PDF Editor program remains.
- Development overrides are now `MONOGRAPH_PDF_RUNTIME_DIR`, `MONOGRAPH_PDF_USER_DATA_DIR` (and `MONOGRAPH_PDF_HEADLESS`, …); the `PDFEDITOR_*` names still work as deprecated aliases during 0.2.x. Temporary folders are named `monographpdf*` / `monograph-pdf-theme`; Setup and the uninstaller clean both the new and the PDF Editor names.
- The release build refuses to rebuild `installer\release\` while it holds another, unarchived release; the frozen PDF Editor 0.1.5 release is kept unchanged under `releases\PDFEditor_0.1.5\`.

#### Installer (upgrade and migration groundwork, previously planned as 0.1.6)

- **Upgrade cleanup**: during an upgrade, Setup removes files belonging to the previous application (from the previous `{app}\installed_files.txt` when present, otherwise a conservative allowlist of known application folders/files) before installing the new application files. Unknown or user-created files in the selected folder are preserved. The destination is never deleted wholesale. Settings and recent files are kept on upgrade; documents are never removed.
- **Existing-install detection and migration**: Setup finds a prior install via AppId uninstall registry, App Paths, known defaults, then a verified Start Menu shortcut (fallback only). Same destination → automatic in-place upgrade. Different destination → dialog offering upgrade in the existing location (recommended) or install in the new location and remove owned application files from the old path **after** the new install is validated. Unregistered look-alike folders are logged and left untouched.
- **Silent policy**: different `/DIR` without `/MIGRATEINSTALL` keeps the registered location; `/MIGRATEINSTALL` migrates and cleans old owned files after success.
- Setup ships `installed_files.txt` (built by `scripts\packaging\write_installed_manifest.py`) listing owned relative install paths for the next upgrade.
- Setup refuses to continue while `MonographPDF.exe` or `PDF_editor.exe` is running (silent install fails safely).
- Expanded `[InstallDelete]` to include `licenses\`, root documentation files, and related owned trees so obsolete license/doc files do not linger.

### [0.1.5] — 2026-10-15

A full audit of every menu (File, Edit, View, Insert, Forms, Organize, Convert, OCR, Protect, Sign, Help) and the toolbar, alone and in combination, and a security, privacy, dependency and installer audit (`reports/audit/SECURITY_AUDIT_0.1.5.md`).

#### Security

- External programs (File Explorer, printer preferences, Windows PowerShell for Microsoft Office, LibreOffice) are started by full path only; a same-named program in the current folder, for example next to a downloaded PDF, could be started before. LibreOffice is taken only from its own installation folder, no longer from `PATH` or the current folder.
- `uninstall.exe` started `cmd.exe` by name while running from `%TEMP%`, so a program named `cmd.exe` placed in `%TEMP%` could have run (with administrator rights during a per-machine uninstall), and a cancelled uninstall moved its parked copy back from `%TEMP%` without checking it. It now starts its clean-up by full path and restores itself from the copy it read into memory.
- LibreOffice conversions run with a throw-away profile in which macros are disabled; Microsoft Office conversions keep macros forced off and no longer change the PowerShell execution policy for the conversion process.
- No recovery copy is kept for a password-protected PDF (the copy was not encrypted, so unsaved text and form entries were readable without the password).
- Split, PDF to Images and Extract Images never replace a file already in the chosen folder (`name (2).png` is used), and names from bookmarks or the PDF are reduced to plain file names.
- The release build leaves out network-capable parts PDF Editor never uses: Qt Network with its TLS, network-information and TUIO (UDP) plugins, Qt Quick / QML, Qt PDF, OpenCV's FFmpeg plugin, software OpenGL and Python's SSL module. A release-contents check fails the build on any unlisted program file, development file, key, secret or private path, and the self-check now fails on any network attempt and checks that every bundled module loads.
- Setup's self-check report is saved in `%LOCALAPPDATA%\PDF Editor\logs` instead of the installation folder, so the installation folder holds only PDF Editor's own files. Uninstall removes only folders named `PDF Editor` in the user's AppData and never follows junctions or symbolic links.
- Each release folder includes `SHA256SUMS.txt` with hashes for `Setup.exe`, `PDF_editor.exe` and `PDFEditor_<version>_Source.zip`; the build is documented as not code-signed.
- **Source archive**: each release includes `PDFEditor_<version>_Source.zip` — corresponding PDF Editor release source (application, build, installer, documentation and release tests) plus the corresponding source of every bundled AGPL, GPL and LGPL component (PyMuPDF and MuPDF, pdf2docx, PySide6 and Qt, and the OCR engine's GLib, Pango, cairo, FriBidi, libthai, libdatrie, Graphite2, libiconv, gettext and JBIG-KIT as the MSYS2 source packages of exactly the shipped DLLs). Local personal-document validation utilities are excluded. The release build fails if a release file needing corresponding source is not covered. The GPL, LGPL and MPL license texts are installed in the `licenses` folder.
- `THIRD_PARTY_NOTICES.md` and `licenses/DEPENDENCY_INVENTORY.md` now list every shipped component (including the OCR engine's libraries, OpenSSL, OpenBLAS and the Microsoft C runtime) and no longer list qpdf, which was never shipped; the earlier statement that FFmpeg was not included was wrong and is now true.

#### Changed

- Documentation consolidation for release readiness: PDF Editor license expression standardized to **AGPL-3.0-or-later** (grant already allowed “or later”); `DIRECTORY_STRUCTURE.md` removed (layout moved into `docs/ARCHITECTURE.md` and `docs/BUILD_AND_RUNTIME.md`); `INSTALLATION.md` limited to end-user install/uninstall; Office conversion wording no longer implies the external suite is absolutely offline; qpdf documented as reserved and not shipped; `SHA256SUMS.txt` documented for Setup.exe, PDF_editor.exe and the source archive.
- **Conversion Quality Guide** is a readable table (Conversion · Quality · What to expect) in plain language, with nothing cut off.
- **Reduce File Size** estimates the new size for the level you choose (it used to show one sample for the default level), and reports sizes in KB / MB.
- **Protect ▸ View Permissions** and **View Metadata** show plain labels (“Printing: allowed”, formatted dates) instead of raw PDF values; attachment sizes are shown in KB / MB.
- **Print**: the paper starts at the size that matches the document (for example A4) instead of the printer's default (often Letter).
- **About**: Enter closes the box (View License was the default button).

#### Fixed

- **Copies and conversions ignored unsaved changes**: Save a Copy (selected pages, flattened PDF, copy with metadata), Reduce File Size, Watermark, Header & Footer, Split, Extract Pages, Copy Pages to another PDF, Protect with Password, Unlock PDF, Remove Metadata and every Convert ▸ PDF to … command now use the document as shown, including text boxes, shapes, images and form entries not yet saved. The open file is not changed.
- **Saving a password-protected PDF removed its password**; Save and Save As now keep the passwords and permissions, and the document stays open after saving.
- **Mark Text for Redaction** marked the text only on the page in view, leaving it readable on other pages; it now marks every occurrence in the document and reports how many pages it found.
- **Reduce File Size** failed with “'str' object has no attribute 'value'”.
- Added **shapes and images could not be undone** (Edit ▸ Undo skipped them).
- Choosing the open PDF as the target of a copy or conversion failed with a Windows “file in use” error; PDF Editor now explains and asks for another name.
- With no document open, empty submenus (Save a Copy, Arrange, Align & Distribute, Selected Image, Shapes, Add Field, Tables) and Insert ▸ Shapes ▸ Circle were enabled; a submenu is now enabled only when it has something to use.
- Toolbar: disabled split buttons (Shape ▾, Fit ▾) kept a dark arrow, and a disabled Select tool kept its highlight; both now look disabled.

### [0.1.4] — 2026-10-08

#### Added

- **Print preview**: File ▸ Print now opens PDF Editor's own print dialog with a live preview of each sheet, plus printer, copies, page range, paper, orientation (Auto per page), scaling (Fit / Actual size / Shrink large pages), color and two-sided options. Windows' dialog previously showed “This app doesn't support print preview”.
- Form-field toolbar: **alignment** (left / center / right) and **text color**.
- **Properties panel close button** (× in its top-right corner); F8 or View ▸ Properties Panel shows it again, and the choice is remembered.
- **Word formatting inside form fields**: select one or more words while typing and give them their own font, size (incl. A− / A+), bold, italic, color or UPPER / lower case — the rest of the entry keeps its look. With no words selected the toolbar changes the whole entry, and every word follows (A− / A+ keep the size differences). Saved as a rich-text field (/RV, read by Acrobat) with the plain text in /V and an appearance every reader shows; reopened with the formats intact. Typing in one-line fields uses the same editor (IME and Japanese included).
- **Justify** for form fields with wrapped text: lines reach both edges of the box (extra space between words, or between characters for Japanese); a paragraph's last line stays left. PDF fields only know left / center / right, so other apps show these fields left-aligned; PDF Editor keeps them justified when the file is reopened.
- **Vertical position** (top / middle / bottom) for form fields and text boxes, on the field and text toolbars. A field's choice is saved in the PDF and kept when the file is reopened.

#### Changed

- **Uninstaller**: installed builds include a standard `uninstall.exe`, registered with **Settings ▸ Apps ▸ Installed apps**. Uninstalling asks whether to also remove your settings (complete removal; `/REMOVEUSERDATA` when silent), refuses to run while PDF Editor is open, lists anything it could not delete, and never removes your documents. The Start menu no longer has an uninstall shortcut (Windows 10/11 practice).
- **User Guide** rewritten for release: clearer structure (Getting started to Troubleshooting), menu paths checked against the app, uninstall instructions, no developer commands; developer documents updated to match.
- **Crop Page** asks how much to trim from each edge in millimetres and shows the resulting page size (was raw x0 / y0 coordinates). Split PDF labels are plainer ("Split by", "Pages", "Pages per file"); the interface uses US spelling throughout (color, center, recognize).
- New text boxes have no background or frame (they used to bake a pale-yellow fill and a light-blue border into the saved PDF); add them in the Properties panel when wanted.
- Form-field formatting is on the toolbar only; the Properties panel no longer repeats it and shows the field's type, name and value. The field name is no longer squeezed into the toolbar.
- About box: removed repeated “runs locally” sentences and the cross-platform note; Components lists only what ships inside PDF Editor (Office suites have their own tab; qpdf and Inno Setup removed); the Tesseract and launcher versions are shown; text is left-aligned.
- Footer: the redundant “Ready” word is gone (“Saved” / “Modified” already show the state).
- Print Preview is no longer a separate File menu item (the Print dialog has the preview; Ctrl+Shift+P still works).

#### Fixed

- About ▸ Office Integration reported Windows 11 as “Windows 10”.
- **Printing a filled-in form before saving printed the empty form**: unsaved form entries (and field formatting) were missing from the print preview and the printout when no text box, shape or image had been added. Every unsaved change is now printed; the file on disk is not changed.
- A form's own push buttons (for example a “Print form” button) were offered as text fields, and typing into one replaced its caption; they are now left as they are.
- A fixed-size entry longer than its box printed the top half of a cut-off line under the last full line; only whole lines are printed now, matching the screen. A red **!** marks fields whose entry does not fit.
- OCR no longer flashes a black console window for each page in the installed app, and a stalled page-orientation check no longer stops OCR with an error.
- A new installation no longer shows the recent files of an earlier, uninstalled copy; uninstalling now removes the recent-files list, working files (cache, logs, recovery sessions) and PDF Editor folders left in `%TEMP%`.
- Change Page Size, Header & Footer with page numbers, and the installer's self-check no longer leave empty work folders in `%TEMP%`.
- The Start menu **User Guide** opened the raw `.md` file (which a new computer usually has no app for); it now opens the guide in PDF Editor's own viewer.
- The installer's self-check now also runs OCR (English + Japanese data), so a missing or quarantined OCR engine is reported at install time.
- UPPERCASE / lowercase toolbar icons were small and faint.
- A filled-in form field showed a black box (and white background) around the text after typing; PDF fields now show only their own border and background, usually none.
- Center / right alignment had no effect while typing in a multi-line field, and the caret stayed at the left edge of centered text; the field or text box being typed in now follows alignment, size, bold/italic and color changes at once, and a text selection is kept.
- A− / A+ on a field set to Auto size started from 10 pt (which could shrink the text); it now steps from the size shown.
- Saving: when one field on a page held Japanese, bold or italic text, other filled fields on the same page could be saved empty.
- A field's center / right alignment saved in the PDF showed as left after reopening.
- A field shown in several places (same name on several pages) now gets the entry and the formatting in every place; only the first copy was filled before.
- Fields with their own border or background color kept them only for plain entries; Japanese, bold, italic or repositioned entries lost them on Save.
- Rotated fields (/MK /R) and punctuation such as – — “ ” € in Japanese, bold or italic entries are drawn correctly, in reading order for copy and search.
- Auto-size one-line fields shrink a long entry to fit the box width (as Acrobat does) instead of cutting it off.
- Some page sizes never appeared at Fit Width / Fit Page (the page area stayed blank): the zoom flipped back and forth as the scrollbar appeared and disappeared.
- A selected form field could not be deselected — its blue box and handles stayed. Esc (a second time after typing), a click on blank paper or on the gray area around the page now selects nothing.
- **Japanese and other non-Latin text in text boxes was saved as "?"**. Text boxes are now saved with the same renderer as form fields: every script, plus the box's font, bold, italic, underline, alignment and line spacing (only the characters used are embedded).
- **Headers, footers, page numbers and watermarks** printed Japanese as "···"; mixed Japanese / English text is now drawn correctly. Long watermarks are made smaller so they stay on the page, and the watermark opacity setting now also applies to English-only text (it was always solid gray).
- Working files are cleaned up as promised: abandoned temporary conversions and print copies after a day, recovery drafts after 30 days (they piled up in runtime\temp and runtime\sessions). Test runs no longer write into the app's runtime folder.
- Redaction count message reads naturally ("3 areas marked for redaction" / "No areas are marked for redaction yet").
- Print dialog: **Printing preferences…** opens the printer driver's own settings instead of Windows' print dialog (which showed a second Print button and “This app doesn't support print preview”).
- Font list could shrink to 3 fonts after the installer's self-check saved a font list made without access to the system fonts; such lists are no longer cached or trusted.

### [0.1.3] — 2026-10-08

#### Added

- **Form fields: Bold, Italic, UPPERCASE and lowercase** on the toolbar and in the Properties panel (Style and Case rows). Case buttons also work on text boxes.
- **Start page Recent list** shows a file icon, name, folder and date; one click opens; right-click offers Open, Show in Folder and Remove from List. Show in Folder now selects the file in Explorer.

#### Fixed

- **Japanese + Latin + numbers in form fields**: full-width letters and digits (ＡＢＣ１２３) were saved as “······”, and normal digits after Japanese text were spread out. Such entries are now drawn with an embedded Unicode font subset (≈10 KB), stay searchable, and Japanese forms keep their own font in the field settings.
- Form fields now show their real font (e.g. Courier, MS Mincho) instead of “sans-serif”.
- **Recent files** no longer collect files from the installer self-check and test runs; existing stray entries are removed automatically.
- **File ▸ Open** right after start-up no longer pauses ~1 s (converters now load on first use).
- Low-contrast text: footer, start-page labels and hints, Properties section titles, menu section headers and placeholders now meet the 4.5 : 1 contrast guideline in light and dark themes; dialog warnings and password errors are readable in dark theme.
- Start-page tool icons follow the dark theme from the first launch.

### [0.1.2] — 2026-10-08

#### Added

- **Change Page Size…** (Organize menu, page toolbar, Properties panel): A3–A6, B4/B5 (JIS and ISO), Letter, Legal, Tabloid, Executive, Japanese postcard or a custom size; fit, fill, stretch or keep original size; orientation; margin; page scope. Content is scaled as vectors, and form fields, links and comments move with it. Saved as a new PDF.
- **Font search**: type a few letters in any Font box to list every installed font containing them; the font is applied only when you pick it.
- **Wrap Text** button on the text toolbar, next to the font controls.
- Form fields now show **Font, Size, −/+ and Wrap Text** on the toolbar while selected.

#### Changed

- **New application logo** (red document with quill) for the app icon, taskbar, start screen, About box and installer. The artwork is kept in `resources/icons/source/PDF_logo.png`; `scripts/prepare_logo.py` makes the transparent master and the build generates every icon size from it.
- **Properties panel** reorganised into Text / Paragraph / Box groups: B/I/U toggle buttons, color swatches without hex-code boxes, position and size on two rows, rotation in degrees and opacity in percent. Removed the read-only text line, the non-working “Writing” option and the “Optional” status row on form fields.
- Page panel shows paper name and size in millimetres, with a **Change Page Size…** button.
- Replace / Save Selected Image are greyed out unless an image is selected.
- Clearer OCR-missing and redaction messages (no developer paths or outdated command names).

#### Fixed

- **Save on Windows** failed with “Permission denied” when saving over the open file; the file is now released before it is replaced (with a short retry if another program has it open).

### [0.1.1] — 2026-10-08

Documentation consolidation and About / Help UI sync.

#### Changed

- Canonical `docs/` set reduced to eight Markdown files; child user-guide pages merged into `docs/USER_GUIDE.md`.
- Changelog relocated to repository root (`CHANGELOG.md`).
- About → Components status labels standardized (Bundled / Optional / External); no absolute development paths in the normal table.
- Office Integration tab wording clarifies optional external suites.
- Conversion and offline privacy claims aligned across README, docs, and UI (absolute layout guarantees removed).
- License introductory source-availability wording improved (AGPL legal text unchanged).

### [0.1.0] — 2026-10-08

First release with a Windows installer.

#### Added

- **PDF to Word with layout** — layout engine keeps fonts, sizes, colors, tables, images, columns, page size and margins. Optional Microsoft Word reflow engine and a text-only mode; page range; runs in the background with progress; can open the result when finished.
- **Word, Excel and PowerPoint to PDF** — uses the installed Office application's native PDF export or print path (Microsoft Office or LibreOffice); macros are never run. Office files and images can also be opened directly and become a new unsaved PDF.
- **Rotate Pages…** dialog — all, current, selected, odd, even or a page range; 90° clockwise, 90° counterclockwise or 180°.
- **Protect with Password** — separate permissions password; individual permissions for high-quality printing, page assembly, comments and form filling; AES-128 option for older readers.
- **Watermark color** choice.
- **Start screen tool tiles** — Merge PDFs, Office to PDF, Images to PDF, PDF to Word, Rotate, Protect, Unlock, Watermark, Sign and OCR.
- **Help → Make PDF Editor the Default PDF App…**
- **Windows installer** (`PDFEditor_{version}_Setup.exe`, Inno Setup) — per-machine or per-user install, Desktop and Start Menu shortcut options, `.pdf` registration and **Open with** entries for images and Office files, Default Apps registration, upgrade clean-up, post-install self-test, uninstall that keeps settings and documents.
- `PDF_editor.exe --smoke-test` offline self-check.
- Root documentation set: README, INSTALLATION, DIRECTORY_STRUCTURE, LICENSE, THIRD_PARTY_NOTICES, SECURITY, CITATION.

#### Changed

- **Menus reorganised** into File · Edit · View · Insert · Forms · Organize · Convert · OCR · Protect · Sign · Help. The Export menu was merged into **File → Save a Copy** and **Convert**; Merge and Split head the Organize menu; Convert is split into *Create PDF* and *Convert PDF to*.
- **Command names** made consistent (Title Case, “PDF to Word…”, “Protect with Password…”, “Unlock PDF (Remove Password)…”, “Type a Signature…”); tooltips no longer repeat shortcuts.
- **About** dialog rewritten with About, Components and Office integration tabs, license and third-party notice viewers.
- **Unlock PDF** now keeps form fields, bookmarks and metadata.
- **Open Recent** hides missing files and tells same-named files apart by folder.
- Installed copies keep working files in `%LOCALAPPDATA%\PDF Editor`.
- License clarified as **AGPL-3.0** (the license of the bundled PDF engine).

### [0.0.16] and earlier

Development releases.

- Professional UI upgrade: light and dark themes, drawn icon set, context toolbar, properties inspector, thumbnail panel, status bar, keyboard-shortcut reference.
- In-place editing of form fields and text boxes: real text selection, copy/paste, Tab between fields, resize handles, font, size, alignment, color and text wrapping saved into the PDF.
- Draw-to-place for highlights, stamps, redactions and signatures.
- Merge, split, page organization, OCR (English/Japanese), redaction, password protection, visual signatures, printing.
- Fixed thumbnail rendering, toolbar overflow and duplicate commands; verified on real government forms, a Japanese spreadsheet PDF and a scientific article.
