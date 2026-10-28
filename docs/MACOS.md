# Monograph PDF for macOS

First macOS line of Monograph PDF. Versioned independently of Windows (`versions/macos.txt`; currently **0.1.0**). Windows remains on its own SemVer (`versions/windows.txt`).

| | |
| :--- | :--- |
| **Platform** | macOS 13+ (Apple silicon validated; Intel not verified in 0.1.0) |
| **UI / PDF stack** | PySide6 + PyMuPDF |
| **OCR** | Offline Tesseract (`engines/ocr`) with bundled `eng` / `jpn` / `osd` |
| **Office → PDF** | LibreOffice (`soffice`) when installed under `/Applications` |

## Develop from source

Use the unified `main` checkout. The retained `macos` branch is a legacy recovery source.
Python 3.11 and native macOS build tools are required; LibreOffice is optional for Office conversion.

```bash
bash scripts/setup_env.sh
bash scripts/vendor_ocr_macos.sh   # optional: stage local OCR into engines/ocr
bash scripts/dev_launch.sh
bash scripts/run_tests.sh
```

## Build a `.app` and packages

```bash
bash scripts/build_app.sh
# → dist/MonographPDF.app  (OCR staged, Info.plist = 0.1.0, signed)

bash scripts/package_macos.sh
# → dist/release/MonographPDF_<macos-version>_macOS.pkg   guided installer (Installer.app)
# → dist/release/MonographPDF_<macos-version>_macOS.dmg   drag-and-drop disk image
# → dist/release/MonographPDF_<macos-version>_macOS.zip   portable app archive
# → dist/release/MonographPDF_<macos-version>_macOS_OCR_Corresponding_Source/
# → dist/release/SHA256SUMS.txt, verification.json
```

### Installer formats

| Format | For | What the user sees |
| :--- | :--- | :--- |
| `.pkg` | Most users (like Windows Setup.exe) | Installer.app: Welcome (product, version, macOS 13+), Read Me (requirements, steps, "your data is kept"), License (AGPL-3.0), disk space, Install, completion page with how to open PDFs |
| `.dmg` | Users who prefer drag and drop | A Finder window with the app on the left, an arrow, and Applications on the right; one line of instruction |
| `.zip` | Portable use / archiving | `MonographPDF.app`, extracted with Finder or `ditto -x -k` |

* **Install location:** the `.pkg` installs exactly `/Applications/MonographPDF.app` for all users. It does
  not relocate into a copy the user moved elsewhere, so it never leaves two copies. It upgrades in place
  and refuses to replace a newer version with an older one. It runs **no** install scripts.
* **User data:** settings and recent files (`~/Library/Application Support/Monograph PDF`) are never
  touched by installing, upgrading or removing the app. To uninstall, drag the app to the Trash. The
  `.pkg` receipt can be removed with `sudo pkgutil --forget com.aungyemun.monographpdf`.
* **Architecture:** Apple silicon (arm64), macOS 13 or later. The bundled Python, Qt and OCR builds are
  arm64-only, and the `.pkg` refuses Intel Macs with a clear message rather than installing an app that
  cannot start. An Intel or universal build would need x86_64 Python, Qt and OCR builds; it is not
  produced or verified here.
* **Artwork:** generated at package time by `scripts/packaging/macos_installer.py` from the brand images
  in `resources/icons/source` and the page templates in `installer/macos/`.
* **Verification:** `scripts/packaging/verify_macos_release.py` checks the app as it comes out of each
  format. It covers identity, version, minimum macOS, architecture, strict signature, symlinks, the
  builder path, the OCR inventory and licenses, and Tesseract running. It also checks the DMG layout
  files, the `.pkg` screens, location, relocation and scripts, the checksums and the corresponding
  source. Any FAIL stops `package_macos.sh`.

### Signing

