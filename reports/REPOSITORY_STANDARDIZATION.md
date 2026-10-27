# Repository standardization and documentation modernization

Baseline: `1c28721e00bfec97ad807dad2d7e8c30acce218b` (`origin/main`, verified 2026-10-27).
Development branch: `chore/repository-structure-docs`, in a separate clean worktree.
Scope: repository ownership and documentation; no runtime architecture or release changes.

## 1. Original structure

The baseline already separates `app/`, `core/`, `ui/` and `engines/` from native packaging.
`platforms/` identifies the host; platform-aware paths, locking and desktop helpers also live in
existing shared modules. `installer/` holds Windows packaging and `installer/linux/` consumes a
built Linux tree. macOS packaging lives in `scripts/build_app.sh` and `scripts/package_macos.sh`.
`scripts/packaging/`, `scripts/ci/`, `scripts/audit/` and `scripts/signing/` separate tooling roles.
`tests/` already has unit/integration/UI suites and synthetic fixtures. `docs/` mixes guides by
audience, alongside images and historical release notes; `reports/` holds engineering evidence.
`licenses/`, `third_party/`, `resources/`, `services/` and `versions/` have distinct existing roles.

The principal issues were stale legacy-branch instructions, Windows-centric source guidance,
contradictory published/draft status, missing navigation and overly broad cross-platform claims.

## 2. Proposed structure

Adopt the existing physical layout as the stable first phase. Define ownership and compatibility
boundaries in `docs/REPOSITORY_LAYOUT.md`; group guides through `docs/README.md`; index platform
build and setup entry points in `scripts/README.md`. Shared PDF functionality remains centralized.
Platform-specific work extends existing adapters instead of copying application implementations.
No speculative empty platform folders or duplicate packaging trees are introduced.

## 3. Actual file relocations

None. The stable runtime, installer, help, resource and command paths are retained deliberately.
This phase standardizes navigation and ownership; a future physical move requires its own evidence
and validation of every affected native package. New files are the three indexes/maps above and
this report.

## 4. Updated imports and references

No Python imports changed. README and installation instructions now use unified `main`, local
macOS documentation and the correct PowerShell launcher. Architecture, cross-platform workflow,
build/runtime, Linux and macOS guides link to the ownership map and current entry points.
Windows installer identity/upgrades, Linux desktop/package contracts, macOS bundle identity,
Unicode path handling, configuration roots and resource discovery are unchanged. Independent
version files and the root Windows VERSION mirror are unchanged.

## 5. README improvements

Retains the official logo and existing synthetic application screenshots. Adds concise feature
and platform tables, explicit published-versus-development status, platform-specific downloads,
source commands, offline/optional-network boundaries, native acceptance limits and developer links.
Removes excessive detail and unsupported blanket claims that every feature is validated on every OS.
Screenshot assets illustrate the Windows interface and are not presented as native OS certification.

## 6. Documentation improvements

INSTALLATION, SECURITY, CONTRIBUTING, LICENSE.md, THIRD_PARTY_NOTICES and CITATION were reviewed
and updated. SECURITY no longer offers an unpublished 0.5.0 draft as an available security upgrade.
Contribution rules allow the existing consent-controlled network features and reserve version bumps
for approved release work. Citation metadata is repository-wide and no longer asserts a release
version/date for unpublished 0.5.0; application version numbers were not changed.
Copyright remains © 2026 Aung Ye Mun. Privacy guidance includes native storage locations and manual
Linux/macOS upgrades. Historical release notes are retained as historical records.

## 7. License audit findings

The project remains AGPL-3.0-or-later. Canonical LICENSE is unchanged; only explanatory prose in
LICENSE.md changes, preserving its complete embedded license. Verification compares the canonical
and embedded texts with the baseline (normalizing line endings and surrounding whitespace only).
GNU's direct text endpoint timed out; the SPDX AGPL-3.0-or-later reference is used for a separate
whitespace-normalized comparison:
https://raw.githubusercontent.com/spdx/license-list-data/main/text/AGPL-3.0-or-later.txt.

Third-party notices, dependency inventory, pinned requirements, corresponding-source manifest,
upstream license files and existing archive/license tests were reviewed for consistency. Existing
PyMuPDF/MuPDF AGPL, pdf2docx GPL and Qt LGPL attribution remains intact. The notices now explicitly
scope their DLL/version inventory to the prepared Windows package. They do not certify native
Linux/macOS package contents; each distribution still needs its actual dependency/source inventory.
No dependencies or upstream license texts were changed. This scoped review does not certify unseen
binary packages or replace release-time corresponding-source verification.

## 8. CI modifications

Only macOS CI comments/summary wording changes: packaging scripts are already on main, while native
packaging/Gatekeeper acceptance is still outside this test-only workflow. Triggers, pinned actions,
permissions, runners, dependencies and test commands remain unchanged. The canonical-document
test's allowed set includes the two new documentation pages; all existing checks remain enabled.
All three native PR workflows are required validation before merge. Their current results are
available in the PR Checks tab; no merge or release publication is authorized by a green test job.

## 9. Test results

Local Windows validation covers canonical docs, installer/document contracts, branding, paths,
independent platform versions, Linux/macOS adapter contracts and source-archive/release scripts.
The initial run found the new docs absent from Git's source selection because they were not yet
committed; the source selector deliberately reads HEAD, so the archive test is rerun after commit.
Final local results and native CI links are recorded below after validation. Skips remain unverified.

## 10. Remaining risks and release follow-ups

* Windows 0.5.0 remains unpublished. Both 0.4.1 and 0.5.0 draft notes list an update manifest that
  is absent from their assets. Record this for a separate controlled release task; do not sign,
  upload or publish anything here.
* Native installer upgrade/uninstall, macOS packaging/Gatekeeper, Linux desktop integration,
  physical printing, Office automation and OCR recognition require appropriate native acceptance.
  Offscreen CI and skipped tests do not establish those outcomes.
* Existing release tags/drafts, production signing keys, trust configuration, versions and main
  are outside this change. No production key is accessed. Retained obsolete branches remain intact;
  no branch-deletion investigation is repeated.
* The original unavailable audit commit remains outside this worktree. Existing user work and
  recovery material are preserved; this report does not claim to recover it.

The PR is for review only and must not be automatically merged.
