# Changelog

All notable changes to Monograph PDF. Versions follow `VERSION` (see `docs/RELEASE_AND_VERSIONING.md`).

Windows, macOS and Linux are versioned independently in one repository. Prefer
platform-specific release tags — GitHub’s repository-wide “Latest” badge may point at any platform.

| Platform | Latest published | Notes |
| :--- | :--- | :--- |
| Windows | **[0.5.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.5.0)** | First Windows release with signed update checks |
| macOS | **[0.1.0](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)** (`v0.1.0-macos-1`) | First macOS line |
| Linux | — | **0.1.0** on branch [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux); **no** `v0.1.0-linux` tag yet |

## [Unreleased — macOS]

macOS line only; the Windows version is unchanged.

### Fixed
- OCR did not work in the installed macOS app (`.dmg`, `.pkg`, zip): the bundle linked
  `engines/ocr` and `models/tessdata` one directory too shallow, and shipped the development
  wrapper that runs `tools/ocr-env` instead of a real Tesseract. The build now stages the binary and
  its dylibs into the bundle with each package's license and an inventory (`THIRD_PARTY_OCR.json`),
  and refuses dangling symlinks.
- `package_macos.sh` retries `hdiutil create` when it fails with "Resource busy".
- The bundled OCR libraries carried the build machine's folder path (conda writes the install path
  into OpenSSL, curl, krb5, libxml2, libtesseract). The build now ships the unmodified published
  conda-forge files, keeps their own signatures, and fails if the builder's home path is anywhere in
  the app.
- Check for Updates on macOS could offer the Windows line; it now explains that Mac updates are
  downloaded from GitHub Releases.

