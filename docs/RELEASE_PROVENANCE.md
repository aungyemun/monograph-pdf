# Release provenance

How a published Monograph PDF file can be traced to the commit it was built from, what is
reproducible, and what is not. Related: [OFFICIAL_DOWNLOAD_VERIFICATION.md](OFFICIAL_DOWNLOAD_VERIFICATION.md),
[CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md), [BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md).

## Where releases are built

Releases are built on the maintainer's Windows workstation with `installer\build_release.bat`
(`scripts\build_release.ps1`), from a commit of https://github.com/aungyemun/monograph-pdf. GitHub
Actions runs the tests (and generates an SBOM) for every change but does not build or publish
releases. A release built on a workstation can be traced and its source reproduced, but its binaries
are not attested by an independent build service (see [Path to CI-built releases](#path-to-ci-built-releases)).

## Traceability chain

| Link | Evidence | Checked by |
| :--- | :--- | :--- |
| Commit → source archive | `MonographPDF_X.Y.Z_Source.zip` is made from the committed files of `HEAD` (never from untracked or uncommitted files; the build stops if selected files have uncommitted changes) and records the commit in `SOURCE_MANIFEST.json` | `make_source_archive.py`, `tests/unit/test_source_archive.py` |
| Commit → program | From 0.3.0 the build writes `resources\build_info.json` (commit, uncommitted-changes flag, version) into the program; **About** shows the commit | `scripts/build_exe.ps1`; `verify_release.py --layout` (*provenance*: program commit = source-archive commit, no uncommitted changes, same version) |
| Commit → all outputs | `build\installer\MonographPDF_X.Y.Z_provenance.json`: commit, tree hash, commit time, build time, tool versions, signing provider and SHA-256 of Setup, the ZIPs, the program files and the SBOM; refused for a working tree with uncommitted changes | `scripts/packaging/provenance.py write / verify` |
| Commit → official history | The commit must be on `origin/main` or tagged `vX.Y.Z` in the official repository | `provenance.py verify --require-published` (after `git fetch`) |
| Release files ↔ each other | `SHA256SUMS.txt` in the Installer ZIP, release notes with the SHA-256 of every file | `verify_release.py --notes` |
| Components | `MonographPDF_X.Y.Z_SBOM.cdx.json` (CycloneDX 1.5): every shipped component with version, license and hashes (pinned OCR files, source archives), and Monograph PDF's own files with the commit | `scripts/packaging/make_sbom.py --check`; generated in CI on every run |
| Version metadata | Every own binary (MonographPDF.exe, uninstall.exe, MonographPDFUpdater.exe, Setup.exe) carries product name "Monograph PDF" and the same product version | `scripts/packaging/check_metadata.py` (release build) |

The provenance record and the SBOM are written to `build\installer\` by every release build; they
can be attached to a release, but are not part of the three release files checked by
`verify_release.py`.

## Reproducibility

Source and binaries are assessed separately.

**Source — reproducible (verified).** For the same commit and the same cached third-party
archives, `MonographPDF_X.Y.Z_Source.zip` has the same bytes whatever the checkout's line-ending
setting: fixed entry order, timestamps from the commit time, fixed attributes and compression.
Verified for 0.2.4 development commits with two fresh clones (`core.autocrlf` true and false), the
working tree and the release build; covered by `tests/unit/test_source_archive.py`.

**Program files — reproducible on the same build environment (measured).** Two builds of the same
0.3.0 development commit on the same workstation (same Python 3.11.9 environment, same pinned
packages and OCR engine) gave 483 files each; 482 were byte-identical. The only difference was
`MonographPDF.exe`, in 6 bytes: the PE header and debug-directory time stamps that PyInstaller sets to
the build time, and the PE checksum. Since then the build sets those time stamps to the commit time
(`scripts/packaging/normalize_pe.py`, from `git log -1 --format=%ct` or `SOURCE_DATE_EPOCH`), which
makes the whole installation folder byte-identical between such rebuilds. Not verified: builds on a
different machine or a freshly created Python environment (package installation order, compiled
`.pyc` files and paths could differ).

**Setup.exe — not reproducible.** Inno Setup stores the files' modification times and its own
compile time, so two `Setup.exe` files built from identical program files differ. To check a release,
compare what it installs: the installed files (or the layout in `build\installer\`) against a rebuild
of the same commit, and `SHA256SUMS.txt` / the provenance record against the published files.

## Path to CI-built releases

A code-signing service for open-source projects (for example SignPath Foundation) signs artifacts
that a CI system built from the repository. Steps that are **not done yet**:

1. A `release` workflow on GitHub Actions (Windows runner) that builds from a tag with the same
   scripts, with `permissions: contents: read` and an `id-token`/attestation permission only in
   that job, all actions pinned to commit SHAs, and no secrets available to pull-request workflows.
2. The OCR engine and third-party source archives fetched and verified by SHA-256 in CI (already
   done for the tests: `scripts/ci/stage_ocr_engine.py`).
3. A GitHub **environment** `release-signing` with the maintainer as required reviewer, holding the
   signing service's API token; the signing step runs only there, after the Signing Approver's
   approval ([CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md)).
4. Build-provenance attestations for the artifacts (GitHub artifact attestations), published with
   the release.
5. Inno Setup in CI (installed and verified by hash), and the release-set verification as a gate.

Until then, releases remain workstation builds with the traceability above.
