"""Engine probes must run offline and never raise."""

from __future__ import annotations

from engines.probe import probe_all


def test_probe_all_returns_statuses():
    statuses = probe_all()
    names = {s.name for s in statuses}
    assert {"PySide6", "PyMuPDF", "qpdf", "Tesseract"} <= names
    for status in statuses:
        assert isinstance(status.available, bool)
        assert status.detail
