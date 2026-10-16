"""Records (and refuses) network use, for the self-check and the offline tests.

Monograph PDF works offline: it never opens network connections or looks up host names. The
installer's self-check (``MonographPDF.exe --smoke-test``) and the test suite install this guard
while they exercise the app, so any library that tried to reach the network would be reported.
"""

from __future__ import annotations

import socket


class NetworkAttempts:
    """Context manager / installable guard around the socket layer."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._saved: dict[str, object] = {}

    def _refuse(self, what: str):
        def blocked(*args, **_kwargs):
            target = args[1] if what == "connect" and len(args) > 1 else (args[0] if args else "")
            self.attempts.append(f"{what}({target!r})")
            raise OSError(f"Monograph PDF works offline: network use refused ({what})")

        return blocked

    def install(self) -> "NetworkAttempts":
        self._saved = {
            "connect": socket.socket.connect,
            "connect_ex": socket.socket.connect_ex,
            "create_connection": socket.create_connection,
            "getaddrinfo": socket.getaddrinfo,
            "gethostbyname": socket.gethostbyname,
        }
        socket.socket.connect = self._refuse("connect")  # type: ignore[method-assign]
        socket.socket.connect_ex = self._refuse("connect")  # type: ignore[method-assign]
        socket.create_connection = self._refuse("create_connection")  # type: ignore[assignment]
        socket.getaddrinfo = self._refuse("getaddrinfo")  # type: ignore[assignment]
        socket.gethostbyname = self._refuse("gethostbyname")  # type: ignore[assignment]
        return self

    def uninstall(self) -> None:
        if not self._saved:
            return
        socket.socket.connect = self._saved["connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = self._saved["connect_ex"]  # type: ignore[method-assign]
        socket.create_connection = self._saved["create_connection"]  # type: ignore[assignment]
        socket.getaddrinfo = self._saved["getaddrinfo"]  # type: ignore[assignment]
        socket.gethostbyname = self._saved["gethostbyname"]  # type: ignore[assignment]
        self._saved = {}

    def __enter__(self) -> "NetworkAttempts":
        return self.install()

    def __exit__(self, *_exc) -> None:
        self.uninstall()
