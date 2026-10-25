# Monograph PDF for Linux — first release (0.1.0)

This tree is the **first Linux build** of Monograph PDF. It is a separate platform
line from the Windows product (currently Windows 0.5.0). Version numbers are not
shared: Linux starts at **0.1.0**.

Feature coverage aims to match the Windows application (view, edit, annotate,
forms, organize, convert, compress, OCR, protect). Platform-specific pieces use
Linux replacements (flock, fontconfig, LibreOffice, XDG, system/micromamba
Tesseract + pinned tessdata).

**Signing.** This first Linux release is **unsigned**. Code signing and signed
update manifests will be added later; until then, build from this repository and
verify checksums when archives are published.

## Requirements

* Linux x86_64 (developed and tested on this PC)
* Python **3.11** (`uv python install 3.11` if needed)
* LibreOffice (Office → PDF)
* Tesseract on `PATH` (or micromamba env linked by `scripts/vendor_ocr.sh`)

## Setup and run

```bash
cd "MonographPDF_Linux"
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh      # engines/ocr + models/tessdata
bash scripts/dev_launch.sh
bash scripts/run_tests.sh
./env/bin/python -m app --smoke-test
```

## Platform mapping

| Area | Linux 0.1.0 |
| :--- | :--- |
| Single instance | `fcntl` lock on `instance.lock` |
| OCR | System/micromamba `tesseract` + pinned tessdata_fast eng/jpn/osd |
| Font embedding | fontconfig (`fc-list`) |
| Default PDF app | `.desktop` + `xdg-mime` |
| Show in folder | FreeDesktop FileManager1 |
| Office → PDF | LibreOffice (`soffice`) |
| Install (optional) | `installer/linux/install.sh` (per-user) |
| Data dirs | XDG (`~/.local/share/monograph-pdf`, cache) |
| Binary name | `MonographPDF` |

## Folder layout in Documents

* `MonographPDF_0.5.0_Source/` / `…_Installer/` — Windows 0.5.0 materials (unchanged)
* `MonographPDF_Linux/` — this Linux first-release workspace (0.1.0)
