"""Sends one approved report to the reporting gateway — the only network code of error reporting.

Called only after the user clicked **Send to Developer**. HTTPS with certificate verification to
the single configured endpoint; no redirects are followed, no retries happen without the user, the
request has a short timeout, and the body is the validated report exactly as the user saw it.
Sending stays disabled until ``resources/diagnostics/reporting.json`` names a verified gateway.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from core.diagnostics import report as reports

TIMEOUT = 15.0


@dataclass(frozen=True)
class ReportingConfig:
    enabled: bool
    endpoint: str
    ca_file: Path | None = None

    @property
    def usable(self) -> bool:
        parts = urlsplit(self.endpoint)
        return self.enabled and parts.scheme == "https" and bool(parts.hostname) and parts.username is None


def load_config(path: Path | None = None) -> ReportingConfig:
    if path is None:
        from app.paths import RESOURCES_DIR

        path = RESOURCES_DIR / "diagnostics" / "reporting.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != 1:
            raise ValueError
        ca = raw.get("ca_file")
        ca_path = path.parent / ca if isinstance(ca, str) and ca and "/" not in ca and "\\" not in ca else None
        return ReportingConfig(bool(raw.get("enabled")), str(raw.get("endpoint", "")), ca_path)
    except (OSError, ValueError, AttributeError):
        return ReportingConfig(False, "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass
class SendResult:
    ok: bool
    message: str


def send(report: dict, config: ReportingConfig | None = None) -> SendResult:
    config = config or load_config()
    if not config.usable:
        return SendResult(False, "Sending error reports is not enabled in this build. Nothing was sent.")
    try:
        body = json.dumps(reports.validate(report), sort_keys=True).encode("utf-8")
    except reports.ReportError:
        return SendResult(False, "The report did not pass the privacy check. Nothing was sent.")
    from core.versioning import get_version

    ctx = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _NoRedirect())
    req = urllib.request.Request(config.endpoint, data=body, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": f"MonographPDF/{get_version()} (+error-report)"})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            if resp.status in (200, 201, 202):
                return SendResult(True, "The report was sent. Thank you.")
            return SendResult(False, f"The reporting service answered HTTP {resp.status}. The report may not have arrived.")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return SendResult(False, "The reporting service is busy (too many reports). Nothing more will be sent.")
        return SendResult(False, f"The reporting service refused the report (HTTP {exc.code}).")
    except Exception as exc:  # noqa: BLE001
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLError):
            return SendResult(False, "The secure connection to the reporting service could not be verified. Nothing was sent.")
        return SendResult(False, "The reporting service could not be reached (offline?). Nothing was sent.")
