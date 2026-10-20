# Security Policy

## Supported versions

| Version | Status |
|---------|--------|
| 0.2.x | Supported (current release 0.2.2) |

## Report a vulnerability

Email **aungyemun25@gmail.com**. Do not open a public issue. Include steps to reproduce; redact personal paths and document contents. Do not send confidential PDFs until asked.

## Scope

Monograph PDF makes no network connections, does not upload documents, and collects no usage data. Optional Office conversion uses a local suite only.

* **Install** — unsigned Setup; verify `SHA256SUMS.txt`
* **Documents** — MuPDF; open never writes; no PDF JavaScript, actions, or link following
* **Encryption** — AES-256 (AES-128 optional); permissions are policy, not crypto
* **Redaction** — removes content, not just covers it
* **Temp / recovery** — under `%LOCALAPPDATA%\Monograph PDF`; none for password-protected PDFs
* **Network** — Qt network/TLS and Python SSL stripped; self-check fails on connect attempts

Details: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md). Audit: [SECURITY_AUDIT_0.2.0.md](reports/audit/SECURITY_AUDIT_0.2.0.md) (Pillow MEDIUM fixed; LOW #13 open).

## Bundled components (summary)

| Component | License |
|-----------|---------|
| Monograph PDF | AGPL-3.0-or-later |
| PyMuPDF / MuPDF | AGPL-3.0 |
| Qt / PySide6 | LGPL-3.0 |
| pdf2docx | GPL-3.0 |
| Tesseract OCR | Apache-2.0 |
| Python | PSF |

Full list: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Out of scope

* Bugs in Microsoft Office / LibreOffice
* Modified or non-standard installs
* Weak user passwords

Unlock requires a known password — Monograph PDF does not crack passwords.
