"""Private, consent-based error reporting.

* Only predefined event identifiers are recorded, in memory, in a small ring buffer.
* A report is built from approved fields only (no document content, names, paths, metadata, user
  names, typed text, clipboard, environment, memory) and validated against an allow-list schema.
* Nothing is sent unless the user clicks **Send to Developer**; only :mod:`core.diagnostics.client`
  contacts the network, and only the configured reporting gateway.
"""

from core.diagnostics.events import Diagnostics, EventId, diagnostics  # noqa: F401
