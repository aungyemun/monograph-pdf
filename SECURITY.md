# Security Policy

## Supported versions

Only the latest release receives security fixes. Fixes are published as a new release, so the
answer to a security problem in an older version is to upgrade.

| Version | Supported |
| :--- | :--- |
| 0.5.0 (latest release) | Yes |
| 0.4.1 | Never released — its fixes are included in 0.5.0 |
| 0.4.0 | No — please upgrade to 0.5.0, which fixes a crash when choosing a font while editing text and keeps the password protection of protected PDFs in every copy |
| 0.3.0 | No — please upgrade to 0.5.0, which also fixes the loss of a permissions password on save |
| 0.2.0 – 0.2.3 | No — please upgrade to the latest release |
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

Monograph PDF is designed to operate offline: it has no telemetry and never uploads documents.
From 0.3.0 exactly two modules may use the network — the update checker and the problem-report
sender — each only for a purpose the user controls (checked by tests). Update checks are switched on
from **0.5.0**, the first published version with them (only when the user asks, or after switching on
automatic checks, which are off by default); in 0.3.0 and 0.4.0 they are off. Sending problem reports is switched off (no reporting
service yet). From **0.5.0** the OCR Languages dialog can download one optional OCR language file when
the user clicks **Download and Install**; it goes through the update checker's HTTPS code (host
allow-list, certificate verification) and the file is installed only if its pinned SHA-256 matches.
Nothing else in Monograph PDF makes network connections.

| Area | How it is protected |
| :--- | :--- |
| **Installation** | Setup is not code-signed; check the SHA-256 checksum against `SHA256SUMS.txt` or the release page before running it. |
| **Opening documents** | PDFs are read with MuPDF. Opening a file does not write to it. PDF JavaScript is not executed, and actions and links are never run or followed automatically. |
| **Encryption** | AES-256 (AES-128 optional). Passwords are kept in memory only. |
| **Permission restrictions** | Printing, copying and editing permissions are respected by compliant PDF readers but are not a cryptographic protection: anyone who can open the file can bypass them with other software. |
| **Redaction** | Applied redactions remove the marked page content (text, image pixels, vector graphics) and overlapping form fields, comments and links, rather than placing a visible overlay. Text inside pictures is not detected. Verification and limitations: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md#redaction). |
| **Hidden information** | **Protect ▸ Remove Hidden Information** writes a cleaned copy and removes only the categories it lists; content that is part of the pages (including layers that are turned off) is kept. Limits: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md#hidden-information). |
| **Working files** | Settings and the recent-files list in `%APPDATA%\Monograph PDF`; cache, logs and recovery sessions in `%LOCALAPPDATA%\Monograph PDF`. No recovery copy is kept for password-protected PDFs. |
| **Offline operation** | Qt's network and TLS modules are removed from the release build; Python's HTTPS support is used only by the update, problem-report and OCR-language-download code. The built-in self-check (also run by Setup) fails if a network connection is attempted while it runs. |
| **Updates (from 0.5.0; off in 0.3.0 and 0.4.0)** | Only Ed25519-signed release manifests verified against built-in keys are accepted; the installer must match the signed SHA-256 and size; downgrades, expired (validity at most 730 days) or replayed manifests and foreign hosts are refused; Update Now is required before anything is downloaded; HTTPS with certificate verification; the installed copy is never replaced by the running program. [Secure updates](docs/SECURE_UPDATES.md) |
| **Problem reports (sending switched off in 0.3.0, 0.4.0 and 0.5.0)** | Approved technical fields only, shown in full before sending; sent only after **Send to Developer**; the reporting gateway can only file issues in one private repository. [Error reporting](docs/ERROR_REPORTING.md) |
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
