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
# → dist/MonographPDF.app  (OCR staged, Info.plist = 0.1.0, ad-hoc codesigned)

bash scripts/package_macos.sh
# → dist/release/MonographPDF_<macos-version>_macOS.{zip,dmg,pkg}
# → dist/release/SHA256SUMS.txt
```

**Signing:** `build_app.sh` applies an **ad-hoc** signature (`codesign -s -`) after all resources are in place. That is for local development validation only. It is **not** Apple Developer ID signing and does **not** satisfy Gatekeeper distribution or notarization.

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
