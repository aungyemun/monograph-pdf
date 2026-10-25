"""Platform adapters for Monograph PDF (Option B unified tree).

Shared PDF/GUI code lives under ``app/``, ``core/`` and ``ui/``. Operating-system
specific helpers are selected at runtime (``sys.platform``) or live beside this
package for packaging scripts. Prefer adapters here over scattering ``if win``
checks through shared modules.
"""

from __future__ import annotations

import sys


def name() -> str:
    """Canonical platform id: ``windows``, ``macos`` or ``linux``."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
