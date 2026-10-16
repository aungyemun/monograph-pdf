# Dependency inventory (Monograph PDF 0.2.0)

Every third-party component that is shipped with, or used to build or test, Monograph PDF. The release build enforces the shipped part: `scripts\packaging\check_release.py` fails when a program file (`.exe`, `.dll`, `.pyd`) does not belong to a component listed in its `RELEASE_COMPONENTS` table, or when that component is missing from `THIRD_PARTY_NOTICES.md`. Python packages are pinned in `requirements.txt`; the Tesseract build is recorded in `engines\ocr\MANIFEST.json`.

Status: **Runtime** = shipped in Setup.exe; **Build** = used only to produce the release; **Test** = development only; **External** = never shipped, used only if already installed.

| Component | Version | Purpose | Source / project | License | Status | Copyright / attribution | Security and update notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Python | 3.11.9 | Language runtime | python.org | PSF-2.0 | Runtime | Python Software Foundation | SSL module and `libssl` removed from the build; no network use by the app |
| OpenSSL libcrypto | 3.0.13 | `hashlib` | openssl.org | Apache-2.0 | Runtime | The OpenSSL Project | Comes with Python; only hashing is used |
| libffi | 3.4 | `ctypes` | sourceware.org/libffi | MIT | Runtime | Anthony Green, Red Hat and others | — |
| MSVC / UCRT runtime | 14.x / 10.0 | C/C++ runtime | Microsoft | VC++ Redistributable terms | Runtime | Microsoft Corporation | Shipped by Python, PySide6, NumPy wheels |
| PySide6 / Shiboken6 / Qt | 6.8.1.1 | User interface, printing | qt.io | LGPL-3.0 | Runtime | The Qt Company | Qt Network, TLS / network-information / TUIO plugins, Qt Quick/QML, virtual keyboard and Qt PDF removed; source (PySide6 6.8.1.1, Qt 6.8.1) in the source archive |
| PyMuPDF / MuPDF | 1.25.3 (MuPDF 1.25.4) | PDF engine | github.com/pymupdf/PyMuPDF | AGPL-3.0 (or Artifex commercial) | Runtime | Artifex Software | JavaScript support never enabled; follow MuPDF security releases; source in the source archive |
| pdf2docx | 0.5.8 | PDF → Word layout | github.com/ArtifexSoftware/pdf2docx | GPL-3.0 | Runtime | pdf2docx contributors | Pinned: newer versions require a newer PyMuPDF; source in the source archive |
| opencv-python-headless | 4.10.0.84 | Line/table detection for pdf2docx | github.com/opencv/opencv-python | Apache-2.0 | Runtime | OpenCV team | FFmpeg video plugin removed from the build |
| NumPy (+ OpenBLAS) | 2.1.3 | Arrays for pdf2docx / OpenCV | numpy.org | BSD-3-Clause | Runtime | NumPy developers | — |
| fontTools | 4.54.1 | Font metrics for pdf2docx | github.com/fonttools/fonttools | MIT | Runtime | fontTools authors | — |
| fire, termcolor, colorama | 0.7.1, 3.3.0, 0.4.6 | Import-time dependencies of pdf2docx | GitHub | Apache-2.0, MIT, BSD-3-Clause | Runtime | Google; termcolor and colorama authors | Not used by Monograph PDF itself |
| python-docx | 1.1.2 | Writing `.docx` | github.com/python-openxml/python-docx | MIT | Runtime | Steve Canny | — |
| openpyxl, et_xmlfile | 3.1.5, 2.0.0 | Writing `.xlsx` | heptapod.net/openpyxl | MIT | Runtime | openpyxl authors | — |
| python-pptx, XlsxWriter | 1.0.2, 3.2.9 | Writing `.pptx` | GitHub | MIT, BSD-2-Clause | Runtime | Steve Canny; John McNamara | — |
| lxml | 6.1.3 | XML for the Office writers | lxml.de | BSD-3-Clause | Runtime | lxml authors (libxml2/libxslt: MIT) | Parses only XML Monograph PDF writes |
| Pillow | 12.3.0 | Image import / export | python-pillow.org | MIT-CMU | Runtime | Secret Labs AB, Fredrik Lundh, Jeffrey A. Clark | Keep current: image decoders process untrusted files |
| packaging, typing_extensions | 24.2, 4.16.0 | Version parsing, typing | PyPA, python/typing_extensions | Apache-2.0 OR BSD-2-Clause, PSF | Runtime | PyPA; PSF | — |
| Tesseract OCR + Leptonica + support libraries | 5.4.0.20240606, Leptonica 1.84.1 | Offline OCR (separate process) | github.com/tesseract-ocr/tesseract, MSYS2 MinGW-w64 build | Apache-2.0; libraries as listed in THIRD_PARTY_NOTICES.md | Runtime | Google LLC and contributors | Built without libcurl (no URL input); started only with full path and fixed arguments; GPL/LGPL libraries (GLib 2.80.2, Pango 1.52.2, cairo 1.18.0, FriBidi 1.0.14, libthai 0.1.29, libdatrie 0.2.13, Graphite2 1.3.14, libiconv 1.17, gettext 0.22.5, JBIG-KIT 2.1; MSYS2 builds) with source and build recipes in the source archive |
| tessdata_fast (eng, jpn, osd) | vendored 2026-10-07 | OCR models | github.com/tesseract-ocr/tessdata_fast | Apache-2.0 | Runtime | Google LLC | Never downloaded at runtime |
| Noto Sans / Serif / Sans CJK JP | — | Fallback fonts | notofonts | OFL-1.1 | Runtime | Google LLC, Adobe | `fetch_fallback_fonts.py` downloads them at development time only |
| PyInstaller (bootloader) | 6.11.1 | `MonographPDF.exe` launcher | pyinstaller.org | GPL-2.0-or-later with bootloader exception | Runtime (bootloader) / Build | PyInstaller team | — |
| Inno Setup | 6.7.1 | `Setup.exe`, `unins000.exe` | jrsoftware.org | Inno Setup License | Runtime (uninstaller) / Build | Jordan Russell, Martijn Laan | — |
| .NET Framework C# compiler | 4.x (part of Windows) | Builds `uninstall.exe` | Microsoft | Windows component | Build | Microsoft | `uninstall.exe` needs no extra runtime |
| pyinstaller-hooks-contrib, altgraph, pefile, pywin32-ctypes | 2026.8, 0.17.5, 2023.2.7, 0.2.3 | PyInstaller dependencies; `pefile` also checks DLL imports after pruning | PyPI | GPL-2.0 / Apache-2.0, MIT, MIT, BSD-3-Clause | Build | respective authors | — |
| pytest, pytest-qt, pluggy, iniconfig | 8.3.4, 4.4.0, 1.6.0, 2.3.1 | Tests | PyPI | MIT | Test | respective authors | — |
| Microsoft Office / LibreOffice | — | Office → PDF, optional Word reflow | Microsoft / The Document Foundation | Vendor licenses | External | — | Macros forced off (Office `AutomationSecurity = 3`; LibreOffice profile with macros disabled); only installed copies in their own folders are started |

