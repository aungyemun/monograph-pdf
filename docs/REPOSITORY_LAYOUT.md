# Repository layout and ownership

The unified `main` tree contains one shared application. Organize by responsibility first;
use platform-specific adapters and packaging entry points only where the OS requires them.
This standardization preserves existing paths. No Python modules, resources or build scripts
are relocated, and no second platform implementation is introduced.

## Directory map

| Location | Responsibility and boundary |
| :--- | :--- |
| `app/` | Application startup, single-instance handover and smoke test |
| `core/` | Shared PDF model, editing, forms, conversion, OCR orchestration, settings and security |
| `ui/` | Shared PySide6 windows, panels, dialogs and themes |
| `engines/` | Shared MuPDF backend and PDF edit baking; `engines/ocr/` is the staged native OCR location |
| `platforms/` | Canonical platform identification; reuse existing helpers rather than duplicating them |
| `installer/` | Windows installer identity, update/uninstall helpers and Linux per-user install script |
| `scripts/` | Stable setup/run/build entry points; see [script map](../scripts/README.md) |
| `scripts/packaging/` | Shared archive, provenance, dependency and release verification tooling |
| `scripts/ci/` | CI-only OCR staging and pins |
| `scripts/audit/` | Developer audit tools, separate from application runtime |
| `scripts/signing/` | Maintainer tooling only; production keys do not belong in the repository |
| `resources/` | Official branding, fonts, styles, OCR catalog and update trust configuration |
| `versions/` | Independent Windows/Linux/macOS versions; root `VERSION` mirrors Windows |
| `tests/` | `unit/`, `integration/`, `ui/`; shared synthetic inputs in `fixtures/` |
| `docs/` | Canonical guides, `images/` screenshots, `releases/` historical notes; [index](README.md) |
| `reports/` | Engineering results and limitations, not runtime dependencies |
| `licenses/` | Dependency inventory; preserve upstream attribution |
| `third_party/` | Redistributed upstream license texts, not downloaded source caches |
| `services/` | Separately deployed report gateway; not bundled with the desktop application |

Generated `env/`, `build/`, `dist/`, `packages/`, `runtime/`, `models/tessdata/` and native
OCR binaries are local build/runtime material. Do not add placeholders for generated trees.
Keep private documents, credentials and signing keys outside version control.

## Platform entry points

| Concern | Windows | Linux | macOS |
| :--- | :--- | :--- | :--- |
| Setup / launch / tests | `scripts/{setup_env,dev_launch,run_tests}.ps1` | Same names with `.sh` | Same names with `.sh` |
| OCR staging | `scripts/vendor_ocr.ps1` | `scripts/vendor_ocr.sh` | `scripts/vendor_ocr_macos.sh` |
| Native build / package | `scripts/build_exe.ps1`, `installer/build_release.bat` | `installer/linux/install.sh` consumes a built tree | `scripts/build_app.sh`, `scripts/package_macos.sh` |
| Desktop integration | Existing Windows branches in shared adapters | `core/linux_desktop.py` and XDG tools | Finder/System Settings paths in existing adapters |
| Version | `versions/windows.txt` + root `VERSION` mirror | `versions/linux.txt` | `versions/macos.txt` |

Common path resolution stays in `core/platform_paths.py`, `app/paths.py` and
`core/ocr/paths.py`; instance locking stays in `app/single_instance.py`. Host selection uses
`sys.platform`/`platforms.name()`. New OS behavior should extend those boundaries, not fork
the shared PDF core. Existing OS branches inside shared adapters are intentional.

## Compatibility boundaries

* Windows: preserve Inno AppId, executable names, registry/file associations, installer scope,
  migration and upgrade rules. Settings use `%APPDATA%/Monograph PDF`; local data uses
  `%LOCALAPPDATA%/Monograph PDF`.
* Linux: preserve `MonographPDF`, desktop/MIME integration and the per-user installer contract.
  Settings use `$XDG_DATA_HOME/monograph-pdf` (default `~/.local/share/monograph-pdf`);
  caches use `$XDG_CACHE_HOME/monograph-pdf` (default `~/.cache/monograph-pdf`).
* macOS: preserve `com.aungyemun.monographpdf`, `.app/Contents` layout, and the existing numeric
  bundle-version mapping. Settings/local data use `~/Library/Application Support/Monograph PDF`;
  caches use `~/Library/Caches/Monograph PDF`.
* Preserve `MONOGRAPH_PDF_*` overrides and supported migration aliases. Use existing path
  helpers and Unicode-safe paths; never infer user settings locations from the working directory.
* Keep resource discovery relative to the source/frozen application layout. Logo, installed help,
  OCR models and trust configuration paths are packaging contracts. Do not rename them casually.

## Change and test policy

Keep the current stable command paths. A future physical relocation must update imports,
PyInstaller data collection, installer/source archive rules, tests, CI and documentation in one
reviewed change, with relevant tests run after each move. No empty OS folders or forwarding
runtime implementations are needed for this documentation phase.

Keep tests organized by behavior and scope, with OS guards for native dependencies. Put reusable
synthetic documents in `tests/fixtures/`, generated outputs under ignored `tests/outputs/` paths,
and private acceptance evidence outside the repository. All three CI workflows must succeed on
the PR; skipped cases remain unverified. Native install/upgrade, Gatekeeper, desktop integration,
physical printing, Office and OCR acceptance still require appropriate native machines.
