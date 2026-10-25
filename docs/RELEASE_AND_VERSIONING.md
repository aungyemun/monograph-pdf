# Release and versioning

## Source of truth

Independent platform lines (Option B):

| Platform | File | Current |
| :--- | :--- | :--- |
| Windows | `versions/windows.txt` | 0.5.0 |
| Linux | `versions/linux.txt` | 0.1.0 |
| macOS | `versions/macos.txt` | 0.1.0 |

Root `VERSION` **mirrors the Windows line** for existing Windows packaging tools. Runtime and scripts
must use `core.versioning.get_version()` / `scripts/read_version.py` (`--platform` / `--all`).
See [CROSS_PLATFORM_DEVELOPMENT.md](CROSS_PLATFORM_DEVELOPMENT.md).

A Linux or macOS bump must **not** change the Windows version (or root `VERSION`).

## Scheme

* Patch bumps after successful app/runtime/UI/resource/dependency fixes (`0.2.0` → `0.2.1` …; `0.0.99` → `0.1.0`).
* Minor bumps are intentional milestones. Below 0.2.0 = internal only; **0.2.x** is the first public line;
  **0.5.0** is the current feature release, following **0.4.0** (0.3.0 added secure updates and
  private problem reports, still switched off; 0.5.0 is the first published version with update
  checks switched on).
* After 0.5.0: bug fixes, security patches and stability improvements go into **0.5.x** releases;
  new features wait for **0.6.0**, the next feature milestone. (0.4.1 was prepared and 0.4.2 built for
  testing; neither was released, and their changes went into 0.5.0.)
* A version prepared but never released is folded into the next public release (0.2.4 into 0.3.0; 0.4.1 and 0.4.2 into 0.5.0);
  no historical release is invented for it.
* Failed builds/tests do not bump. Pure doc-only edits usually do not bump.

```powershell
.\env\Scripts\python.exe scripts\read_version.py
.\env\Scripts\python.exe scripts\bump_version.py
```

## Package a release

Follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) step by step. In short:

1. Update `CHANGELOG.md` for the version in `VERSION`.
2. `installer\build_release.bat` → tests (JUnit counts), exe, smoke, Setup, Source.zip, Installer.zip, contents check, release-set check (`scripts\packaging\verify_release.py`) ([BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md#release-build)).
3. `scripts\test_installer.ps1` ([TESTING.md](TESTING.md#installer-and-uninstaller-test)).
4. Write the release notes in `docs/releases/vX.Y.Z.md` and check them together with the files: `verify_release.py --dir installer --notes docs\releases\vX.Y.Z.md --tests P,F,S` must print `RESULT: PASS`.
5. Publish Setup, Installer.zip and Source.zip with exactly that notes file as the release text, then re-check what was published.
   Once updates are enabled for production ([SECURE_UPDATES.md](SECURE_UPDATES.md#production-setup)), also sign and attach
   `MonographPDF_update_manifest.json` (`scripts\packaging\update_manifest.py make` / `verify`) — never before.
6. End-user docs in the release ZIP: README, INSTALLATION, LICENSE, notices, SECURITY, CITATION, CHANGELOG, USER_GUIDE, `licenses\`. Developer docs stay in the repo/source archive only.

Releases are not code-signed ([CODE_SIGNING.md](CODE_SIGNING.md)).

## Freeze rules

* Stays **Unreleased** until validation + maintainer freeze; then date + `CITATION.cff` `date-released`.
* Frozen releases are never rebuilt. Archive under `releases\<Product>_<version>\`. `guard-frozen` blocks overwrite otherwise.
* Internal archive: `releases\PDFEditor_0.1.5\` (not a public release).

## Related

[BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md) · [TESTING.md](TESTING.md) · [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) · [CODE_SIGNING.md](CODE_SIGNING.md)
