# Security Policy

## Supported versions

Security fixes are made on `main` and reach users only in a new platform release. Use the latest
release for your platform.

| Platform | Supported | Not supported |
| :--- | :--- | :--- |
| Windows | **0.5.1** | 0.5.0 and earlier: upgrade with the 0.5.1 Setup. 0.4.0 and earlier predate the protected-PDF fixes of 0.5.0. |
| macOS | **0.1.1** | 0.1.0 |
| Linux | **0.1.1** | — (0.1.0 was never published) |

Windows 0.4.1 and 0.4.2 were never published; their changes are in 0.5.0. A fix on `main` does not
make an older release safe. Before sharing a sensitive document, confirm that the output is
protected as you expect.

## Reporting a vulnerability

Report security problems **privately**, never in a public issue:

* **Preferred:** [GitHub private vulnerability reporting](https://github.com/aungyemun/monograph-pdf/security/advisories/new)
  (Security tab ▸ **Report a vulnerability**).
* **Alternative:** email **aungyemun25@gmail.com**.

Please include:

* the platform and version (**Help ▸ About Monograph PDF**) and your operating-system version;
* the steps to reproduce the problem and what you expected;
* a sample file, **only if it contains no confidential information**. Remove personal paths and
  document contents from logs and screenshots.

Monograph PDF is maintained by one person. Reports are handled as quickly as possible, but no
response time is guaranteed. Fixes are listed in the [changelog](CHANGELOG.md).

## Security design

Monograph PDF works offline. It has no telemetry and never uploads documents. Only three features
can use the network, and only when you ask:

* **Update checks (Windows):** on request, or automatically if you switch that on (off by default).
* **OCR language downloads:** only after **Download and Install**.
* **Problem reports:** switched off in every release so far.

| Area | Protection |
| :--- | :--- |
| **Downloads** | Check every file against the release's SHA-256 checksums. Windows and macOS packages are not code-signed (macOS is ad-hoc signed, not notarized); Linux archives are GPG-signed. |
| **Opening documents** | PDFs are read with MuPDF and never modified by opening. PDF JavaScript is not executed; actions and links are never run or followed automatically. |
| **Encryption** | AES-256 (AES-128 optional). Passwords are kept in memory only. |
| **Permissions** | Print, copy and edit restrictions are honored by compliant readers but are not cryptographic: other software can ignore them. |
| **Redaction** | Removes the marked content (text, image pixels, vector graphics) and overlapping fields, comments and links; it is not an overlay. Text inside images is not detected. [Details](docs/SECURITY_AND_PRIVACY.md#redaction) |
| **Hidden information** | **Protect ▸ Remove Hidden Information** writes a cleaned copy and removes only the listed categories; page content, including hidden layers, is kept. [Details](docs/SECURITY_AND_PRIVACY.md#hidden-information) |
| **Working files** | Stored in the user profile (Windows AppData, macOS Application Support/Caches, Linux XDG folders). No recovery copy is kept for password-protected PDFs. [Path map](docs/REPOSITORY_LAYOUT.md#compatibility-boundaries) |
| **Network code** | Only the update, OCR-download and problem-report modules may connect (enforced by tests), over HTTPS with certificate checks and a host allow-list. The Windows build removes Qt's network and TLS modules; the Linux and macOS builds still include them, unused. The built-in self-check fails if any connection is attempted. |
| **Updates (Windows 0.5.0+)** | Only Ed25519-signed manifests verified against built-in keys are accepted. The installer must match the signed size and SHA-256. Downgrades, expired or replayed manifests and unknown hosts are refused. Nothing downloads before **Update Now**. [Secure updates](docs/SECURE_UPDATES.md) |
| **OCR language files** | Installed only if the pinned size and SHA-256 match. |
| **Office conversion** | Uses local Microsoft Office (macros disabled) or LibreOffice (temporary profile, macros disabled). These programs follow their own settings, including network access. |
| **External programs** | Started by full path only, never looked up in the current folder. |

More detail: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) ·
[Error reporting](docs/ERROR_REPORTING.md) ·
[Security audit of the 0.2 line](reports/audit/SECURITY_AUDIT_0.2.0.md)

## Out of scope

* Vulnerabilities in Microsoft Office or LibreOffice themselves
* Builds or installations modified after download
* Weak passwords: Monograph PDF opens protected files only with the correct password and never
  tries to recover or guess one

Third-party component licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

© 2026 Aung Ye Mun
