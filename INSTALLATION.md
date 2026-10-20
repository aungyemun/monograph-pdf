# Installation

Offline Windows installer for Monograph PDF. Python, Qt, and OCR are bundled.

## Requirements

| | Minimum | Recommended |
| :--- | :--- | :--- |
| OS | Windows 10 x64 | Windows 11 x64 |
| RAM | 4 GB | 8 GB+ |
| Disk | 1 GB free | 2 GB |
| Display | 1280×720 | 1920×1080+ |
| Office suite | — | Optional, for Office → PDF |

## Install

Run `Setup.exe` (`installer\MonographPDF_{version}_Setup.exe`).

* **All users** → `C:\Program Files\Monograph PDF` (admin)
* **Current user** → `%LOCALAPPDATA%\Programs\Monograph PDF`

Setup copies the app, OCR data, docs, and `uninstall.exe`; registers file types if selected; then runs an offline self-check (`install_smoke_test.json` under `%LOCALAPPDATA%\Monograph PDF\logs`). Upgrades replace owned app files only; settings and documents stay.

### Silent (admins)

```bat
MonographPDF_0.2.3_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
MonographPDF_0.2.3_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="D:\Apps\Monograph PDF" /MIGRATEINSTALL
```

Same path = in-place upgrade. Different `/DIR` without `/MIGRATEINSTALL` keeps the registered location. Stops if `MonographPDF.exe` is running.

## File types

| Option | Default |
| :--- | :--- |
| Register for `.pdf` (Open with / Default apps) | On |
| Open with for images and Office files | On |

Setup never silently becomes the default PDF app. Use **Help ▸ Make Monograph PDF the Default PDF App…** or Windows **Open with ▸ Always**.

## Uninstallation

**Settings ▸ Apps ▸ Installed apps** → **Monograph PDF**, or run `uninstall.exe`.

Removes the install folder contents Setup owns, shortcuts, registrations, recent files, and `%LOCALAPPDATA%\Monograph PDF` working data. Settings (`%APPDATA%\Monograph PDF`) are optional. Your documents are never removed.

```bat
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
"C:\Program Files\Monograph PDF\uninstall.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REMOVEUSERDATA
```

## Offline smoke check

On a clean offline PC: install → open a PDF → fill a field → PDF to Word → protect/unlock → OCR → uninstall with settings removed. Expect `install_smoke_test.json` with `"passed": true`. Automated: `scripts\test_installer.ps1` ([Testing](docs/TESTING.md#installer-and-uninstaller-test)).

## Troubleshooting

1. Re-run Setup.
2. Check `%LOCALAPPDATA%\Monograph PDF\logs\install_smoke_test.json` or `MonographPDF.exe --smoke-test`.
3. Check antivirus quarantine for `MonographPDF.exe` / `_internal`.
4. Office → PDF: **Help ▸ About Monograph PDF ▸ Office Integration**.

Builds are **not code-signed**. Compare Setup with `SHA256SUMS.txt` before **More info ▸ Run anyway**.

Developers: [Build and Runtime](docs/BUILD_AND_RUNTIME.md) · [Release](docs/RELEASE_AND_VERSIONING.md).

© 2026 Aung Ye Mun. **AGPL-3.0-or-later** — [LICENSE.md](LICENSE.md). Source: `MonographPDF_{version}_Source.zip`.
