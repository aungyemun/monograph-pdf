"""Basic import smoke tests for scaffolding packages."""

from __future__ import annotations


def test_import_app_and_version():
    import app

    assert app.__version__
    assert len(app.__version__.split(".")) == 3


def test_import_core_engines_ui():
    import core
    import core.versioning
    import core.dependency_audit
    import engines
    import engines.probe
    import ui
    import ui.main_window

    assert core.dependency_audit.list_accepted()
    assert callable(engines.probe.probe_all)
