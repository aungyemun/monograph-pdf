# Release and versioning

## Single source of truth

`VERSION` at the repository root is the only authoritative application version. Product version, executable metadata, About page, manifests, release packages, and diagnostics must derive from it via `core.versioning` / `app.read_version`. Never maintain independent version strings in code.

## Scheme

- Initial version: `0.0.1`
- Successful application / runtime / UI / resource / dependency fixes **increment patch automatically**:
  - `0.0.1` → `0.0.2` → … → `0.0.99` → `0.1.0`
  - then `0.1.0` → `0.1.1` → …
- Significant milestones may deliberately advance the minor version (manual intentional write to `VERSION`). Version numbers below 0.2.0 belong to internal development and were never part of a public release; 0.2.0 is the first public release version.
- Failed build/test must **not** consume an official version bump
- Pure non-runtime documentation edits need no bump unless shipped behavior/content changes

## Tooling

```powershell
.\env\Scripts\python.exe scripts\read_version.py
.\env\Scripts\python.exe scripts\bump_version.py
.\env\Scripts\python.exe scripts\bump_version.py --print
```

Bump only after a successful fix that warrants it (see scheme above).

## Release packaging

1. Add the user-visible changes to `CHANGELOG.md` under the version in `VERSION`.
2. Run the release build: `installer\build_release.bat` (tests → exe → self-check → `uninstall.exe` → Setup → source archive → `MonographPDF_{version}_Installer.zip`; see [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md#release-build-installer)).
3. Run the installer test: `scripts\test_installer.ps1` (install → launch → uninstall → reinstall, upgrade matrix, internal-compatibility checks; see [TESTING.md](TESTING.md#installer-and-uninstaller-test)).
4. Publish `installer\release\`: `Setup.exe` (or `installer\MonographPDF_{version}_Installer.zip`) **always together with** `MonographPDF_{version}_Source.zip` and `SHA256SUMS.txt` (hashes for Setup.exe, MonographPDF.exe and the source archive). The source archive is the corresponding Monograph PDF release source (application, build, installer, documentation and release tests) plus the corresponding source of the bundled AGPL / GPL / LGPL components, as the licenses require; local personal-document validation utilities are excluded. Never publish an installer without the source archive of the same build. `installer\build_release_summary.txt` lists all SHA-256 hashes.
5. Release folder documents for end users: `README.md`, `INSTALLATION.md`, `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `SECURITY.md`, `CITATION.cff`, `CHANGELOG.md`, `docs/USER_GUIDE.md`, plus `licenses\`. Do **not** put developer-only docs (`ARCHITECTURE`, `BUILD_AND_RUNTIME`, `FEATURES`, `FILE_FORMATS_AND_COMPATIBILITY`, `RELEASE_AND_VERSIONING`, `TESTING`, `SECURITY_AND_PRIVACY`) into the installer ZIP or the installed application — they remain in the repository and the source archive.
6. License texts (`LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `third_party/licenses/`) are packaged by the build. Audits are kept in `reports/audit/` (update the existing files in place; do not create duplicate “final/latest” copies).

## Release status and frozen releases

- A version stays **Unreleased** in `CHANGELOG.md` (`## [x.y.z] — Unreleased`) until full validation, the installer and internal-compatibility tests, the branding scan and the source-compliance check pass **and** the maintainer approves the release freeze. Only then does it get its date, and `CITATION.cff` its `date-released`. Monograph PDF **0.2.0 is the first public release version**.
- A released (frozen) public version is never rebuilt or changed: its installer, source archive, `SHA256SUMS.txt`, audit report and changelog entry stay as published. Keep a byte-for-byte copy of its release folder under `releases\<Product>_<version>\` (read-only); the release build refuses to replace `installer\release\` while it holds another version's release that is not archived there (`check_release.py guard-frozen`).
- **Internal development archive:** the last internal development build (0.1.5, 2026-10-15) is kept byte for byte in `releases\PDFEditor_0.1.5\` (Setup SHA-256 `6EF9072C…A891`, source archive `D97C1147…F950F`) and must never be modified. It is an internal freeze only — not a public Monograph PDF release and not a prior public product under another name. Monograph PDF 0.2.0 is Unreleased until freeze.

## Repository

The source repository is `monograph-pdf` (https://github.com/aungyemun/monograph-pdf, private). `.gitignore` keeps out build output (`build/`, `dist/`, `_internal/`, `MonographPDF.exe`), environments, installers and ZIPs, `releases/`, test outputs and generated samples, third-party downloads, the personal-document validation utilities, and keys or certificates.

## Related

- Build: [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md)
- Testing: [TESTING.md](TESTING.md)