Not used: qpdf (listed in earlier inventories; never shipped — the empty `engines\qpdf` folder is a placeholder).

## Placement

| Kind | Location |
| :--- | :--- |
| Python environment (development) | `.\env` |
| Cached wheels (development) | `.\packages\wheels` |
| Build tools (Inno Setup) | `.\tools` |
| Native engines | `.\engines\ocr` |
| OCR language data | `.\models\tessdata` |
| Upstream license texts | `.\third_party\licenses` (GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MPL-1.1, GCC exception, Tesseract notice; installed into `{app}\licenses`), `resources\fonts\OFL.txt` |
| Third-party source archives (download cache, not in the repository) | `.\packages\sources` |

## Review notes

1. **AGPL / GPL / LGPL — corresponding source**: Monograph PDF is licensed **AGPL-3.0-or-later**; PyMuPDF/MuPDF retain upstream AGPL-3.0 (and pdf2docx, GPL-3.0). Every binary release is published with `MonographPDF_<version>_Source.zip`, built by `scripts\packaging\make_source_archive.py` from `scripts\packaging\third_party_sources.json`: Monograph PDF's source, the upstream source archives of PyMuPDF, MuPDF, pdf2docx, PySide6/Shiboken6 and Qt (qtbase, qtsvg, qtimageformats), and the MSYS2 source packages of the OCR engine's GPL/LGPL libraries (each DLL is byte-identical to the MSYS2 binary package of that version; `third_party_sources.json` records the DLL hashes, which `check-source` compares with the release). `check_release.py check-source` fails the release build if a release file whose license requires corresponding source is not covered. Exempt: PyInstaller bootloader (bootloader exception) and GCC runtime libraries (GCC Runtime Library Exception). A closed-source edition would need an Artifex commercial licence and replacing pdf2docx.
2. **LGPL (Qt, GLib/Pango/cairo in the OCR engine)**: shipped as separate, replaceable DLLs.
3. **No network at runtime**: do not add SDKs that call home, analytics, online OCR/APIs or updaters. The self-check (`--smoke-test`) and the test suite refuse and report network use.
4. **Adding a component**: add it to `requirements.txt` (pinned), to `RELEASE_COMPONENTS` in `scripts\packaging\check_release.py`, to this inventory and to `THIRD_PARTY_NOTICES.md`; otherwise the release build fails.
