"""Predefined diagnostic event identifiers and the in-memory ring buffer."""

from __future__ import annotations

import enum
import threading
import time
from collections import deque


class EventId(str, enum.Enum):
    APP_STARTED = "APP_STARTED"
    PDF_OPEN_STARTED = "PDF_OPEN_STARTED"
    PDF_OPEN_FAILED = "PDF_OPEN_FAILED"
    TEXT_EDIT_STARTED = "TEXT_EDIT_STARTED"
    TEXT_EDIT_FAILED = "TEXT_EDIT_FAILED"
    PDF_SAVE_STARTED = "PDF_SAVE_STARTED"
    PDF_SAVE_FAILED = "PDF_SAVE_FAILED"
    PDF_EXPORT_STARTED = "PDF_EXPORT_STARTED"
    PDF_EXPORT_FAILED = "PDF_EXPORT_FAILED"
    PDF_PRINT_STARTED = "PDF_PRINT_STARTED"
    PDF_PRINT_FAILED = "PDF_PRINT_FAILED"
    CONVERT_STARTED = "CONVERT_STARTED"
    CONVERT_FAILED = "CONVERT_FAILED"
    OCR_STARTED = "OCR_STARTED"
    OCR_FAILED = "OCR_FAILED"
    SUBPROCESS_FAILED = "SUBPROCESS_FAILED"
    UPDATE_CHECK_STARTED = "UPDATE_CHECK_STARTED"
    UPDATE_CHECK_FAILED = "UPDATE_CHECK_FAILED"
    UPDATE_DOWNLOAD_STARTED = "UPDATE_DOWNLOAD_STARTED"
    UPDATE_DOWNLOAD_FAILED = "UPDATE_DOWNLOAD_FAILED"
    UPDATE_INSTALL_STARTED = "UPDATE_INSTALL_STARTED"
    UPDATE_INSTALL_FAILED = "UPDATE_INSTALL_FAILED"
    QT_CRITICAL = "QT_CRITICAL"
    UNHANDLED_EXCEPTION = "UNHANDLED_EXCEPTION"
    UNEXPECTED_TERMINATION = "UNEXPECTED_TERMINATION"
    # What the user was doing (so a report of a crash says more than "it stopped")
    STYLE_CHANGED = "STYLE_CHANGED"
    PAGES_CHANGED = "PAGES_CHANGED"
    COMMENT_CHANGED = "COMMENT_CHANGED"


# Failure identifier -> (component, operation)
FAILURES: dict[EventId, tuple[str, str]] = {
    EventId.PDF_OPEN_FAILED: ("pdf", "PDF_OPEN"),
    EventId.TEXT_EDIT_FAILED: ("editing", "TEXT_EDIT"),
    EventId.PDF_SAVE_FAILED: ("pdf", "PDF_SAVE"),
    EventId.PDF_EXPORT_FAILED: ("pdf", "PDF_EXPORT"),
    EventId.PDF_PRINT_FAILED: ("print", "PDF_PRINT"),
    EventId.CONVERT_FAILED: ("convert", "CONVERT"),
    EventId.OCR_FAILED: ("ocr", "OCR"),
    EventId.SUBPROCESS_FAILED: ("app", "SUBPROCESS"),
    EventId.UPDATE_CHECK_FAILED: ("update", "UPDATE_CHECK"),
    EventId.UPDATE_DOWNLOAD_FAILED: ("update", "UPDATE_DOWNLOAD"),
    EventId.UPDATE_INSTALL_FAILED: ("update", "UPDATE_INSTALL"),
    EventId.QT_CRITICAL: ("ui", "QT"),
    EventId.UNHANDLED_EXCEPTION: ("app", "UNHANDLED"),
    EventId.UNEXPECTED_TERMINATION: ("app", "TERMINATION"),
}

RING_SIZE = 30
_REPEATABLE = {"STYLE_CHANGED", "PAGES_CHANGED", "COMMENT_CHANGED", "TEXT_EDIT_STARTED"}


class Diagnostics:
    """Bounded record of the most recent event identifiers (in memory only)."""

    def __init__(self, size: int = RING_SIZE) -> None:
        self._events: deque[str] = deque(maxlen=size)
        self._lock = threading.Lock()
        self.started = time.monotonic()
        self._listener = None  # keeps a copy with the session record (survives a hard crash)

    def set_listener(self, listener) -> None:
        self._listener = listener

    def record(self, event: EventId | str) -> None:
        try:
            ev = EventId(event)
        except ValueError:
            return  # only predefined identifiers are ever recorded
        with self._lock:
            if self._events and self._events[-1] == ev.value and ev.value in _REPEATABLE:
                return  # one entry for a run of the same action (e.g. many style changes)
            self._events.append(ev.value)
            snapshot = list(self._events)
        listener = self._listener
        if listener is not None:
            try:
                listener(snapshot)
            except Exception:  # noqa: BLE001 — recording never disturbs the program
                pass

    def recent(self) -> list[str]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


diagnostics = Diagnostics()
