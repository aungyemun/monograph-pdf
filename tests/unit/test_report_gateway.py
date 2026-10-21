"""Reporting gateway: request validation, abuse limits and least-privilege GitHub access (mocked)."""

from __future__ import annotations

import io
import json

import pytest

from core.diagnostics import EventId
from core.diagnostics import report as reports
from services.report_gateway import github_client as gh
from services.report_gateway.gateway import RateLimiter, issue_text, make_app


class FakeGitHub:
    """Records every call; answers like GitHub's REST API."""

    def __init__(self, *, token_status=201, permissions=None, fail_on=None) -> None:
        self.calls: list[tuple[str, str, dict, dict | None]] = []
        self.issues: dict[str, int] = {}
        self.token_status = token_status
        self.permissions = permissions if permissions is not None else {"issues": "write", "metadata": "read"}
        self.fail_on = fail_on

    def __call__(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        path = url.removeprefix(gh.API)
        self.calls.append((method, path, headers, payload))
        if self.fail_on and self.fail_on in path:
            return 500, {}
        if path.endswith("/access_tokens"):
            return self.token_status, {"token": "ghs_test", "permissions": self.permissions}
        if method == "GET":
            label = path.split("labels=")[1].split("&")[0]
            return 200, ([{"number": self.issues[label]}] if label in self.issues else [])
        if path.endswith("/issues"):
            label = [x for x in payload["labels"] if x.startswith("fp-")][0]
            self.issues[label] = len(self.issues) + 1
            return 201, {"number": self.issues[label]}
        if path.endswith("/comments"):
            return 201, {}
        return 404, {}


def _repo(fake=None, complete=True):
    fake = fake or FakeGitHub()
    # the key text is split so that secret scanners do not flag this fake value
    fake_key = b"-----BEGIN " + b"PRIVATE KEY-----test"
    creds = gh.Credentials("12345", "678", fake_key if complete else b"")
    return gh.ReportRepository("owner/monograph-pdf-reports", creds, transport=fake, jwt_factory=lambda c: "jwt"), fake


def _call(app, body, *, method="POST", path="/v1/reports", ctype="application/json", length=None, addr="198.51.100.7"):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_TYPE": ctype, "REMOTE_ADDR": addr,
           "CONTENT_LENGTH": str(len(raw) if length is None else length), "wsgi.input": io.BytesIO(raw)}
    out = {}
    data = b"".join(app(env, lambda status, headers: out.update(status=status, headers=dict(headers))))
    return int(out["status"].split()[0]), json.loads(data)


def _report(**kw):
    rep = reports.build(EventId.PDF_SAVE_FAILED, events=["PDF_OPEN_STARTED", "PDF_SAVE_STARTED"])
    rep.update(kw)
    return rep


def test_valid_report_creates_a_private_issue_and_duplicates_are_grouped():
    repo, fake = _repo()
    app = make_app(repo)
    assert _call(app, _report()) == (202, {"status": "created"})
    assert _call(app, _report()) == (202, {"status": "grouped"})
    posts = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/issues")]
    assert len(posts) == 1 and "error-report" in posts[0][3]["labels"]
    assert any(c[1].endswith("/issues/1/comments") for c in fake.calls)
    token_req = [c for c in fake.calls if c[1].endswith("/access_tokens")][0]
    assert token_req[3] == {"repositories": ["monograph-pdf-reports"], "permissions": {"issues": "write"}}


@pytest.mark.parametrize("body,status", [
    ({"schema": 1}, 400),
    (lambda: _report(unexpected="field"), 400),
    (lambda: _report(component="pdf; DROP TABLE"), 400),
    (lambda: _report(exception_type="Error `@everyone` [link](https://evil)"), 400),
    (lambda: _report(code_location=["core.x:f:1", "<script>alert(1)</script>"]), 400),
    (lambda: _report(recent_events=["$(rm -rf /)"]), 400),
    ([1, 2, 3], 400),
    (b"{not json", 400),
    (b"\xff\xfe\x00", 400),
])
def test_invalid_reports_and_injection_attempts_are_rejected(body, status):
    repo, fake = _repo()
    app = make_app(repo)
    code, _ = _call(app, body() if callable(body) else body)
    assert code == status
    assert not any(c[0] == "POST" for c in fake.calls)  # nothing reached GitHub


