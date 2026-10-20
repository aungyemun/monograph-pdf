# Code signing

## Current state

Monograph PDF releases are **not code-signed**. No code-signing certificate is owned, used or stored
for this project, and no build step signs anything. This applies to:

| File | Signed |
|---|---|
| `MonographPDF_X.Y.Z_Setup.exe` (Inno Setup installer) | no |
| `MonographPDF.exe` (the application, PyInstaller) | no |
| `uninstall.exe` (built from `installer/uninstall_launcher.cs`) | no |
| Bundled third-party programs (for example the OCR engine) | as shipped by their upstream builds; not re-signed by this project |

Consequences for users:

* Windows SmartScreen may show "Windows protected your PC" for a new release until it has built up
  a reputation. **More info ▸ Run anyway** continues.
* Integrity is checked with SHA-256 instead: compare the downloaded file with the value in the
  release notes and in `SHA256SUMS.txt` ([INSTALLATION.md](../INSTALLATION.md)).

```powershell
Get-FileHash .\MonographPDF_X.Y.Z_Setup.exe -Algorithm SHA256
Get-AuthenticodeSignature .\MonographPDF_X.Y.Z_Setup.exe   # Status: NotSigned (expected today)
```

A checksum proves the file is the one the release page lists; it does not prove who published it.
That is what a signature would add.

## Rules

* Never claim in notes, docs or the app that a build is signed unless `Get-AuthenticodeSignature`
  reports `Valid` for that exact file.
* Never commit certificates, private keys, `.pfx` files, passwords or signing tokens. Releases are
  checked for secrets by `scripts/packaging/check_release.py`.
* No self-signed certificate for public releases: it gives users no trust and teaches them to accept
  warnings.
* Signing is never automatic in pull-request CI. A signing step, if added, runs only for a
  maintainer-approved release build.

## If signing is adopted later

This is a plan, not a commitment; nothing below is implemented.

1. **Obtain a certificate** from a provider that issues publicly trusted Windows code-signing
   certificates (an organisation-validated certificate on a hardware token or a cloud signing
   service, or a free open-source signing programme). Compare current terms, identity
   requirements and cost at the time; they change.
2. **Sign in this order** in `scripts/build_release.ps1`, because each later step packages the earlier
   file and signing changes a file's hash:
   1. `dist\MonographPDF\MonographPDF.exe` after PyInstaller;
   2. `build\installer\uninstall.exe` after it is compiled;
   3. `Setup.exe` (Inno Setup's `SignTool` directive signs the installer and its uninstaller stub);
   4. only then compute `SHA256SUMS.txt`, build `Installer.zip` and run `verify_release.py`.
3. **Timestamp** every signature (RFC 3161) so it stays valid after the certificate expires.
4. **Verify** each signed file: `signtool verify /pa /v <file>` and
   `Get-AuthenticodeSignature <file>` → `Valid`. Add this to `verify_release.py` as a check that
   fails when a file expected to be signed is not.
5. **Keep the key out of the repository**: a hardware token on the maintainer's machine, or a cloud
   signing service whose credentials live only in a protected CI environment with required
   reviewers. Document the provider and the certificate subject in this file.
6. **Update user docs**: `INSTALLATION.md`, `README.md`, `SECURITY.md` and the release notes'
   "Known limitations" currently say releases are unsigned.

## Related

[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) · [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) ·
[INSTALLATION.md](../INSTALLATION.md)
