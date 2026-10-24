# Privacy policy

Monograph PDF processes documents on your computer. It has no account, no advertising, no telemetry
and no usage statistics, and it never uploads documents.

**Monograph PDF does not transfer information to other networked systems unless you request it.**
There are only three such requests, all described below. Update checks are available from version
0.4.1 and happen only when you ask (or after you switch on automatic checks, which are off by default).
OCR language downloads (from version 0.5.0) happen only when you click **Download and Install**.
Sending problem reports is switched off (no reporting service yet). Versions 0.3.0 and 0.4.0 make no
network connections at all; the same holds for earlier versions, which do not have these features.

## Update checks (built in since 0.3.0, switched on from 0.4.1)

When you choose **Help ▸ Check for Updates…**, **Check Now**, or switch on *Automatically check for
updates* (off by default; **File ▸ Settings… ▸ Updates**), Monograph PDF connects to GitHub, which
hosts the project's releases (`github.com`, `api.github.com`, `objects.githubusercontent.com`,
`release-assets.githubusercontent.com`), and downloads the signed update information. When you
click **Update Now**, it downloads that version's installer from the same place.

* Sent: an ordinary HTTPS request with the program's name and version
  (`MonographPDF/0.3.0 (+updater)`). As with any internet connection, GitHub sees your IP address.
* Not sent: documents, file names, settings, account data, identifiers of you or your computer.
* GitHub's own privacy statement applies to its servers:
  https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement
* Turning automatic checks off (the default) stops all background checks; manual checks happen only
  when you ask.

## OCR language downloads (from version 0.5.0)

English and Japanese OCR are included. When you select another language in **OCR ▸ OCR Languages** and
click **Download and Install**, Monograph PDF downloads that one language file from the official
Tesseract release on GitHub (`github.com`, redirected to `raw.githubusercontent.com`; HTTPS with
certificate verification; no other address is accepted). The file is installed only if its size and
SHA-256 match the value shipped with Monograph PDF.

* Sent: an ordinary HTTPS request for the file, with the program's name and version. GitHub sees your
  IP address and which language file was requested.
* Not sent: documents, file names, settings or identifiers of you or your computer.
* Nothing is downloaded at any other time. **Install from File…** and the offer to install language
  files found in your Downloads folder (only files named like a supported language file are looked
  at) work without a connection.

## Problem reports (from version 0.3.0)

If something fails unexpectedly, Monograph PDF can show a problem report. It contains only limited
technical information — program version, Windows version and display language, the failing
operation, the error type and where in Monograph PDF's own code it failed, a short list of recent
operation names and a fingerprint that groups identical errors. It never contains documents, file
names, folder paths, user names, typed text or identifiers of you or your computer. The complete
report is shown before you decide.

* **Don't Send** discards it. Nothing is sent.
* **Send to Developer** sends exactly that report over HTTPS to the project's reporting service,
  which stores it as an issue in a private GitHub repository visible only to the maintainer. The
  service sees your IP address for rate limiting; it does not log or store it.
* Sending is disabled until that service is deployed; the dialog says so.
* Details: [ERROR_REPORTING.md](ERROR_REPORTING.md).

## Data kept on your computer

Settings, the recent-files list, working files, update downloads waiting to be installed and
problem-report records stay in your user profile (`%APPDATA%\Monograph PDF`,
`%LOCALAPPDATA%\Monograph PDF`); uninstalling removes them (settings only if you choose).
Details: [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md#data-on-disk).

## Other programs

Optional Office conversion uses the Microsoft Office or LibreOffice installed on your computer; those
programs follow their own privacy settings, which Monograph PDF does not control.

## Contact

Questions about privacy: open an issue on https://github.com/aungyemun/monograph-pdf, or for
anything sensitive use GitHub's private vulnerability reporting ([SECURITY.md](../SECURITY.md)).
