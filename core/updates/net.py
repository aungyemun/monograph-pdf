"""HTTPS access for update checks and downloads — the only network code of the updater.

* HTTPS only, with certificate and host-name verification (``ssl.create_default_context``: the
  Windows certificate store on Windows). TLS verification is never disabled; there is no HTTP
  fallback.
* Every URL, including each redirect target, must be HTTPS on a host from the bundled allow-list
  (GitHub's release download redirects stay inside it). At most 5 redirects.
* Response sizes are bounded; downloads stream to disk in chunks and can be cancelled.
* No cookies, credentials or tokens are sent; the only identifying header is the product
  User-Agent with its version (GitHub's API requires a User-Agent).
"""

from __future__ import annotations

import socket
import ssl
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.updates.config import UpdateConfig

TIMEOUT = 20.0
CHUNK = 256 * 1024
MAX_REDIRECTS = 5


class NetworkError(Exception):
    """Could not reach or use the update source. ``kind`` drives the status shown to the user."""

    def __init__(self, message: str, kind: str = "network") -> None:
        super().__init__(message)
        self.kind = kind  # offline | timeout | tls | http | rate_limited | redirect | too_large | cancelled | not_found


class Cancelled(NetworkError):
    def __init__(self) -> None:
        super().__init__("cancelled", "cancelled")


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, config: UpdateConfig) -> None:
        super().__init__()
        self._config = config

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self._config.host_allowed(newurl):
            raise NetworkError("the update source redirected to a location that is not allowed", "redirect")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            # never forward anything that could identify the user to another host
            for h in ("Authorization", "Cookie"):
                new.remove_header(h)
        return new


def _context(config: UpdateConfig) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    # create_default_context already sets these; checked so a future edit cannot weaken them
    if ctx.verify_mode != ssl.CERT_REQUIRED or not ctx.check_hostname:
        raise NetworkError("certificate verification is required", "tls")
    return ctx


def _opener(config: UpdateConfig) -> urllib.request.OpenerDirector:
    # build_opener adds the system proxy handler; there is no plain-HTTP or file: handler use since
    # every URL is checked before it is opened
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=_context(config)), _Redirects(config))


def _user_agent() -> str:
    try:
        from core.versioning import get_version

        return f"MonographPDF/{get_version()} (+updater)"
    except Exception:  # noqa: BLE001
        return "MonographPDF (+updater)"


def _classify(exc: BaseException) -> NetworkError:
    if isinstance(exc, NetworkError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
        if exc.code == 429 or (exc.code == 403 and remaining == "0"):
            return NetworkError("the update server's request limit was reached; try again later", "rate_limited")
        if exc.code == 404:
            return NetworkError("the update information was not found on the server", "not_found")
        return NetworkError(f"the update server answered HTTP {exc.code}", "http")
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLError) or isinstance(exc, ssl.SSLError):
        return NetworkError("the secure connection to the update server could not be verified", "tls")
    if isinstance(reason, (socket.timeout, TimeoutError)) or isinstance(exc, (socket.timeout, TimeoutError)):
        return NetworkError("the update server did not respond in time", "timeout")
    if isinstance(reason, socket.gaierror) or isinstance(exc, socket.gaierror):
        return NetworkError("no internet connection (the update server's name could not be resolved)", "offline")
    return NetworkError("could not connect to the update server", "offline")


def _open(config: UpdateConfig, url: str, accept: str):
    if not config.host_allowed(url):
        raise NetworkError("this address is not an allowed update source", "redirect")
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent(), "Accept": accept})
    try:
        resp = _opener(config).open(req, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc) from None
    final = resp.geturl()
    if not config.host_allowed(final):
        resp.close()
        raise NetworkError("the update source ended at a location that is not allowed", "redirect")
    return resp


def fetch_bytes(config: UpdateConfig, url: str, limit: int, accept: str = "application/json") -> bytes:
    """GET a small document (manifest, release list) and return at most ``limit`` bytes."""
    resp = _open(config, url, accept)
    try:
        length = resp.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > limit:
            raise NetworkError("the update information is too large", "too_large")
        data = resp.read(limit + 1)
    except NetworkError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc) from None
    finally:
        resp.close()
    if len(data) > limit:
        raise NetworkError("the update information is too large", "too_large")
    return data


@dataclass
class DownloadProgress:
    received: int
    total: int


def download(config: UpdateConfig, url: str, dest: Path, expected_size: int, cancel: threading.Event,
             progress: Callable[[DownloadProgress], None] | None = None) -> None:
    """Stream ``url`` into ``dest`` (a new file). Stops at ``expected_size`` + 1 bytes."""
    resp = _open(config, url, "application/octet-stream")
    received = 0
    try:
        length = resp.headers.get("Content-Length")
        if length and length.isdigit() and int(length) != expected_size:
            raise NetworkError("the installer on the server has an unexpected size", "too_large")
        with open(dest, "xb") as fh:
            while True:
                if cancel.is_set():
                    raise Cancelled()
                try:
                    block = resp.read(CHUNK)
                except Exception as exc:  # noqa: BLE001
                    raise _classify(exc) from None
                if not block:
                    break
                received += len(block)
                if received > expected_size:
                    raise NetworkError("the installer download is larger than announced", "too_large")
                fh.write(block)
                if progress is not None:
                    progress(DownloadProgress(received, expected_size))
    finally:
        resp.close()
    if received != expected_size:
        raise NetworkError("the download was interrupted before it completed", "network")
