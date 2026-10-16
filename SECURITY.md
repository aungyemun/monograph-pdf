# Security Policy

## Supported Versions

| Version | Status |
|---------|--------|
| 0.2.x (Monograph PDF) | In development (0.2.0 unreleased); becomes the supported line when 0.2.0 is released |
| 0.1.5 (PDF Editor) | Legacy — final PDF Editor release; supported until Monograph PDF 0.2.0 is released, after which fixes are made only in Monograph PDF |
| < 0.1.5 | Not supported |

Monograph PDF is the successor to PDF Editor; reports about PDF Editor 0.1.5 are welcome at the same address.

## Reporting a Vulnerability

To report a security vulnerability in Monograph PDF, contact the maintainer directly at **aungyemun25@gmail.com**.

Do not open a public issue for security vulnerabilities. Include a description of the issue, steps to reproduce, and any relevant log files (with personal paths and document contents redacted). If the issue needs a specific PDF to reproduce, describe it first — do not send confidential documents.

## Responsible Use

Monograph PDF is intended for working with documents you are entitled to open and change. Unlocking removes a password only when you already know it; Monograph PDF does not crack, guess or bypass passwords.

## Scope

Monograph PDF itself makes no network connections, does not upload documents, and does not collect usage data. Optional Microsoft Office / LibreOffice conversion is external software: Monograph PDF does not upload the document; conversion uses the locally installed suite, which follows its own settings and remote-content behavior. Relevant security areas are:

- **Installation integrity** — Setup.exe is produced by Inno Setup from the verified source tree after a release-contents check. The build is **not code-signed** (Windows SmartScreen may warn). Each release folder includes `SHA256SUMS.txt` with hashes for `Setup.exe`, `MonographPDF.exe` and `MonographPDF_<version>_Source.zip`.
- **Document handling** — PDFs are parsed by MuPDF. Opening a document never modifies it; edits are written only when you save. Untrusted PDFs are rendered, not executed: PDF JavaScript, actions and launch commands are not run, links are not followed and attachments are never opened.
- **Encryption** — Protect with Password uses AES-256 (AES-128 optional). Permissions passwords are enforced by PDF readers, not by cryptography, so treat them as a policy rather than a security boundary.
- **Redaction** — Apply Redactions removes the underlying text and image content, not just covers it.
- **Office conversion** — Word, Excel and PowerPoint files are converted by the suite already installed on the computer (Microsoft Office through COM automation, or LibreOffice headless). Documents are opened read-only with macros forced off. Those suites may still follow their own remote-content settings.
- **Temporary files** — working files are kept under `%LOCALAPPDATA%\Monograph PDF\runtime` and cleaned up automatically; nothing is written into the installation folder, and no recovery copy is kept for password-protected PDFs. Uninstalling removes them, the recent-files list and, if the user chooses, all settings; it never removes user documents.
- **Network** — Monograph PDF makes no network connections; the release build leaves out Qt's network and TLS plugins and Python's SSL module, and the installer's self-check fails if anything tries to connect. No telemetry, advertising, online OCR or runtime downloads.

Technical details: [Security and Privacy](docs/SECURITY_AND_PRIVACY.md). Audit evidence for the last release (PDF Editor 0.1.5): [SECURITY_AUDIT_0.1.5.md](reports/audit/SECURITY_AUDIT_0.1.5.md); the 0.2.0 audit is done before 0.2.0 is released.

## Bundled Third-Party Components (summary)

| Component | License | Notes |
|-----------|---------|-------|
| Monograph PDF | AGPL-3.0-or-later | This application |
| PyMuPDF / MuPDF | AGPL-3.0 | Upstream PDF engine |
| Qt 6 / PySide6 | LGPL-3.0 | User interface; dynamic libraries in `_internal` |
| pdf2docx | GPL-3.0 | PDF to Word |
| OpenCV (headless) | Apache-2.0 | Used by pdf2docx |
| Tesseract OCR | Apache-2.0 | Standalone executable in `engines\ocr`; not linked into MonographPDF.exe |
| Python runtime | PSF | Bundled by PyInstaller |

See `THIRD_PARTY_NOTICES.md` for the full list.

## Out of Scope

- Vulnerabilities in Microsoft Office, LibreOffice or other software installed by the user
- Issues that require running Monograph PDF in a modified or non-standard environment
- The strength of passwords chosen by users
