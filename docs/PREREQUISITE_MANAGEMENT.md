# Prerequisite management

## Decision: Setup.exe installs no system-wide prerequisite

The decision rests on binary inspection of the built program. [WINDOWS_RUNTIME_DEPENDENCIES.md](WINDOWS_RUNTIME_DEPENDENCIES.md) has the evidence. Every native dependency of Monograph PDF is in one of these groups:

| Class | Examples | How it is satisfied |
|---|---|---|
| A. Bundled | Python 3.11 runtime, Qt 6.8 / PySide6, MuPDF (PyMuPDF), Pillow, lxml, NumPy, OpenCV, Tesseract OCR 5 with eng/jpn/osd data, the Microsoft Visual C++ 2015–2022 runtime DLLs (app-local), the Universal CRT forwarders | shipped inside the installation folder |
| B. Windows baseline (Windows 10 1809+ / 11, x64) | kernel32, user32, gdi32, DirectWrite, Direct2D/3D, UI Automation, the Universal C Runtime (a Windows component since Windows 10), .NET Framework 4.8 (for the small uninstall and update helpers) | part of every supported Windows |
| C. Optional external application | Microsoft Office or LibreOffice (only for Word/Excel/PowerPoint → PDF and Word's PDF reflow) | detected; never installed, bundled or required |
| D. Required redistributable prerequisite | none | — |
| E. Development only | pytest, pytest-qt, PyInstaller, pefile, ruff, Inno Setup, the C# compiler | never in Setup.exe |

### The Visual C++ runtime is app-local

The Visual C++ runtime is shipped **app-local**. Microsoft permits redistribution of these DLLs with an application under the Visual Studio redistribution terms ("Distributable Code"). Three facts were verified:

1. **Every importer finds a bundled copy.** Every program file that imports `vcruntime140*.dll` or `msvcp140*.dll` finds a bundled copy in its own folder or in `_internal`.
2. **The DLLs are loaded from the installation.** A loaded-module listing of the running program shows the VC++ DLLs coming from the installation folder, even on a PC that also has a newer system-wide runtime (14.51).
3. **The search-path case is fixed.** MuPDF and some Qt plug-ins could otherwise find `MSVCP140.dll` only through PySide6's folder. That would make loading depend on import order. The build therefore places a copy in `_internal` (`runtime_dependencies.py --place-app-local`), and `--check` fails the build if such a case reappears.

Because nothing system-wide is needed, cases A–F of a prerequisite installer do not apply. The table states what Setup.exe does in each case:

| Case | Situation | Monograph PDF Setup |
|---|---|---|
| A | VC++ runtime not installed | nothing to install; the app uses its own copies |
| B | older system runtime | not touched |
| C | same version | not touched |
| D | newer system runtime | not touched; never downgraded |
| E | satisfies minimum, older than bundled | not touched (no unnecessary system change) |
| F | detection ambiguous | no detection is performed, because nothing depends on it |

**Test matrix.** The prerequisite test matrix (scenarios 1–12) is therefore **not applicable**: no prerequisite installer is executed. Scenario 12, an offline installation, applies to the whole installer and was exercised by installing from the local Setup.exe with no network access needed. See [CLEAN_WINDOWS_INSTALLATION.md](CLEAN_WINDOWS_INSTALLATION.md).

## If a prerequisite ever becomes necessary

The following policy applies if a future change requires a system-wide prerequisite:

- **Source.** Download only from the publisher's official source, and verify its Authenticode signature and SHA-256.
- **Pinning.** Record the exact version, source, hash, licence and redistribution right in this document, and pin the file in the build.
- **Detection.** Detect with the publisher's documented method. For the VC++ x64 runtime, that is `HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64` (`Installed`, `Major`, `Minor`, `Bld`).
- **Install or upgrade.** Install only when the runtime is absent or older than the minimum. Never downgrade, and never replace a working newer version.
- **Corrupted or wrong installers.** Reject an installer with a wrong hash or architecture before running it.
- **Failures and restarts.** Report failures without changing anything else, and honour a requested restart.

## Inventory of bundled components

Versions, licences and sources are listed in `THIRD_PARTY_NOTICES.md` and in the SBOM produced with each build (`scripts/packaging/make_sbom.py`). OCR language data is pinned by SHA-256 in `resources/ocr/language_packs.json` and `scripts/vendor_ocr.ps1`. Nothing is downloaded at build time without a pinned hash. At run time only an optional OCR language you choose to download (OCR ▸ OCR Languages ▸ Download and Install) is fetched, and it is installed only if it matches its pin.
