# Automatic in-place upgrade and update cleanup

Status: **included since 0.3.0; switched on from 0.4.1** with the production update-signing key
([SECURE_UPDATES.md](SECURE_UPDATES.md#production-setup)). 0.4.0 and earlier cannot update themselves;
the first upgrade through this path is from 0.4.1 to a later release. This page describes what happens after
the user clicks **Update Now**, which installation is changed, which files may be replaced or
removed, how temporary update files are cleaned up and what happens when something fails.

## Workflow

```
Update Now
  → identify the installation (registry, before anything is downloaded)
  → download Setup.exe into the staging folder        (progress in bytes, Cancel)
  → verify size + SHA-256 against the signed manifest (+ Authenticode when required)
  → save or discard unsaved changes                    (Cancel stops the update and deletes the download)
  → write handoff.json, copy MonographPDFUpdater.exe into the staging folder, start it
  → Monograph PDF exits
  → helper: wait for every Monograph PDF window of that installation to close
  → helper: lock Setup.exe (read sharing only), verify size + SHA-256 again
  → helper: run the existing Setup silently in upgrade mode for the same folder and mode
  → helper: verify the installed version and files, run the program's self-check
  → helper: delete the installer and staging files, write a short result, start the new version
  → new version: shows "updated to X.Y.Z" (or the failure), removes what the helper could not
```

The running application never replaces its own executable or DLLs: the replacement is done by
Inno Setup, started by a separate helper after the application has exited. The user's click on
**Update Now** authorizes the download, verification and installation of that version; there is no
second confirmation. Windows' own prompts are never bypassed: an all-users installation shows the
normal administrator (UAC) prompt; a per-user installation needs none.

## Which installation is updated

`core/updates/install_target.py` decides before downloading:

* The running program must be `MonographPDF.exe` in a folder that holds Setup's uninstaller
  (`unins000.exe`). A source checkout, a portable copy or a development build is never updated
  automatically.
* That folder must equal the `InstallLocation` of Monograph PDF's uninstall entry
  (`…\Uninstall\{64FC0D97-5E17-405F-9461-D6C075E1B467}_is1`, the stable Inno Setup AppId) in
  exactly **one** hive: `HKCU` → per-user installation (`/CURRENTUSER`), `HKLM` (64- or 32-bit
  view) → all-users installation (`/ALLUSERS`). Paths are compared case-insensitively after
  normalization, so `C:\Program Files\Monograph PDF`,
  `C:\Users\Example\AppData\Local\Programs\Monograph PDF`, `D:\Applications\Monograph PDF` and
  `D:\ソフトウェア\Monograph PDF` are all handled.
* Other registered installations are reported but left alone. If the running copy is not the
  registered one, or the same folder is registered both per-user and for all users, automatic
  installation stops with an explanation; the user can install the update with Setup instead.
* The helper checks the registration again before it runs Setup, and Setup itself (unchanged
  installer logic, `DetectExistingInstallDir`) prefers the registration of the same mode and keeps
  the registered folder in silent mode — so no second installation is created.

## Setup command line

Built by the helper (`installer/update_helper.cs`) as an explicit argument list; documented in
`core/updates/manager.py: setup_arguments`:

```
MonographPDF_<version>_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
    /CURRENTUSER | /ALLUSERS  "/DIR=<existing installation folder>"  "/LOG=<staging>\setup.log"
```

* `UsePreviousAppDir=yes` and the explicit `/DIR` keep the folder; `UsePreviousTasks=yes` keeps the
  previous choices: Start menu and desktop shortcuts, `.pdf` registration and *Open with* entries.
* Setup's own checks still apply: it refuses to run while a Monograph PDF window of that folder is
  open, runs the new program's self-check, and an upgrade keeps settings, the recent-files list and
  everything under `%APPDATA%` / `%LOCALAPPDATA%` (only a *new* installation starts with an empty
  recent-files list).
* `/NORESTART`: if Windows must restart to finish (files in use), the helper reports
  "Restart Windows to finish" instead of claiming the update is complete, and does not start the
  program.

## File ownership and replacement

| Category | Examples | During an upgrade |
| :--- | :--- | :--- |
| A. Application-owned managed files | `MonographPDF.exe`, `_internal\`, `engines\ocr\`, `models\tessdata\`, `licenses\`, `docs\USER_GUIDE.md`, notices, `uninstall.exe`, `MonographPDFUpdater.exe`, `installed_files.txt` | Replaced; obsolete ones removed |
| B. User-created or modified files in the installation folder | a file you placed beside the program | Kept |
| C. Settings and preferences | `%APPDATA%\Monograph PDF` | Kept |
| D. Documents | wherever you saved them | Never touched |
| E. Optional components and choices | shortcuts, file-type registrations | Kept as previously chosen |
| F. Temporary update files | `%LOCALAPPDATA%\Monograph PDF\Updates\Staging\…` | Removed after success (below) |

Setup removes only what Monograph PDF owns, using the mechanisms that already existed for
upgrades and are covered by `scripts/test_installer.ps1`:

* `[InstallDelete]` removes the application's own trees (`_internal`, `engines`, `models`, `docs`,
  `licenses`, …) and listed root files before copying, so no stale DLL or incompatible Python module
  survives. These trees belong to the application entirely (a file put inside `_internal` by hand is
  removed with it).
* `installed_files.txt` (written at build time by `scripts/packaging/write_installed_manifest.py`)
  lists every owned path of the previous version; Setup removes each of them before copying the new
  files (`CleanTargetBeforeCopy`), so an owned file the new version no longer ships does not survive
  (checked by the end-to-end test). Paths are validated (relative, no `..`, no drive),
  never outside the installation folder, never through a junction or link, never the folder itself.
* Anything not owned — category B — is never deleted; the installation folder is never deleted
  recursively.
* Tightly coupled parts (Python runtime, Qt, PyMuPDF, OCR engine) are only ever replaced together,
  as one signed installer. Selective component updates are not part of 0.3.0, 0.4.0 or 0.4.1.

## Staging folder and cleanup

```
%LOCALAPPDATA%\Monograph PDF\Updates\
    state.json                 last check, last status, highest manifest sequence per channel, "remind me later"
    update.lock                one update at a time (the helper also holds the named mutex Local\MonographPDF.Updater)
    result-<id>.json           the helper's outcome; read and deleted at the next start
    Staging\<version>-<random>\
        .monograph-update      ownership marker (owner, id, version, state, time)
        MonographPDF_<version>_Setup.exe(.part)
        handoff.json  setup.log  MonographPDFUpdater.exe
```

The folder is per user, separate from settings, never in Documents, Desktop or Downloads. Even for
an all-users installation the download stays in the user's own folder; the helper keeps the
installer locked against changes (read sharing only) from its final hash check until elevated
Setup has finished reading it.

Rules (`core/updates/staging.py`, run at every start a few seconds after the window appears, and by
the helper for its own files):

* Only folders directly inside `Staging` whose name matches `<version>-<12 hex>` **and** whose
  marker names that folder are considered. Unknown files and folders, links and junctions are
  left alone; nothing is removed recursively; inside an owned folder only the file names the
  updater creates are removed.
* **Success:** the helper deletes the installer, `.part`, `handoff.json` and `setup.log`; its own
  copy (still running) and the marker are removed at the next start.
* **Cancelled / download failed / verification failed:** everything of that attempt is removed
  immediately.
* **Install failed:** the verified installer and `setup.log` of the **newest** failed attempt are
  kept for up to 7 days (a retry or a manual Setup run); older failed attempts are removed.
* **Interrupted** (application or computer stopped): unfinished downloads nobody works on are
  removed after 24 hours; a hand-off whose helper is still running is left alone.
* **Size bound:** whatever remains is trimmed, oldest first, to 1 GB.
* **Disk space:** before downloading, the free space for the installer (plus a margin) in the
  staging folder and the installed size on the installation drive are checked; nothing is
  downloaded or changed when space is missing.
* Uninstalling Monograph PDF removes the `Updates` and `Diagnostics` folders of the user who
  uninstalls.

## Verification of the result

The helper reports success only when Setup exited with 0 **and** the uninstall entry of that mode
and folder shows the expected `DisplayVersion` **and** `MonographPDF.exe` reports the expected
product version **and** `_internal` exists **and** the new program's `--smoke-test` passes. It then
starts the new `MonographPDF.exe` once (never the old one, never elevated: the helper runs with the
user's normal rights), with `--update-finished <id>`; no document is reopened automatically. The
new version reads `result-<id>.json`, shows the outcome once and deletes it.

## Failure and recovery

* Nothing is changed before the download is complete and verified.
* If Setup fails before changing files (exit codes 1–3, 7), or the administrator prompt is
  declined, the previous version is still installed; the helper says so and starts it again.
* If Setup fails while copying (exit 4–6) or the result cannot be verified, the helper does not
  claim success, keeps the verified installer and Setup's log, and tells the user to run Setup
  again. **There is no automatic rollback:** files Setup removed at the start of an upgrade
  (`[InstallDelete]` and the previous owned-file list) are not restored if it fails later. The
  supported recovery is running Setup again (the kept installer, or a fresh download from the
  release page) — an in-place reinstall keeps settings and documents.
* The helper never retries Setup on its own and never restarts the application more than once.
* One update at a time: a second **Update Now** is refused while the lock is held; a second helper
  exits immediately (named mutex).

## Testing

* Automated (any platform): `tests/unit/test_update_install.py`, `test_update_staging.py`,
  `test_update_ui.py`, `test_international.py`.
* Windows end-to-end: `scripts/test_update_e2e.py` builds two test versions of the current source
  with a synthetic update key and a local HTTPS mock release server, installs the first per-user into
  a Unicode folder, runs the complete flow through the real helper and Setup, and checks the result
  (see [TESTING.md](TESTING.md)). It never touches an existing installation, the user's settings or
  release artifacts. All-users (elevated) upgrades and real localized Windows installations need
  separate manual verification.