def test_protocol_limits():
    repo, _ = _repo()
    app = make_app(repo)
    assert _call(app, _report(), method="GET")[0] == 405
    assert _call(app, _report(), path="/v1/upload")[0] == 404
    assert _call(app, _report(), ctype="multipart/form-data")[0] == 415
    assert _call(app, b"x" * 9000)[0] == 413
    assert _call(app, _report(), length=0)[0] == 400
    assert _call(app, _report(), length="abc")[0] == 400
    # only the declared length is read: a body cut short by its declared length is malformed
    raw = json.dumps(_report()).encode()
    assert _call(app, raw + b"tail", length=len(raw) // 2)[0] == 400


def test_rate_limiting_per_client_and_globally():
    repo, _ = _repo()
    clock = [0.0]
    limiter = RateLimiter(per_client=2, global_limit=3, clock=lambda: clock[0])
    app = make_app(repo, limiter)
    assert _call(app, _report(), addr="a")[0] == 202
    assert _call(app, _report(), addr="a")[0] == 202
    assert _call(app, _report(), addr="a")[0] == 429
    assert _call(app, _report(), addr="b")[0] == 202
    assert _call(app, _report(), addr="c")[0] == 429  # global limit
    clock[0] += 3601
    assert _call(app, _report(), addr="a")[0] == 202
    # client addresses are only kept as salted hashes in memory
    assert all("a" != k and len(k) == 64 for k in limiter._clients)  # noqa: SLF001


def test_github_failures_and_missing_credentials():
    repo, _ = _repo(FakeGitHub(fail_on="/issues?labels"))
    assert _call(make_app(repo), _report())[0] == 502
    repo, _ = _repo(FakeGitHub(token_status=401))
    assert _call(make_app(repo), _report())[0] == 502
    repo, _ = _repo(complete=False)
    assert _call(make_app(repo), _report())[0] == 503
    assert _call(make_app(None), _report())[0] == 503


@pytest.mark.parametrize("granted", [
    {"issues": "write", "contents": "write"}, {"issues": "write", "pull_requests": "write"},
    {"issues": "write", "workflows": "write"}, {"issues": "write", "administration": "read"},
    {"issues": "read"}, {},
])
def test_tokens_broader_or_narrower_than_issues_write_are_refused(granted):
    repo, fake = _repo(FakeGitHub(permissions=granted))
    assert _call(make_app(repo), _report())[0] == 503
    assert not any(c[1].endswith("/issues") for c in fake.calls if c[0] == "POST")


def test_client_cannot_touch_code_releases_tags_or_workflows():
    repo, _ = _repo()
    for method, path in [("PUT", "/repos/o/r/contents/core/x.py"), ("POST", "/repos/o/r/git/refs"),
                         ("POST", "/repos/o/r/releases"), ("PATCH", "/repos/o/r/releases/1"),
                         ("POST", "/repos/o/r/pulls"), ("POST", "/repos/o/r/actions/workflows/x/dispatches"),
                         ("DELETE", "/repos/o/r/git/refs/tags/v0.2.3"), ("POST", "/repos/o/r/git/tags"),
                         ("GET", "/repos/o/r/issues?labels=x&state=all")]:
        with pytest.raises(gh.GitHubError, match="not allowed"):
            repo._call(method, path, "t")  # noqa: SLF001
    with pytest.raises(gh.GitHubError):
        gh.urllib_transport("GET", "https://evil.example/x", {}, None)


def test_issue_text_is_fenced_and_free_of_markdown_tricks():
    title, body, comment = issue_text(_report())
    assert "```" in body and body.count("```") == 2
    assert "@" not in title and "](" not in body


def test_app_jwt_is_a_valid_rs256_token():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    token = gh.app_jwt("12345", pem, now=1_800_000_000)
    head, payload, sig = token.split(".")
    import base64

    def b64(s):
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    assert json.loads(b64(head)) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(b64(payload))
    assert claims["iss"] == "12345" and claims["exp"] - claims["iat"] <= 600
    key.public_key().verify(b64(sig), f"{head}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_gateway_is_separate_from_the_application():
    """The app never imports the gateway; the gateway never imports the app (deployed separately)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for folder in ("app", "core", "ui", "engines"):
        for f in (root / folder).rglob("*.py"):
            assert "report_gateway" not in f.read_text(encoding="utf-8"), f
    for f in (root / "services" / "report_gateway").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "from core" not in text and "import core" not in text and "from app" not in text, f
        # no access to update signing material or release configuration
        assert "update_config" not in text and "signing key" not in text.lower() and "/releases" not in text, f