### Added
- OCR provenance and corresponding source: `scripts/packaging/macos_ocr_env.lock` pins the exact
  conda-forge builds; `scripts/packaging/macos_ocr_sources.json` records each bundled package, its
  feedstock commit, upstream sources (SHA-256 from the package's own recipe) and the hash of every
  bundled file. `package_macos.sh` publishes verified corresponding source for the copyleft
  libraries (lzo, libiconv) next to the .dmg and fails on any missing license, source or mismatch.
- Opening PDFs from Finder, Open With and the Dock icon.
- Make Monograph PDF the Default PDF App on macOS through LaunchServices.
- Application-menu roles for About, Settings… and Quit; dark mode follows the system appearance.
- Mac keys for document tabs (Control+Tab, ⌘⇧] / ⌘⇧[) and full screen (Control+⌘F); tooltips show ⌘.

## [0.5.0] — 2026-10-28

Windows line. Changes after 0.4.0: versions 0.4.1 and 0.4.2 were never released; their changes are
part of 0.5.0. This is the first Windows release with signed update checks switched on.

### Security

- **Copies of a password-protected PDF were written without protection.** Save a Copy (Whole
  Document), Metadata-Preserving Copy, Remove Document Information, Flattened PDF, Watermark, Header &
  Footer, Background, Remove Header/Footer/Watermark/Background, Extract Pages, Redact, Compress and
  Make Searchable (OCR) now keep the same open password, permissions password, permissions and
  encryption as the original. Several of them also lost bookmarks and attachments; they are kept.
- **The permissions of a protected PDF are honoured.** A PDF opened with its open password only can be
  printed, converted or changed only as far as its author allowed; otherwise Monograph PDF asks for the
  permissions (owner) password, which then applies until the document is closed: converting to Word,
  PowerPoint, Excel, text or pictures, Extract Images, copying a page as a picture and OCR text export
  need content copying; Print needs printing; saving changes, page design, Flatten and Compress need
  changes; extracting, splitting and combining pages need page assembly; changing the protection
  always needs the permissions password. **Remove Protection** with only the open password is refused
  when the PDF restricts anything. Batch Convert skips such files with a message. Opening a restricted
  PDF says what needs the permissions password.
- **Digitally signed PDFs**: saving under another name without changes now copies the file byte for byte,
  so its signatures stay valid (it used to be rewritten, which invalidated them); Save without changes
  does nothing instead of rewriting the file; Save with changes over a signed PDF asks first, because
  the signatures become invalid. Word and PowerPoint exports say that the signature is shown as it looks
  but the exported file is not digitally signed.
- **Temporary copies of protected PDFs**: a temporary copy made for an export or print from a protected
  PDF is removed also when the operation fails, and one left behind by a crash is removed at the next
  start (it used to stay up to a day in Monograph PDF's temporary folder).
- **OCR language downloads** happen only when you click **Download and Install** (see Added), over
  HTTPS with certificate checks to github.com / raw.githubusercontent.com only, and the file is
  installed only if its size and SHA-256 match the pin shipped with Monograph PDF.
- **Update checks look only at Windows releases.** The repository also publishes macOS and Linux
  releases, and GitHub's "Latest" may point at one of them. Check for Updates now reads the list of
  releases and takes the newest Windows release that carries a signed update manifest (all pages of
  the list, no silent fallback); a release of another platform is never offered.

### Added

- **Several PDFs open at once**, each in its own tab above the page (search results, page, zoom and
  unsaved changes are kept per tab); opening a PDF that is already open switches to its tab. Closing a
  tab with unsaved changes asks first.
- **Arrow keys move** the selected shapes, text boxes, form fields and comments (Shift: 10 pt steps).
- **Scroll button**: press the mouse wheel button on a page and a round scroll marker appears; move the
  pointer above or below it and the pages scroll that way, faster the further away (sideways too on
  wide pages). A click keeps scrolling until the next click or Esc; holding the button scrolls until it
  is released. **View ▸ Automatic Scrolling** (Ctrl+Shift+L) scrolls at a steady reading speed: ↓ / ↑
  change the speed, Esc stops, and it stops by itself at the end of the document.
- **New colour picker** for every colour choice (text, highlight, shapes, comments, stamps, notes, form
  fields, page design): a large colour field with hue strip (and opacity where it applies), current and
  new colour side by side, Hex (also colour names) and R G B fields, standard colours, the recent
  colours (kept between sessions), **Pick from Screen** with a magnifier, and for text colours the
  contrast on white paper. It replaces Qt's generic colour dialog.
- **Pictures behind text**: a placed picture can be **In Front of Text** (covers what is under it) or
  **Behind Text** — the page's text and lines show through it, as if the picture were printed on the
  paper beneath them; this also works on scanned pages and on pages with a white background, and the
  text stays selectable. In the Image toolbar, **Edit ▸ Selected Image** and the Properties panel
  (Placement); shown on screen exactly as saved; undoable.
- **Exports and page-design marks**: PDF to Word and PDF to PowerPoint can leave out the watermark,
  header/footer and background added with Monograph PDF (a locked watermark and other programs'
  watermarks always stay). **Protect ▸ View Permissions** also explains how Monograph PDF handles the
  PDF (protection, signatures, watermarks).
- **OCR languages**: 35 more languages (45 in all, besides the included English and Japanese), among
  them Arabic, Burmese (Myanmar), Dutch, Greek, Hebrew, Hindi, Indonesian, Italian, Polish, Portuguese,
  Russian, Thai, Turkish, Ukrainian and Vietnamese. **OCR ▸ OCR Languages** was redesigned: a searchable
  table (language, code, size, status), **Download and Install** (one click, verified), **Install from
  File…** (several files at once), language files already in the Downloads folder offered for
  installation, and **Copy Address**. An installed language is ready at once and is ticked for
  recognition. Every download address and SHA-256 was checked against the official Tesseract release.
  When Tesseract's automatic page layout finds no text (seen with Burmese), the page is read again as
  one block of text.

### Changed

- A placed picture whose box was stretched with **Lock aspect ratio** off is saved stretched, as shown
  on screen (it was saved letterboxed).
- **Flatten Form on Save** has an icon in the Forms menu, like its neighbours.

### Removed

- Two internal modules that the application no longer used (an older PDF optimiser replaced by
  Compress PDF, and a duplicate OCR wrapper) and their tests.

### Fixed

- **A text box just placed could not be resized**: its handles lie half inside the box being typed in,
  which took the click. Every handle now resizes the box, while typing and afterwards.
- **Eraser** about 200 times faster on pages with many marks (it read every annotation of the page
  again for every 1.5 pt of the stroke: over a second for a long stroke); its reach matches the drawn
  stroke. **Highlighter** strokes reuse the page's text instead of extracting it twice per stroke, and
  only the newest piece of a stroke is redrawn while drawing.
- **Sticky notes**: dragging a note moves its icon with the pointer at once (it used to jump only
  after the drop); pointing at a note no longer reveals its text — one click opens it, a second click
  closes it, a double-click edits it, and a drag never opens it. New notes have a smaller icon
  (15 pt). The note card and the note dialog have a cleaner look in both themes.
- **Zoom**: Ctrl + mouse wheel zooms around the pointer (the text being read stays under it), a burst
  of wheel steps renders once, and pages are shown scaled instead of blank until the sharp picture is
  ready. Touchpad pinch / small wheel steps zoom smoothly.
- **Drop-down lists, menus and tooltips** open at once (Windows' slide and fade animations made them
  flicker); every drop-down list is at least as wide as its longest entry.
- Typing in a text box does less work per key (plain text skips the per-character format pass).
- **Crash while scrolling the font list** after placing a text box and typing (access violation).
  The font box was rebuilt: Monograph PDF's own font list and row painter instead of wrapping the
  painter of Qt's font box (which Qt may replace or delete), one font list per session, every row
  the same height, the Properties panel keeps one font box instead of creating and deleting one at
  every refresh, and nothing is rebuilt under an open or scrolling list. Fonts without Latin letters
  (symbol and Japanese-only fonts) show their name readably with a sample in the font.
- **Selected words in a text box** keep their selection (and its highlight) while the font box, size
  box or a colour is used, and only those words change: a text box can now hold words with their own
  font, size, bold, italic and colour — shown while typing and on the page, undone and redone with
  the text, kept in the session and written into the saved PDF. Selecting all of the text changes
  the box itself. The font box used to close the text box first, so the selection was lost and the
  font went to the whole box.
- The **problem report window** no longer opens inside the code that failed (for example in the middle
  of drawing a list); it opens right after, once per burst of the same error. Opening it inside a
  drawing handler could itself end the application.
- **Filled forms looked empty in Adobe Acrobat.** Forms made with Adobe LiveCycle Designer (many
  Japanese government forms) keep every field twice — as ordinary PDF fields and in an Adobe XFA
  copy that only Acrobat shows. Saving now writes the typed values into the XFA copy as well; when a
  field cannot be matched with it (or fields were added, or the form is flattened) the XFA copy is
  removed instead, with a message, so Acrobat shows the same values as other PDF apps.
- Typing in **Find** no longer makes the zoom and page buttons jump to the left.
- A **text box** keeps the size it was drawn at while you type (it used to collapse to one line at the
  first letter and jump); longer text makes it taller downwards, and every typed line stays visible.
- **Pictures** resize smoothly and keep their proportions (Shift: stretch freely); only the changed
  area is redrawn, an edge can no longer be dragged across the opposite one, and handles are easier
  to catch.
- **Lines and arrows** keep their direction when moved, resized or after Undo (they could flip to point
  down-right), moving a shape can be undone, and arrow heads look the same on screen and in the saved
  PDF.
- The **font list** no longer jumps while it is open (the toolbar refresh waits until it closes), and
  the font in use is marked also when it is listed under its Japanese name (ＭＳ 明朝 for MS Mincho).
- **Print**: the paper list is short and scrolls, the settings scroll on small screens, and “Flip on
  long edge / short edge” are no longer cut off. No text in the dialogs and the Properties panel is
  cut off at 100–150 % display scaling (checked with `scripts/audit/clipped_text_audit.py`).
- **Forms**: text fields stay fillable after an ordinary Save (they were sometimes flattened), check
  boxes keep their tick after Save, Save As and reopening, and printing or flattening uses the values
  just typed. Check boxes whose "on" name is not plain ASCII (many Japanese forms) were saved ticked on
  screen but **unticked in the value** and showed unticked after reopening; they are now saved and
  read correctly.
- **Form fonts**: a field whose form defines its own font (for example Times New Roman) kept it
  only until Save, which replaced it with Helvetica for other PDF readers; the form's font is kept.
- **Long entries in multi-line fields with Auto font size** were cut off at the bottom of the
  field in the saved PDF; the text now shrinks until all of it fits, as in Adobe Acrobat.
- **Japanese text in a chosen Japanese font** (MS Gothic, MS Mincho, Meiryo …) was shown on screen,
  and its lines broken, in Yu Gothic UI / Yu Mincho, while Save used the chosen font: the screen and the
  saved PDF now use the same font. Whether a font has a character is now asked of the font file itself
  (the previous check gave wrong answers for non-ASCII characters).
- **Edit Text on existing text**: the edited text keeps the original's font (MS Gothic, Yu Gothic, Times
  New Roman … used to come out in a substitute font), and words placed one by one on the page (also
  text saved by Monograph PDF) are edited as one run, so a longer word no longer overlaps the next.
- **Freezes of several seconds while scrolling long documents**: when the top or bottom edge of the
  window fell into the gap between two pages, every page from there to the end of the document was
  drawn at once, and the page number jumped to the last page for a moment. Zooming with Ctrl + wheel
  with the pointer between two pages no longer jumps to the end either.
- **Find Next / Find Previous** made the page of the match the current page one match late, so page
  commands right after a search could act on the previous page.
- **Selecting several objects**: dragging one of several selected objects moves all of them (only the
  one under the pointer used to move, and Delete then removed only it); a drag on empty paper also
  selects shapes and pictures; a resize handle caught a few pixels off its centre no longer makes the
  edge jump to the pointer.

### Added

- **Find** understands scientific writing: Greek letters and their names (TNF-alpha finds TNF-α,
  IL-1beta finds IL-1β), micro sign and Greek mu (µM / μM), minus sign, en dash and hyphen, degree
  signs, typographic quotes, unit exponents (cm2 / cm², s-1 / s⁻¹), ligatures, capitals of
  non-Latin letters (Α / α, Ü / ü), and pasted text with line breaks.
- **Shape toolbar**: line thickness, line style, opacity, and the start and end of lines and arrows
  (arrow head, dot, bar or none), right above the page.
- **Form fields**: background and border of a field (or none) in the Properties panel, saved into the
  PDF field itself.
- **Recognize Text**: a page range (e.g. 1-3, 7), and a language list ready for many languages
  (search box, the chosen languages listed, at least one always kept).
- **Protect with Password**: AES-256 stays the default (the strongest PDF encryption); a line tells
  whether the document information is encrypted (with an open password) or readable by anyone; it
  can be removed from the protected copy; a watermark added by Monograph PDF can be locked into the
  pages (no layer to hide, not removable with Remove Watermark) while changes stay disallowed.
- **Colors to the monitor profile**: on a wide-gamut monitor with a non-sRGB color profile, pages,
  thumbnails, the print preview, edited objects and placed pictures are shown converted to that
  profile (View ▸ Match Colors to Monitor Profile; nothing changes on an sRGB monitor or in the
  saved document). Placed pictures with their own color profile are shown with it.

- **Sticky notes** open as a pop-up beside the note when clicked (author, date, text, Edit…); Esc or a
  click elsewhere closes it. Eight icons (speech bubble, note page, question, insert, key, paragraph,
  check mark, star) and ten colours, chosen when adding or editing a note, optionally as the default.
- **Lines and arrows**: round handles on both ends to move each end (Shift: 45° steps); start and end
  styles (filled, open or sharp arrow, dot, bar or none), head size, **Reverse direction**, and dash
  styles solid, dashed, dotted, dash-dot and long dash. Circles and squares can be stretched into ovals
  and oblongs afterwards.
- **Freehand** strokes are smoothed (mouse jitter removed, drawn as curves) and resize with their box.
- **Insert ▸ Symbol…**: check marks, stars, arrows, maths and currency signs, circled numbers and
  Japanese marks, placed as text boxes.
- **Rotate Pages**: clearer rotate icons with “Left 90°” / “Right 90°” labels and **Rotate…** on the
  Page bar; the dialog turns 90° left, 90° right or 180°, or sets an exact orientation (0°, 90°, 180°,
  270°) for all, odd, even, selected or chosen pages, with a preview — one Undo step.
- **Print ▸ Custom size…**: any paper size in mm, cm, in or ft (values convert when the unit changes).
- **Find** also finds text typed into form fields, and full-width and half-width forms find each other
  (２月 / 2月).

### Performance

- Opening a 3000-page document took 3.3 s, now 0.4 s (page contents are analysed only when needed).
- Searching a long document no longer freezes the window: matches appear while the search continues
  (3000 pages with a match on every line: the window stays responsive, at most about 0.1 s per step).

## macOS 0.1.0 — 2026-10-25

First **macOS** release
([`v0.1.0-macos-1`](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.0-macos-1)).
Versioned independently of the Windows line. Feature set mirrors Windows; platform integration is
documented on the [`macos`](https://github.com/aungyemun/monograph-pdf/tree/macos) branch
([docs/MACOS.md](https://github.com/aungyemun/monograph-pdf/blob/macos/docs/MACOS.md)).

### Added (macOS)

- macOS application built from the shared PySide6 / PyMuPDF core.
- Project-local development scripts (`setup_env.sh`, `dev_launch.sh`, `run_tests.sh`,
  `vendor_ocr_macos.sh`, `build_app.sh`).
- Offline OCR via a project-local Tesseract and bundled `eng` / `jpn` / `osd` language data.
- Single-instance handover with an `fcntl` file lock; **Show in Folder** reveals in Finder;
  user data under `~/Library/Application Support/Monograph PDF`.
- Office → PDF uses LibreOffice when installed at `/Applications/LibreOffice.app`.

### Notes

- Automatic Windows installer / Authenticode update installation is not used on macOS.
- Microsoft Office COM conversion remains Windows-only.
- Builds for this first line are unsigned; use **Right-click → Open** if Gatekeeper blocks them.

## Linux 0.1.0 — 2026-10-25 (branch only — no release tag)

First **Linux** build on branch [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux).
Versioning is independent of the Windows line. **No** `v0.1.0-linux` (or other Linux) release tag
has been published yet — clone the branch and build from source. See [LINUX.md](LINUX.md).

### Added (Linux)

- `scripts/setup_env.sh`, `dev_launch.sh`, `run_tests.sh`, `vendor_ocr.sh`
- Per-user install helper (`installer/linux/install.sh`)
- Desktop integration (`core/linux_desktop.py`): flock single-instance, fontconfig, LibreOffice,
  XDG desktop / default PDF handler, Tesseract + pinned tessdata

### Notes

- **Unsigned** for this first line; signing later.
- Do not advertise Linux through a nonexistent GitHub release tag.

## [0.4.1] — 2026-10-23

Prepared on this date but **never published**; everything below is included in 0.5.0. A bug-fix
version for 0.4.0 that also switches on signed update checks. The sending of problem reports
remains switched off.

### Security

- **Update checks are switched on**, trusting one production Ed25519 update-signing key (key id
  `27c3b3b23b949c40`). **Help ▸ Check for Updates…** contacts only the official GitHub Releases page
  when you ask, accepts only update information signed with that key, and downloads or installs
  nothing until you click **Update Now**. Automatic checks are optional and off by default. 0.4.0 and
  earlier cannot update themselves; install 0.4.1 once with Setup.
- Failed checks and updates name the situation — no internet connection, GitHub temporarily
  unavailable, no compatible release found, invalid digital signature, expired update information,
  invalid date, different product, unsupported upgrade path, installer integrity check failed,
  download interrupted, update canceled — say that nothing was downloaded or installed, and offer
  **Open Releases Page**. Checking again always repeats the full verification.
- Update information (the signed manifest of each release) is valid for **730 days** from its
  publication; the application refuses manifests with a longer validity or invalid dates. Expiry
  never affects using the application, offline or online.
- Monograph PDF and its helper programs are checked to never open a console window: every console
  program it starts runs without a window (test), and the release check script reports the program
  type of the installed files.
- Maintainer tooling: the update-signing key is stored encrypted with a passphrase that is only read
  from the console, and additionally as a standard encrypted PKCS#8 file (PBES2 + scrypt +
  AES-256-CBC, decrypted with the maintained `cryptography` library and bound to the known public
  key); `update_manifest.py selftest` checks one or more key copies against the application's own
  verification code and scans for unencrypted copies; `make` refuses to write a manifest unless two
  independent Ed25519 implementations agree and it verifies; `make_signing_bundle.py` builds a small
  stand-alone signing-tool folder with hash-pinned optional dependencies; `verify_release.py` checks
  the signed update manifest of every release that has updates switched on.
- Release testing: `docs/WINDOWS_RELEASE_TEST_CHECKLIST.md` and the read-only
  `scripts/windows_release_check.ps1` for installation, upgrade and update tests on real Windows
  computers.

### Fixed

- **Crash when choosing a font while editing text.** Adding a text box, typing, selecting the text and
  then picking a font in the **Properties** panel could close Monograph PDF without a message (an
  access violation): the panel rebuilt its rows while the font list was still open and deleted the
  list under the mouse. The panel now waits until the list has closed and removes old rows safely.
- The font list in the text toolbar closed on the first click instead of opening, and turning the
  mouse wheel over a font box changed the font of the selected text. The list now opens on the first
  click, and the wheel scrolls the panel instead of changing the font.
- **Fonts installed as collections (.ttc / .otc)** — for example MS Mincho, MS Gothic, Meiryo,
  Yu Gothic, SimSun or Cambria — were replaced by a built-in font with the message "font collections
  (.ttc) are not embedded". The chosen face is now taken from the collection and embedded (only the
  characters used), after checking that face's embedding permission. Japanese fonts that declare
  themselves "fixed pitch" although full-width characters are twice as wide (MS Mincho, MS Gothic)
  keep each character's own width in the saved PDF; otherwise the saved text would be spaced at half
  width with overlapping characters.

- Settings survive direct upgrades over many versions: `preferences.json` records its layout and is
  migrated step by step; a value of the wrong type no longer replaces the setting silently later
  (the default is used); settings of a newer version are kept; an unreadable settings file is copied
  aside instead of being overwritten; settings and the recent-files list are saved atomically.

### Changed

- **Compress PDF** is easier to use. It asks one question — *How do you want to compress it?* — with
  five answers, each explained in one line: **Best quality (lossless)**, **Balanced (recommended)**,
  **Smallest file**, **Fit a size limit** (e-mail attachment 10 MB, online form 2 MB, or your own exact
  limit) and **My own picture settings**. Only the settings of the chosen answer are shown. A box
  states what is always kept exactly as it is: text (also text you added), fonts, comments, form
  fields, drawings, links, bookmarks and the page layout; only pictures can be reduced. The button
  reads **Compress and Save As…**, and the dialog fits a 1366 × 768 screen. What compression does to a
  file is unchanged.
- **Problem reports after a crash** now say what happened instead of only "did not close normally":
  the kind of fault (for example an access violation), the place in Monograph PDF's own code, the
  program file it happened in (only files of Monograph PDF itself; anything else is reported as
  "external") and the last few actions (such as changing a font, a style, pages or a comment). The
  report is built from approved fields only, is shown in full, and is still not sent anywhere: sending
  remains switched off. The fault details stay in a local file until the next start.

## [0.4.0] — 2026-10-23

Feature and reliability release: fixes for problems found in daily use of 0.3.0 (a crash in the font
list, slow dragging, comments and undo not refreshing the page, an eraser that needed several passes,
sticky notes that could not be opened, fields that could not be typed into after adding them, pictures
pushed half off the page) and new editing options for stamps, signatures, pages, printing and
compression. Update checks, automatic upgrades and the sending of problem reports remain switched off.

### Security

- A PDF protected only with a permissions (owner) password — it opens without a password but forbids,
  for example, copying or changing — lost its owner password and all its restrictions when saved:
  Monograph PDF wrote an unprotected file. Saving (also after undoing page operations) now keeps the
  protection exactly as it was. **Document Properties** and **Protect ▸ View Permissions** showed such
  files as "not encrypted, every action allowed"; they now show the real restrictions.

### Added

- **One window at a time** — starting Monograph PDF again while it runs (Start menu, shortcut, or
  opening a PDF in Explorer) no longer starts a second copy: the open window comes to the front and
  opens that PDF (asking first about unsaved changes), or says it is already running. Uses a Windows
  named mutex and a local request file; no network.
- **Memory saving while minimized** — a few seconds after minimizing, page pictures, tiles and
  thumbnails are released, MuPDF's cache is emptied, the working set is trimmed and Windows efficiency
  mode is switched on (not while OCR or a conversion runs). Measured: about 30 MB while minimized
  (from 340–470 MB); the page reappears at once when restored.
- `scripts/perf_check.py` measures start-up, scrolling, zooming, thumbnails and memory on the real
  window with generated documents (300 text pages; 40 scanned pages).

- **Edit Stamp** — double-click a placed stamp to switch its type (Approved, Rejected, Draft …), change
  its text and second line, font, text / border / fill color, border (double, single or none), corners
  (rounded, square or round ends), line thickness, opacity and rotation, with a live preview.
  **Customize Look…** in the stamp library sets the same before placing. Stamps made with 0.3.0 keep
  exactly their look. Undoable.
- **Edit a placed signature** by double-clicking it: a typed signature reopens with its name, style and
  ink; a drawn one can be drawn again; a picture can be replaced. Four more ink colors.
- **Exact page position** — **Insert Blank Pages…** (several at once), **Insert Pages from PDF…** and the
  new **Move Pages…** ask for before / after page N, the beginning or the end. Also on the thumbnails'
  right-click menu; undoable.
- **Several boxes at once** — drag a rectangle from empty paper, or Ctrl+click, to select form fields and
  text boxes; font, size, bold, italic, color and alignment then apply to all of them (one Undo step).
  Press in a field and drag to select some of its words.
- **Shape colors** — **Line** and **Fill** color buttons on the context toolbar for rectangles, ellipses,
  lines and arrows, with a palette of professional colors.
- **Two-sided printing** — **Print on both sides of paper** (flip on long edge by default, or short
  edge) when the printer supports it. **Actual size** and **All pages** are now the defaults.
- **Compress PDF ▸ Custom** — choose the picture resolution (100–600 ppi) and JPEG quality (40–95).
- **Page-design previews** (header / footer, watermark, background) are larger, page through the
  document, zoom (Fit page, Fit width, 100–400 %, Ctrl + mouse wheel, re-rendered sharp) and open in a
  resizable **Larger Preview…** window.
- The font list includes the fonts that come with Monograph PDF (Noto Sans, Noto Serif, Noto Sans CJK JP)
  next to the fonts installed on the PC.

### Fixed

- Zooming in on scanned pages stuttered and used much memory: at 400 % each page was drawn whole
  (about 110 ms and 57 MB per page). Large zooms now show a quick preview of the page and draw sharp
  tiles a few at a time. Measured on a 40-page scan: zoom to 400 % 835 → 131 ms, slowest scroll step
  144 → 33 ms; peak memory of the whole check 605 → 353 MB. Very long documents no longer keep every
  thumbnail in memory.

- A crash (AttributeError in the font list's row drawing) that could close the program; the font list
  now opens with one click and scrolls evenly.
- Dragging text boxes and pictures was slow (about 27 ms per frame on a large form); only the changed
  area is now redrawn, text layout and pictures are cached, and fonts are registered once (about 4 ms).
- Highlights and other comments now appear at once without the page flashing; **Undo** / **Redo** of
  comments now update the page and thumbnail (they did not before).
- The eraser removes everything it crosses in one pass (it needed three or four) and one Undo restores it.
- Sticky notes: shown as a clean speech bubble, the note text appears when pointing at or clicking it,
  and a double-click edits it.
- A field or text box just added can be typed into by double-clicking it (every field kind); the page
  text underneath is never edited by mistake.
- Pictures, text boxes, shapes and fields stay on the page while dragged, nudged or after rotating the
  page (they could end half outside it and not show in other apps or print).
- Number boxes were too narrow for their values (for example "100" showed as "00" in the watermark size).
- User Guide: the Contents links now scroll to their section.
- About / Check for Updates: "Updates not configured" is explained, with a button to the Releases page.
- **Protect ▸ View Permissions** lists allowed and not-allowed actions in plain words.
- Problem reports: a build without a reporting service no longer offers **Send to Developer** (it could
  only fail after showing "Sending…"); it offers **Copy Report**, **Open Issues Page** and **Close**
  instead. The program still sends nothing.
- Page background and color choices use a curated palette, and the color picker is no longer tinted by
  the button's own color.

## [0.3.0] — 2026-10-22

Feature release: new editing, comment, stamp, signature, OCR, conversion, printing and compression
tools, interface fixes for small screens and display scaling, and the groundwork for secure updates,
automatic in-place upgrades and private problem reports. It also contains the release-tooling and
maintenance work that had been prepared as 0.2.4, which was never released on its own.

**Disabled in this release:** update checks, automatic upgrades and the sending of problem reports
are built in but switched off. No production update-signing key and no reporting service exist yet,
so **Help ▸ Check for Updates…** reports "Updates not configured" and **Send to Developer** sends
nothing. New versions are published on the GitHub Releases page. Normal PDF work stays offline.

### Added

- **Secure update checks** (switched off in this release) — **Help ▸ Check for Updates…**, **File ▸ Settings… ▸ Updates**
  (automatic checks, off by default; interval; stable or prerelease channel; last successful check;
  Check Now; status) and the update status in **About**. Update information is a release manifest
  signed with Ed25519 and verified against keys built into the program; the download must match the
  signed size and SHA-256. Identity, channel, architecture, downgrade, expiry and replay checks; HTTPS
  with certificate verification and an allow-list of GitHub hosts, also for redirects. An unreachable
  server or unverifiable information is never reported as "up to date" ([docs/SECURE_UPDATES.md](docs/SECURE_UPDATES.md)).
- **Automatic in-place upgrade** (switched off in this release) — **Update Now** downloads and verifies the new Setup, lets you save
  or discard open changes, closes Monograph PDF and hands over to `MonographPDFUpdater.exe`, which
  waits for the program to exit, checks the installer again, runs the existing Setup silently for the
  same folder and install mode (keeping shortcuts, file-type choices and settings), verifies the
  installed version, deletes the downloaded installer and restarts the new version
  ([docs/AUTOMATIC_UPGRADE_AND_CLEANUP.md](docs/AUTOMATIC_UPGRADE_AND_CLEANUP.md)). Only the
  installation registered in Windows for the running copy is updated; ambiguous cases stop.
- **Update staging cleanup** with ownership markers, bounded retention for failed attempts, a size
  limit and no deletion outside the updater's own files.
- **Private problem reports** (sending switched off in this release) — unexpected errors, unhandled exceptions, Qt critical errors and
  unexpected termination produce a report of approved technical fields only (no documents, names,
  paths, user names or typed text), shown in full with exactly two buttons, **Don't Send** and
  **Send to Developer**; nothing is sent without that click. Sending is disabled until the reporting
  gateway is deployed. Reference gateway in `services/report_gateway` (GitHub App limited to
  issues in one private repository) ([docs/ERROR_REPORTING.md](docs/ERROR_REPORTING.md)).
- **International Windows compatibility** tests and documentation: Japanese, Chinese, Korean, German
  and French folder and file names, Unicode temporary and user folders, locale-independent versions
  and metadata ([docs/INTERNATIONAL_WINDOWS_COMPATIBILITY.md](docs/INTERNATIONAL_WINDOWS_COMPATIBILITY.md)).
- `scripts/packaging/update_manifest.py` (key generation outside the repository, manifest signing and
  verification), `scripts/test_update_e2e.py` (Windows end-to-end upgrade test with synthetic keys
  and a local HTTPS mock server).

### Added — PDF work

- **Editing**:
  - Replaced text no longer overlaps the original: the original glyphs are removed and the
    replacement keeps the span's font, size, colour, bold and italic.
  - The Inspector edits a text box's opacity, letter spacing and rotation, and a shape's opacity,
    rotation and dash style; all of these are saved as shown.
  - Shapes and pictures can be copied, pasted, duplicated, brought forward or sent back.
  - Inspector picture changes are undoable.
  - Save can be repeated without drawing objects twice.
- **Comments**:
  - Squiggly underline and opacity for markup.
  - A **Comments** panel (View ▸ Comments Panel) that lists, selects, edits, moves and deletes notes.
  - Every annotation change can be undone.
- **Stamps and signatures**:
  - A stamp library: ten standard stamps, custom text and picture stamps, rotation and opacity.
  - Stamps are real PDF stamp annotations.
  - Drawn, typed and picture signatures placed as movable objects.
- **Pages**: page operations (reorder, insert, delete, duplicate, replace, crop) are undoable, and the
  thumbnail right-click menu has them.
- **OCR**:
  - **OCR ▸ Recognize Text in Area…**, with a text preview that can be corrected, copied and saved as .txt or .docx.
  - **OCR ▸ Extract Text (OCR)…**.
  - **OCR ▸ Scanned PDF to Word (OCR)…**.
  - Optional language packs (Simplified and Traditional Chinese, Korean, vertical Japanese, German,
    French, Spanish), installed only from a file you supply that matches the pinned size and SHA-256.
    Nothing is downloaded.
- **Batch conversion** (Convert ▸ Batch Convert…): many files to Word, Excel, PowerPoint, text,
  images, searchable PDF, Word via OCR, or Office/images to PDF, with per-file status and Cancel.
- **Printing**:
  - True black-and-white (dithered) besides grayscale, custom scale, and 2/4/6/9 pages per sheet.
  - **Save as PDF** from the print dialog.
  - A multi-page preview.
  - Progress, Cancel and clear printer errors.
- **Viewing**:
  - Very large pages (A0 posters, high zoom) are drawn as sharp tiles with bounded memory.
  - Mixed page sizes are centred.
- **PDF to PowerPoint**: mixed-size policies (true size, fitted, first page's size, chosen slide
  size, one presentation per page size) and a picture quality choice.
- **PDF to Word**: one section per page at that page's size and orientation (both engines).
- **Document properties**: Word, PowerPoint and Excel files carry the PDF's title, author, subject,
  keywords and dates; the library template values are removed.
- **Unsaved changes**: a conversion or compression of a document with unsaved changes first asks
  **Save**, **Save As…** or **Cancel**.
- **Save a copy**: **File ▸ Save a Copy ▸ Whole Document (Keep Working on This One)…**.
- **Compress PDF** (replaces Reduce File Size):
  - Lossless, Balanced, Smallest file, or an exact maximum size (for example 956 KB or 1.99 MB;
    1 KB = 1,000 bytes).
  - A slider kept in step with the number, an estimate before and the measured size after.
  - A side-by-side preview and profiles.
  - Quality floors that keep text and scans readable.
  - An honest "cannot be achieved" with the smallest acceptable result.
  - See [docs/PDF_COMPRESSION.md](docs/PDF_COMPRESSION.md).
- **Documentation**:
  - [Converting PDF to Office](docs/PDF_TO_OFFICE_CONVERSION.md)
  - [Converting Office to PDF](docs/OFFICE_TO_PDF_CONVERSION.md)
  - [Conversion fidelity](docs/CONVERSION_FIDELITY.md)
  - [Save As and export](docs/SAVE_AS_AND_EXPORT.md)
  - [Rendering and page sizes](docs/PDF_RENDERING_AND_PAGE_SIZES.md)
  - [Colour and image fidelity](docs/COLOR_AND_IMAGE_FIDELITY.md)
  - [Printing and print preview](docs/PRINTING_AND_PRINT_PREVIEW.md)
  - [Save and export fidelity](docs/PDF_SAVE_AND_EXPORT_FIDELITY.md)
  - [Performance and rendering](docs/PERFORMANCE_AND_RENDERING.md)
  - [Windows runtime dependencies](docs/WINDOWS_RUNTIME_DEPENDENCIES.md)
  - [Prerequisite management](docs/PREREQUISITE_MANAGEMENT.md)
  - [Installer package contents](docs/INSTALLER_PACKAGE_CONTENTS.md)
  - [Clean Windows installation](docs/CLEAN_WINDOWS_INSTALLATION.md)

### Fixed

- OCR on a rotated page or a scan stored upside down placed the text layer upside down or in the
  wrong place; OCR read the file on disk instead of the document as shown (missing unsaved page
  changes); running OCR twice added a second text layer.
- Overwriting an existing file (Save As, Save a Copy, exports, Office to PDF) is now atomic: a failed
  write leaves the existing file untouched and no partial file behind. Office to PDF used to delete an
  existing PDF of the same name before converting.
- The Visual C++ runtime DLLs are placed beside the program so MuPDF and Qt plug-ins never depend on
  the order in which libraries happen to load; the program's PE timestamps are normalised to the
  commit time (reproducible builds).
- OCR failed when the temporary folder, the document's folder or the installation folder contained
  characters outside the Windows ANSI code page (for example a Japanese user name on an English
  Windows): Tesseract now receives no file path — the image goes through standard input, the result
  comes back on standard output and the language data is found by relative name.
- Interface at 1366 × 768 and smaller windows: the status bar no longer prints a message over the
  zoom value; the main toolbar shows Select, Text, Highlight and Eraser as icons only when the window
  is too narrow, so zoom, page navigation, search and the panel buttons stay visible; the Navigation
  panel tabs (including Comments) are no longer hidden behind scroll arrows; the start screen scrolls
  instead of clipping; the Compress PDF window fits the screen (settings beside the preview) and its
  preview shows the whole page; the Stamps window no longer cuts off "Make a white background
  transparent"; the font-size box on the context toolbar stays readable when the bar is crowded.
- The window could freeze in Fit Width or Fit Page on a document with both portrait and landscape
  pages (for example after rotating or inserting a page): the zoom was re-measured on whichever page
  was centred, which moved the pages and changed the centred page, endlessly. The fit is now measured
  on the page you last went to.
- At 150 % display scaling and in narrow panels: the Navigation panel's tabs could slide out of view and
  leave icon fragments at the panel's edge (labels now give way to icons; the panel is never narrower
  than its five tab icons); a status message shown before the window appeared ran over "No document";
  Fit Width / Fit Page centre the page in documents with wider pages instead of cutting it off at the
  right; the Properties panel keeps clear of its scroll bar and position/size values are no longer
  cut off; the Compress PDF page box and mode labels and the header/footer margin labels are no longer
  squeezed; check boxes in lists (OCR languages) follow the theme; the highlight colour swatch is pale
  while there is no document; "Opened … (1 page)" instead of "(1 pages)"; a light line / fragment along
  the top of the Navigation panel tabs (dark theme) is gone; page thumbnails fill a widened Navigation
  panel (an empty grey strip was left beside them); the toolbar overflow button (») now shows
  an arrow — it was blank, so tools moved into it could not be found; the Comments panel keeps its tools
  at the top when the document has no comments.
- The Split PDF window enables only the fields the chosen split method uses; Draw a Signature no longer
  makes Undo Stroke the Enter-key button.
- Compress PDF: choosing Lossless, Balanced, Smallest or Target size now also updates the profile
  list, so the two never disagree.

### Changed

- Start screen: twelve tools in two rows, adding PDF to PowerPoint and Compress PDF.
- Clearer tooltips for PDF to PowerPoint, Callout, Stamp, Save a Copy, Check for Updates and About.

- The release build keeps Python's own `ssl` module (HTTPS for update checks and approved reports);
  Qt's network and TLS modules are still removed. Exactly two modules may use the network
  (`core/updates/net.py`, `core/diagnostics/client.py`), checked by the security tests.
- Setup installs `MonographPDFUpdater.exe`; uninstalling removes the user's update and
  problem-report folders.
- `verify_release.py --layout` fails if the bundled update or reporting configuration differs from
  the repository's.

### Changed — release tooling and maintenance

Prepared as maintenance version 0.2.4 (never released); these changes are part of 0.3.0 and do not
change the application.

- `scripts/vendor_ocr.ps1` repaired: it now prepares only the pinned OCR engine — Tesseract 5.4.0.20240606 (Windows x64) and the `eng`, `jpn` and `osd` data of tessdata_fast 4.1.0 — through `scripts/ci/stage_ocr_engine.py`, and refuses anything whose SHA-256 differs from `scripts/ci/ocr_engine_pins.json`. It used to install the newest Tesseract through winget and download the language data from a moving branch without any integrity check.
- The release build checks `engines\ocr` and `models\tessdata` against those pins before packaging and stops on any difference, including unpinned extra files.
- OCR staging copies the project's own `TESSERACT_NOTICE.txt` and checks it against the pins (CI used to write a placeholder in its place); the language data comes from the tessdata_fast tag 4.1.0 instead of the `main` branch; `--require` turns a refused engine into a failure.
- Source archive: `CONTRIBUTING.md` and `.gitattributes` are included, and the build instructions in `README_SOURCE.md` describe the pinned OCR workflow. When built from a git checkout, the archive is made from the committed files and their committed bytes, so an untracked local file or an uncommitted edit can never be published (a local development build had picked up an untracked copy of the OCR notice), and uncommitted changes to selected files stop the build unless `--allow-dirty` is given. The archive is now reproducible: the same commit gives the same ZIP bytes whatever the checkout's line-ending setting (fixed entry order, dates, attributes and compression). `LICENSES/AGPL-3.0.txt` is now the official license text (`LICENSE`) instead of `LICENSE.md`. New tests check the required documents and license texts, the files linked from the README, the exclusion of internal audit records and private paths, unique portable entry names, and the SHA-256 of every third-party source file.
- `scripts/setup_env.ps1` creates the environment with Python 3.11, the version releases bundle (it used to take any `python` on the PATH first), and stops when creating the environment or installing the requirements fails (it used to report success); a failed pip self-upgrade (for example offline) is only a warning.
- `scripts/test_installer.ps1`: the upgrade sections now install a Setup built fresh from the current build as the next patch version; they used to reuse a cached Setup hard-coded as 0.2.1 and built from an old payload, so they did not test an upgrade of the build under test.
- `scripts/test_installer.ps1` refuses to run inside an app package, where `%APPDATA%` is virtualised and a settings backup and restore can see a different folder from the one the installer changes; it checks every restored settings file by SHA-256 and keeps an earlier run's backup instead of deleting it.
- `engines/ocr/MANIFEST.json` no longer records a local build folder.
- Documentation: clearer privacy, installation, security and license wording, contribution templates, and a clarification of the published 0.2.3 release notes (source downloads, SmartScreen guidance); the 0.2.3 release files were not changed.

### Removed

- `scripts/prepare_windows_release.ps1` and its helpers `scripts/validate_release_smoke.py` and `scripts/write_runtime_manifest.py`: unused and superseded by `installer\build_release.bat`. The script bumped `VERSION` by itself, staged an unofficial build and stopped on harmless standard-error output.

## [0.2.3] — 2026-10-21

Release reliability, security verification, automated testing on GitHub Actions and refreshed documentation; no new features.

### Added

- Release-note validation (`scripts/packaging/validate_release_notes.py`): fails on unresolved template values, missing or wrong SHA-256 values, missing test or installer results, other-version names, broken links, inconsistent dates and broken Markdown.
- Release-set verification (`scripts/packaging/verify_release.py`), run by every release build: artifact names, `SHA256SUMS.txt`, ZIP entry names, required notices, version consistency inside the release's own source, privacy scan of both ZIPs, OCR components; with `--notes`, the release notes.
- Release notes kept in the repository (`docs/releases/`), release checklist (`docs/RELEASE_CHECKLIST.md`), code-signing plan (`docs/CODE_SIGNING.md`) and a Windows CI workflow.
- Release builds record exact test counts (passed / failed / skipped) in `build_release_summary.txt`.
- Test categories (portable, Windows, GUI, external application, OCR, private fixture, security, golden) with a per-category PASS / FAIL / NOT VERIFIED summary after every run; skipped tests are never counted as passed.
- Windows CI (`.github/workflows/windows-ci.yml`) on every push and pull request: pinned dependencies, release-note validation, unit / integration / UI tests offscreen, and OCR tests with an engine used only when every file is SHA-256 identical to the one the release ships (`scripts/ci/stage_ocr_engine.py`).
- Byte-level tests for password protection (nothing readable without the password, chosen cipher, no earlier revisions) and further Remove Hidden Information tests (incremental-save history, page and image XMP, XFA, thumbnails).
- README rewritten for the public repository; new screenshots of page thumbnails, header and footer, password protection and Remove Hidden Information.

### Fixed

- The first published 0.2.2 release notes showed template placeholders instead of the checksums and results; the notes were not checked before publishing. Corrected notes: `docs/releases/v0.2.2.md`.
- `MonographPDF_x.y.z_Installer.zip` was written with `\` in entry names (Windows PowerShell's `Compress-Archive`), which other unzip tools turn into odd file names; it is now written with standard `/` names, in a fixed order.
- Remove Hidden Information missed some actions: an open action that opens a web address, launches a program or submits a form (only JavaScript open actions were removed), document and page automatic actions (`AA`) were not counted, and JavaScript in bookmarks was neither counted nor removed. All are now counted and removed with scripts; plain "open at page" actions, bookmarks and web-link bookmarks are kept.
- Tests on a fresh checkout: the generated sample PDFs are created before test collection (one test module read them at import time).
- `scripts/run_tests.ps1` stopped the whole test run when a test wrote anything to standard error (Windows PowerShell treats it as an error); the result now comes from pytest's exit code.
- Navigation panel: tabs no longer hide behind scroll arrows at normal widths (the current tab keeps its label, the others show icons); the scroll buttons were drawn as white boxes in the dark theme.

## [0.2.2] — 2026-10-21

First public release of Monograph PDF. Version 0.2.1 was a release candidate that was never published; its changes are included here.

### Added

- Bookmark editing in the Navigation panel: add (**Insert ▸ Bookmark for This Page…**, Ctrl+B), rename (F2), point at the current page, move up/down and delete (with the bookmarks under it); undoable and saved with the document. The Bookmarks tab is always available.
- **Protect ▸ Remove Hidden Information…**: shows what a document carries besides its visible pages — properties and XMP metadata, attached files, scripts and automatic actions, page thumbnails, private application data, comments, form fields, links, bookmarks and invisible (OCR) text — and saves a copy without the kinds you choose. The copy is re-checked and the result reported; the open document is not changed; protected files must be unlocked first.
- Bates numbers in **Insert ▸ Header, Footer & Page Numbers…** (`{bates}`: prefix, first number, digits, suffix).
- Print: odd or even pages only, reverse order, and printing the document without its comments (form fields still print).
- **Protect with Password**: offline strength rating while typing, and a warning when the permissions password is the same as the open password.
- **Edit ▸ Copy Page as Picture** (Ctrl+Alt+C).
- Icons for every menu command (new ones drawn for this release) and a menu/toolbar inventory check (`scripts/audit/ui_control_inventory.py`).

- Continuous Highlight tool (click toolbar to toggle on/off; Esc cancels an unfinished stroke, Esc again exits): pen over text marks characters; over blank/image/table/scan saves a free-area highlight; mixed strokes undo as one. Colour menu changes only future strokes. Works on rotated pages and CropBox.
- Eraser tool (toolbar / **Insert ▸ Eraser**, `Shift+E`): click a highlight or ink annotation to remove it; stays active for consecutive removals; undo/redo restores colour and geometry. Does not erase original page content.
- Template PDFs (`tests/fixtures/templates`) and `scripts/check_pdfs.py` for Downloads-folder PDF checks from temporary copies.
- Page design: header and footer in six positions (left/center/right) with `{page}`, `{total}` and `{date}`, number style and place, first page number, date style, text size and color, margins; text or picture watermark with position and in-front/behind placement; **Insert ▸ Background…** (color and/or picture); live preview and remembered settings in each dialog.
- Marks added by Monograph PDF are tagged (optional-content layer + private key) so **Replace** and **Insert ▸ Remove Header, Footer, Watermark or Background…** affect only them.
- **Protect ▸ Mark Whole Pages for Redaction…**; after applying text redactions, the saved file is checked for the same text in comments, form values, bookmarks, properties and attachments, with an option to remove it there too.

### Fixed

- Menus: 20 groups of items shared the same Alt-letter (for example Insert ▸ Highlight Text and Header, Footer & Page Numbers, or Protect ▸ Apply Redactions and Remove Metadata), so the letter did not reach the second item. Every item in a menu now has its own letter.
- 25 menu commands had no icon (Background, Remove page design, Align right/top/bottom, Find next/previous, table row/column commands and others).
- File pickers for Insert PDF Pages, Replace Page, images, signatures, Merge and watermark/background pictures opened in the program's working folder; they now open in the document's folder, and Merge / Images to PDF suggest saving next to the source files.
- Redaction: form fields, annotations and links overlapping a redaction mark were kept — a form field showing the redacted text stayed visible and stored in the file. They are now removed with the mark.
- Watermark, header/footer and page numbers were placed in unrotated page coordinates: on pages turned 90°/180°/270° they ran sideways or upside down, sat on the wrong edge, or fell off the page. They are now drawn upright on the page as displayed.
- Form-field appearance: a failure while drawing a custom appearance could leave a temporary extra page in the saved PDF; the temporary page is now always removed.
- Merge / Combine dropped every bookmark of the combined files. Bookmarks are now carried over and point to the right pages; bookmarks to pages left out are skipped. Combining password-protected files now says that the result is not protected.
- Images to PDF copied each JPEG byte for byte, including its EXIF block (GPS position, camera, date). Photo metadata is now left out; the picture data stays unchanged and the orientation is kept as page rotation.
- Setup for one user did not find an earlier unregistered installation of that user in a custom folder when Monograph PDF was also installed for all users; it now does, and upgrades it in place.
- Installed copies no longer write a drag-timing log on every object move, keep at most 20 startup-timing files, and no longer use a doubled `logs\logs` folder.
- Text/form editors: Ctrl+Z / Ctrl+Y undo typing and paste while open; leaving still records one document undo step.
- Highlight Text: pen + toolbar color; underline/strikethrough undoable; only touched characters; empty space marks nothing.
- Page rotation layout/coords for text, search, forms, overlays; undoable; signed docs ask first.
- PDF to PowerPoint: PDF page size for slides; **Layout-preserving** and **Editable text** modes.
- Generic fonts no longer resolve to Windows “Sans Serif Collection” (clipped text boxes).
- Added images keep aspect ratio; save-over wait ~4.5 s; rotate re-analyses one page; Excel tables detect outlined cells and write numbers as numbers.
- Build no longer packs OpenSSL from PATH; font subset embedding when license allows; font list shows current face correctly.
- Docs: no unmeasured fidelity claims; OCR / Excel / PowerPoint limits in the User Guide.

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
- Release-candidate audit: `reports/audit/SECURITY_AUDIT_0.2.0.md` (no blocker; the MEDIUM dependency finding, Pillow 11.1.0, is fixed by upgrading to Pillow 12.3.0).
- Pillow 12.3.0. Placing and saving a picture reads only PNG, JPEG, BMP, GIF, TIFF and WEBP files, so Pillow's rarely used decoders (PSD, FITS, JPEG 2000, …) are never run on a user-supplied file.
- A printer whose name contains a quotation mark is never passed to the printer-preferences command line.

### Testing

- Unit, UI, integration and installer tests, a packaged-application smoke test, a release-content check and a branding scan; see `docs/TESTING.md`.
- Security audit of the release candidate: `reports/audit/SECURITY_AUDIT_0.2.0.md`.

## Internal development history

Versions before 0.2.0 were internal development builds and were not public releases. Their entries are kept below as the development record; they describe the product under its earlier internal name, and nothing in them is a published release.

### Internal compatibility notes for 0.2.x

These describe technical behaviour kept so that a machine that still has an earlier **internal** development build continues to work cleanly. They are not user-facing migration instructions, and they do not describe a prior public product.

#### Product identity

- Public product: Monograph PDF; executable `MonographPDF.exe`; branding and icons from `resources/icons/source/Monograph_PDF_logo.png`.
- Release files: `MonographPDF_<version>_Setup.exe`, `MonographPDF_<version>_Installer.zip`, `MonographPDF_<version>_Source.zip` (source folder `monograph-pdf/`); `SHA256SUMS.txt` lists `MonographPDF.exe`.
- Default folders `C:\Program Files\Monograph PDF` / `%LOCALAPPDATA%\Programs\Monograph PDF`; data in `%APPDATA%\Monograph PDF` and `%LOCALAPPDATA%\Monograph PDF`.
- Windows registration uses `MonographPDF.exe`, ProgIDs `MonographPDF.Document` / `MonographPDF.Convertible`; Setup never makes itself the default PDF app.
- License: AGPL-3.0-or-later; bundled components keep their own licenses.

#### Compatibility with earlier internal builds (≤ 0.1.5)

Earlier internal builds used a different application name and executable. Setup keeps the same Windows AppId so such an install is recognised and replaced (one *Installed apps* entry). This is internal-development continuity only — not a public-product migration.

- Folder / registration cleanup after a validated install; unknown files in an old folder are kept; an unregistered second copy elsewhere is left untouched.
- First-start may copy preferences, existing recent files and version-1 recovery sessions from earlier internal AppData folders (cache/logs/temp are not). Uninstall cleans those folders only with proven provenance.
- `MONOGRAPH_PDF_*` overrides; deprecated aliases from earlier internal builds remain during 0.2.x.
- Last internal freeze archived under `releases\PDFEditor_0.1.5\` (not a public release; never modify).

#### Installer (upgrade groundwork from the last internal series)

- Owned-file cleanup via `installed_files.txt` (or a conservative allowlist); destination never wiped wholesale; settings and documents kept on upgrade.
- Same-folder upgrade is automatic; a different folder offers keep-existing (recommended) or move-after-validation; silent Setup keeps the registered path unless `/MIGRATEINSTALL`.
- Setup refuses to continue while the installed program (or an earlier internal executable still running) cannot be replaced.

### [0.1.5] — 2026-10-15

A full audit of every menu (File, Edit, View, Insert, Forms, Organize, Convert, OCR, Protect, Sign, Help) and the toolbar, alone and in combination, and a security, privacy, dependency and installer audit.

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
