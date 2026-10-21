# Security Policy

## Supported versions

Only the latest release receives security fixes. Fixes are published as a new release, so the
answer to a security problem in an older version is to upgrade.

| Version | Supported |
| :--- | :--- |
| 0.2.3 (latest release) | Yes |
| 0.2.0 – 0.2.2 | No — please upgrade to the latest release |
| 0.1.x and earlier internal builds | No |

## Reporting a vulnerability

Please report security problems **privately** — do not open a public GitHub issue.

* **Preferred:** GitHub private vulnerability reporting —
  [Report a vulnerability](https://github.com/aungyemun/monograph-pdf/security/advisories/new)
  (Security tab ▸ **Report a vulnerability**; requires a GitHub account).
* **Alternative:** email **aungyemun25@gmail.com**.

Monograph PDF is maintained by one person; reports are handled as quickly as possible, but no fixed
response time can be promised.

Include, where possible:

* the Monograph PDF version (**Help ▸ About Monograph PDF**) and your Windows version;
* the steps to reproduce the problem and what you expected to happen;
* a sample file that triggers it, **only if it contains no confidential information**. Please
  remove personal paths and document contents from logs and screenshots, and do not send
  confidential PDFs unless asked.

Fixes are described in the [changelog](CHANGELOG.md) of the release that contains them.

## Security design

Monograph PDF is designed to operate entirely offline. Its own code uses no networking modules
(checked by tests); it has no telemetry, update check or document upload.

| Area | How it is protected |
| :--- | :--- |
| **Installation** | Setup is not code-signed; check the SHA-256 checksum against `SHA256SUMS.txt` or the release page before running it. |
| **Opening documents** | PDFs are read with MuPDF. Opening a file does not write to it. PDF JavaScript is not executed, and actions and links are never run or followed automatically. |
| **Encryption** | AES-256 (AES-128 optional). Passwords are kept in memory only. |
| **Permission restrictions** | Printing, copying and editing permissions are respected by compliant PDF readers but are not a cryptographic protection: anyone who can open the file can bypass them with other software. |
| **Redaction** | Applied redactions remove the marked page content (text, image pixels, vector graphics) and overlapping form fields, comments and links, rather than placing a visible overlay. Text inside pictures is not detected. Verification and limitations: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md#redaction). |
| **Hidden information** | **Protect ▸ Remove Hidden Information** writes a cleaned copy and removes only the categories it lists; content that is part of the pages (including layers that are turned off) is kept. Limits: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md#hidden-information). |
| **Working files** | Settings and the recent-files list in `%APPDATA%\Monograph PDF`; cache, logs and recovery sessions in `%LOCALAPPDATA%\Monograph PDF`. No recovery copy is kept for password-protected PDFs. |
| **Offline operation** | Qt's network and TLS modules and Python's SSL module are removed from the release build; the built-in self-check (also run by Setup) fails if a network connection is attempted while it runs. |
| **Office conversion** | Uses the locally installed Microsoft Office (macros force-disabled) or LibreOffice (a temporary profile with macros disabled). These applications run independently and follow their own settings, including network access. |
| **External programs** | Started only by their full system or installation path, never found through the current folder. |

More detail: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) · Security audit of the 0.2 line:
[SECURITY_AUDIT_0.2.0.md](reports/audit/SECURITY_AUDIT_0.2.0.md)

## Main bundled components

| Component | License |
| :--- | :--- |
| Monograph PDF | AGPL-3.0-or-later |
| PyMuPDF / MuPDF | AGPL-3.0 |
| Qt for Python (PySide6) | LGPL-3.0 |
| pdf2docx | GPL-3.0 |
| Tesseract OCR | Apache-2.0 |
| Python | PSF-2.0 |

Complete list with versions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Out of scope

* Vulnerabilities in Microsoft Office or LibreOffice themselves
* Modified builds or installations that were changed after Setup
* Weak passwords chosen by the user — Monograph PDF unlocks files only with the correct password and
  does not attempt to recover or guess passwords
