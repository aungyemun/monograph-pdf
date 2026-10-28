"""TLS trust of the updater (0.5.1): Windows verifies with the Windows certificate chain engine.

0.5.0 verified GitHub's certificate with OpenSSL fed with a snapshot of the Windows ROOT and CA
stores. On PCs where Windows had not yet installed the Sectigo Public Server Authentication Root E46,
OpenSSL followed the cross-certificate "USERTrust ECC <- AAA Certificate Services" from the CA store
to a root that is not installed and failed ("unable to get issuer certificate"), so Check for Updates
reported "Secure connection could not be verified". These tests pin the fix and the protections that
must not change with it. The live check against GitHub runs only when MONOGRAPH_PDF_LIVE_NETWORK=1.
"""

from __future__ import annotations

import os
import ssl
import sys
import types
from dataclasses import replace

import pytest

from core.updates import net
from tests.fixtures.update_fixtures import make_config

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows certificate chain engine")


@pytest.fixture
def cfg():
    return make_config(hosts=("api.github.com", "github.com"), ca_file=None)


@windows_only
def test_windows_uses_the_windows_chain_engine_with_full_verification(cfg):
    import truststore

    ctx = net._context(cfg)  # noqa: SLF001
    assert isinstance(ctx, truststore.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2
    # nothing loaded into the wrapped OpenSSL context, which is what truststore's "custom CA" retry
    # reads (sock.context.get_ca_certs()): the Windows trusted roots are the only trust source
    assert ctx._ctx.get_ca_certs() == []  # noqa: SLF001


@windows_only
def test_truststore_pin_is_the_audited_version():
    import truststore

    # 0.10.5 also verifies sockets whose handshake runs outside wrap_socket(); 0.10.4 did not
    assert truststore.__version__ == "0.10.5"


def test_test_ca_file_is_the_only_trust_anchor(tmp_path, cfg):
    pytest.importorskip("cryptography")
    from tests.unit.test_update_net import _certs

    ca, _cert, _key = _certs(tmp_path)
    ctx = net._context(replace(cfg, ca_file=ca))  # noqa: SLF001
    assert type(ctx) is ssl.SSLContext
    assert len(ctx.get_ca_certs()) == 1
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_other_platforms_keep_openssl_with_system_roots(cfg, monkeypatch):
    monkeypatch.setattr(net, "sys", types.SimpleNamespace(platform="linux"))
    ctx = net._context(cfg)  # noqa: SLF001
    assert type(ctx) is ssl.SSLContext
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_missing_truststore_on_windows_refuses_instead_of_falling_back(cfg, monkeypatch):
    monkeypatch.setattr(net, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setitem(sys.modules, "truststore", None)  # import truststore -> ImportError
    with pytest.raises(net.NetworkError) as e:
        net._context(cfg)  # noqa: SLF001
    assert e.value.kind == "tls"


def test_a_context_without_verification_is_rejected(cfg, monkeypatch):
    def weak():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    monkeypatch.setattr(net, "_system_trust_context", weak)
    with pytest.raises(net.NetworkError) as e:
        net._context(cfg)  # noqa: SLF001
    assert e.value.kind == "tls"
    monkeypatch.setattr(net, "_system_trust_context",
                        lambda: (c := ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), setattr(c, "check_hostname", False))[0])
    with pytest.raises(net.NetworkError):
        net._context(cfg)  # noqa: SLF001


@pytest.mark.parametrize("message", [
    "A certificate chain processed, but terminated in a root certificate which is not trusted by the trust provider.",
    "unable to get issuer certificate",
])
def test_verification_failures_are_tls_and_keep_the_verifier_reason(message):
    err = ssl.SSLCertVerificationError(message)
    err.verify_message = message
    for exc in (err, net.urllib.error.URLError(err)):
        out = net._classify(exc)  # noqa: SLF001
        assert out.kind == "tls"
        assert message in str(out)


def test_connectivity_failures_are_not_reported_as_tls():
    import socket

    assert net._classify(net.urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))).kind == "offline"  # noqa: SLF001
    assert net._classify(net.urllib.error.URLError(TimeoutError())).kind == "timeout"  # noqa: SLF001
    assert net._classify(ConnectionRefusedError()).kind == "offline"  # noqa: SLF001


@windows_only
@pytest.mark.skipif(os.environ.get("MONOGRAPH_PDF_LIVE_NETWORK") != "1", reason="live network check (opt-in)")
def test_live_github_release_listing_verifies(cfg):
    data = net.fetch_bytes(cfg, "https://api.github.com/repos/aungyemun/monograph-pdf/releases?per_page=1", 2_000_000)
    assert data.lstrip().startswith(b"[")
