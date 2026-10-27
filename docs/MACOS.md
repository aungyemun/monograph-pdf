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
* **Default PDF App** opens System Settings.
* Automatic Windows installers / Authenticode update installation are Windows-only.
* Microsoft Office COM conversion is Windows-only; LibreOffice works when installed.
