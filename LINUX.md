# Monograph PDF for Linux

Linux uses an independent version (`versions/linux.txt`, currently 0.1.1) in the unified `main`
tree. The latest published Linux release is [v0.1.1-linux](https://github.com/aungyemun/monograph-pdf/releases/tag/v0.1.1-linux). The retained `linux` branch is a
legacy source, not the starting point for new development. The Windows releases (currently 0.5.1) are not Linux packages.

## Requirements and source setup

Target: Linux x86_64, Python 3.11 and the pinned Python dependencies. Desktop/font support uses
fontconfig, XDG and FreeDesktop tools. LibreOffice is optional for Office-to-PDF conversion.
Tesseract and the pinned language data are required for OCR. See [CI](.github/workflows/linux-ci.yml)
for the Ubuntu offscreen test libraries; CI is not certification of every distribution.

```bash
git clone --branch main https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
bash scripts/run_tests.sh
./env/bin/python -m app --smoke-test
```

The setup/vendor scripts may download dependencies. Once installed, document processing and OCR
work offline. Missing OCR/Office dependencies leave those operations unverified, not passed.

## Build and package a release

```bash
bash scripts/vendor_ocr.sh              # stage Tesseract + pinned tessdata
bash scripts/build_linux.sh             # dist/MonographPDF (bundles Tesseract), smoke test
bash scripts/package_linux.sh --sign KEYID   # dist/release-linux: tarballs, SHA256SUMS.txt, *.asc
```

`build_linux.sh` needs `patchelf`. The build needs at least the glibc of the build machine
(PyInstaller bundles some host libraries), so build on the oldest distribution you want to support. The bundled Tesseract is relinked to load only the libraries
shipped beside it (glibc excepted). `package_linux.sh` refuses uncommitted changes, because the
source archive is `git archive HEAD`.

## Native installation and integration

`bash installer/linux/install.sh /path/to/MonographPDF` consumes a **built application directory**
containing `MonographPDF`; it does not create that binary from source. Review the script before
running it: it synchronizes its destination, writes a desktop launcher and selects the PDF MIME handler.
Do not point it at a directory of unrelated user files. No distro-specific package is claimed here.

| Concern | Implementation |
| :--- | :--- |
| Single instance | `fcntl` lock |
| Font embedding | fontconfig (`fc-list`) |
| Default PDF application | `.desktop` entry and `xdg-mime` |
| Reveal document | FreeDesktop FileManager1 |
| Office to PDF | Locally installed LibreOffice |
| Settings | `$XDG_DATA_HOME/monograph-pdf` or `~/.local/share/monograph-pdf` |
| Cache | `$XDG_CACHE_HOME/monograph-pdf` or `~/.cache/monograph-pdf` |

Linux uses manual upgrades; Windows signed-Setup auto-installation does not apply. Native desktop,
package/install and printing acceptance remain separate from offscreen CI.
[Repository layout](docs/REPOSITORY_LAYOUT.md) · [Testing](docs/TESTING.md).
