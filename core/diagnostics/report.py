"""Building, validating and displaying sanitized error reports.

A report is assembled from approved fields only — it never starts from an exception message, a
traceback text, file names or the environment and then tries to scrub them. Every field is checked
against :data:`SCHEMA` (also enforced by the reporting gateway), so a value that does not fit its
pattern is dropped before the user even sees the report.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import traceback
from datetime import datetime, timezone

from core.diagnostics.events import FAILURES, EventId, diagnostics

SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 8192
_IDENT = r"[A-Za-z_][A-Za-z0-9_]{0,63}"
_EVENT_NAMES = {e.value for e in EventId}
APP_MODULES = ("app.", "core.", "ui.", "engines.")

# field -> (regex, required)
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


class ReportError(ValueError):
    pass


def validate(report: dict) -> dict:
    """Return ``report`` if every field is known and matches its pattern, else raise ReportError."""
    if not isinstance(report, dict):
        raise ReportError("report must be an object")
    unknown = set(report) - set(SCHEMA)
    if unknown:
        raise ReportError(f"unexpected fields: {sorted(unknown)}")
    for name, (pattern, required) in SCHEMA.items():
        if name not in report:
            if required:
                raise ReportError(f"missing field {name}")
            continue
        value = report[name]
        if name in LIST_FIELDS:
            if not isinstance(value, list) or len(value) > LIST_FIELDS[name]:
                raise ReportError(f"{name} must be a short list")
            items = value
        else:
            items = [value]
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (str, int)) or not pattern.match(str(item)):
                raise ReportError(f"invalid value for {name}")
        if name == "recent_events" and not set(value) <= _EVENT_NAMES:
            raise ReportError("unknown event identifier")
    if len(json.dumps(report, sort_keys=True)) > MAX_REPORT_BYTES:
        raise ReportError("report too large")
    return report


def _ok(name: str, value) -> bool:
    pattern = SCHEMA[name][0]
    return isinstance(value, (str, int)) and not isinstance(value, bool) and bool(pattern.match(str(value)))


def display_language() -> str:
    """Windows display (UI) language as a BCP-47 tag, e.g. ``ja-JP``; ``und`` when unknown."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            k32 = ctypes.windll.kernel32
            buf = ctypes.create_unicode_buffer(85)
            if k32.LCIDToLocaleName(k32.GetUserDefaultUILanguage(), buf, 85, 0):
                return buf.value
        except Exception:  # noqa: BLE001
            pass
    return "und"


def _build_kind() -> str:
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64", "x86": "x86"}.get(
        platform.machine().lower(), "unknown")
    if sys.maxsize <= 2**32 and arch == "x64":
        arch = "x86"
    if not getattr(sys, "frozen", False):
        return f"source-{arch}"
    try:
        from app.paths import INSTALLED_READ_ONLY

        return f"{'installed' if INSTALLED_READ_ONLY else 'portable'}-{arch}"
    except Exception:  # noqa: BLE001
        return f"portable-{arch}"


def code_location(tb) -> list[str]:
    """``module:function:line`` of Monograph PDF's own frames (no paths, no variable values)."""
    out = []
    for frame, lineno in traceback.walk_tb(tb):
        module = str(frame.f_globals.get("__name__", ""))
        if not module.startswith(APP_MODULES):
            continue
        entry = f"{module}:{frame.f_code.co_name}:{lineno}"
        if _ok("code_location", entry):
            out.append(entry)
    return out[-LIST_FIELDS["code_location"]:]


def exception_type(exc: BaseException) -> str:
    cls = type(exc)
    mod = cls.__module__
    name = cls.__qualname__ if mod in ("builtins", "__main__") else f"{mod}.{cls.__qualname__}"
    return name if _ok("exception_type", name) else "Exception"


def build(error: EventId | str, exc: BaseException | None = None, *, report_type: str = "error",
          events: list[str] | None = None, now: datetime | None = None) -> dict:
    """A validated report for failure ``error`` (one of the ``*_FAILED`` identifiers)."""
    from core.versioning import get_version

    ev = EventId(error)
    component, operation = FAILURES.get(ev, ("app", "UNKNOWN"))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    report = {
        "schema": SCHEMA_VERSION,
        "report_type": report_type,
        "app_version": get_version(),
        "build": _build_kind(),
        "python_version": platform.python_version(),
        "os": {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else "other"),
        "os_version": platform.version().split(" ")[0] if sys.platform.startswith("win") else platform.release().split("-")[0],
        "os_arch": platform.machine() or "unknown",
        "display_language": display_language(),
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:00Z"),
        "component": component,
        "operation": operation,
        "error_code": ev.value,
        "recent_events": [e for e in (diagnostics.recent() if events is None else events) if e in {x.value for x in EventId}][-30:],
    }
    if exc is not None:
        report["exception_type"] = exception_type(exc)
        report["code_location"] = code_location(exc.__traceback__)
    # optional fields that do not match their pattern are dropped rather than sent
    for name in list(report):
        if name in LIST_FIELDS:
            continue
        if not SCHEMA[name][1] and not _ok(name, report[name]):
            del report[name]
    report["fingerprint"] = fingerprint(report)
    return validate(report)


def fingerprint(report: dict) -> str:
    """Groups identical software failures; derived from code, never from the user or the device."""
    basis = "|".join([str(report.get("error_code", "")), str(report.get("exception_type", "")),
                      ",".join(report.get("code_location", [])[-3:]), str(report.get("app_version", ""))])
    return hashlib.sha256(basis.encode("ascii", "replace")).hexdigest()[:16]


def render(report: dict) -> str:
    """The exact report as the user sees it before deciding (one field per line)."""
    lines = []
    for name in SCHEMA:
        if name not in report:
            continue
        value = report[name]
        if isinstance(value, list):
            lines.append(f"{name}:")
            lines.extend(f"  - {v}" for v in value)
        else:
            lines.append(f"{name}: {value}")
    return "\n".join(lines)
