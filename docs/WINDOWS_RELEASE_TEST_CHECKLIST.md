# Windows release test checklist (manual, on real computers)

For testing a release candidate of Monograph PDF on your own Windows computers before publishing.
Record each item as **PASS**, **FAIL** (with what you saw) or **NOT TESTED**. Never record an item you
did not do as passed. The release notes report these results.

* Prefer a computer that is not your main work computer for install/uninstall tests, or at least
  close Monograph PDF and keep a copy of your documents first.
* `scripts\windows_release_check.ps1` only reads: it never installs, uninstalls, deletes or changes
  settings (see its header). `scripts\test_installer.ps1` **does** install and uninstall a per-user test
  copy and temporarily backs up and restores your Monograph PDF settings — run it only on a test
  computer, never on a computer whose settings you must not risk.

Write down for every computer: Windows edition and version (`winver`), 64-bit, display language,
display scaling, whether another Monograph PDF version was installed and for which users.

## A. Can be tested now (0.4.1 release candidate)

### A1. Download and file checks

| # | Step | Expected |
|---|---|---|
| 1 | Copy `MonographPDF_0.4.1_Setup.exe`, `_Installer.zip`, `_Source.zip` (and, once signed, `MonographPDF_update_manifest.json`) into an empty folder | — |
| 2 | `powershell -NoProfile -ExecutionPolicy Bypass -File windows_release_check.ps1 -ReleaseDir <folder>` | `PASS` for both SHA256SUMS entries; Authenticode `NotSigned`; with a manifest: `PASS` manifest names this Setup.exe |
| 3 | Compare the printed SHA-256 of Setup.exe with the release notes | identical |

### A2. Clean installation (computer without Monograph PDF)

| # | Step | Expected |
|---|---|---|
| 1 | Run Setup; note the SmartScreen warning text | the unsigned-installer warning described in INSTALLATION.md; Setup offers per-user / all-users |
| 2 | Finish Setup with **Launch** checked | Monograph PDF opens; **Help ▸ About** shows 0.4.1 |
| 3 | `windows_release_check.ps1 -SelfTest` | `PASS self-check`, every line `ok`; update checks enabled `True`, trusted key id `27c3b3b23b949c40` |
| 4 | Start menu entry, desktop shortcut (if chosen), "Open with" for a PDF | all open Monograph PDF |

### A3. Upgrade 0.4.0 → 0.4.1 (computer with 0.4.0 installed)

0.4.0 cannot update itself (its update checks are switched off); the upgrade is done with Setup.

| # | Step | Expected |
|---|---|---|
| 1 | In 0.4.0: change a few settings you can recognise (e.g. **File ▸ Settings…**, recent files, window size, a toolbar choice); close it | — |
| 2 | Run the 0.4.1 Setup **for the same users** (an all-users 0.4.0 needs the administrator prompt) | Setup upgrades in place, same folder |
| 3 | Start 0.4.1 | About shows 0.4.1; the settings and recent files of step 1 are still there |
| 4 | `windows_release_check.ps1 -SelfTest` | one installation listed, version 0.4.1, self-check `PASS` |

### A4. Application functions

| # | Area | Steps | Expected |
|---|---|---|---|
| 1 | Open / view | open several PDFs (text, scanned, large, password-protected, permissions-only) | render correctly; password prompt only where needed |
| 2 | Editing | add a text box, type, select the text, **choose fonts from the font list** in the toolbar and the Properties panel (also scroll the list with the wheel) | no crash; the list opens on the first click; the wheel does not change the font |
| 3 | Fonts / Unicode | text in Japanese (MS Mincho, Meiryo, Yu Gothic), accented Latin, emoji-free symbols; save and reopen | text kept, searchable/copyable; no "font collections (.ttc) are not embedded" message |
| 4 | Saving | Save, Save As (new name, folder with non-ASCII characters), reopen | identical content; permissions-only PDF keeps its restrictions |
| 5 | Conversion | PDF → Word, Word/Excel → PDF (if Office/LibreOffice installed), images → PDF | output opens in the target application |
| 6 | Compression | **File ▸ Compress PDF…**: each of the five choices, **Preview**, **Compress and Save As…** | dialog fits the screen; text/fonts/comments unchanged in the result; size as previewed |
| 7 | Printing | print preview; one real print if possible | correct pages; a real print not done = NOT TESTED |
| 8 | Problem reports | (only if something fails) the report dialog | shows the report in full; **Send** is not offered (sending switched off) |

### A5. Update checking (before 0.4.1 is published)

| # | Step | Expected now |
|---|---|---|
| 1 | Settings ▸ Updates | *Automatically check for updates* **off**; **Check Now** enabled |
| 2 | **Help ▸ Check for Updates…** while online | Until a release with `MonographPDF_update_manifest.json` is the latest on GitHub: **Unable to check**, "Nothing was downloaded or installed", **Open Releases Page** button — never "Up to date" |
| 3 | Same while offline (Wi-Fi off / cable out) | **Unable to check**; the app keeps working normally |
| 4 | Start the app offline | starts normally; no message about updates |

### A6. Offline operation

| # | Step | Expected |
|---|---|---|
| 1 | Disconnect the network; open, edit, save, OCR, compress, convert | everything works |
| 2 | Self-check `no_network` line | `ok` |

### A7. Uninstallation and reinstallation

| # | Step | Expected |
|---|---|---|
| 1 | Uninstall from Windows Settings ▸ Apps | program folder and Start menu entry removed; your documents untouched |
| 2 | Reinstall 0.4.1 | installs and starts; settings kept unless you chose to remove them |

## B. Needs a future signed update (cannot be tested before publication)

| # | Test | When |
|---|---|---|
| B1 | After 0.4.1 is published **with** its signed manifest: **Check for Updates** on 0.4.1 says **Up to date** (verified) | right after publication |
| B2 | Optional automatic check (switch on, wait for the interval): stays quiet when up to date | after publication |
| B3 | **Update Now** from 0.4.1 to the next release (0.4.2): download, verify, close, install in place, restart, settings kept; all-users install shows the administrator prompt | when 0.4.2 is published |
| B4 | A tampered or unsigned manifest is refused (**Verification failed**) | covered by automated tests; on real computers only with a test release |
| B5 | **Skipped versions:** keep one test computer on 0.4.1 without updating; when a later release (e.g. 0.6.0) is out, **Check for Updates** offers it directly and **Update Now** installs it in one step; settings, recent files and documents kept | when that release is published |
| B6 | A release that sets `min_upgrade_from` above the installed version: Update Now disabled with the reason; Setup from the release page works | only if such a release is made |

## Logs and failure reports

* `windows_release_check.ps1 -CollectLogs` copies `%LOCALAPPDATA%\Monograph PDF\logs` into a new
  folder on the Desktop. Read it before sharing; it stays on your computer.
* The check report (`MonographPDF-release-check-<time>.txt` on the Desktop) lists Windows version,
  installed copies, update configuration and self-check results.
* For each failure note: the item number, what you did, what happened, a screenshot, the time, and
  whether it repeats. A crash is shown as a problem report at the next start: use **Copy** and paste it.
