"""WSGI application: receives Monograph PDF error reports and files them as private GitHub issues.

    POST /v1/reports   Content-Type: application/json   body: one report (<= 8 KB)

Responses: 202 accepted · 400 invalid · 405/404 wrong method or path · 413 too large ·
415 wrong content type · 429 rate limited · 502 GitHub failed · 503 not configured.

Security properties
* Allow-listed schema only (report_schema.py); unknown fields are rejected, nothing is executed or
  interpreted; values are restricted to fixed vocabularies and identifier patterns.
* No PDF or file uploads, no free text, no personal data fields.
* Rate limits per client (keyed by a salted hash of the address that lives only in memory) and
  globally; client addresses are never logged or stored.
* Minimal logging: status code and fingerprint only.
* The GitHub client can only list/create issues and comments in one private repository, with an
  installation token down-scoped to issues:write.
* HTTPS is terminated by the hosting platform or reverse proxy in front of this application.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from typing import Callable

from services.report_gateway.github_client import Credentials, GitHubError, ReportRepository
from services.report_gateway.report_schema import MAX_REPORT_BYTES, InvalidReport, validate

log = logging.getLogger("report_gateway")


class RateLimiter:
    """Token buckets: per client (hashed with a per-process random salt) and global."""

    def __init__(self, per_client: int = 5, per_client_window: float = 3600.0, global_limit: int = 500,
                 global_window: float = 3600.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._salt = secrets.token_bytes(16)
        self._clock = clock
        self._lock = threading.Lock()
        self._clients: dict[str, list[float]] = {}
        self._global: list[float] = []
        self.per_client, self.per_client_window = per_client, per_client_window
        self.global_limit, self.global_window = global_limit, global_window

    def allow(self, client: str) -> bool:
        key = hashlib.sha256(self._salt + client.encode("utf-8", "replace")).hexdigest()
        now = self._clock()
        with self._lock:
            self._global = [t for t in self._global if now - t < self.global_window]
            hits = [t for t in self._clients.get(key, []) if now - t < self.per_client_window]
            if len(self._global) >= self.global_limit or len(hits) >= self.per_client:
                self._clients[key] = hits
                return False
            hits.append(now)
            self._clients[key] = hits
            self._global.append(now)
            if len(self._clients) > 50000:  # bounded memory
                self._clients = {k: v for k, v in self._clients.items() if v and now - v[-1] < self.per_client_window}
            return True


def _fence(text: str) -> str:
    return "```\n" + text.replace("`", "'") + "\n```"


def issue_text(report: dict) -> tuple[str, str, str]:
    title = f"[{report['error_code']}] {report.get('exception_type', 'no exception')} in {report['component']} " \
            f"(v{report['app_version']}, fp {report['fingerprint']})"
    details = json.dumps(report, indent=2, sort_keys=True)
    body = ("Automated Monograph PDF error report, sent with the user's approval. It contains only "
            "allow-listed technical fields (no documents, file names, paths or personal data).\n\n" + _fence(details))
    comment = f"Another report with fingerprint `{report['fingerprint']}`:\n\n" + _fence(details)
    return title[:250], body, comment


def _respond(start_response, status: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(data))),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
    return [data]


def make_app(repository: ReportRepository | None, limiter: RateLimiter | None = None):
    limiter = limiter or RateLimiter()

    def app(environ, start_response):
        if environ.get("PATH_INFO") != "/v1/reports":
            return _respond(start_response, "404 Not Found", {"error": "not found"})
        if environ.get("REQUEST_METHOD") != "POST":
            return _respond(start_response, "405 Method Not Allowed", {"error": "method not allowed"})
        if (environ.get("CONTENT_TYPE") or "").split(";")[0].strip().lower() != "application/json":
            return _respond(start_response, "415 Unsupported Media Type", {"error": "JSON only"})
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return _respond(start_response, "400 Bad Request", {"error": "invalid length"})
        if length <= 0:
            return _respond(start_response, "400 Bad Request", {"error": "empty body"})
        if length > MAX_REPORT_BYTES:
            return _respond(start_response, "413 Payload Too Large", {"error": "too large"})
        if not limiter.allow(environ.get("REMOTE_ADDR", "")):
            return _respond(start_response, "429 Too Many Requests", {"error": "rate limited"})
        raw = environ["wsgi.input"].read(length + 1)
        if len(raw) > MAX_REPORT_BYTES:
            return _respond(start_response, "413 Payload Too Large", {"error": "too large"})
        try:
            report = validate(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, ValueError, InvalidReport) as exc:
            msg = str(exc) if isinstance(exc, InvalidReport) else "malformed JSON"
            return _respond(start_response, "400 Bad Request", {"error": msg})
        if repository is None:
            return _respond(start_response, "503 Service Unavailable", {"error": "not configured"})
        title, body, comment = issue_text(report)
        try:
            outcome = repository.file_report(report["fingerprint"], title, body, comment)
        except GitHubError as exc:
            log.warning("report %s not filed (GitHub status %s)", report["fingerprint"], exc.status)
            if exc.status == 503:
                return _respond(start_response, "503 Service Unavailable", {"error": "not configured"})
            return _respond(start_response, "502 Bad Gateway", {"error": "could not store the report"})
        log.info("report %s %s", report["fingerprint"], outcome)
        return _respond(start_response, "202 Accepted", {"status": outcome})

    return app


def from_environment():
    """Build the app from environment variables (see README.md). The private key is read from a
    file path, never from the repository."""
    repo = os.environ.get("REPORT_REPOSITORY", "")
    key_file = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "")
    key = b""
    if key_file:
        with open(key_file, "rb") as fh:
            key = fh.read()
    creds = Credentials(os.environ.get("GITHUB_APP_ID", ""), os.environ.get("GITHUB_APP_INSTALLATION_ID", ""), key)
    repository = ReportRepository(repo, creds) if repo and creds.complete else None
    return make_app(repository)
