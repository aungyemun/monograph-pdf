# Monograph PDF — Phase 1 Critical Reliability Audit (2026-11-04)

> Public copy of the Phase 1 / 1.1 / 1.2 reliability audit report. Local paths, the test computer's hardware details and the names of private documents are generalised; findings, test counts and checksums are unchanged.


Local audit. Nothing was pushed, merged, tagged, signed or published; no version number, signing key or
update-signing configuration was changed; the installed application (`C:\Program Files\Monograph PDF`,
0.5.1) was not touched; real user documents were only read (one copied to a temporary folder, hash
checked unchanged). **All changes are uncommitted** on the local branch `audit/phase1-reliability`.

## A. Environment

| Item | Value |
| :--- | :--- |
| Operating system | Windows 11 (64-bit), `LongPathsEnabled=1` |
| Linux (second platform) | Ubuntu 24.04.5 LTS cloud container, headless (`QT_QPA_PLATFORM=offscreen`), Python 3.11.18 |
| Repository | local clone of github.com/aungyemun/monograph-pdf |
| Branch / base commit | `audit/phase1-reliability` at `909ea8e` (= local `fix/ui-perf-audit`, 1 commit ahead of `main` `2e3cb3a`, not pushed) |
| Versions | Windows 0.5.1, Linux 0.1.1, macOS 0.1.1 (`versions/*.txt`; unchanged) |
| Python / key libraries | 3.11.9; PySide6 6.8.1.1; PyMuPDF 1.25.3 (MuPDF 1.25.4); pytest 8.3.4, pytest-qt 4.4.0, pytest-timeout 2.4.0 |
| Dev-environment changes | Installed into `env` at the pinned versions of `requirements*.txt`: truststore 0.10.5, pytest-timeout 2.4.0, cryptography 50.0.1 (+ cffi 2.1.1, pycparser 3.11) |
| Independent validators | Separate venv in a temporary folder (not the app's `env`): pypdf 5.1.0, pikepdf 9.4.2 (**qpdf 11.9.1** check), cryptography 43.0.3, Pillow 11.0.0. Poppler, mutool, Ghostscript, qpdf CLI: **not installed — not used**. Adobe Acrobat/Reader: **not run** (see §E). |
| Test environment | All runs in isolated temporary folders (settings, runtime, updates, diagnostics); synthetic fixtures; processes owned by `scripts/run_isolated.py` Job Objects |

## B. Findings

| ID | Sev. | Feature | Status |
| :--- | :--- | :--- | :--- |
| F-01 | **P0** | Save over the open file while it stays locked | **Fixed** |
| F-02 | **P1** | Exports overwriting an existing file (disk full / interrupted write) | **Fixed** |
| F-03 | P2 | Save error message on a full disk | **Fixed** |
| F-04 | P2 | Apply Redaction ignored the PDF's "no changes" permission | **Fixed** |
| F-05 | P1 (gap) | Selecting and copying page text | **Not implemented** in the product (reported, not added: no new features in Phase 1) |
| F-06 | P3 | Permissions: saving comments needs the "edit" permission | Reported (over-restrictive, safe) |
| F-07 | P3 | Memory while saving over the open file (F-01 fix) | Reported |
| F-08 | P3 | Deep UI audit harness: access violation inside its forced `os._exit` | Reported (harness only; pre-existing) |

### F-01 (P0) — A failed Save silently discarded annotations and page changes
* **Reproduce:** open a PDF, add an underline, rotate page 1, keep the file open in another program
  (antivirus scan, viewer) for more than ~4.5 s, press Save.
* **Expected:** the save fails with an explanation; every change stays in the window.
* **Actual:** the message said *"Your changes are still here"*, but the window had reopened the
  unchanged file from disk: the rotation and the underline were gone. Closing the window then raised
  `DocumentError: Document is closed` (the tab still referenced the closed document).
* **Root cause:** `_bake_to` closed the whole document to release the file before `os.replace`; on a
  failed replace it reopened the file from disk. Changes stored in the document itself (annotations,
  page operations, form values written to widgets) exist only in memory and were lost; edit-model
  overlays (text boxes) survived, which is why the existing test passed.
* **Fix (ui/main_window.py):** `_detach_document_from_file()` moves the live document into memory with
  the existing undo snapshot functions (`snapshot_bytes`/`restore_bytes`: object numbers and password
  protection unchanged) and closes only the file-backed MuPDF document; a failed replace keeps
  everything. The last-resort reopen path now also updates the tab's session record.
* **Tests:** `tests/ui/test_save_retry.py::test_a_lock_that_stays_keeps_annotations_and_page_changes_too`
  (real Windows file lock; failed before the fix: rotation 0 instead of 90). Updated
  `tests/ui/test_pro_ui.py::test_save_releases_open_file_before_replacing_it`: it checked the internal
  `_closed` flag; it now checks that the file-backed MuPDF document is closed before the replace (same
  intent: the file is not held open).

### F-02 (P1) — A failed export write destroyed the existing destination file
* **Reproduce (error injection):** every `fitz.Document.save` to a file writes part of a file, then fails
  with `ENOSPC`. Apply Redaction / Remove Hidden Information / Protect onto an existing PDF.
* **Expected:** the existing file unchanged, no partial file. **Actual:** the existing file was replaced
  by a truncated PDF. (Save, Save As, Save a Copy and Compress were already atomic.)
* **Root cause:** eight writers called `doc.save(destination)` directly.
* **Fix:** new `core/safe_write.py` (`save_pdf_atomic`: temporary file in the same folder, `fsync`,
  `os.replace`, temporary file removed on failure), used by `core/redaction/ops.py`,
  `core/security/sanitize.py`, `core/security/ops.py` (protect, remove password), `core/security/protection.py`
  (`save_copy`, used by several exports), `core/organize/page_ops.py` (extract pages),
  `core/convert/images_to_pdf.py`, `engines/mupdf_backend.py` (`save_as`). `engines/bake_edits.py` (the
  main save) now also `fsync`s its temporary file before swapping it in.
* **Tests:** `tests/unit/test_safe_write.py` — 19 tests (failure keeps the existing file / leaves no new
  file / success replaces, for each writer). **13 failed before the fix, 19 pass after.**
* **Limitation:** `os.replace` gives the new file the folder's default permissions and replaces a
  symbolic or hard link with a regular file (as the main Save already did).

### F-03 (P2) — Save showed Python's error text and an internal file name on a full disk
* **Actual:** `OSError: [Errno 28] No space left on device: '…/.df.saving-51387ac2.pdf'`;
  Save As / Save a Copy already said "There is not enough free space on the drive to save …".
* **Fix:** Save reports file-system errors of the write step through `explain_save_error`
  (`ui/main_window.py`); the "file still open in another program" case keeps its own message
  (`core/save_errors.FileStillInUse`).
* **Test:** `tests/ui/test_save_disk_full.py` (message, file unchanged, no temporary file, edits kept,
  the next Save succeeds).

### F-04 (P2) — Apply Redaction wrote a changed copy of a PDF that forbids changes
* Every other content-changing command checks the "edit" permission (or asks for the permissions
  password); Apply Redaction did not. **Fix:** the same `_allow("edit", …)` check.
* **Test:** `tests/ui/test_redaction_permissions.py` (restricted → nothing written; permitted → written);
  failed before the fix, passes after.

### F-05 (P1, product gap) — No selection and copying of page text
Ctrl+C copies edit objects (text boxes, shapes); there is no command to select page text with the mouse
and copy it, so word/line/paragraph/Select-All selection, reading-order copy and selection of Japanese
text (Phase 1 §4) **cannot be audited — the feature does not exist**. Adding it is new functionality
(excluded from Phase 1). Text *markup* placement, which uses the same coordinate mapping, was audited
(16/16 pass, see §C).

### F-06 / F-07 / F-08 (P3)
* **F-06:** saving any change needs the "edit" permission, so in a PDF that allows comments but not
  changes, comments can be added but not saved. Safe (never bypasses a restriction), over-restrictive.
* **F-07:** to keep every change if the replace fails, Save over the open file briefly holds a second
  in-memory copy of the document (peak private memory ~+930 MB while saving a 414 MB file in the
  measurement process). Fine on the test PC; a concern only for very large files on low-memory PCs.
  *Phase 1.1 correction:* this attribution was wrong — the peak comes from the pre-existing bake copy
  (922 MB before vs 926 MB after the F-01 fix at 399 MB); see §L.
* **F-08:** `scripts/deep_ui_audit.py` ends with `os._exit` while offscreen; Windows reports an access
  violation during process teardown after all 432 checks passed. Identical before and after these
  changes; the application's own exit path (`app.exec()` → normal shutdown) exited cleanly 3/3 with a
  449 MB PDF open.

## C. Test results

### Full suite
| Platform | Result |
| :--- | :--- |
| **Windows 11** (this PC, offscreen Qt) | 2,210 test items: **2,194 passed, 0 failed, 0 errors, 16 skipped** (18 skip records incl. 2 module-level). After installing `cryptography`, the 6 cryptography skips were re-run: **57 passed, 1 skipped** (opt-in live-network check). |
| **Linux** (Ubuntu 24.04 container, headless, same command as `linux-ci.yml`) | **2,052 passed, 4 failed, 104 skipped** (21 min). The 4 failures were environmental, caused by how the tree was copied from Windows: `installer/linux/install.sh` arrived with CRLF line endings (2 tests), and there was no `.git` folder for the source-archive tests (2). After converting to LF, installing `rsync` (present on the GitHub Ubuntu runners) and initialising a throw-away repository, those two files pass **36/36**. |
| **macOS** | **NOT TESTED** (no macOS machine available) |

Skipped on Windows (environment, not failures): Linux/macOS-only tests (8), no local test build (1),
no printer installed (1), inactive-window keyboard focus (1), opt-in live network (1), cryptography (6;
re-run after installing, above). Baseline before the audit (same PC, morning): 12 failures, all
resolved — 10 in local-only tests (outdated expectations, updated and passing), 2 from the
missing `truststore` package.

### Targeted P0 scenarios (real `MainWindow`, synthetic fixtures; `p1_scenarios.py` → `p1_check.py`)
15 scenarios, 16 output files, checked **only** with pypdf + qpdf (pikepdf). Final run on the fixed code:
**15/15 scenarios pass; 15/16 outputs pass every independent check**, the 16th (`encrypted_saved.pdf`)
every check except pypdf text extraction (fixture font, §D).

| Scenario | Result |
| :--- | :--- |
| Fill text (Japanese), multiline, checkbox, radio, dropdown, list box, clear a pre-filled field → Save over the open file → reopen | Pass: values in pypdf; cleared field has no stale appearance text; radio state persisted; dirty flag clean |
| Save As then Save a Copy | Pass: window moves to the Save As file; Save a Copy leaves the document modified; source unchanged |
| Undo / Redo of field entries, then Save | Pass |
| Highlight, underline, strike-out, squiggly, sticky note, rectangle + rotate a page → Save | Pass: annotation types, rotation, 5 bookmarks and links kept |
| AES-256 PDF (user+owner password): fill + text box → Save | Pass: still AES-256 (R6, V5, AESV3); wrong password rejected by qpdf; pypdf decrypts with the password and reads the field value. The text box's text could **not** be extracted independently: pypdf's extraction stops at the fixture's own embedded CJK font (see §D) |
| Redaction of text (also under an invisible OCR-style layer) | Pass: text absent from extracted text and from every content stream; copies in the document title and in a comment are reported to the user (residue dialog), not silently left |
| Area redaction over a picture | Pass: no original (red) pixels left in the redacted area of the image |
| Remove Hidden Information (all options) | Pass: no Info properties, XMP, attachments, JavaScript / OpenAction, annotations or invisible text; visible text kept |
| Malformed PDF (broken `startxref`) → edit → Save As | Pass (repaired; qpdf clean) |
| Japanese / Unicode path; 324-character path | Pass (long path works with `LongPathsEnabled=1`; not tested without it) |
| Save As onto a read-only file | Pass: clear message, target unchanged, edits kept |
| Disk full during Save, Save As, Save a Copy (existing and new targets) | Pass |
| Disk full during Remove Hidden Information / Protect / Apply Redaction onto an existing file | **Fail before the fix (F-02)**, pass after (`test_safe_write.py` and the final scenario run) |
| Close with unsaved changes → Cancel, then → Save | Pass |
| Japanese text box → Save As | Pass (text extracted by pypdf) |

Additional new regression tests: `tests/ui/test_markup_geometry.py` — a real Highlight drag lands on the
dragged word (IoU > 0.6, no spill onto neighbours) at zoom 0.5 / 1 / 2 / 3 × page rotation 0 / 90 /
180 / 270: **16/16 pass**.

### Deep UI audit (`scripts/deep_ui_audit.py`)
36 steps, **432 checks, 0 failed** (every menu item and toolbar control, dialogs filled and accepted,
combination flows). Its 43 output PDFs were then checked independently: **43/43 pass qpdf's structural
check and open in pypdf**; the 3 protected outputs are AES-256 (R6/V5).

## D. File integrity and compatibility

* Independent structural validation (qpdf 11.9.1): 43 deep-audit outputs + 16 scenario outputs, **no
  problems**.
* pypdf semantic checks: as in §C. One observation: PDFs whose *embedded CJK font* was written by
  PyMuPDF's `insert_font` (my synthetic fixture) carry a `ToUnicode` CMap with 5-digit hex codes for
  characters outside the Basic Multilingual Plane; qpdf accepts it, pypdf's text extraction raises
  "Odd-length string". The app preserves such fonts unchanged; the app's own Japanese text boxes are not
  affected (pypdf extracts them).
* Hybrid AcroForm/XFA (previously reported problem, on a temporary copy of a real hybrid form supplied by the maintainer (not included)):
  after fill + Save, the values are in **both** the AcroForm fields (pypdf) and the XFA `datasets`
  packet (what Acrobat shows); qpdf clean; the original's hash unchanged.
* **Not tested:** Adobe Acrobat / Reader and other GUI viewers (not run); Poppler (not installed).

## E. Cross-platform status

| Platform | Status |
| :--- | :--- |
| Windows 11 | **Tested** (full suite, deep UI audit, scenarios, performance, real file locks) |
| Linux | **Tested headless only** (Ubuntu 24.04 container, offscreen Qt): no display server, no printing, no native dialogs, no desktop integration — those remain NOT TESTED |
| macOS | **NOT TESTED** |

## F. Performance (Windows, real window, synthetic documents)

| Actual size / pages | Open | First page | Save | Save a Copy | Lossless compress |
| :--- | :--- | :--- | :--- | :--- | :--- |
| < 1 MB / 60 | 0.07 s | 0.14 s | 0.06 s | 0.17 s | 0.04 s |
| 42 MB / 30 | 0.06 s | 0.13 s | 0.41 s | 0.18 s | 2.0 s |
| 49 MB / 35 | 0.04 s | 0.10 s | 0.51 s | 0.21 s | 3.2 s |
| 99 MB / 71 | 0.04 s | 0.09 s | 0.81 s | 0.41 s | 7.3 s |
| 414 MB / 357 | 0.08 s | 0.13 s | 3.6 s | 2.0 s | not run |

Startup to window 1.06 s; OCR of 2 scanned pages 3.5 s (280 words, searchable). Search of all pages
≤ 0.1 s (414 MB). Scrolling (from the same day's UI audit, commit `909ea8e`): worst freeze while dragging
the scroll bar through picture-heavy PDFs 167–273 ms → 37–74 ms, none over 100 ms; closing a large
document releases MuPDF's cache (460 → 213 MB). The documents' sizes overshoot the targets at the small
end; memory figures of the measurement process include its own image generation (baseline 827 MB), so
only differences are meaningful.

## G. Remaining risks (document safety)

1. **Acrobat interoperability not verified by running Acrobat** (forms, annotations, XFA) — verify on
   the release PC before publishing.
2. **macOS untested; Linux untested with a real display, printing and dialogs.**
3. **No page-text selection/copy feature (F-05)** — a user expectation for a PDF editor; not a data risk.
4. Power-loss safety now relies on `fsync` + `os.replace`; not tested by actually cutting power.
   *Phase 1.1 correction:* the main Save path did not flush at all (F-09, now fixed), and `fsync` +
   `os.replace` does not guarantee survival of a power loss (§K, durability).
5. Long paths were tested only with Windows long-path support enabled.
6. `.gitattributes` does not force LF for `*.sh`: a Windows checkout gets a CRLF `install.sh` that bash
   rejects (found by the Linux run). Recommendation: add `*.sh text eol=lf` (not changed here).
7. Existing-text replacement, object rotation/resizing, copy/paste of annotations, stamps, visual
   signatures: covered by the existing suite and the deep UI audit (all passing) but **not re-audited
   independently** in this phase.

## H. Release assessment

**CONDITIONAL GO** for the next Windows maintenance release: every confirmed P0/P1 defect is fixed with
failing-first regression tests, the full Windows suite and the deep UI audit pass, and every output
tested is valid in qpdf and pypdf. Conditions: (1) your own real-Windows install/upgrade tests, (2) a
manual check of saved forms, annotations and an XFA form in Adobe Acrobat Reader, (3) review and commit
of this uncommitted work. **NO-GO for macOS** (not tested) and for any claim of a page-text selection
feature.

## I. Reproducing the audit

Harness (copied to `scripts/audit/phase1/`): `p1_scenarios.py` (scenarios, app `env`),
`p1_check.py` and `validate_pdfs.py` (independent checks; run with a separate venv holding pypdf,
pikepdf, cryptography, Pillow).

```
$env:MPDF_ROOT = (Get-Location).Path            # repository root
env\Scripts\python.exe -u -I scripts\audit\phase1\p1_scenarios.py <out>
<validators>\python.exe -I scripts\audit\phase1\p1_check.py <out>
<validators>\python.exe -I scripts\audit\phase1\validate_pdfs.py <folder> --json report.json
```

## J. Git status at the end of the audit

* Branch `audit/phase1-reliability`, HEAD `909ea8e7964c8d6abb861735920aee9636dc89ee` (no new commit;
  `fix/ui-perf-audit` and this branch exist only on this PC).
* **Working tree not clean — uncommitted audit changes, for review:**
  * Modified (12 files, +133 / −20): `core/convert/images_to_pdf.py`, `core/organize/page_ops.py`,
    `core/redaction/ops.py`, `core/save_errors.py`, `core/security/ops.py`, `core/security/protection.py`,
    `core/security/sanitize.py`, `engines/bake_edits.py`, `engines/mupdf_backend.py`, `ui/main_window.py`,
    `tests/ui/test_pro_ui.py`, `tests/ui/test_save_retry.py`.
  * New: `core/safe_write.py`, `tests/unit/test_safe_write.py`, `tests/ui/test_save_disk_full.py`,
    `tests/ui/test_redaction_permissions.py`, `tests/ui/test_markup_geometry.py`, `scripts/audit/phase1/`
    (`p1_scenarios.py`, `p1_check.py`, `validate_pdfs.py`).
  * This report: `reports/audit/` is ignored by `.gitignore` (`/reports/audit/*`); add it with
    `git add -f` if it should be kept in the repository.
* Not tracked, local only: audit scratch output in `tests/outputs/audit_baseline/` (excluded through
  `.git/info/exclude`), untracked local-only tests in `tests/integration/` (git-ignored; two
  outdated expectations updated on 2026-11-04 earlier in the day).
* No push, merge, tag, release, signing or history rewrite was performed.

---

# Phase 1.1 — Final Reliability Verification (2026-11-04)

Scope: verify F-01…F-08 before Phase 2; no new features, no version change, nothing committed,
pushed, merged, tagged, signed or installed. Sections A–J above are the original Phase 1 record and
are kept unchanged except for two marked *Phase 1.1 correction* notes (F-07, §G item 4). New findings
continue the numbering (F-09…F-16).

## K. Verification of F-01 … F-08

| Finding | Verification in Phase 1.1 | Status |
| :--- | :--- | :--- |
| F-01 failed Save kept changes | Re-read `_bake_to` / `_detach_document_from_file`: the open document is detached from the file (re-opened from an in-memory snapshot that keeps object numbers and encryption) before the swap; the snapshot replaces the session's document too. Sequences tested: failed Save (lock held through all retries) → successful Save keeps annotations, rotated/moved pages and form values (`test_save_retry.py`, 2 tests); repeated Saves (`test_save_sequences.py`) | **Confirmed fixed** |
| F-02 export writers atomic | `save_pdf_atomic` used by all 8 writers; disk-full injection for each writer onto existing and new files; successful write replaces completely; no temporary file left (`test_safe_write.py`) | **Confirmed fixed**; two gaps found in the same area → F-09, F-10 (fixed) |
| F-03 disk-full message | `test_save_disk_full.py`: plain message, no internal `.part` name, edits kept | **Confirmed fixed** |
| F-04 redaction needs "edit" permission | `test_redaction_permissions.py` | **Confirmed fixed** |
| F-05 text selection/copy | Investigated, §M | **Open — P1 product gap** |
| F-06 annotate-only PDFs cannot be saved | Unchanged (safe, over-restrictive) | Open, P3 |
| F-07 Save memory | Measured, §L. The Phase 1 attribution to the F-01 fix was **wrong** | Re-classified, P3 |
| F-08 audit-script teardown crash | Unchanged, test harness only | Open, P3 |

### Save sequences requested in Phase 1.1 (all on Windows, real `MainWindow`, offscreen)

| # | Sequence | Evidence | Result |
| :--- | :--- | :--- | :--- |
| 1 | Failed Save → successful Save | `test_save_retry.py::…keeps_annotations_and_page_changes_too`, `test_save_disk_full.py` | Pass |
| 2 | Repeated Saves (form value, checkbox, highlight, rotation, text box across 3 Saves) | `test_save_sequences.py::test_repeated_saves_accumulate_every_kind_of_change` (text box written once, not duplicated) | Pass |
| 3 | Save As onto an existing file | `…save_as_onto_an_existing_file_replaces_it_completely` (old pages gone, source hash unchanged) | Pass |
| 4–6 | Save after rotation / annotations / form edits | sequences test + scenario `annotations_page_ops_save`, `forms_fill_save_over_open_file` (independent pypdf/qpdf checks) | Pass |
| 7 | Save after OCR (searchable PDF, then edit + Save) | `…ocr_searchable_pdf_keeps_its_text_layer…` (Windows, bundled engine) | Pass on Windows; **skipped on Linux** (no bundled OCR engine) |
| 8 | Save after a failed replacement | `test_save_retry.py` (lock held through all retries, then released) | Pass |
| 9 | Interrupted writing | disk-full injection part-way through every writer and Save/Save As/Save a Copy; folder as destination | Pass: destination unchanged, no partial or temporary file |
| 10 | Original preserved | hashes of source / existing destination compared in every failure test | Pass |

### Safe-write helper review

* **Temporary names:** `.{stem}.{uuid4[:8]}.part` in the destination folder (same volume, so
  `os.replace` is a rename). Collision probability negligible; unrelated `.part` files are never
  touched (tested).
* **Leaks:** removed on every exception including `KeyboardInterrupt` (`BaseException`). Not removed
  if the process is killed or the power fails mid-write — see F-13.
* **Races:** (a) `bake_edits` decides "existing file → temporary + replace" vs "new file → direct
  write" with `final.exists()`; a file created by another program in between would be overwritten
  directly (TOCTOU, practically only with two programs saving the same name at the same instant).
  (b) Two Monograph windows saving the same file: last writer wins (pre-existing, no cross-process
  lock). Neither is introduced by Phase 1.
* **Permissions:** three regressions/defects found and handled: F-10 and F-12 (read-only files
  replaced on Linux/macOS; misleading message on Windows) — fixed; F-11 (attributes/ACL of the
  replaced file are not preserved) — documented, not fixed.
* **Durability (NTFS, C: and D: on this PC):** the new file's data is flushed with `os.fsync`
  (`FlushFileBuffers`) before the swap. The swap is `os.replace` → `MoveFileExW(MOVEFILE_REPLACE_EXISTING)`
  **without** `MOVEFILE_WRITE_THROUGH`; NTFS journals the rename (after a crash the name points to the
  old or the new file, not a mixture), but the rename may not yet be on disk when Save returns, and
  disk write caches without power-loss protection can reorder writes. On Linux the folder is not
  fsynced. **Flushing the temporary file therefore does not guarantee that a Save survives a sudden
  power loss**; it only narrows the window in which a partial file could appear. Not tested by cutting
  power. The `flush_to_disk` docstring was corrected accordingly (it previously overstated this).

### New findings from the verification

* **F-09 (P2, fixed) — Save swapped an unflushed file over the open document.** `flush_to_disk` ran
  only when `bake_edits` replaced an existing file itself. Save over the open file bakes to a *new*
  temporary file and `main_window` swaps it in, so the most common save path never flushed; the
  redaction residue clean-up (`Remove These Too`) had the same gap. Fix: `bake_edits` flushes every
  file it writes; the residue clean-up flushes before `os.replace`. Test:
  `test_save_sequences.py::test_save_flushes_the_new_file_before_it_replaces_the_original` — **failed
  with the old `bake_edits` (verified by temporarily restoring it), passes with the fix**.
* **F-10 (P2, fixed) — On Linux/macOS, writing through a temporary file replaced read-only files.**
  POSIX `rename` checks only the folder's permissions. For the 8 export writers this was introduced
  by F-02 (writing in place had refused); for Save As onto an existing file (`bake_edits`) it was
  pre-existing. Found by the clean Linux run (`test_safe_write_refuses_a_read_only_destination…`
  failed: DID NOT RAISE). Fix: `safe_write.refuse_read_only` (checks the read-only attribute / mode
  bits, so it holds for root too) in `save_pdf_atomic` and `bake_edits`. Test:
  `test_safe_write.py::test_a_read_only_destination_is_refused_on_every_platform` (7 cases).
* **F-11 (P3, documented, not fixed) — replacing a file drops its Hidden attribute and explicit ACL
  entries.** Measured on NTFS: Hidden → Archive; an explicit `BUILTIN\Users:(R)` entry is lost; the
  new file inherits the folder's permissions. Same for the pre-existing main Save path. Preserving
  them needs `ReplaceFileW` (Windows) / copying mode and ownership (POSIX) — a design change, left for
  review.
* **F-12 (P2, fixed) — Save over the open file after it became read-only.** Reproduced before the fix:
  Linux — the read-only file was **replaced and became writable (0644)** with no message; Windows —
  not replaced, changes kept, but after 4.8 s of retries reported as "open in another program". Fix:
  `_bake_to` refuses a read-only destination before writing (message now names "read-only", changes
  kept, no retries). Test: `test_save_sequences.py::test_save_never_replaces_the_open_file_once_it_is_read_only`.
* **F-13 (P3) — temporary files after a crash.** A killed process or power cut mid-write leaves
  `.name.xxxxxxxx.part` / `.name.saving-xxxxxxxx.pdf` beside the document; nothing removes them later.
  The destination itself is intact.
* **F-14 (P3)** — see §L (second Save after a failed Save has a higher peak).
* **F-15 (P3, documentation)** — `docs/USER_GUIDE.md` (OCR section) says "open the copy to search or
  select its text"; selecting page text is not possible in Monograph PDF (§M).
* **F-16 (P3, repository)** — see §N (executable bits, CRLF files in the index).

## L. Save memory analysis (Task 3)

Method: fresh process per measurement on Windows; private bytes (`PagefileUsage` /
`PeakPagefileUsage` via psapi) before Save, peak during Save, after Save; synthetic documents
(a temporary folder): text 400 pages (0.2 MB), 50 / 150 / 400 photos (48.9 / 149.4 / 399.3 MB).
"Legacy" = the pre-F-01 behaviour (close and reopen the file), "current" = F-01 (detach to an
in-memory snapshot).

| Document | Peak legacy → current (MB) | After Save (MB) | After **failed** Save (MB) | Failed → successful Save: peak / after (MB) |
| :--- | :--- | :--- | :--- | :--- |
| text, 400 p, 0.2 MB | 126 → 126 | — | — | — |
| 50 photos, 49 MB | 218 → 223 | 133 | 198 | — |
| 150 photos, 149 MB | 427 → 431 | — | 300 | 611 / 156 |
| 400 photos, 399 MB | 922 → 926 | — | 552 | 1,358 / 162 |

* **Cause of the ~930 MB peak:** the pre-existing bake (`engines/bake_edits._working_copy`:
  `tobytes(garbage=0, deflate=False)` + `fitz.open` of that copy) — roughly 2.3 × the file size.
  The F-01 fix adds **≤ 5 MB** to the peak (922 → 926 MB at 400 MB). *The Phase 1 report's F-07
  attribution to F-01 was wrong.* Save time at 400 MB: 2.2 s → 3.6 s (the snapshot copy).
* **Proportional and temporary:** peak scales with file size; memory returns to the baseline after a
  successful Save.
* **Retained:** after a *failed* Save the in-memory snapshot is kept on purpose (it holds the unsaved
  changes): +65 MB (49 MB file) to +390 MB (399 MB file), released by the next successful Save or by
  closing the document.
* **F-14 (P3):** the Save that follows a failed Save peaks higher (1,358 MB for 399 MB) because the
  bake copies the in-memory document. Acceptable on the test PC; relevant for very large files on
  low-memory PCs.
* **Repeated Saves:** about +8 MB per Save, independent of document size (MuPDF caches; not a leak
  proportional to content).
* **Lower-memory alternatives explored:** (1) skipping the snapshot when the document is unchanged on
  disk — rejected: MuPDF's `is_dirty` is unreliable (True after form entry + render, stays True after
  undo), so it cannot prove there is nothing to lose; (2) snapshot only after the swap fails — not
  possible on Windows (the file must be released *before* the swap); (3) reducing the bake copy
  (`_working_copy`) — the real 2.3 × source, but it changes how every Save is written, which needs
  its own regression campaign. **No memory optimization was implemented**; none could be proven
  correct within this task.

## M. F-05 investigation — selecting and copying page text (Task 2)

Checked in code, tests and the user guide (no changes made):

| Question | Answer |
| :--- | :--- |
| Feature exists but is inaccessible? | **No.** There is no text-selection code path anywhere in `ui/`, `core/` or `engines/`. |
| UI actions disconnected? | **No.** Edit ▸ Copy (Ctrl+C) is connected to `_copy` → `EditableDocument.clipboard_copy()`, which copies the selected *edit objects* (text boxes, shapes, pictures) into an internal list (`_object_clipboard`); it never writes the system clipboard. Working as designed. |
| Text-selection mode missing? | **Yes.** `EditTool` has `SELECT` (objects), text box, image, shapes, form and layout tools — no text-select tool. |
| Selection coordinates incorrect? | Not applicable. The word-geometry building block it would use (`_text_line_rects`, words from `page.get_text("words")`, display ↔ page mapping incl. rotation) is what text markup uses, verified in Phase 1 (16/16 zoom × rotation cases). |
| Copy incomplete? | Not applicable. |
| Tests? | None for page-text selection/copy (none can exist). |

Existing ways to get page text today: **Convert ▸ PDF → Plain Text…** (whole document to a .txt),
**OCR ▸ Extract Text (OCR)…** / **Recognize Text in Area…** (dialog with Copy, OCR results only),
**Edit ▸ Copy Page as Picture** (image only).

**Classification: P1 usability gap (missing feature), not a defect.** Not implemented, as instructed.

### Implementation proposal (for separate authorization)

1. **Tool:** a *Select Text* tool (`EditTool.TEXT_SELECT`, toolbar + shortcut, cursor I-beam); the
   existing Select tool unchanged.
2. **Selection model:** per page, words from `page.get_text("words", sort=False)` with block/line/word
   numbers; drag selects from the anchor word to the word under the cursor in reading order
   (block → line → word), across pages; double-click = word, triple-click = line; Ctrl+A within the
   tool = page text. CJK: words without spaces are joined without inserting spaces (use the
   `rawdict` character boxes for character-level selection in CJK lines).
3. **Display:** translucent selection rectangles drawn by the canvas (never written into the PDF),
   updated with zoom/rotation through the existing mapping.
4. **Copy:** Ctrl+C / context menu *Copy* puts plain text on `QClipboard` (line breaks between
   lines, blank line between blocks); respects the PDF "copy/extract" permission through the existing
   `_allow("copy", …)`; nothing copied from redaction-marked areas.
5. **Tests:** unit — reading order, CJK joining, rotated pages; UI — drag at zoom 0.5/1/2/3 ×
   rotation 0/90/180/270 (as `test_markup_geometry.py`), double/triple click, cross-page drag,
   clipboard content, permission refusal, no change to the document (hash unchanged, not dirty).
6. **Effort / risk:** moderate (estimate several hundred lines plus tests); isolated from saving —
   read-only on the document.

## N. Linux verification (Task 4) — clean Git-based checkout

Method: on Windows, `git bundle create … audit/phase1-reliability` (no change to the user's refs or
index) plus `git diff HEAD --binary` of the uncommitted changes and a tar of the untracked files;
in the Linux container: `git clone` from the bundle, `git apply`, untracked files extracted and
converted CRLF → LF (what a commit with `core.autocrlf=true` stores). Environment: Ubuntu 24.04
container, Python 3.11.18, PyMuPDF 1.25.3, PySide6 6.8.1.1, `QT_QPA_PLATFORM=offscreen`, isolated
`MONOGRAPH_PDF_*` folders and `HOME`, running as root.

**Line endings and permissions (clean checkout):** 599 text files LF in index and working tree;
**6 Python files are stored with CRLF in the index** (`scripts/packaging/archive_safety.py`,
`msys2_corresponding_source.py`, `refresh_msys2_sources.py`, `tests/unit/test_archive_safety.py`,
`test_msys2_corresponding_source.py`, `test_stage_ocr_engine_linux.py`) — harmless for Python;
every `*.sh` is LF. Executable in git: `build_app.sh`, `build_linux.sh`, `package_linux.sh`,
`package_macos.sh`, `vendor_ocr_macos.sh`, `ci/commit-msg`; **not** executable: `installer/linux/install.sh`
(documented as `bash install.sh`; `build_linux.sh` sets 0755 when packaging), `dev_launch.sh`,
`run_tests.sh`, `setup_env.sh`, `vendor_ocr.sh` (F-16, P3). The new `core/safe_write.py` has CRLF in
the Windows working tree; it is normalised to LF on commit (autocrlf) — confirmed by the round trip.
The Phase 1 CRLF `install.sh` failures came from copying the Windows working tree, not from the
repository.

**Results** (`pytest tests/unit tests/integration tests/ui`, same selection as `linux-ci.yml`):

| Run | Result |
| :--- | :--- |
| 1 (Phase 1 code + F-09) | 2,060 passed, **2 failed**, 105 skipped (23 min 18 s) |
| — failure 1 `test_organize.py::test_temp_dirs_not_project_root` | **Environmental** — my isolation folder was named `RUNTIME_DIR`; the test expects "runtime" in the path. Passes with a lower-case folder name (same failure on Windows with the same naming). |
| — failure 2 `test_save_sequences.py::test_safe_write_refuses_a_read_only_destination…` | **Genuine defect** → F-10, fixed |
| **Final (all Phase 1.1 fixes, fresh clone)** | **2,175 items: 2,070 passed, 0 failed, 105 skipped** (23 min 21 s) |

Skips on Linux (environment): Windows-only behaviour (file sharing/locks, read-only attribute, registry
fonts, certificate store, update staging), no bundled OCR engine (`engines/ocr`), no Office/LibreOffice,
no printer, macOS-only tests, opt-in live network, no Downloads PDFs.

**Not equivalent to native desktop testing:** no display server or window manager, no native file
dialogs, printing, clipboard integration with other programs, desktop integration (`.desktop`,
icons, MIME), packaging/installation, HiDPI or input methods.

## O. External compatibility — Adobe Acrobat Reader (Task 5)

**NOT TESTED.** Acrobat is installed on this PC but was not opened, so its settings and recent-files
list stay untouched. A synthetic test pack (22 PDFs produced by the app on the fixed code: 15/15
scenarios pass; existing-text edit; hybrid AcroForm/XFA form) and a checklist were prepared:
`tests/outputs/audit_baseline/acrobat_pack_2026-11-04/ACROBAT_READER_CHECKLIST.md` (local, git-excluded).
Checklist rows: text editing, annotations (4 markup types, note, rectangle), checkbox, radio buttons,
text fields (incl. Japanese, multi-line, cleared, read-only), dropdown and list box, XFA (hybrid),
page rotation, AES-256 password, redacted text and picture, hidden-information removal, Japanese
fonts, re-saved damaged input. Independent pre-checks: 16/16 scenario outputs qpdf-clean, 15/16 pass
every pypdf check (`encrypted_saved.pdf`: pypdf cannot extract the fixture font, as in Phase 1);
`text_edited.pdf` qpdf-clean, edited text present and original gone; `xfa_hybrid_filled.pdf`
qpdf-clean, value and checkbox present in the XFA `datasets`. No personal or research PDF used.

## P. Exact test counts (Phase 1.1)

| Run | Result |
| :--- | :--- |
| Windows, full suite (`pytest tests`, final code, Python 3.11.9 `env`) | 2,262 items: **2,249 passed, 0 failed, 0 errors, 13 skipped** (20 min 44 s). Skips: macOS-only 5, Linux-only 4, no printer 1, inactive-window focus 1, no local test build 1, opt-in live network 1. The runner's stderr contained a bare `Traceback (most recent call last):` line with no failing test (pytest exit 0); its source was not identified. An earlier full run in this phase showed 1 failure, `test_temp_dirs_not_project_root` — environmental (isolation folder named `RUNTIME_DIR`), gone with lower-case folder names. |
| Windows, targeted save/safe-write/permission tests after F-12 | 56 passed, 0 failed |
| Windows, scenarios (`p1_scenarios.py`, after F-09) | 15/15 pass; independent checks 15/16 outputs all checks, 16/16 qpdf-clean |
| Linux clean checkout, final (`tests/unit tests/integration tests/ui`) | 2,175 items: **2,070 passed, 0 failed, 105 skipped** |
| F-09 test with the old code | failed (as expected), passes with the fix |
| F-12 probe with the old code | Linux: replaced (bug); Windows: misleading "in another program" after 4.8 s |
| macOS | NOT TESTED |
| Acrobat Reader | NOT TESTED |
| Installed application / installer / upgrade | NOT TESTED (not run on this production PC by rule) |

New regression tests in Phase 1.1: `tests/ui/test_save_sequences.py` (8 tests: 6 sequences, F-09
flush order, F-12 read-only open file) and 7 cases in `tests/unit/test_safe_write.py` (F-10). All
Phase 1 tests remain.

## Q. Updated risk classification

| ID | Severity | Status |
| :--- | :--- | :--- |
| F-01, F-02 | P0 / P1 | Fixed, verified |
| F-03, F-04 | P2 | Fixed, verified |
| **F-05** | **P1 (product gap)** | **Open** — proposal §M |
| F-09, F-10, F-12 | P2 | Fixed in Phase 1.1, regression tests |
| F-06, F-08, F-11, F-13, F-14, F-15, F-16, F-07 | P3 | Open, documented |

**Remaining P0: none known. Remaining P1: F-05 (missing feature, no data risk).** Verification gaps
(not defects): Acrobat Reader, installed-application/upgrade tests, native Linux desktop, macOS,
power-loss behaviour.

## R. Cross-platform limitations

* Windows 11: full suite, scenarios and probes — offscreen Qt (no visible window except Phase 1's
  real-window performance runs); NTFS only (no network share, FAT/exFAT or removable drive tested).
* Linux: headless container only (see §N); root user, so permission tests rely on mode bits.
* macOS: not tested; POSIX rename semantics (F-10, F-12) apply there too and are covered only by the
  Linux run.
* Long paths: only with `LongPathsEnabled=1`.

## S. Proposed next actions

1. Review and commit the Phase 1/1.1 changes (suggested split: F-01/F-03; F-02 + F-10 safe write;
   F-04; F-09 + F-12; tests; audit harness) — without AI attribution.
2. Run the Acrobat Reader checklist (§O) on the release PC.
3. Installed-application and upgrade tests on a non-production Windows PC.
4. Decide on F-05 (authorize the §M proposal) and correct the user-guide sentence (F-15).
5. Decide on F-11 (preserve attributes/ACL with `ReplaceFileW`) and F-13 (clean up stale temporary
   files when a document is opened).
6. Optional: `*.sh text eol=lf` in `.gitattributes` and executable bits for the four scripts (F-16);
   reduce the bake copy's memory (§L) with its own regression campaign.
7. Linux desktop session and macOS runs before claiming those platforms.

## T. Updated release assessment

**CONDITIONAL GO — Windows maintenance release only.**
Evidence: all confirmed P0/P1 *defects* are fixed with failing-first regression tests (F-01, F-02)
and verified again in Phase 1.1; three additional P2 defects found during verification (F-09, F-10,
F-12) are fixed with tests that failed or reproduced the defect before the fix; full Windows suite
2,249 passed / 0 failed; clean Linux checkout 2,070 passed / 0 failed (headless); every scenario output is structurally valid in qpdf.
Conditions (an unconditional GO is not possible while these are open): (1) the Acrobat Reader
checklist passes; (2) installed-application/upgrade tests pass on a non-production PC; (3) the
uncommitted changes are reviewed and committed. F-05 must not be advertised as a feature.
**NO-GO** for macOS and for a Linux release claim beyond headless tests.

## U. Repository status at the end of Phase 1.1

* Branch `audit/phase1-reliability`, HEAD `909ea8e7964c8d6abb861735920aee9636dc89ee` — **nothing
  committed** in Phase 1 or 1.1; no stash; no push, merge, tag, release, signing, version change or
  history rewrite; `.gitignore` not modified.
* Modified (12 files, +146 / −20 against HEAD): `core/convert/images_to_pdf.py`, `core/organize/page_ops.py`,
  `core/redaction/ops.py`, `core/save_errors.py`, `core/security/ops.py`, `core/security/protection.py`,
  `core/security/sanitize.py`, `engines/bake_edits.py` (+F-09, F-10), `engines/mupdf_backend.py`,
  `ui/main_window.py` (+F-09, F-12), `tests/ui/test_pro_ui.py`, `tests/ui/test_save_retry.py`.
* Untracked: `core/safe_write.py` (+F-10, docstring correction), `scripts/audit/phase1/` (3 files),
  `tests/ui/test_markup_geometry.py`, `tests/ui/test_redaction_permissions.py`,
  `tests/ui/test_save_disk_full.py`, `tests/ui/test_save_sequences.py` (new in 1.1),
  `tests/unit/test_safe_write.py` (+7 cases in 1.1).
* Remaining failures: **none** on Windows or Linux in the final runs.
* Local only (excluded through `.git/info/exclude`): `tests/outputs/audit_baseline/` — memory
  scripts and results (`mem_*.py`, `mem/*.json`), probes (`f12_probe.py`, `attr_probe.ps1`, …), the
  Linux transfer bundles (`linux_xfer*/`), the Acrobat pack.

### Tracking this report without adding unrelated audit artifacts

`/reports/audit/*` is ignored, which is why the report does not appear in `git status`. Options,
none applied:
1. **`git add -f reports/audit/PHASE1_RELIABILITY_AUDIT_2026-11-04.md`** — adds exactly this one
   file; the ignore rule stays and keeps other audit output out. Check with
   `git status --short` / `git diff --cached --name-only` that only this path is staged.
2. Copy it to a tracked folder (e.g. `docs/audit/`) and add it there — keeps `reports/` purely local.
3. A negation rule (`!/reports/audit/PHASE1_*.md`) in `.gitignore` — changes `.gitignore`, so not
   recommended unless audit reports should be tracked routinely.
When committing, add the files above path by path rather than with `git add -A` / `git add .`, so
nothing unintended is picked up.

---

# Phase 1.2 — Windows Release-Candidate Preparation and Compatibility Validation (2026-11-04)

Statuses: **PASS**, **FAIL**, **NOT TESTED**, **BLOCKED**. Sections A–U above are unchanged.

## V. Executive summary

The source on `audit/phase1-reliability` (uncommitted) passes the full Windows suite
(2,262 items: 2,249 passed, 0 failed, 13 skipped) and the independent PDF checks. An unsigned Windows release-candidate Setup was built
outside the repository from that exact source; its built-in smoke test passes. The release pipeline
itself correctly **refuses** to finish a release from uncommitted source (provenance check), so the
candidate is a test build, not a releasable artifact. Acrobat Reader compatibility and every
installer test remain **NOT TESTED** (they need the separate test PC). Two documentation sentences
that implied page-text selection were corrected. **Release decision: CONDITIONAL GO.**

## W. Review of the working-tree changes (Task 1)

Reviewed: the complete `git diff HEAD` (12 tracked files before Phase 1.2, now 15 with the three
documentation files) and all 7 untracked paths.

| Fix | Review result | Status |
| :--- | :--- | :--- |
| F-01 failed Save keeps changes | `_detach_document_from_file` snapshots the live document into memory (object numbers and encryption kept) and closes the file-backed MuPDF document; after a successful swap the window reloads the saved file (fresh edit model), after a failed swap it keeps the in-memory document. Extra probe (Linux, offscreen): after a failed Save, scrolling, rendering all 30 pages, adding an underline and a second (successful) Save all work; highlight, underline and text box are all in the file | PASS |
| F-02 atomic writing | 8 writers call `save_pdf_atomic`; temporary file in the same folder, flushed, `os.replace`, removed on any exception | PASS |
| F-03 disk-full message | `save_document` reports `OSError` through `explain_save_error`; `FileStillInUse` keeps its own text | PASS |
| F-04 redaction permission | `_allow("edit", …)` before Apply Redaction | PASS |
| F-09 flush before replace | `bake_edits` flushes every file it writes; residue clean-up flushes before `os.replace` | PASS |
| F-10 read-only destination | `refuse_read_only` in `save_pdf_atomic` and `bake_edits` (mode bits / read-only attribute) | PASS |
| F-12 read-only open file | `refuse_read_only(dest)` in `_bake_to` before anything is written or detached | PASS |

Dependencies: only the Python standard library (`os`, `uuid`, `errno`); no new package, no change to
`requirements*.txt`. Unintended changes: none found (the only test edits are the intent-preserving
update of `test_save_releases_open_file_before_replacing_it` and new tests).

Observations (not defects, recorded for review):
* `MuPdfBackend.save_as(path)` onto **its own open file**: before, MuPDF refused ("save to original
  must be incremental"); now it writes a complete copy through a temporary file. On Linux/macOS the
  file is replaced (contents identical to the open document); on Windows `os.replace` is refused
  while the file is open. The UI's Save does not use this path. Risk: low.
* `refuse_read_only` uses the private helper `core.save_errors._read_only` (internal coupling).
* `_detach_document_from_file` closes the old MuPDF document although `restore_bytes`' docstring says
  a view may still hold it; the probe above and the full suites found no use after close.

## X. Final Windows source regression (Task 5)

| Check | Result | Status |
| :--- | :--- | :--- |
| Full suite `pytest tests` (Python 3.11.9 `env`, offscreen, isolated profile folders) | 2,262 items: **2,249 passed, 0 failed, 0 errors, 13 skipped** (22 min 21 s; JUnit: tests=2262 failures=0 errors=0 skipped=13). Skips: macOS-only 5, Linux-only 4, no printer 1, inactive-window focus 1, no local test build 1, opt-in live network 1. Stderr: one `socketserver` traceback from a local test HTTP server whose client disconnected (the origin of the bare `Traceback` line noted in §P); no failing test | PASS |
| Safe-writing (`test_safe_write.py`), save retry (`test_save_retry.py`), disk full, save sequences, read-only, redaction permissions | included in the full run, all passed | PASS |
| Form / annotation persistence, encryption (AES-256), redaction, Unicode file names, document integrity | full run + scenarios (`p1_scenarios.py`): 15/15 scenarios pass | PASS |
| Independent validation (qpdf 11.9.1 via pikepdf, pypdf 5.1.0; never PyMuPDF) | 16 scenario outputs: qpdf finds no problems in any (the AES-256 one opened with its password); all pypdf checks pass in 15/16 — `encrypted_saved.pdf`: pypdf cannot extract text with the fixture's embedded CJK font (known since Phase 1, §D). `validate_pdfs.py` over all 20 files: 19 clean, 1 = the same encrypted file (needs its password) | PASS |
| Excluded or deselected tests | none (`-o addopts=` and the whole `tests` folder) | — |

## Y. Acrobat Reader compatibility (Task 2)

**All 19 checks: NOT TESTED.** Adobe Acrobat (64-bit) 26.001.21662 is installed on the development
PC but was not opened: opening files writes Acrobat's recent-files list and can trigger first-run,
sign-in, default-app or update prompts, i.e. it changes Acrobat's user data, which this phase must
not do; no GUI automation was attempted. qpdf/pypdf results are **not** counted as Acrobat results.
Prepared: `tests/outputs/audit_baseline/acrobat_pack_2026-11-04/ACROBAT_READER_CHECKLIST.md`
(rows 1–19 exactly as the Phase 1.2 list, files, steps, expected results, how to avoid saving from
Acrobat; run on the separate test PC).

## Z. Windows release-candidate build (Task 3)

| Item | Value |
| :--- | :--- |
| Location (outside the repository) | a folder outside the repository (`src\` = `git archive HEAD` + copies of every modified/untracked file + vendored OCR files; `env` and `packages` are directory junctions to the repository's development environment and third-party source cache) |
| Command | `scripts\build_release.ps1 -SkipTests` (tests run separately, §X), signing provider `none`, isolated `MONOGRAPH_PDF_*` folders, `SOURCE_DATE_EPOCH` = commit time of `909ea8e`, `MONOGRAPH_PDF_BUILD_COMMIT` = `909ea8e…+uncommitted-phase1.2-rc` |
| Environment | Windows 11, Python 3.11.9, PyInstaller (from `env`), Inno Setup 6 (`%LOCALAPPDATA%\Programs\Inno Setup 6`), .NET Framework `csc` |
| `src\installer\MonographPDF_0.5.1_Setup.exe` | 129,552,989 bytes, SHA-256 `e54445346f4afc3eb540f330316c4ea64eb0b7438a752b806ec8162625b751f4`, **NotSigned**, ProductVersion 0.5.1 |
| `src\installer\MonographPDF_0.5.1_Installer.zip` | 129,203,149 bytes, SHA-256 `91a6f62833f21f827fa0e4448d01f3cb43d2fc3011b445f7f54c0b8c10e75aaa` |
| `src\installer\MonographPDF_0.5.1_Source.zip` | 297,914,009 bytes, SHA-256 `fc63ddf1e8bc5d7eb241735a3a13d60943751ee35eca6b90eace12a45d380686` (contains `core/safe_write.py` with F-10 and the corrected User Guide) |
| Frozen app contains the fixes | `pyi-archive_viewer`: `core.safe_write`, `core.save_errors` in the bundle — PASS |
| Built-in smoke test (`--smoke-test`, own temporary settings) | create, render, protect/unlock, PDF→Word, OCR, Office detection, main window, imports, **no network**: all ok — PASS |
| Release contents / branding / metadata checks | PASS |
| Release-set verification (`verify_release.py`) | **FAIL — provenance**: the application does not record a real source commit; update manifest NOT VERIFIED (not signed — by design); release notes NOT VERIFIED |
| Overall | Setup.exe produced for testing — **PASS (test build)**; releasable RC — **BLOCKED**: the pipeline only finishes a release built from a commit (no commit was authorised). First attempt stopped because `build_exe.ps1` treats `git`'s error in a folder without `.git` as fatal under PowerShell's `Stop` preference; the documented environment variables were then used |
| Production safety | the installed application (0.5.1, `MonographPDF.exe` dated 2026-11-02) unchanged; nothing installed, no registry or file-association change, no signing, nothing published. Side effect: PyInstaller's normal per-user cache under `%LOCALAPPDATA%\pyinstaller` |
| Version caveat | the candidate is 0.5.1, the same number as the installed 0.5.1: on a PC with 0.5.1, its Setup is a same-version reinstall, and the updater does not offer it |

## AA. Separate-PC installer checklist (Task 4)

`reports/audit/PHASE1_2_INSTALLER_TEST_CHECKLIST_2026-11-04.md` — clean install (per-user,
all-users), upgrade from the published release, same-version reinstall, launch, opening, Save /
Save As incl. each fix (F-01 lock, F-12 read-only open file, F-10 read-only target, F-03/F-02 full
drive, F-04 permissions), forms and annotations, OCR, conversion, printing, Unicode paths, file
associations, uninstallation, settings preservation, recovery from failed/cancelled installs.
**Every item NOT TESTED.** It complements `docs/WINDOWS_RELEASE_TEST_CHECKLIST.md` (A1–A8, C).
The public releases page showed **0.4.0** as *Latest* when checked during this audit; "upgrade from
published 0.5.1" is therefore not possible as stated — use the newest published Windows release.

## AB. Documentation corrections (Task 6)

| File | Before | After | Status |
| :--- | :--- | :--- | :--- |
| `docs/USER_GUIDE.md` (OCR) | "open the copy to search or select its text" | "open the copy to search its text. Selecting and copying page text with the mouse is not available in Monograph PDF yet — … use Convert ▸ PDF to Text…, OCR ▸ Extract Text (OCR)… (with Copy), or another PDF reader" | PASS |
| `docs/FEATURES.md` (Editing) | — (no statement; Ctrl+C behaviour undocumented) | new line: page-text selection **not available yet**; Edit ▸ Copy copies text boxes, shapes, pictures; how to get page text out | PASS |
| `docs/WINDOWS_RELEASE_TEST_CHECKLIST.md` A4.4 | "copy the text out" | "… (in another PDF reader — Monograph PDF does not select page text)" | PASS |

Checked without change: README, CHANGELOG entries (they describe selection *inside* text boxes and
fields, which exists), OCR dialog texts ("copied" = the OCR result dialog), Compress dialog
("copyable" = property of the PDF in other readers). F-05 is not advertised anywhere else found.

## AC. Proposed commit plan (Task 7) — not executed

Order matters (B uses helpers from A). Each command adds explicit paths only; no `git add .` /
`-A`; no AI trailers; the user's own identity; no history rewrite.

| # | Commit (suggested subject) | Files |
| :--- | :--- | :--- |
| A | Write exported PDFs atomically and refuse read-only destinations | `core/safe_write.py` `core/convert/images_to_pdf.py` `core/organize/page_ops.py` `core/redaction/ops.py` `core/security/ops.py` `core/security/protection.py` `core/security/sanitize.py` `engines/mupdf_backend.py` `engines/bake_edits.py` `tests/unit/test_safe_write.py` |
| B | Keep unsaved changes when Save fails; plain save errors; redaction permission; flush and read-only checks on Save | `ui/main_window.py` `core/save_errors.py` `tests/ui/test_save_retry.py` `tests/ui/test_pro_ui.py` `tests/ui/test_save_disk_full.py` `tests/ui/test_redaction_permissions.py` `tests/ui/test_save_sequences.py` `tests/ui/test_markup_geometry.py` |
| C | Docs: page-text selection is not available yet | `docs/USER_GUIDE.md` `docs/FEATURES.md` `docs/WINDOWS_RELEASE_TEST_CHECKLIST.md` |
| D (optional) | Phase 1 reliability audit harness | `scripts/audit/phase1/p1_scenarios.py` `scripts/audit/phase1/p1_check.py` `scripts/audit/phase1/validate_pdfs.py` |

```
git add -- core/safe_write.py core/convert/images_to_pdf.py core/organize/page_ops.py core/redaction/ops.py core/security/ops.py core/security/protection.py core/security/sanitize.py engines/mupdf_backend.py engines/bake_edits.py tests/unit/test_safe_write.py
git diff --cached --name-only        # check: exactly these 10 paths
git commit                           # message without any AI attribution
```
(likewise for B, C, D). Before committing, `scripts/ci/check_commit_trailers.py` (used by
`.github/workflows/commit-message-check.yml`) can check the messages. A is self-contained (its tests use only A and existing code); B needs A. A CHANGELOG /
release-notes entry is still needed before any release (version work, not done here).

**Audit report:** this is the public copy of the report; the full local report (with local paths, the test computer's details and the names of private documents) is kept outside the repository.

## AD. Remaining issues and risks

| ID | Issue | Severity | Status |
| :--- | :--- | :--- | :--- |
| F-05 | No selection/copy of existing page text (proposal §M) | P1 product gap | open — documented, not advertised |
| — | Acrobat Reader compatibility | verification gap | NOT TESTED |
| — | Installer: clean install, upgrade, uninstall, associations, recovery | verification gap | NOT TESTED |
| — | Releasable RC (signed manifest, provenance from a commit, release notes) | release gap | BLOCKED until the changes are committed and the release is prepared |
| — | Same version number 0.5.1 as the installed build | release/process | needs a decision |
| F-11, F-13, F-14, F-06, F-08, F-16 | attributes/ACL not kept on replace; stale temp files after a crash; peak memory after a failed Save; annotate-only PDFs; audit-script teardown; repo exec bits | P3 | open |
| — | `build_exe.ps1` without `.git` fails under PowerShell `Stop` unless `MONOGRAPH_PDF_BUILD_COMMIT` is set | P3 (build) | open |
| — | Power-loss durability not tested; macOS not tested; Linux headless only | verification gap | NOT TESTED |

## AE. Release recommendation

**CONDITIONAL GO** — the source is ready (all reviewed fixes PASS, full Windows suite 2,249 passed / 0 failed,
independent PDF checks PASS); external compatibility (Acrobat) and installer validation are **NOT
TESTED**, and a releasable candidate is **BLOCKED** until the changes are committed and the release
is built from that commit (then signed manifest and release notes). Not a GO: required external-
reader and installed-application tests are incomplete.
