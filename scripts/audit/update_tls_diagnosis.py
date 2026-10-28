"""Diagnose "Secure connection could not be verified" from Check for Updates (Windows).

For each update host it separates the usual causes:

* connectivity   — the name does not resolve or no TCP connection can be made (offline, firewall);
* proxy          — a system proxy is configured, or the certificate presented is not issued by the
                   public CA chain GitHub uses (a TLS-inspecting proxy or antivirus re-signs traffic);
* trust store    — OpenSSL with a snapshot of the Windows stores fails while the Windows certificate
                   chain engine succeeds (the 0.5.0 defect, fixed in 0.5.1);
* application    — the updater's own code path (core.updates.net) fails although the Windows chain
                   engine succeeds.

Read-only and offline-safe: nothing is trusted, written or sent beyond TLS handshakes and one GET of
the public release list through the updater's normal code. The presented certificates are read
without verification for display only (subject and issuer names).

Usage (repository root): env\\Scripts\\python.exe -I scripts\\audit\\update_tls_diagnosis.py
"""

from __future__ import annotations

import socket
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HOSTS = ("api.github.com", "github.com", "release-assets.githubusercontent.com")
PUBLIC_ISSUERS = ("Sectigo", "DigiCert", "Let's Encrypt", "USERTrust", "GlobalSign", "Microsoft")


def _names(der: bytes) -> tuple[str, str]:
    try:
        from cryptography import x509

        c = x509.load_der_x509_certificate(der)
        return c.subject.rfc4514_string(), c.issuer.rfc4514_string()
    except Exception:  # noqa: BLE001 — cryptography is optional here
        return "?", "?"


def _presented(host: str) -> str:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # display only: the result is never trusted or used
    with socket.create_connection((host, 443), timeout=15) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        return _names(t.getpeercert(binary_form=True))[1]


def _verify(host: str, ctx: ssl.SSLContext) -> str:
    try:
        with socket.create_connection((host, 443), timeout=15) as s, ctx.wrap_socket(s, server_hostname=host):
            return "OK"
    except ssl.SSLCertVerificationError as e:
        return f"FAIL ({getattr(e, 'verify_message', '') or e})"
    except OSError as e:
        return f"FAIL ({type(e).__name__}: {e})"


def main() -> int:
    print("Python", sys.version.split()[0], "|", ssl.OPENSSL_VERSION)
    proxies = urllib.request.getproxies()
    print("system proxy:", proxies or "none")
    try:
        import truststore

        win_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT) if sys.platform == "win32" else None
    except ImportError:
        win_ctx = None
    for host in HOSTS:
        print(f"\n{host}")
        try:
            addrs = sorted({a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
            print("  DNS:", ", ".join(addrs))
        except OSError as e:
            print("  DNS: FAIL", e, "-> connectivity (offline, DNS or firewall)")
            continue
        try:
            issuer = _presented(host)
        except OSError as e:
            print("  TCP/TLS: FAIL", e, "-> connectivity (firewall or proxy-only network)")
            continue
        public = any(p in issuer for p in PUBLIC_ISSUERS)
        print("  presented by:", issuer, "" if public else "-> NOT a public CA: TLS-inspecting proxy/antivirus?")
        snap = _verify(host, ssl.create_default_context())
        print("  OpenSSL + Windows store snapshot (0.5.0 verifier):", snap)
        if win_ctx is not None:
            eng = _verify(host, win_ctx)
            print("  Windows certificate chain engine (0.5.1 verifier):", eng)
            if snap.startswith("FAIL") and eng == "OK":
                print("  -> trust-store snapshot problem (0.5.0 defect); 0.5.1 is not affected")
    try:
        from core.updates import config, net

        cfg = config.load()
        data = net.fetch_bytes(cfg, cfg.releases_api_url, cfg.max_manifest_bytes * 64)
        print("\nupdater code path (core.updates.net): OK,", len(data), "bytes of release list")
    except Exception as e:  # noqa: BLE001
        kind = getattr(e, "kind", type(e).__name__)
        print(f"\nupdater code path (core.updates.net): FAIL [{kind}] {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
