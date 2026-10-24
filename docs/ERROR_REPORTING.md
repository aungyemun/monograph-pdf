# Private error reporting

Status: **included since 0.3.0, sending switched off (also in 0.4.0 and 0.5.0)**. Problem reports are detected, built and shown to the user;
**sending is disabled** until the reporting gateway described below is deployed and verified
(`resources/diagnostics/reporting.json` has `"enabled": false` and no endpoint). In such a build
the dialog does not offer **Send to Developer** at all; it offers **Copy Report**, **Open Issues
Page** and **Close** instead (see below), and the app sends nothing.

## What is detected

* Unexpected failures of main operations: opening, saving, exporting, converting and printing a
  PDF. Ordinary, expected problems (file in use, no permission, file not found, disk full — any
  `OSError`) show the usual message and do not offer a report.
* Unhandled Python exceptions (also in background threads) and Qt critical or fatal messages.
* OCR and its subprocess failures, update check / download / installation failures (recorded as
  events, so a later report shows them).
* Unexpected termination: a tiny session record exists while the application runs and is removed
  at a normal exit; one left behind by a process that no longer runs is reported at the next start.
* Hard crashes (from 0.5.0): a fatal native error such as an access violation ends the process before
  any Python code can react. Python's `faulthandler` then writes the stack of the failing thread to
  `fault-<pid>.log`; at the next start only the kind of fault and Monograph PDF's own
  `module:function:line` entries are taken from it, and the file is deleted. The Windows Error
  Reporting record of that process (event 1000 in the local Application log, read as XML with
  `wevtutil`) gives the file in which the crash happened — named only when it is one of Monograph
  PDF's own files, otherwise reported as `external`. The report dialog starts with a plain-language
  summary (for example: "stopped because of a memory access error inside python311.dll … The last
  step in Monograph PDF's own code was paint in ui.font_picker (line 28). Just before, Monograph PDF
  was changing fonts or formatting.").

## What a report contains — and what it never contains

Reports are assembled from approved fields only (`core/diagnostics/report.py`); nothing is
collected first and filtered afterwards. Every field must match a fixed pattern, unknown fields are
refused, and the gateway enforces the same schema.

| Field | Example |
| :--- | :--- |
| `schema`, `report_type` | `1`, `error` · `crash` · `termination` |
| `app_version`, `build` | `0.5.0`, `installed-x64` |
| `python_version`, `os`, `os_version`, `os_arch` | `3.11.9`, `windows`, `10.0.26100`, `AMD64` |
| `display_language` | `ja-JP` (Windows display language) |
| `timestamp` | `2026-10-21T07:19:00Z` (minute resolution, UTC) |
| `component`, `operation`, `error_code` | `pdf`, `PDF_SAVE`, `PDF_SAVE_FAILED` |
| `exception_type` | `ValueError` or `fitz.FileDataError` (class name only — never the message) |
| `code_location` | `core.document:save_as:171` (Monograph PDF's own module, function and line; up to 12) |
| `recent_events` | up to 30 predefined identifiers such as `PDF_OPEN_STARTED` |
| `fault_kind` | hard crashes only: `ACCESS_VIOLATION`, `STACK_OVERFLOW`, `ILLEGAL_INSTRUCTION`, `INT_DIVIDE_BY_ZERO`, `FLOATING_POINT`, `ABORT`, `FATAL_ERROR` or `OTHER` |
| `faulting_module` | hard crashes only: the program file in which it happened, such as `python311.dll` or `Qt6Widgets.dll`; `external` for any file that is not part of Monograph PDF |
| `fingerprint` | 16 hex digits derived from error code, exception type, the last code locations and version — the same software failure gives the same value on every computer |

Never collected: document contents, file or folder names and paths, PDF metadata, user names,
e-mail addresses, passwords, tokens, clipboard contents, typed text or keystrokes, memory dumps,
environment variables, network addresses, device identifiers or usage history. Exception messages
and tracebacks are not included because they can contain paths and file names.

Predefined event identifiers: `APP_STARTED`, `PDF_OPEN_STARTED/FAILED`, `TEXT_EDIT_STARTED/FAILED`,
`PDF_SAVE_STARTED/FAILED`, `PDF_EXPORT_STARTED/FAILED`, `PDF_PRINT_STARTED/FAILED`,
`CONVERT_STARTED/FAILED`, `OCR_STARTED/FAILED`, `SUBPROCESS_FAILED`, `UPDATE_CHECK_STARTED/FAILED`,
`UPDATE_DOWNLOAD_STARTED/FAILED`, `UPDATE_INSTALL_STARTED/FAILED`, `QT_CRITICAL`,
`UNHANDLED_EXCEPTION`, `UNEXPECTED_TERMINATION`, `STYLE_CHANGED`, `PAGES_CHANGED`,
`COMMENT_CHANGED` (a run of the same action is recorded once).

## Storage

* Recent events live in a ring buffer of 30 identifiers; a copy is kept in the session record so
  that it survives a hard crash (identifiers only).
* A recoverable error's report is built in memory and discarded after the dialog.
* Only three kinds of small file can exist, in `%LOCALAPPDATA%\Monograph PDF\Diagnostics`:
  `session-<pid>.json` while the application runs (version, start time and recent event
  identifiers); `fault-<pid>.log` while it runs (empty unless a hard crash happens; it then holds
  the stack of the failing thread, including file paths of the program, and is read and deleted at
  the next start — only the approved fields above are taken from it); and `pending-report.json` —
  one validated report of a crash that could not be shown, offered at the next start. All expire
  after 14 days, are removed once the user has decided, and are removed by the uninstaller. Normal use writes no
  report files; nothing is written to document folders.

## The dialog

When a reporting gateway is configured: exactly two decision buttons, **Don't Send** (default)
and **Send to Developer**. The complete
report is shown read-only above them, with an explanation that it holds limited technical
information and is sent only with approval. Recoverable errors are offered without closing the
application; crashes are offered at the next successful start.

When no gateway is configured (0.3.x): **Copy Report** puts the report, exactly as shown, on the
clipboard; **Open Issues Page** opens the project's GitHub issues page in the browser so the user
can paste it into a new issue themselves; **Close** (default) discards it. The app transmits nothing.

* **Don't Send**: nothing is transmitted; the dialog closes; the report is discarded.
* **Send to Developer**: the report exactly as shown is sent once over HTTPS to the configured
  gateway, off the user-interface thread, with a 15-second limit and no redirects. The real outcome
  is shown ("sent", "not reachable", "refused", "not enabled in this build"); there is no silent
  retry and the application never freezes waiting for it.

## Reporting gateway

```
Monograph PDF ──HTTPS POST /v1/reports──▶ reporting gateway ──GitHub App, issues:write──▶ private repository ▶ issues
```

Reference implementation: `services/report_gateway/` (Python WSGI, standard library plus
`cryptography` for the GitHub App token). It is **not** part of the application, is not deployed by
this project's build or CI, and needs no access to the source repository, releases or update keys.

* Accepts only `POST /v1/reports`, `Content-Type: application/json`, at most 8 KB; validates the
  allow-listed schema (same patterns as the client; checked by `tests/unit/test_diagnostics.py`);
  never executes or interprets report text; no file or PDF upload.
* Abuse protection: per-client limit (default 5 per hour) and global limit (default 500 per hour);
  the client address is used only as a salted hash in memory and is never logged or stored.
* Duplicate grouping: the issue is labelled `fp-<fingerprint>`; another report with the same
  fingerprint becomes a comment on that issue.
* Minimal logging: status and fingerprint only.
* Responses: 202 accepted · 400 invalid · 404/405 wrong path or method · 413 too large · 415 wrong
  type · 429 rate limited · 502 GitHub failure · 503 not configured.

### GitHub permissions

* A dedicated **GitHub App** installed **only** on the private reporting repository, with the
  repository permission **Issues: read and write** (and the mandatory *Metadata: read*), nothing
  else — no contents, pull requests, workflows, releases, administration or organization access.
* The gateway additionally requests each installation token **down-scoped** to
  `{"issues": "write"}` on that single repository and refuses to use a token whose granted
  permissions are broader; its client can only call three issue endpoints (list by label, create
  issue, add comment). It therefore cannot modify source code, commits, branches, tags, pull
  requests, release assets, published versions or build workflows.
* Configuration by environment: `REPORT_REPOSITORY` (`owner/name` of the private repository),
  `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY_FILE` (path to the App's
  private key on the server; never in a repository). Missing values → 503.

### Deployment (production setup)

1. Create a **private** repository for reports (separate from `monograph-pdf`).
2. Create the GitHub App with only *Issues: read and write*; install it on that repository only;
   store its private key in the hosting platform's secret store.
3. Deploy `services/report_gateway` (`gateway.from_environment()` under a WSGI server) behind HTTPS
   with a valid certificate, request-size limits and the platform's own rate limiting; keep access
   logs off or without client addresses.
4. Test with the reference test server (`python -m services.report_gateway`, 127.0.0.1 only) and
   then against the deployed endpoint with a non-production report.
5. Only then put the endpoint into `resources/diagnostics/reporting.json` (`enabled: true`) in a
   release, after review. `verify_release.py --layout` checks that the shipped file equals the
   repository's.

Not done in this development milestone: no gateway is deployed, no GitHub App or private repository
was created, and no report has been sent anywhere.
