# Code signing policy

This is Monograph PDF's code signing policy: who may change the code, who reviews changes, who
approves a release for signing, how signing is done and what users can verify.

**Current state: Monograph PDF releases are not code-signed.** No code-signing certificate has been
issued to or is used by this project, and no signing service has been engaged. No application has
been submitted to SignPath Foundation or any other provider. Until that changes, verify downloads
with their SHA-256 checksums ([OFFICIAL_DOWNLOAD_VERIFICATION.md](OFFICIAL_DOWNLOAD_VERIFICATION.md)).
When a provider signs releases, this page will name it, the certificate and the first signed
version — and, if SignPath Foundation signs them, carry the attribution text that SignPath requires.

## Project

| | |
| :--- | :--- |
| Product | Monograph PDF — an offline-first PDF application for Windows |
| Source | https://github.com/aungyemun/monograph-pdf (the only official repository) |
| License | GNU Affero General Public License v3.0 or later; bundled components keep their own open-source licenses ([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)) |
| Official downloads | GitHub Releases of that repository only |

## Team and roles

Monograph PDF has a single maintainer. All three roles are held by the same person, so there is no
independent second review today; the process below makes each role's decision explicit and recorded.

| Role | Member | Responsibility |
| :--- | :--- | :--- |
| Author (committer) | [Aung Ye Mun (@aungyemun)](https://github.com/aungyemun) | The only account with write access to the repository; commits and merges changes |
| Reviewer | [Aung Ye Mun (@aungyemun)](https://github.com/aungyemun) | Reviews every change from anyone without write access (pull requests) before it is merged; reviews release contents against the [release checklist](RELEASE_CHECKLIST.md) |
| Signing Approver | [Aung Ye Mun (@aungyemun)](https://github.com/aungyemun) | Decides whether a specific version, built from a specific commit, is signed; records that decision (below) |

Requirements for every member: multi-factor authentication on GitHub and on any signing service
account; no shared accounts; signing credentials are never stored in the repository, in CI secrets
of pull-request workflows, in the application or in a release.

## What may be signed

* Only binaries built from this repository's own source by the project's documented build
  ([BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md)): `MonographPDF.exe`, `uninstall.exe`,
  `MonographPDFUpdater.exe` and `MonographPDF_X.Y.Z_Setup.exe`.
* Third-party binaries shipped inside the installation (Python, Qt, MuPDF, Tesseract and their
  libraries) are included as published by their projects and are **not** re-signed with Monograph
  PDF's certificate.
* Every signed binary carries the product name "Monograph PDF" and the same product version
  (`scripts/packaging/check_metadata.py`, run by the release build).
* Development, test and pull-request builds are never signed.

## Release signing process

1. The release is prepared and validated as described in the
   [release checklist](RELEASE_CHECKLIST.md) (tests, release-set verification, provenance record).
2. The **Signing Approver** reviews the commit, the changelog and the verification results, then
   records the approval for exactly that version and commit:

   ```powershell
   .\env\Scripts\python.exe scripts\signing\sign_release.py approve --version X.Y.Z --approver "Aung Ye Mun"
   ```

   The command asks for the typed confirmation `SIGN MONOGRAPH PDF X.Y.Z` and refuses a working tree
   with uncommitted changes.
3. The release build signs only with `-Production` and an approval that matches the version, the
   commit (`HEAD`) and a clean working tree; otherwise it stops before building:

   ```powershell
   powershell -File scripts\build_release.ps1 -SigningProvider signtool -Production
   ```

   With the default provider `none`, nothing is signed and the build summary says "not signed".
4. A signing service adds its own manual approval: SignPath requires every signing request to be
   approved in SignPath by an approver of the project.
5. The signed files are verified (`Get-AuthenticodeSignature` reports `Valid`, publisher name as
   expected) before publication; the release notes state the signing status.

## Signing providers

`scripts/signing/signing.py` keeps signing modular; ordinary local builds need no provider:

| Provider | Use | Status |
| :--- | :--- | :--- |
| `none` | Default for every build; nothing is signed | In use |
| `signtool` | Windows SDK `signtool` with a certificate in the Windows certificate store or on a hardware token, selected by thumbprint (`MONOGRAPH_SIGN_CERT_SHA1`), RFC 3161 timestamp (`MONOGRAPH_SIGN_TIMESTAMP_URL`) | Implemented; no certificate exists |
| `signpath` | SignPath (for example SignPath Foundation for open-source projects): signs artifacts of a verified CI build after manual approval in SignPath | Configuration check only; requires an accepted SignPath project and a release workflow (see [RELEASE_PROVENANCE.md](RELEASE_PROVENANCE.md#path-to-ci-built-releases)) |

## Code signing and update security are independent

Windows code signing proves who published a file to Windows (SmartScreen, the UAC prompt).
Monograph PDF's automatic updates are authenticated separately: only an update manifest signed with
the project's Ed25519 update key, verified against public keys built into the program, is accepted,
and the download must match the signed SHA-256 ([SECURE_UPDATES.md](SECURE_UPDATES.md)). Neither key
can stand in for the other; a change of signing provider or certificate does not change update
trust, and the update key is never given to a signing service.

## Privacy

Monograph PDF does not transfer information to other networked systems unless the user requests it:
it checks for updates only when the user asks (or after the user switches on automatic checks) and
sends a problem report only when the user clicks **Send to Developer**. Details, including the
third-party services involved (GitHub), are in the [privacy policy](PRIVACY_POLICY.md).

## Reporting misuse

Report a suspected malicious or wrongly signed file, or misuse of the project's name, privately
through GitHub's private vulnerability reporting ([SECURITY.md](../SECURITY.md)). The maintainer will
assist any certificate authority or signing service in verification, investigation and root-cause
analysis.
