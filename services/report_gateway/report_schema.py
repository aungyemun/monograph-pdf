"""The report allow-list, kept identical to core/diagnostics/report.py (tests compare the two).

The gateway is deployed on its own, so it does not import the application; any field or value
outside this schema is rejected.
"""

from __future__ import annotations

import json
import re

MAX_REPORT_BYTES = 8192
_IDENT = r"[A-Za-z_][A-Za-z0-9_]{0,63}"
EVENT_NAMES = {
    "APP_STARTED", "PDF_OPEN_STARTED", "PDF_OPEN_FAILED", "TEXT_EDIT_STARTED", "TEXT_EDIT_FAILED",
    "PDF_SAVE_STARTED", "PDF_SAVE_FAILED", "PDF_EXPORT_STARTED", "PDF_EXPORT_FAILED", "PDF_PRINT_STARTED",
    "PDF_PRINT_FAILED", "CONVERT_STARTED", "CONVERT_FAILED", "OCR_STARTED", "OCR_FAILED", "SUBPROCESS_FAILED",
    "UPDATE_CHECK_STARTED", "UPDATE_CHECK_FAILED", "UPDATE_DOWNLOAD_STARTED", "UPDATE_DOWNLOAD_FAILED",
    "UPDATE_INSTALL_STARTED", "UPDATE_INSTALL_FAILED", "QT_CRITICAL", "UNHANDLED_EXCEPTION",
    "UNEXPECTED_TERMINATION",
}

SCHEMA: dict[str, tuple[re.Pattern, bool]] = {
    "schema": (re.compile(r"^1$"), True),
    "report_type": (re.compile(r"^(error|crash|termination)$"), True),
    "app_version": (re.compile(r"^\d{1,5}\.\d{1,5}\.\d{1,5}(-[0-9A-Za-z.-]{1,32})?$"), True),
    "build": (re.compile(r"^(installed|portable|source)-(x64|x86|arm64|unknown)$"), True),
    "python_version": (re.compile(r"^\d{1,2}\.\d{1,2}\.\d{1,3}$"), False),
    "os": (re.compile(r"^(windows|macos|linux|other)$"), True),
    "os_version": (re.compile(r"^[0-9][0-9.]{0,24}$"), False),
    "os_arch": (re.compile(r"^(AMD64|x86_64|ARM64|aarch64|x86|i386|i686|unknown)$"), False),
    "display_language": (re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$|^und$"), False),
    "timestamp": (re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$"), True),
    "component": (re.compile(r"^(app|pdf|editing|forms|print|convert|ocr|update|ui)$"), True),
    "operation": (re.compile(r"^[A-Z][A-Z_]{1,40}$"), True),
    "error_code": (re.compile(r"^[A-Z][A-Z_]{1,40}$"), True),
    "exception_type": (re.compile(r"^(" + _IDENT + r")(\." + _IDENT + r"){0,6}$"), False),
    "code_location": (re.compile(r"^(app|core|ui|engines)(\." + _IDENT + r"){0,6}:" + _IDENT + r":\d{1,6}$"), False),
    "recent_events": (re.compile(r"^[A-Z][A-Z_]{1,40}$"), False),
    "fingerprint": (re.compile(r"^[0-9a-f]{16}$"), True),
}
LIST_FIELDS = {"code_location": 12, "recent_events": 30}


class InvalidReport(ValueError):
    pass


def validate(report) -> dict:
    if not isinstance(report, dict):
        raise InvalidReport("report must be a JSON object")
    unknown = set(report) - set(SCHEMA)
    if unknown:
        raise InvalidReport("unexpected fields")
    for name, (pattern, required) in SCHEMA.items():
        if name not in report:
            if required:
                raise InvalidReport(f"missing field {name}")
            continue
        value = report[name]
        if name in LIST_FIELDS:
            if not isinstance(value, list) or len(value) > LIST_FIELDS[name]:
                raise InvalidReport(f"{name} must be a short list")
            items = value
        else:
            items = [value]
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (str, int)) or not pattern.match(str(item)):
                raise InvalidReport(f"invalid value for {name}")
        if name == "recent_events" and not set(value) <= EVENT_NAMES:
            raise InvalidReport("unknown event identifier")
    if len(json.dumps(report, sort_keys=True)) > MAX_REPORT_BYTES:
        raise InvalidReport("report too large")
    return report
