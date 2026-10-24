# Windows release test checklist (manual, on real computers)

For testing a release candidate of Monograph PDF on your own Windows computers before publishing.
Record each item as **PASS**, **FAIL** (with what you saw) or **NOT TESTED**. Never record an item you
did not do as passed. The release notes report these results.

## Before you start: what changes your computer

| Tool / step | Effect on the computer |
|---|---|
| `scripts\windows_release_check.ps1` | **Read-only.** Never installs, uninstalls, deletes or changes settings or registry entries. Writes one report file to the Desktop; `-SelfTest` runs the installed program's offline self-check with a new temporary settings folder (deleted afterwards); `-CollectLogs` copies the log folder to a new Desktop folder. |
| Running a Setup (A2, A3, A8) | Installs or upgrades Monograph PDF (Start menu, file associations you choose). An all-users Setup asks for administrator rights. Your settings and documents are kept. |
| Uninstalling (A8) | Removes the program; asks before removing settings. Documents are never touched. |
| `scripts\test_installer.ps1` | Installs, uninstalls and reinstalls a per-user **test** copy and temporarily backs up and restores your Monograph PDF settings. Run it only on a test computer, never on the computer whose settings you must not risk. |

Prefer a computer that is not your main work computer for install/uninstall tests, or close
Monograph PDF and keep a copy of your documents first. Write down for every computer: Windows edition
and version (`winver`), display language, regional format / system locale (e.g. Japanese), display
scaling, and whether another Monograph PDF version was installed and for which users.

## A. Tests you can do now (0.4.1 release candidate)

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
| 3 | `windows_release_check.ps1 -SelfTest` | `PASS self-check`, every line `ok`; update checks enabled `True`, trusted key id `27c3b3b23b949c40`; `MonographPDF.exe`, `MonographPDFUpdater.exe`, `uninstall.exe` reported as **Windows GUI** programs |
| 4 | Start menu entry, desktop shortcut (if chosen), "Open with" for a PDF | all open Monograph PDF |

### A3. Manual upgrade 0.4.0 → 0.4.1 and settings preservation

0.4.0 cannot update itself (its update checks are switched off and it trusts no signing key); the
upgrade is done with Setup.

| # | Step | Expected |
|---|---|---|
| 1 | In 0.4.0: change settings you can recognise (theme, **File ▸ Settings… ▸ Updates** interval, OCR languages, window size, a recent font), open two PDFs so they appear in the recent-files list; close it | — |
| 2 | Run the 0.4.1 Setup **for the same users** (an all-users 0.4.0 needs the administrator prompt) | Setup upgrades in place, same folder |
| 3 | Start 0.4.1 | About shows 0.4.1; every setting and recent file of step 1 is still there |
| 4 | `windows_release_check.ps1 -SelfTest` | one installation listed, version 0.4.1, self-check `PASS` |

### A4. Startup, shutdown and the application

| # | Area | Steps | Expected |
|---|---|---|---|
| 1 | Startup / shutdown | start from the Start menu and by double-clicking a PDF; close with the window's X and with **File ▸ Exit**; start again | **no Command Prompt or PowerShell window appears at any point**; one window only (a second start brings the open window to the front); no problem report at the next start |
| 2 | Open / render | open several PDFs (text, scanned, large, password-protected, permissions-only); zoom, scroll, thumbnails | correct rendering; password prompt only where needed |
| 3 | Editing and saving | add a text box, type, select the text, **choose fonts from the font list** in the toolbar and the Properties panel (also turn the mouse wheel over it); Save, Save As (new name), reopen | no crash; the list opens on the first click; the wheel does not change the font; content identical after reopening; a permissions-only PDF keeps its restrictions |
| 4 | Fonts incl. TTC | text in **MS Mincho, MS Gothic, Meiryo, Yu Gothic** (installed as `.ttc` collections) and an accented Latin font; save, reopen, copy the text out | text kept and searchable; **no** "font collections (.ttc) are not embedded" message; **File ▸ Properties** lists the fonts as embedded |
| 5 | Compression | **File ▸ Compress PDF…**: each of the five choices, **Preview**, **Compress and Save As…** | dialog fits the screen; text, fonts, comments unchanged; size as previewed |
| 6 | Conversion | PDF → Word, Word/Excel → PDF (if Office/LibreOffice installed), images → PDF | output opens in the target application |
| 7 | Printing | print preview; one real print if possible | correct pages; a real print not done = NOT TESTED |
| 8 | Problem reports | only if something fails: the report dialog | shows the report in full; **Copy** and **Close** offered, no **Send** (sending is switched off) |

