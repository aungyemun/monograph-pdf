# Verifying an official download

Official Monograph PDF files come only from the GitHub Releases page of
https://github.com/aungyemun/monograph-pdf. Each release publishes three files:

| File | Contents |
| :--- | :--- |
| `MonographPDF_X.Y.Z_Setup.exe` | The installer |
| `MonographPDF_X.Y.Z_Installer.zip` | The same installer as `Setup.exe`, with `SHA256SUMS.txt`, license texts and documentation |
| `MonographPDF_X.Y.Z_Source.zip` | The complete corresponding source of the release, with the source of every bundled AGPL, GPL and LGPL component |

## 1. Check the SHA-256 checksum

The release notes list the SHA-256 of every file; `SHA256SUMS.txt` inside the Installer ZIP lists
`Setup.exe` and the Source ZIP.

```powershell
Get-FileHash .\MonographPDF_X.Y.Z_Setup.exe -Algorithm SHA256
```

The value must equal the one in the release notes. A matching checksum shows the file is the one
the release page lists; it does not by itself show who published it.

## 2. Check the code signature

```powershell
Get-AuthenticodeSignature .\MonographPDF_X.Y.Z_Setup.exe | Format-List Status, SignerCertificate
```

* The releases published so far (0.2.2, 0.2.3, 0.3.0 and 0.4.0) are **not code-signed**: the expected status is `NotSigned`.
  Windows SmartScreen may warn ("Windows protected your PC"); continue (**More info ▸ Run anyway**)
  only for a file whose checksum matched in step 1.
* If a future release is signed, its release notes and [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md)
  name the signer. The status must then be `Valid` and the certificate subject must match; any other
  result (`HashMismatch`, `NotTrusted`, an unexpected signer) means: do not run the file.

## 3. Optional: check the source and the build record

* `MonographPDF_X.Y.Z_Source.zip` contains `SOURCE_MANIFEST.json` with the commit the release was
  built from; it is reproducible from that commit (same bytes for the same commit and cached
  third-party archives — [RELEASE_PROVENANCE.md](RELEASE_PROVENANCE.md)).
* From 0.3.0, **Help ▸ About Monograph PDF** shows the commit the installed program was built from.
  It must equal the commit in `SOURCE_MANIFEST.json` and be part of the official repository's history:

  ```powershell
  git clone https://github.com/aungyemun/monograph-pdf; cd monograph-pdf
  git merge-base --is-ancestor <commit> origin/main; $LASTEXITCODE   # 0 = on the official main branch
  ```

## Automatic updates

From 0.3.0 the program can install updates itself; it accepts only update information signed with
the project's update key and an installer whose SHA-256 matches that signed information, and it
downloads only from GitHub's release servers ([SECURE_UPDATES.md](SECURE_UPDATES.md)). This works
independently of Windows code signing.

## Unofficial copies

Files from other websites, mirrors, file-sharing services or e-mail attachments are not official,
even if they carry the name Monograph PDF. Report suspicious copies privately through
[SECURITY.md](../SECURITY.md).
