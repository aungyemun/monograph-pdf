# Developer script map

Run commands from the repository root. Existing entry points are retained because CI, packaging
and maintainer workflows depend on them. The layout is organized logically without moving scripts.

| Purpose | Entry points |
| :--- | :--- |
| Setup, launch, tests | `setup_env`, `dev_launch`, `run_tests`: `.ps1` on Windows, `.sh` on Linux/macOS |
| Windows build | `build_exe.ps1`, `build_release.ps1`; public build entry point `../installer/build_release.bat` |
| Linux native install | `../installer/linux/install.sh` (requires an already built tree) |
| macOS build/package | `build_app.sh`, `package_macos.sh` (native macOS tools required) |
| OCR staging | `vendor_ocr.ps1`, `vendor_ocr.sh`, `vendor_ocr_macos.sh` |
| Shared packaging checks | `packaging/`: source archives, metadata, notices, provenance and verification |
| CI support | `ci/`: native OCR staging and file pins |
| Audit/acceptance | `audit/`, `deep_ui_audit.py`, `test_installer.ps1` |
| Maintainer signing | `signing/`; separate controlled operation, not ordinary development setup |

See [Build and runtime](../docs/BUILD_AND_RUNTIME.md), [repository ownership](../docs/REPOSITORY_LAYOUT.md)
and [testing](../docs/TESTING.md). Do not run installer acceptance against a working user installation.
No setup, test or documentation change authorizes accessing production keys or publishing a release.
