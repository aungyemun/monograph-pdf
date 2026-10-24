# Monograph PDF for macOS

This is the **first macOS release** of Monograph PDF. It is versioned independently of the Windows line (Windows remains on its own releases, currently 0.5.x on GitHub).

| | |
| :--- | :--- |
| **Platform** | macOS 13+ (Apple silicon; Intel not verified in this first release) |
| **First version** | 0.1.0 |
| **UI / PDF stack** | PySide6 + PyMuPDF (same core as Windows where reusable) |
| **OCR** | Offline Tesseract with bundled `eng` / `jpn` / `osd` language data |
| **Office → PDF** | LibreOffice (`soffice`) when installed under `/Applications` |

## Develop from source

```bash
# Create ./env (Python 3.11) and install pinned requirements
bash scripts/setup_env.sh

# Optional: stage a local OCR engine + tessdata into engines/ocr and models/tessdata
bash scripts/vendor_ocr_macos.sh

# Run from source
bash scripts/dev_launch.sh

# Tests
bash scripts/run_tests.sh
```

## Build a `.app` and packages

```bash
bash scripts/build_app.sh
# → dist/MonographPDF.app

bash scripts/package_macos.sh
# → dist/release/MonographPDF_<version>_macOS.zip  (.app archive)
# → dist/release/MonographPDF_<version>_macOS.dmg
# → dist/release/MonographPDF_<version>_macOS.pkg
# → dist/release/SHA256SUMS.txt
```

These packages are **unsigned**. First open may need **Right-click → Open** (or allow in System Settings ▸ Privacy & Security).
## User data locations

| Kind | Path |
| :--- | :--- |
| Preferences / recent files | `~/Library/Application Support/Monograph PDF` |
| Runtime / caches (installed `.app`) | `~/Library/Application Support/Monograph PDF/runtime` |
| Cache (preferences helper) | `~/Library/Caches/Monograph PDF` |

## What differs from Windows

* Single-instance handover uses an `fcntl` file lock (not a Windows mutex).
* **Show in Folder** reveals the file in Finder (`open -R`).
* **Default PDF App** opens System Settings (you choose the default yourself).
* Automatic update installers (Inno Setup / Authenticode) are Windows-only; Help ▸ Check for Updates still reports newer GitHub releases when signed update metadata is available.
* Microsoft Office COM conversion is Windows-only; LibreOffice works on macOS when installed.
