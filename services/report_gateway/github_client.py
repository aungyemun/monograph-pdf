"""Minimal GitHub client for the gateway: issues in ONE private repository, nothing else.

Authentication is a GitHub App (private key on the server only). Every installation token is
requested *down-scoped* to ``{"issues": "write"}`` on the single reporting repository, so even a
mis-configured App installation cannot give the gateway access to code, commits, branches, tags,
pull requests, releases or workflows. The client also only knows three issue endpoints.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

API = "https://api.github.com"
TOKEN_PERMISSIONS = {"issues": "write"}
# GitHub adds read-only repository metadata to every installation token
ACCEPTED_GRANTS = {"issues": "write", "metadata": "read"}
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def app_jwt(app_id: str, private_key_pem: bytes, now: int | None = None) -> str:
    """RS256 JSON Web Token for the GitHub App (signed with ``cryptography``)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time()) if now is None else now
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    sig = key.sign(f"{header}.{payload}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64(sig)}"


@dataclass
class Credentials:
    app_id: str
    installation_id: str
    private_key_pem: bytes

    @property
    def complete(self) -> bool:
        return bool(self.app_id and self.installation_id and self.private_key_pem)


Transport = Callable[[str, str, dict, bytes | None], tuple[int, dict]]


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict]:
    if not url.startswith(API + "/"):
        raise GitHubError("refusing to contact a non-GitHub API URL")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(1024 * 1024)
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        return exc.code, {}


class ReportRepository:
    # The only API calls the gateway can make (checked by the tests)
    ALLOWED = (
        ("POST", re.compile(r"^/app/installations/\d+/access_tokens$")),
        ("GET", re.compile(r"^/repos/[^/]+/[^/]+/issues\?labels=fp-[0-9a-f]{16}&state=all&per_page=1$")),
        ("POST", re.compile(r"^/repos/[^/]+/[^/]+/issues$")),
        ("POST", re.compile(r"^/repos/[^/]+/[^/]+/issues/\d+/comments$")),
    )

    def __init__(self, repository: str, credentials: Credentials, transport: Transport = urllib_transport,
                 jwt_factory: Callable[[Credentials], str] | None = None) -> None:
        if not _REPO.match(repository or ""):
            raise GitHubError("REPORT_REPOSITORY must be owner/name")
        self.repository = repository
        self.credentials = credentials
        self._transport = transport
        self._jwt = jwt_factory or (lambda c: app_jwt(c.app_id, c.private_key_pem))
        self._token: tuple[str, float] | None = None

    def _call(self, method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
        if not any(m == method and rx.match(path) for m, rx in self.ALLOWED):
            raise GitHubError(f"API call not allowed: {method} {path}")
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "monograph-pdf-report-gateway"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return self._transport(method, API + path, headers, body)

    def _installation_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        if not self.credentials.complete:
            raise GitHubError("GitHub App credentials are not configured", 503)
        name = self.repository.split("/", 1)[1]
        status, data = self._call("POST", f"/app/installations/{self.credentials.installation_id}/access_tokens",
                                  self._jwt(self.credentials),
                                  {"repositories": [name], "permissions": TOKEN_PERMISSIONS})
        if status != 201 or not isinstance(data.get("token"), str):
            raise GitHubError("could not obtain an installation token for the reporting repository", status)
        granted = data.get("permissions") or {}
        if granted.get("issues") != "write" or any(ACCEPTED_GRANTS.get(k) != v for k, v in granted.items()):
            # GitHub returned broader (or different) permissions than requested: do not use the token
            raise GitHubError("installation token permissions are not limited to issues:write", 503)
        self._token = (data["token"], time.time() + 50 * 60)
        return data["token"]

    def file_report(self, fingerprint: str, title: str, body: str, comment: str) -> str:
        """Comment on the issue of this fingerprint, or open one. Returns "created" or "grouped"."""
        token = self._installation_token()
        label = f"fp-{fingerprint}"
        status, data = self._call("GET", f"/repos/{self.repository}/issues?labels={label}&state=all&per_page=1", token)
        if status != 200:
            raise GitHubError("GitHub issue lookup failed", status)
        if isinstance(data, list) and data and isinstance(data[0].get("number"), int):
            status, _ = self._call("POST", f"/repos/{self.repository}/issues/{data[0]['number']}/comments", token,
                                   {"body": comment})
            if status != 201:
                raise GitHubError("GitHub comment failed", status)
            return "grouped"
        status, _ = self._call("POST", f"/repos/{self.repository}/issues", token,
                               {"title": title, "body": body, "labels": ["error-report", label]})
        if status != 201:
            raise GitHubError("GitHub issue creation failed", status)
        return "created"
