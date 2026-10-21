"""HTTPS behaviour of the updater against a local mock release server (test CA, 127.0.0.1)."""

from __future__ import annotations

import datetime as dt
import hashlib
import http.server
import ipaddress
import ssl
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from core.updates import manager, net
from core.updates.install_target import InstallTarget
from core.updates.manifest import parse_and_verify
from tests.fixtures.update_fixtures import make_config, manifest_bytes, setup_bytes, signed_fields

x509 = pytest.importorskip("cryptography.x509", reason="needs cryptography to create a test certificate")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

SETUP = setup_bytes("0.3.1", 300_000)


def _certs(folder: Path) -> tuple[Path, Path, Path]:
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Monograph PDF update test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
          .not_valid_after(now + dt.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                       crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_pem, cert_pem, key_pem = folder / "ca.pem", folder / "server.pem", folder / "server-key.pem"
    ca_pem.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return ca_pem, cert_pem, key_pem


class _Handler(http.server.BaseHTTPRequestHandler):
    routes: dict = {}

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):  # noqa: N802
        route = self.routes.get(self.path.split("?")[0])
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        route(self)


def _send(h, data: bytes, status=200, headers=None, declare=None):
    h.send_response(status)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.send_header("Content-Length", str(len(data) if declare is None else declare))
    h.end_headers()
    h.wfile.write(data)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    folder = tmp_path_factory.mktemp("tls")
    ca, cert, key = _certs(folder)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    base = f"https://127.0.0.1:{port}"
    _Handler.routes = {
        "/ok.json": lambda h: _send(h, b'{"ok": true}'),
        "/redirect-allowed": lambda h: _send(h, b"", 302, {"Location": f"{base}/ok.json"}),
        "/redirect-evil": lambda h: _send(h, b"", 302, {"Location": "https://evil.example/ok.json"}),
        "/redirect-http": lambda h: _send(h, b"", 302, {"Location": f"http://127.0.0.1:{port}/ok.json"}),
        "/big.json": lambda h: _send(h, b"x" * 5000),
        "/setup.exe": lambda h: _send(h, SETUP),
        "/truncated.exe": lambda h: _send(h, SETUP[:1000], declare=len(SETUP)),
        "/wrong-length.exe": lambda h: _send(h, SETUP + b"extra"),
        "/slow.json": lambda h: (time.sleep(3), _send(h, b"{}")),
        "/ratelimit.json": lambda h: _send(h, b"{}", 403, {"X-RateLimit-Remaining": "0"}),
        "/429.json": lambda h: _send(h, b"{}", 429),
        "/500.json": lambda h: _send(h, b"{}", 500),
    }
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield base, ca
    httpd.shutdown()


@pytest.fixture
def cfg(server):
    base, ca = server
    return make_config(hosts=("127.0.0.1",), ca_file=ca, base=base)


def test_fetch_over_verified_tls(server, cfg):
    base, _ = server
    assert net.fetch_bytes(cfg, f"{base}/ok.json", 1000) == b'{"ok": true}'


def test_redirects_are_followed_only_inside_the_allow_list(server, cfg):
    base, _ = server
    assert net.fetch_bytes(cfg, f"{base}/redirect-allowed", 1000) == b'{"ok": true}'
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(cfg, f"{base}/redirect-evil", 1000)
    assert e.value.kind == "redirect"
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(cfg, f"{base}/redirect-http", 1000)
    assert e.value.kind == "redirect"


def test_plain_http_and_unlisted_hosts_are_never_contacted(server, cfg):
    base, _ = server
    for url in (base.replace("https", "http") + "/ok.json", "https://example.com/ok.json", "file:///etc/passwd"):
        with pytest.raises(net.NetworkError) as e:
            net.fetch_bytes(cfg, url, 1000)
        assert e.value.kind == "redirect"


def test_untrusted_certificate_fails_without_fallback(server, cfg):
    base, _ = server
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(replace(cfg, ca_file=None), f"{base}/ok.json", 1000)
    assert e.value.kind == "tls"


def test_size_limits(server, cfg):
    base, _ = server
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(cfg, f"{base}/big.json", 1000)
    assert e.value.kind == "too_large"


def test_rate_limit_server_errors_and_timeout(server, cfg, monkeypatch):
    base, _ = server
    for path, kind in (("/ratelimit.json", "rate_limited"), ("/429.json", "rate_limited"), ("/500.json", "http"),
                       ("/missing.json", "not_found")):
        with pytest.raises(net.NetworkError) as e:
            net.fetch_bytes(cfg, base + path, 1000)
        assert e.value.kind == kind, path
    monkeypatch.setattr(net, "TIMEOUT", 0.5)
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(cfg, f"{base}/slow.json", 1000)
    assert e.value.kind == "timeout"


def test_offline_is_reported_as_offline(cfg):
    cfg2 = replace(cfg, allowed_hosts=("no-such-host.invalid",))
    with pytest.raises(net.NetworkError) as e:
        net.fetch_bytes(cfg2, "https://no-such-host.invalid/ok.json", 1000)
    assert e.value.kind in ("offline", "timeout")


def test_download_complete_interrupted_wrong_length_and_cancelled(server, cfg, tmp_path):
    base, _ = server
    cancel = threading.Event()
    seen = []
    net.download(cfg, f"{base}/setup.exe", tmp_path / "a.part", len(SETUP), cancel, seen.append)
    assert (tmp_path / "a.part").read_bytes() == SETUP and seen[-1].received == len(SETUP)
    with pytest.raises(net.NetworkError):
        net.download(cfg, f"{base}/truncated.exe", tmp_path / "b.part", len(SETUP), cancel)
    with pytest.raises(net.NetworkError) as e:
        net.download(cfg, f"{base}/wrong-length.exe", tmp_path / "c.part", len(SETUP), cancel)
    assert e.value.kind == "too_large"
    cancel.set()
    with pytest.raises(net.Cancelled):
        net.download(cfg, f"{base}/setup.exe", tmp_path / "d.part", len(SETUP), cancel)


def test_end_to_end_download_and_verify_against_the_mock_server(server, cfg, tmp_path, monkeypatch):
    base, _ = server
    data = SETUP
    fields = signed_fields(data=data, base=base, release_page=f"{base}/release")
    fields["artifacts"][0]["url"] = f"{base}/v0.3.1/MonographPDF_0.3.1_Setup.exe"
    _Handler.routes["/v0.3.1/MonographPDF_0.3.1_Setup.exe"] = lambda h: _send(h, data)
    rel = parse_and_verify(manifest_bytes(fields), cfg)
    target = InstallTarget(True, install_dir=tmp_path / "app", mode="user", version="0.3.0")
    target.install_dir.mkdir()
    sd = manager.download_and_verify(cfg, rel, target, threading.Event())
    assert sd.installer.read_bytes() == data
    assert hashlib.sha256(sd.installer.read_bytes()).hexdigest() == rel.artifact.sha256
    # a server that serves different bytes for the same name is caught by the signed checksum
    _Handler.routes["/v0.3.1/MonographPDF_0.3.1_Setup.exe"] = lambda h: _send(h, b"MZ" + data[2:-1] + b"!")
    with pytest.raises(manager.UpdateError) as e:
        manager.download_and_verify(cfg, rel, target, threading.Event())
    assert e.value.code == "verify"
