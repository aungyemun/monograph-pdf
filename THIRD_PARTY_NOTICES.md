# Monograph PDF — Third-Party Notices

This document identifies the third-party software redistributed with Monograph PDF 0.2.0 (inside `MonographPDF.exe`, its `_internal` folder, `engines\ocr` and `models\tessdata`). Each component remains under its own license. The statements below do not amend those licenses.

License texts: `LICENSE.md` (Monograph PDF: **AGPL-3.0-or-later**; PyMuPDF/MuPDF retain upstream **AGPL-3.0**) and, in the `licenses` folder of the installation, GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-1.1 and the GCC Runtime Library Exception. Corresponding Monograph PDF release source, including application, build, installer, documentation and release tests, together with the corresponding source of every bundled AGPL, GPL and LGPL component, is published with each release as `MonographPDF_0.2.0_Source.zip` (see [Corresponding source](#corresponding-source)). Local personal-document validation utilities that contain private or machine-local paths are intentionally excluded from that archive.

Each bundled component keeps its own license, listed below.

All **bundled** components listed below run locally. None of them is used by Monograph PDF to communicate over a network. Optional external Microsoft Office / LibreOffice (not included) follow their own settings and behavior when invoked for conversion. The release build removes the parts of the bundled libraries that only serve network use (Qt network and TLS plugins, Python's SSL module, OpenCV's FFmpeg video I/O); `scripts\packaging\check_release.py` fails a build that contains a program file not listed here.

## Summary

| Component | Version | Role in Monograph PDF | Status | License |
| :--- | :--- | :--- | :--- | :--- |
| PyMuPDF / MuPDF (Artifex Software) | PyMuPDF 1.25.3 / MuPDF 1.25.4 | PDF rendering, editing, forms, encryption, and redaction | Bundled runtime | AGPL-3.0 |
| Qt 6 / PySide6 / Shiboken6 (The Qt Company) | 6.8.1.1 (Qt 6.8.1) | Graphical user interface and printing | Bundled runtime | LGPL-3.0 |
| Python | 3.11.9 | Bundled runtime | Bundled runtime | PSF License |
| OpenSSL (libcrypto only) | 3.0.13 | Hash functions used by Python's `hashlib` | Bundled runtime | Apache-2.0 |
| libffi | 3.4 (`libffi-8.dll`) | Python `ctypes` support | Bundled runtime | MIT |
| Microsoft Visual C++ and Universal C runtime | 14.x / 10.0 | C/C++ runtime libraries required by Python, Qt and NumPy | Bundled runtime (redistributable) | Microsoft Visual C++ Redistributable license |
| pdf2docx | 0.5.8 | PDF-to-Word layout reconstruction | Bundled runtime | GPL-3.0 |
| OpenCV (opencv-python-headless) | 4.10.0.84 | Table and line detection for PDF-to-Word | Bundled runtime | Apache-2.0 |
| NumPy | 2.1.3 | Numerical arrays for PDF-to-Word | Bundled runtime | BSD-3-Clause |
| OpenBLAS (scipy-openblas, shipped with NumPy) | as bundled with NumPy 2.1.3 | Linear algebra for NumPy | Bundled runtime | BSD-3-Clause |
| fontTools | 4.54.1 | Font metrics for PDF-to-Word | Bundled runtime | MIT |
| python-fire / termcolor / colorama | 0.7.1 / 3.3.0 / 0.4.6 | Import-time dependencies of pdf2docx | Bundled runtime | Apache-2.0 / MIT / BSD-3-Clause |
| python-docx | 1.1.2 | Writing Word (`.docx`) files | Bundled runtime | MIT |
| openpyxl / et_xmlfile | 3.1.5 / 2.0.0 | Writing Excel (`.xlsx`) files | Bundled runtime | MIT |
| python-pptx / XlsxWriter | 1.0.2 / 3.2.9 | Writing PowerPoint (`.pptx`) files | Bundled runtime | MIT / BSD-2-Clause |
| lxml | 6.1.3 | XML processing for Office writers | Bundled runtime | BSD-3-Clause |
| Pillow | 12.3.0 | Image import and export | Bundled runtime | MIT-CMU (HPND) |
| packaging / typing_extensions | 24.2 / 4.16.0 | Version parsing; typing support | Bundled runtime | Apache-2.0 OR BSD-2-Clause / PSF |
| Tesseract OCR | 5.4.0 (Windows build) | Offline optical character recognition | Bundled runtime (separate program) | Apache-2.0 |
| Tesseract support libraries | see [Tesseract OCR](#tesseract-ocr) | Image formats, text layout and compression for Tesseract | Bundled runtime (separate program) | Various (listed below) |
| Tesseract language data (eng, jpn, osd) | tessdata_fast | OCR language models | Bundled resources | Apache-2.0 |
| Noto Sans, Noto Serif, Noto Sans CJK JP | — | Fallback fonts for newly inserted text | Bundled resources | SIL Open Font License 1.1 |
| PyInstaller bootloader | 6.11.1 | Application launcher for `MonographPDF.exe` | Bundled launcher | GPL-2.0-or-later with bootloader exception |
| Inno Setup | 6.7 | Builds `Setup.exe`; its uninstaller `unins000.exe` is installed | Installer and uninstaller | Inno Setup License |
| Microsoft Office / LibreOffice | — | Optional Office→PDF / Word reflow | External (not included) | Vendor licenses |

## Corresponding source

Each release is published together with `MonographPDF_<version>_Source.zip` (for this release `MonographPDF_0.2.0_Source.zip`, listed in the release's `SHA256SUMS.txt`). It contains:

| Component | Version | License | Release files | In the source archive |
| :--- | :--- | :--- | :--- | :--- |
| Monograph PDF | 0.2.0 | AGPL-3.0-or-later | `MonographPDF.exe` (application code), `uninstall.exe` | `monograph-pdf/` — corresponding release source (application, build, installer, documentation and release tests; personal-document validation utilities excluded) |
| PyMuPDF | 1.25.3 | AGPL-3.0 | `_internal\pymupdf` | `third-party/pymupdf/pymupdf-1.25.3.tar.gz` (PyPI source distribution) |
| MuPDF | 1.25.4 | AGPL-3.0 | `_internal\pymupdf\mupdfcpp64.dll`, `_mupdf.pyd` | `third-party/mupdf/mupdf-1.25.4-source.tar.gz` (the MuPDF release PyMuPDF 1.25.3 builds) |
| pdf2docx | 0.5.8 | GPL-3.0 | inside `MonographPDF.exe` | `third-party/pdf2docx/pdf2docx-0.5.8.tar.gz` |
| PySide6 / Shiboken6 | 6.8.1.1 | LGPL-3.0 | `_internal\PySide6\*.pyd`, `_internal\shiboken6` | `third-party/qt/pyside-setup-everywhere-src-6.8.1.1.tar.xz` |
| Qt (qtbase, qtsvg, qtimageformats) | 6.8.1 | LGPL-3.0 | `_internal\PySide6\Qt6*.dll`, `plugins` | `third-party/qt/<module>-everywhere-src-6.8.1.tar.xz` |
| GLib, Pango, cairo, FriBidi, libthai, libdatrie, Graphite2, GNU libiconv, GNU gettext (libintl) | as listed under [Tesseract OCR](#tesseract-ocr) | LGPL-2.1-or-later (cairo LGPL-2.1 / MPL-1.1) | `engines\ocr` DLLs | `third-party/ocr-engine/<library>/mingw-w64-<library>-<version>.src.tar.zst`: the MSYS2 source package of the exact binary package (upstream release archive, PKGBUILD and every patch) |
| JBIG-KIT | 2.1 | GPL-2.0-or-later | `engines\ocr\libjbig-0.dll` | `third-party/ocr-engine/jbigkit/mingw-w64-jbigkit-2.1-5.src.tar.zst` (MSYS2 source package) |

Third-party archives are the unmodified upstream files, checked against their published or recorded SHA-256; `SOURCE_MANIFEST.json` in the archive lists every file with its hash and origin, and `README_SOURCE.md` explains how to build. Not requiring source distribution: the PyInstaller bootloader in `MonographPDF.exe` (GPL-2.0-or-later with the bootloader exception) and the GCC runtime libraries `libgcc_s_seh-1.dll` / `libstdc++-6.dll` (GPL-3.0-or-later with the GCC Runtime Library Exception). The remaining bundled components not listed above as requiring corresponding-source distribution use permissive licenses or applicable runtime/bootloader exceptions. The release build checks that every release file whose license requires corresponding source is covered by the source archive (`check_release.py check-source`).

## PyMuPDF and MuPDF

Monograph PDF uses PyMuPDF, the Python bindings for MuPDF, for PDF reading, rendering, and writing.

- Copyright © Artifex Software, Inc.
- License: GNU Affero General Public License v3.0 (also available under an Artifex commercial license)
- Source: `MonographPDF_0.2.0_Source.zip` (`third-party/pymupdf`, `third-party/mupdf`); upstream https://github.com/pymupdf/PyMuPDF and https://mupdf.com

PyMuPDF / MuPDF are licensed upstream under AGPL-3.0. Monograph PDF is licensed separately under **AGPL-3.0-or-later** (see `LICENSE.md`). MuPDF includes third-party libraries (for example FreeType, HarfBuzz, libjpeg, OpenJPEG, jbig2dec, lcms2, zlib and Gumbo) under their own permissive or compatible licenses; see the MuPDF source distribution. Monograph PDF does not enable MuPDF's JavaScript support, so scripts inside PDF documents are never run.

## Qt and PySide6

The user interface is implemented with Qt 6 through PySide6 and Shiboken6.

- Copyright © The Qt Company Ltd. and other contributors
- License: GNU Lesser General Public License v3.0
- Source: `MonographPDF_0.2.0_Source.zip` (`third-party/qt`); upstream https://code.qt.io/cgit/pyside/pyside-setup.git and https://download.qt.io

Qt libraries are shipped as separate dynamic libraries in the `_internal\PySide6` folder so that compatible builds may be substituted in accordance with the LGPL. Qt includes third-party code (for example FreeType, HarfBuzz, libjpeg, libpng, libwebp, libtiff and zlib) whose notices are part of the Qt distribution. The Monograph PDF build leaves out Qt Network, its TLS and network-information plugins, Qt Quick / QML, the virtual keyboard, the TUIO touch plugin and Qt PDF, none of which Monograph PDF uses.

## Python and its runtime libraries

The Python 3.11.9 runtime is bundled by PyInstaller under the Python Software Foundation License: https://www.python.org/ — together with libffi (MIT, for `ctypes`) and the `libcrypto` library of OpenSSL 3.0.13 (Apache License 2.0, https://www.openssl.org/) used for hash functions. Python's SSL module and `libssl` are removed from the build. The Python standard library also contains networking modules; Monograph PDF's code does not use them, and its self-check refuses and reports any network connection attempt.

## Microsoft Visual C++ and Universal C runtime

`VCRUNTIME140*.dll`, `MSVCP140*.dll`, `ucrtbase.dll` and the `api-ms-win-*.dll` forwarders are Microsoft redistributable runtime files shipped with Python, PySide6 and NumPy. They are distributed under the Microsoft Visual C++ Redistributable and Windows SDK license terms; Copyright © Microsoft Corporation.

## pdf2docx

PDF-to-Word conversion uses pdf2docx to reconstruct text, fonts, tables, images, columns, and page layout in an editable `.docx` file.

- Copyright © the pdf2docx contributors (originally by dothinking; maintained by Artifex Software)
- License: GNU General Public License v3.0 (compatible with AGPL-3.0 under section 13)
- Source: `MonographPDF_0.2.0_Source.zip` (`third-party/pdf2docx`); upstream https://github.com/ArtifexSoftware/pdf2docx

## OpenCV, NumPy, OpenBLAS, fontTools, python-fire, termcolor, and colorama

These libraries support pdf2docx during conversion.

- OpenCV — Apache License 2.0 — https://github.com/opencv/opencv-python
- NumPy — BSD 3-Clause — https://numpy.org
- OpenBLAS (scipy-openblas build shipped in `numpy.libs`) — BSD 3-Clause — https://www.openblas.net
- fontTools — MIT — https://github.com/fonttools/fonttools
- python-fire — Apache License 2.0 — https://github.com/google/python-fire
- termcolor — MIT — https://github.com/termcolor/termcolor
- colorama — BSD 3-Clause — https://github.com/tartley/colorama

The OpenCV wheel includes additional third-party notices (for example libpng, libjpeg-turbo, libtiff, libwebp, OpenJPEG and zlib built into `cv2.pyd`). OpenCV's FFmpeg video plugin (`opencv_videoio_ffmpeg*.dll`) is removed from the Monograph PDF build; FFmpeg is therefore not distributed.

## Office file writers

- python-docx — MIT — https://github.com/python-openxml/python-docx
- openpyxl and et_xmlfile — MIT — https://foss.heptapod.net/openpyxl/openpyxl
- python-pptx — MIT — https://github.com/scanny/python-pptx
- XlsxWriter — BSD-2-Clause — https://github.com/jmcnamara/XlsxWriter
- lxml — BSD-3-Clause — https://lxml.de (includes libxml2 and libxslt, MIT)
- packaging — Apache-2.0 OR BSD-2-Clause — https://github.com/pypa/packaging
- typing_extensions — PSF License — https://github.com/python/typing_extensions

## Pillow

- Copyright © 1997–2011 Secret Labs AB; © 1995–2011 Fredrik Lundh and contributors; © 2010 Jeffrey A. Clark and contributors
- License: MIT-CMU (Historical Permission Notice and Disclaimer)
- Source: https://github.com/python-pillow/Pillow

Pillow's wheel includes Brotli, FreeType, HarfBuzz, Little CMS (lcms2), libavif, libjpeg-turbo, libpng, libwebp, OpenJPEG, libtiff, XZ Utils (liblzma) and zlib-ng. Their license texts are collected in the `LICENSE` file of the Pillow 12.3.0 wheel (https://pypi.org/project/pillow/12.3.0/ and the Pillow source repository) and are permissive (MIT, BSD-style, IJG, zlib, libpng, 0BSD; FreeType under its FreeType License). Monograph PDF decodes only PNG, JPEG, BMP, GIF, TIFF and WEBP files supplied by a user; the AVIF code is present in the wheel but is not used on user files.

## Tesseract OCR

Monograph PDF ships a Windows build of Tesseract 5.4.0 (Leptonica 1.84.1) under `engines\ocr` and language data (`eng`, `jpn`, `osd`) under `models\tessdata` so that optical character recognition operates offline.

- Copyright © Google LLC and the Tesseract contributors
- License: Apache License 2.0
- Source: https://github.com/tesseract-ocr/tesseract, https://github.com/tesseract-ocr/tessdata_fast

Tesseract runs as a separate process and is not linked into `MonographPDF.exe`. This build has no network support (it is built without libcurl). The libraries shipped beside it keep their own licenses:

| Libraries | License |
| :--- | :--- |
| Leptonica | BSD-2-Clause |
| libarchive, OpenJPEG (`libopenjp2`), LZ4 | BSD-2-Clause |
| libwebp, libsharpyuv, PCRE2, Zstandard, libjpeg-turbo | BSD-3-Clause (libjpeg-turbo also IJG) |
| libpng | libpng license |
| libtiff | libtiff license (BSD-style) |
| zlib, bzip2 | zlib / bzip2 licenses |
| XZ Utils (`liblzma`) | 0BSD / public domain |
| libb2 (BLAKE2) | CC0-1.0 |
| Brotli, libdeflate, Expat, libffi, giflib, HarfBuzz, pixman, fontconfig | MIT-style |
| FreeType | FreeType License |
| LERC | Apache-2.0 |
| ICU | Unicode License |
| OpenSSL 3.3 (`libcrypto-3-x64`, used by libarchive) | Apache-2.0 |
| GLib 2.80.2, Pango 1.52.2, cairo 1.18.0, FriBidi 1.0.14, libthai 0.1.29, libdatrie 0.2.13, Graphite2 1.3.14, GNU libiconv 1.17, GNU gettext 0.22.5 (`libintl`) | LGPL-2.1-or-later (cairo LGPL-2.1 or MPL-1.1; Graphite2 also MPL-2.0 or GPL-2.0-or-later) |
| JBIG-KIT 2.1 (`libjbig`) | GPL-2.0-or-later |
| GCC runtime (`libgcc_s_seh`, `libstdc++`) | GPL-3.0-or-later with the GCC Runtime Library Exception |
| MinGW-w64 winpthreads | MIT and BSD-3-Clause |

These libraries are MSYS2 MinGW-w64 builds: each DLL is byte-identical to the DLL in the MSYS2 binary package of that version (for example `mingw-w64-x86_64-glib2-2.80.2-2`). The LGPL libraries are separate DLLs that may be replaced. The corresponding source of the GPL- and LGPL-licensed libraries — the MSYS2 source packages of exactly those binary packages, each containing the upstream release archive, the build script (PKGBUILD) and all patches — is included in `MonographPDF_0.2.0_Source.zip` (`third-party/ocr-engine/`).

## Fonts

`resources\fonts` includes Noto Sans, Noto Serif, and Noto Sans CJK JP. These fonts are used only as fallbacks when newly inserted text references a typeface that is not available on the host system. They are licensed under the SIL Open Font License 1.1 (`OFL.txt` is included with the font files). Monograph PDF does not redistribute Microsoft fonts.

## PyInstaller

`MonographPDF.exe` is produced with PyInstaller. The PyInstaller bootloader is licensed under GPL-2.0-or-later with a bootloader exception that permits use with programs under any license: https://pyinstaller.org

## Microsoft Office and LibreOffice (not included)

Monograph PDF does **not** include Microsoft Office or LibreOffice. When either suite is already installed, Monograph PDF may invoke it locally—through Office automation (macros forced off) or `soffice --headless` (with a throw-away profile in which macros are disabled)—to convert Word, Excel, and PowerPoint files to PDF, and may optionally use Microsoft Word PDF reflow for PDF-to-Word conversion. Those suites are external applications: they follow their own license terms, settings and remote-content behavior, which Monograph PDF does not control.

## Inno Setup

`Setup.exe` is built with Inno Setup by Jordan Russell and Martijn Laan (https://jrsoftware.org/isinfo.php) under the Inno Setup License. The Inno Setup uninstaller (`unins000.exe`) is installed with Monograph PDF so that it can be removed; `uninstall.exe` is Monograph PDF's own small launcher for it.
