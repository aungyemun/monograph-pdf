"""Integration: application factory and main window construct offline."""

from __future__ import annotations

import os

import pytest

# Prefer offscreen for CI/headless; harmless on normal Windows sessions if overridden.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_create_application_and_main_window():
    pytest.importorskip("PySide6")
    from app import __version__
    from ui.main_window import MainWindow, create_application

    app = create_application(["monograph-pdf-test"])
    window = MainWindow()
    assert window.windowTitle() == "Monograph PDF"
    assert window.isWindow()
    # Version remains in About / VERSION — not the title bar
    from core.versioning import get_version

    assert get_version() == __version__
    window.close()
    assert app is not None