### A5. Japanese and Unicode paths

| # | Step | Expected |
|---|---|---|
| 1 | Folder `C:\テスト\資料 2026\` with `見積書（最終）.pdf` and `Café – Ünïcode.pdf`: open, edit, save, Save As into the same folder | works; names shown correctly; recent-files list shows them after a restart |
| 2 | OCR (Japanese) on a scanned page in that folder | text recognised; saved PDF searchable |
| 3 | On a computer whose Windows user name contains Japanese characters (if available) | settings saved and kept across restarts |
| 4 | Per-user installation into a custom folder with Japanese characters | installs, starts, self-check `PASS` |

### A6. Update checking (before 0.4.1 is published)

| # | Step | Expected now |
|---|---|---|
| 1 | Settings ▸ Updates | *Automatically check for updates* **off**; **Check Now** enabled |
| 2 | **Help ▸ Check for Updates…** while online | Until a release with `MonographPDF_update_manifest.json` is the latest on GitHub: **No compatible release found**, "Nothing was downloaded or installed", **Open Releases Page** — never "Up to date" |
| 3 | Same while offline (Wi-Fi off / cable out) | **No internet connection**; the app keeps working normally |
| 4 | Start the app offline | starts normally; no message about updates |

### A7. Offline operation

| # | Step | Expected |
|---|---|---|
| 1 | Disconnect the network; open, edit, save, OCR, compress, convert | everything works |
| 2 | Self-check `no_network` line | `ok` |

### A8. Uninstallation and reinstallation

| # | Step | Expected |
|---|---|---|
| 1 | Uninstall from Windows Settings ▸ Apps (answer the settings question as you like) | program folder and Start menu entry removed; documents untouched; settings removed only if you chose so |
| 2 | Reinstall 0.4.1 | installs and starts; settings kept unless removed in step 1 |

## B. Needs a published signed release (cannot be tested before publication)

| # | Test | When |
|---|---|---|
| B1 | After 0.4.1 is published **with** its signed manifest: **Check for Updates** on 0.4.1 reports **No update available** | right after publication |
| B2 | Optional automatic check (switch on, wait for the interval): stays quiet when up to date | after publication |
| B3 | **Update Now** from 0.4.1 to the next release (0.5.0): download, verify, close, install in place, restart, settings kept; all-users install shows the administrator prompt; **Cancel** during the download says "Update canceled. Nothing was installed." | when 0.4.2 is published |
| B4 | A tampered or unsigned manifest is refused (*Invalid digital signature*) | covered by automated tests; on real computers only with a test release |
| B5 | **Skipped versions:** keep one test computer on 0.4.1 without updating; when a later release (e.g. 0.6.0) is out, **Check for Updates** offers it directly and **Update Now** installs it in one step; settings, recent files and documents kept | when that release is published |
| B6 | A release that sets `min_upgrade_from` above the installed version: **Update Now** disabled with the reason; Setup from the release page works | only if such a release is made |

## Logs and failure reports

* `windows_release_check.ps1 -CollectLogs` copies `%LOCALAPPDATA%\Monograph PDF\logs` into a new
  folder on the Desktop. Read it before sharing; it stays on your computer.
* The check report (`MonographPDF-release-check-<time>.txt` on the Desktop) lists Windows version,
  installed copies, their update configuration, program types (GUI/console) and self-check results.
* For each failure note: the item number, what you did, what happened, a screenshot, the time, and
  whether it repeats. A crash is shown as a problem report at the next start: use **Copy** and paste it.
