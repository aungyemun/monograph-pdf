# Release checklist

Use this list for every public release (`X.Y.Z` = the version in `VERSION`). Each item says whether a
script checks it (**automated**) or a person must (**manual**). A release is not published until every
item is done. If an item could not be checked, record it as **NOT VERIFIED** in the release notes;
never as passed.

Nothing in this list publishes anything by itself. Publishing, tagging and editing a published
release are always deliberate maintainer steps.

## 1. Before building

| # | Item | How |
|---|---|---|
| 1.1 | Everything committed; on `main` | manual: `git status`; the source archive is made from the committed files and the build stops on uncommitted changes to them |
| 1.2 | `VERSION`, `CITATION.cff` `version`, `THIRD_PARTY_NOTICES.md`, `licenses/DEPENDENCY_INVENTORY.md` and `scripts/packaging/third_party_sources.json` name `X.Y.Z` | automated by `verify_release.py` (step 3); fix by hand |
| 1.3 | `CHANGELOG.md` has `## [X.Y.Z] — Unreleased` describing every user-visible change | manual |
| 1.4 | Third-party versions changed? Update `THIRD_PARTY_NOTICES.md`, `licenses/DEPENDENCY_INVENTORY.md` and `third_party_sources.json` together | manual (compare `pip freeze` with the inventory) |
| 1.5 | Windows CI green on the commit to be released | automated (`.github/workflows/windows-ci.yml`); check the run page |
| 1.6 | OCR engine prepared with `scripts\vendor_ocr.ps1` ([Build and Runtime](BUILD_AND_RUNTIME.md#ocr-engine-and-language-data)) | automated: the build stops unless every OCR file matches `scripts/ci/ocr_engine_pins.json` |

## 2. Build

| # | Item | How |
|---|---|---|
| 2.1 | `installer\build_release.bat` completes | automated: tests (JUnit counts), exe, smoke test, Setup, Source.zip, Installer.zip, contents check, release-set check |
| 2.1a | Release files of the previous version left in `installer\` are moved to `build\superseded\<version>\`, only when an identical copy is archived under `releases\` (step 6.5); otherwise the build stops | automated (`check_release.py superseded`) |
| 2.2 | Record the test counts printed in `installer\build_release_summary.txt` (`P passed, F failed, S skipped`) | manual: copy into the notes |
| 2.3 | Skipped tests: note why (private PDFs, Office, …) | manual: `pytest -rs` output |

The build accepts an `Unreleased` CHANGELOG entry (`--allow-unreleased`); publishing does not (step 5).

## 3. Installer and application checks

| # | Item | How |
|---|---|---|
| 3.1 | `scripts\test_installer.ps1` (install, launch, shortcuts, uninstall, reinstall, upgrade) | automated; record `passed / failed / skipped`. It installs a per-user test copy and backs up / restores the Monograph PDF settings: run it only on a test computer |
| 3.1a | [Windows release test checklist](WINDOWS_RELEASE_TEST_CHECKLIST.md) on real computers: clean install, upgrade from the previous version (settings kept), functions, update checking, offline use, uninstall/reinstall; `scripts\windows_release_check.ps1` (read-only) | manual; record each item PASS / FAIL / NOT TESTED |
| 3.2 | Launch the installed app, open a PDF, save, print preview | manual |
| 3.3 | Physical printing on a real printer | manual; if not done, write **NOT VERIFIED** in the notes |
| 3.4 | SmartScreen / unsigned-installer warning still described correctly in `INSTALLATION.md` | manual ([CODE_SIGNING.md](CODE_SIGNING.md)) |

## 4. Freeze

| # | Item | How |
|---|---|---|
| 4.1 | Replace `Unreleased` with the release date in `CHANGELOG.md`; add `date-released` to `CITATION.cff` | manual |
| 4.2 | Rebuild (step 2) so the archives carry the dated files | automated |
| 4.3 | Commit; tag `vX.Y.Z` on that commit (annotated) | manual, maintainer only |

## 5. Release notes and the release set

| # | Item | How |
|---|---|---|
| 5.1 | Write `docs/releases/vX.Y.Z.md` with the sections in [Release-notes structure](#release-notes-structure) | manual |
| 5.2 | Validate notes and release files together | automated, must print `RESULT: PASS`: |

```powershell
.\env\Scripts\python.exe scripts\packaging\verify_release.py --dir installer --version X.Y.Z `
    --layout dist\MonographPDF --notes docs\releases\vX.Y.Z.md --tests P,F,S
```

This fails on unresolved template values (`__X__`, `{{ }}`, `TODO`, …), checksums that do not match
the files, other versions' file names, missing test or installer results, broken links, a missing or
`Unreleased` CHANGELOG date, backslash ZIP entry names, missing notices and private paths.

### Release-notes structure

Use these sections, in this order, and leave out any that would be empty. Keep sentences short.

1. **Summary** — one or two sentences: the kind of release (for example, a maintenance release
   focused on security and reliability) and whether it adds user-facing features. State
   compatibility with the previous version only as far as it was tested.
2. **Download** — the three files with their SHA-256 values and the PowerShell command
   `Get-FileHash .\MonographPDF_X.Y.Z_Setup.exe -Algorithm SHA256`. Unsigned-installer wording:
   "Monograph PDF is currently distributed without a code-signing certificate, so Windows
   SmartScreen may display a warning. Download the installer only from this release page and verify
   its SHA-256 checksum before deciding whether to continue."
3. **Security updates**, 4. **Defects corrected**, 5. **Improvements** — what changed, precisely.
6. **Compatibility** — Windows versions; upgrade path and how it was tested.
7. **Verification** — exact test counts, each with the build or CI run it comes from; installer
   test result; anything **NOT VERIFIED** (for example physical printing).
8. **Known limitations** — including "not code-signed".
9. **Source** — `MonographPDF_X.Y.Z_Source.zip` is the corresponding source of Monograph PDF and of
   the bundled AGPL, GPL and LGPL components. The **Source code** archives GitHub adds to the release
   contain only the repository at the tag, without the third-party sources.

## 5b. Provenance, SBOM and signing

- [ ] `build\installer\MonographPDF_<version>_provenance.json` names the release commit (clean tree) and the SHA-256 of every output; `python scripts\packaging\provenance.py verify --record … --dir installer` passes ([RELEASE_PROVENANCE.md](RELEASE_PROVENANCE.md)).
- [ ] `build\installer\MonographPDF_<version>_SBOM.cdx.json` is generated and `make_sbom.py --check` passes.
- [ ] Signing status decided by the Signing Approver ([CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md)); an unsigned release says so in its notes. A signed release: approval recorded, `Get-AuthenticodeSignature` → `Valid` for every own binary.

## 5c. Signed update manifest (releases with update checks switched on — from 0.4.1)

| # | Item | How |
|---|---|---|
| 5c.1 | Sign `installer\MonographPDF_update_manifest.json` locally with the production key and the **next** sequence number from the sequence log; never in CI | manual: `update_manifest.py make` in the signing environment ([Secure updates](SECURE_UPDATES.md#maintainer-tooling)) |
| 5c.2 | `update_manifest.py verify` passes; `verify_release.py` (step 5.2) prints `PASS update-manifest` | automated |
| 5c.3 | Add the line to the sequence log and refresh the key backup's copy of it | manual |

## 6. Publish (maintainer)

Published releases are **immutable** (repository setting): nothing in a release can be changed or
added after publication. Create it as a draft, check it, then publish.

| # | Item | How |
|---|---|---|
| 6.1 | Push the commit and the tag | manual |
| 6.2 | Create a **draft** GitHub release from the tag with **the exact text of `docs/releases/vX.Y.Z.md`** (for example `gh release create vX.Y.Z --draft --verify-tag --notes-file docs/releases/vX.Y.Z.md …`); never paste a template | manual |
| 6.3 | Attach exactly the files `MonographPDF_X.Y.Z_Setup.exe`, `_Installer.zip`, `_Source.zip` and (5c) `MonographPDF_update_manifest.json`; check the draft; publish (`gh release edit vX.Y.Z --draft=false`) only after an explicit decision | manual |
| 6.4 | Re-check what was published: download the assets into an empty folder and the published body (`gh release view vX.Y.Z --json body -q .body > published.md`), then run `verify_release.py --dir <folder> --notes published.md` and `update_manifest.py verify --manifest <folder>\MonographPDF_update_manifest.json`; on an installed previous version, **Check for Updates** | automated check, manual run |
| 6.5 | Archive the frozen release under `releases\MonographPDF_X.Y.Z\` | manual; `guard-frozen` prevents overwriting |

## 7. After publishing

* Bump `VERSION` to the next development version, add `## [next] — Unreleased`, remove
  `date-released` from `CITATION.cff` (see [RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md)).
* A mistake found in published notes is corrected by editing the release text from a corrected
  `docs/releases/vX.Y.Z.md`; assets and tags are never replaced or moved. Say in the notes what was
  corrected.

## Related

[RELEASE_AND_VERSIONING.md](RELEASE_AND_VERSIONING.md) · [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md) ·
[TESTING.md](TESTING.md) · [CODE_SIGNING.md](CODE_SIGNING.md)
