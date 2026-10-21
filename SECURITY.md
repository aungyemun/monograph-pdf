# Security Policy

## Supported versions

| Version | Supported |
| :--- | :--- |
| 0.2.x (current release: 0.2.3) | Yes — security fixes are made in the latest 0.2 release |
| Earlier versions | No |

## Reporting a vulnerability

Please report security problems **privately** by email to **aungyemun25@gmail.com** — do not open
a public GitHub issue.

Include, where possible:

* the Monograph PDF version (**Help ▸ About Monograph PDF**) and your Windows version;
* the steps to reproduce the problem and what you expected to happen;
* a sample file that triggers it, **only if it contains no confidential information**. Please
  remove personal paths and document contents from logs and screenshots, and do not send
  confidential PDFs unless asked.

Fixes are described in the [changelog](CHANGELOG.md) of the release that contains them.

## Security design

Monograph PDF makes no network connections, does not upload documents and collects no usage data.

| Area | How it is protected |
| :--- | :--- |
| **Installation** | Setup is not code-signed; check the SHA-256 checksum against `SHA256SUMS.txt` or the release page before running it. |
| **Opening documents** | PDFs are read with MuPDF. Opening a file never writes to it. PDF JavaScript, actions and links are never run or followed automatically. |
| **Encryption** | AES-256 (AES-128 optional). Permission settings are honored by PDF readers but are not a cryptographic protection. |
| **Redaction** | Applying a redaction removes the content underneath; it does not just cover it. |
| **Hidden information** | **Protect ▸ Remove Hidden Information** writes a cleaned copy; its limits are documented in [Security and Privacy](docs/SECURITY_AND_PRIVACY.md#hidden-information). |
| **Working files** | Stored in `%LOCALAPPDATA%\Monograph PDF`. No recovery copy is kept for password-protected PDFs. |
| **Network** | Qt's network and TLS modules and Python's SSL module are removed from the release build; the built-in self-check fails if anything tries to connect. |
| **External programs** | Started only by their full system path. Office conversions run with macros disabled. |

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