| Mode | How | Result |
| :--- | :--- | :--- |
| Development (default) | `bash scripts/build_app.sh && bash scripts/package_macos.sh` | Ad-hoc signed app, unsigned `.pkg`. For local testing only: Gatekeeper rejects it on other Macs, and it is **not notarized**. |
| Production | `MONOGRAPH_MACOS_SIGN_IDENTITY="Developer ID Application: Name (TEAMID)"` for both scripts, plus `MONOGRAPH_MACOS_INSTALLER_IDENTITY="Developer ID Installer: Name (TEAMID)"` and `MONOGRAPH_NOTARY_PROFILE=<profile>` for `package_macos.sh` | Every Mach-O (the OCR engine included) is signed with Hardened Runtime, a secure timestamp and `installer/macos/entitlements.plist`. The app, `.dmg` and `.pkg` are notarized with `notarytool` and stapled. Verification requires Gatekeeper acceptance. |

Create the notary profile once with
`xcrun notarytool store-credentials <profile> --apple-id <id> --team-id <TEAMID>` (an app-specific
password is entered there, not in these scripts). Production mode refuses to run without the
identities in the keychain. `MONOGRAPH_MACOS_SKIP_NOTARIZE=1` tests signing only, and its output is not
notarized. Apple signing needs Apple-issued Developer ID certificates; the Windows update-manifest key
cannot sign macOS code or packages.

## User data locations

| Kind | Path |
| :--- | :--- |
| Preferences / recent files | `~/Library/Application Support/Monograph PDF` |
| Caches | `~/Library/Caches/Monograph PDF` |

## What differs from Windows

* Single-instance handover uses an `fcntl` file lock.
* **Show in Folder** reveals the file in Finder (`open -R`).
* **Default PDF App** asks LaunchServices to open PDFs with the installed app (macOS may ask
  you to confirm); if that fails it explains Finder ▸ Get Info ▸ Open with ▸ Change All….
* PDFs opened from Finder, **Open With** or dropped on the Dock icon arrive as `QFileOpenEvent`s and
  open in the running window (also on a cold start).
* About, Settings… and Quit sit in the application menu by menu role.
* Dark mode follows the system appearance (`FORCE_DARK=1` still forces it).
* Shortcuts shown as Ctrl in the User Guide use ⌘ Command. Exceptions: switch document tabs with
  Control+Tab / Control+Shift+Tab or ⌘⇧] / ⌘⇧[ (⌘Tab is the system app switcher); full screen is
  Control+⌘F (F11 is Show Desktop).
* Automatic updates are not available on macOS yet: **Check for Updates** says so instead of
  reading the Windows release line. Download new Mac versions (`.dmg`) from GitHub Releases.
* The `.app` carries its own Tesseract (`Contents/Resources/engines/ocr/bin` + `lib`), staged by
  `scripts/packaging/stage_ocr_macos.py`; the build fails on dangling symlinks or OCR libraries
  linked from outside the bundle.
  Each bundled conda package's license is copied to `engines/ocr/licenses/<package>/` and listed
  in `engines/ocr/THIRD_PARTY_OCR.json`. lzo (GPL-2.0-or-later) and libiconv (LGPL-2.1) are
  copyleft; `package_macos.sh` writes their corresponding source (upstream archive verified
  against the recipe's SHA-256, recipe, patches, build scripts, licenses) to
  `MonographPDF_<version>_macOS_OCR_Corresponding_Source/` and adds it to `SHA256SUMS.txt`.
* OCR provenance: `scripts/vendor_ocr_macos.sh` installs the exact builds in
  `scripts/packaging/macos_ocr_env.lock`; `scripts/packaging/macos_ocr_sources.json` records every
  bundled file's SHA-256. The bundle ships the published package files unmodified (their own
  ad-hoc signatures are verified, not replaced), so a build fails if the environment drifts. After
  changing the OCR environment, regenerate with `macos_ocr_sources.py lock`, `inventory` and
  `sources` (see the script's docstring).
* Microsoft Office COM conversion is Windows-only; LibreOffice works when installed.
