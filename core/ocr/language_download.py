"""Download an optional OCR language when the user clicks **Download and Install**.

Nothing is downloaded at any other time. The file comes from the official Tesseract release pinned in
``resources/ocr/language_packs.json`` (tesseract-ocr/tessdata_fast 4.1.0, the release of the bundled
English and Japanese data) and is installed only if its size and SHA-256 match the pin, exactly like a
file installed with **Install from File** (core/ocr/language_packs.py).

Connection rules are those of the update checker (core/updates/net.py): HTTPS only with certificate
and host-name verification, every address and redirect on an allow-list (github.com and
raw.githubusercontent.com), bounded size, no cookies or credentials, cancellable.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Callable

from core.ocr.language_packs import LanguagePack, LanguagePackError, install_from_file, user_language_dir

DOWNLOAD_HOSTS = ("github.com", "raw.githubusercontent.com")


class _Source:
    """The part of an update configuration core.updates.net needs: allowed hosts and CA file."""

    ca_file = None

    def host_allowed(self, url: str) -> bool:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        return parts.scheme == "https" and (parts.hostname or "").lower() in DOWNLOAD_HOSTS


def _message(text: str) -> str:
    return (text.replace("update server", "download server").replace("update source", "download address")
            .replace("installer download", "download").replace("the installer on the server", "the file on the server")
            .replace("the update information", "the file"))


def download_and_install(pack: LanguagePack, cancel: threading.Event | None = None,
                         progress: Callable[[int, int], None] | None = None) -> LanguagePack:
    """Download ``pack`` from its pinned address, verify it and install it. Raises LanguagePackError
    (with a message for the user) when anything fails; nothing half-done is left behind."""
    from core.updates import net

    cancel = cancel or threading.Event()
    folder = user_language_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{pack.code}.{uuid.uuid4().hex[:8]}.download"
    try:
        try:
            net.download(_Source(), pack.url, tmp, pack.size, cancel,
                         (lambda p: progress(p.received, p.total)) if progress else None)
        except net.Cancelled:
            raise LanguagePackError("The download was cancelled; nothing was installed.") from None
        except net.NetworkError as exc:
            raise LanguagePackError(f"{pack.name} could not be downloaded: {_message(str(exc))}. "
                                    "Nothing was installed.") from None
        installed = install_from_file(tmp)  # size and SHA-256 must match the pin
        if installed.code != pack.code:
            raise LanguagePackError("The downloaded file is a different language; nothing was installed.")
        return installed
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
