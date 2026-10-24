# Installation (Linux 0.1.0)

Monograph PDF **0.1.0** is the first Linux release. It is separate from the Windows
installer line (Windows 0.5.0).

## System requirements

| | Minimum | Recommended |
| :--- | :--- | :--- |
| Operating system | Linux x86_64 | Recent Ubuntu / Debian / Fedora |
| Memory | 4 GB | 8 GB or more |
| Free disk space | 1 GB | 2 GB |
| Screen | 1280 × 720 | 1920 × 1080 or larger |
| Office suite | — | LibreOffice (Office files → PDF) |
| OCR | Tesseract on `PATH` (or via `scripts/vendor_ocr.sh`) | eng + jpn tessdata (vendored) |

## Run from source (development)

```bash
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

Self-check: `./env/bin/python -m app --smoke-test`

## Per-user install (built tree)

After you have a built `MonographPDF` folder (PyInstaller one-folder layout):

```bash
bash installer/linux/install.sh /path/to/MonographPDF
```

This installs under `~/.local/share/Monograph PDF`, adds a `~/.local/bin/MonographPDF`
launcher and a desktop entry. Uninstall: run `uninstall.sh` in the install folder.
Settings stay in `~/.local/share/monograph-pdf` unless you remove them yourself.

## Default PDF app

**Help ▸ Make Monograph PDF the Default PDF App…** writes a `.desktop` file and runs
`xdg-mime default … application/pdf`.

## Windows installation

See the Windows 0.5.0 materials (`MonographPDF_0.5.0_Installer` / GitHub Releases) for
`Setup.exe`. That line is versioned separately from this Linux 0.1.0 tree.
