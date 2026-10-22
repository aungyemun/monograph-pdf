# Windows runtime dependencies

## Supported Windows

Monograph PDF runs on Windows 10 version 1809 or later, and Windows 11, on x64. Setup refuses other systems (`MinVersion=10.0`, `ArchitecturesAllowed=x64compatible`).

Nothing has to be installed first: no Python, no Visual C++ Redistributable, no .NET download, no OCR engine, and no PATH change.

## How the dependencies were determined

`scripts/packaging/runtime_dependencies.py` reads the import table, including delay-loads, of every `.exe`, `.dll` and `.pyd` in the built installation layout. It classifies each imported DLL and runs no code while doing so. The release build runs it twice:

- `--place-app-local` copies the newest bundled VC++ DLL into `_internal` when a library could otherwise find it only through another package's folder.
- `--check` fails the build on any unresolved import, a VC++ DLL that is not bundled where the loader looks, or a 32-bit library.

Result for the 0.3.0 release build (tag `v0.3.0`, commit 96c36b9; 485 files, 456 MB unpacked), the same as for the earlier 0.3.0 development build 96b6c6f:

| Measure | Result |
|---|---|
| Program files inspected | 189 |
| Imported DLLs: bundled | 108 |
| Imported DLLs: part of Windows | 47 (API sets, kernel32, user32, gdi32, DirectWrite, Direct3D, UI Automation …) |
| Unresolved imports | 0 |
| Not x64 | 0 |
| `--check` | passed |

## Visual C++ 2015–2022 runtime

The runtime DLLs are bundled app-local. No Redistributable is installed.

| DLL | Used by (files) | Shipped at |
|---|---|---|
| vcruntime140.dll | 85 | `_internal`, `_internal/PySide6`, `_internal/shiboken6` |
| vcruntime140_1.dll | 18 | the same three folders |
| msvcp140.dll | 14 | `_internal` (placed by the build), `_internal/PySide6`, `_internal/shiboken6` |
| msvcp140_1.dll | 3 | `_internal/PySide6` (its only users are Qt libraries there) |
| msvcp140_2.dll | 1 | `_internal/PySide6` |

The bundled DLL versions are 14.38–14.39, from the Python 3.11 and PySide6 6.8.1 wheels. Two wheels were linked with a newer toolset than that runtime:

- Pillow, linked with 14.51;
- lxml, linked with 14.44.

They load and pass all tests with the bundled runtime. Microsoft documents the 2015–2022 runtime as binary compatible, *provided the runtime is at least as new as the newest toolset used*. This combination therefore works in practice but is outside Microsoft's stated guarantee. It is a documented limitation, kept under watch, and it is resolved by bundling a 14.44+ runtime if a problem appears.

Measured on the development PC, which also has a system-wide 14.51 runtime: the loaded-module list of the running program shows every VC++ DLL coming from the installation folder. The program does not depend on the system-wide copy.

## Universal C Runtime

The UCRT (`ucrtbase.dll`, the `api-ms-win-crt-*` sets) is a Windows component since Windows 10. The copies PyInstaller adds to `_internal` are used only if Windows' own copies are missing, which they never are on a supported Windows.

## Other components

| Component | Status |
|---|---|
| Python 3.11.9 runtime and standard library | bundled |
| Qt 6.8.1 (PySide6), platform plugin `qwindows` | bundled |
| MuPDF via PyMuPDF 1.25.3 | bundled |
| Pillow, NumPy, OpenCV (headless), lxml, fontTools, python-docx, python-pptx, openpyxl, pdf2docx | bundled |
| Tesseract OCR 5.4.0 and its libraries (`engines/ocr`, 52 files) | bundled, pinned by SHA-256 |
| OCR data eng, jpn, osd (tessdata_fast 4.1.0) | bundled, pinned by SHA-256 |
| .NET Framework 4.x (uninstall and update helpers, written in C#) | part of Windows 10 / 11 |
| Microsoft Office or LibreOffice | optional, for Office → PDF and Word reflow only; never bundled or installed |
| pytest, PyInstaller, pefile, Inno Setup, the C# compiler | development only; not in the installer (the audit found no test or build files in the layout) |

See [PREREQUISITE_MANAGEMENT.md](PREREQUISITE_MANAGEMENT.md) for the resulting policy, and [INSTALLER_PACKAGE_CONTENTS.md](INSTALLER_PACKAGE_CONTENTS.md) for the package audit.
