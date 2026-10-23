"""Test-wide isolation: never read or write the real user's settings or recent files."""

from __future__ import annotations

import os
import tempfile

import pytest

# Working files (recovery drafts, temp conversions, caches) go to a throwaway folder, never the
# project's own runtime folder. Set before any test imports app.paths.
os.environ.setdefault("MONOGRAPH_PDF_RUNTIME_DIR", tempfile.mkdtemp(prefix="monographpdf-test-runtime-"))
# Update staging/status and problem-report records likewise never touch the user's real folders
os.environ.setdefault("MONOGRAPH_PDF_UPDATES_DIR", tempfile.mkdtemp(prefix="monographpdf-test-updates-"))
os.environ.setdefault("MONOGRAPH_PDF_DIAGNOSTICS_DIR", tempfile.mkdtemp(prefix="monographpdf-test-diagnostics-"))


@pytest.fixture(autouse=True, scope="session")
def _isolated_user_data(tmp_path_factory):
    old = os.environ.get("MONOGRAPH_PDF_USER_DATA_DIR")
    os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(tmp_path_factory.mktemp("userdata"))
    yield
    if old is None:
        os.environ.pop("MONOGRAPH_PDF_USER_DATA_DIR", None)
    else:
        os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = old


# ---------------------------------------------------------------------------------------------
# Test categories. Every test gets one or more markers from the rules below (one place to read and
# maintain), and the run ends with a per-category summary: PASS, FAIL or NOT VERIFIED (every test
# of the category was skipped, e.g. private PDFs or Microsoft Office are not on this machine).
# Select with -m, e.g.  -m "not private_fixture"  or  -m gui.
# ---------------------------------------------------------------------------------------------

CATEGORY_HELP = {
    "portable": "pure Python / PDF logic; runs anywhere with the pinned requirements",
    "windows": "needs Windows behaviour (installed fonts, file locking, registry, Windows paths)",
    "gui": "builds Qt widgets or the main window (offscreen platform)",
    "external_app": "needs Microsoft Office or LibreOffice installed",
    "ocr": "needs the vendored OCR engine and language data (engines/ocr, models/tessdata)",
    "private_fixture": "needs the maintainer's own PDFs (never in the repository or CI)",
    "security": "security, privacy and release-integrity regression tests",
    "golden": "golden documents and template PDFs compared with their manifests",
}

_MODULE_CATEGORIES = {
    # GUI outside tests/ui
    "test_document_lifecycle.py": {"gui"}, "test_editing_ui.py": {"gui"}, "test_startup.py": {"gui"},
    "test_output_text_scripts.py": {"gui"}, "test_real_pdf_quality.py": {"gui"},
    "test_shapes_and_inspector.py": {"gui"},
    # Windows-specific
    "test_font_embedding.py": {"windows"}, "test_save_retry.py": {"windows", "gui"},
    "test_monograph_migration.py": {"windows"}, "test_installer_and_docs.py": {"windows"},
    "test_installed_manifest.py": {"windows"},
    # External applications
    "test_office_to_pdf.py": {"external_app", "windows"},
    "test_office_round_trip.py": {"external_app"},
    # OCR
    "test_ocr_corpus.py": {"ocr"}, "test_ocr.py": {"ocr"},
    # Private fixtures (these files are not in the repository)
    "test_user_real_pdfs.py": {"private_fixture"}, "test_live_real_pdf_qa.py": {"private_fixture"},
    "test_round6_real_pdfs.py": {"private_fixture"},
    # Golden / template documents
    "test_golden_documents.py": {"golden"}, "test_templates.py": {"golden"},
    # Security, privacy and release integrity
    "test_security_hardening.py": {"security"}, "test_security_tools.py": {"security"},
    "test_security_validation_0_2_0.py": {"security"}, "test_security_ui.py": {"security", "gui"},
    "test_redaction_residue.py": {"security"}, "test_redaction_ui.py": {"security", "gui"},
    "test_remove_hidden_info.py": {"security"}, "test_password_strength.py": {"security"},
    "test_images_to_pdf_privacy.py": {"security"}, "test_source_archive.py": {"security"},
    "test_verify_release.py": {"security"}, "test_release_notes_validation.py": {"security"},
    "test_encryption_bytes.py": {"security"},
    "test_stage_ocr_engine.py": {"security"},
    # Secure updates and private error reporting (0.3.0)
    "test_update_crypto.py": {"security"}, "test_update_manifest.py": {"security"},
    "test_update_net.py": {"security"}, "test_update_staging.py": {"security"},
    "test_update_install.py": {"security"}, "test_diagnostics.py": {"security"},
    "test_report_gateway.py": {"security"}, "test_update_ui.py": {"security", "gui"},
    "test_code_signing_readiness.py": {"security"}, "test_windows_runtime_packaging.py": {"security"},
    "test_update_signing_key.py": {"security"}, "test_update_manifest_release_check.py": {"security"},
    "test_update_signing_key_pkcs8.py": {"security"}, "test_update_signing_bundle.py": {"security"},
    "test_update_direct_upgrade.py": {"security"}, "test_update_manifest_validity.py": {"security"},
    "test_no_console_windows.py": {"security"},
}
# Individual tests inside otherwise portable modules (matched against the test name)
_NAME_CATEGORIES = [
    ("downloads_pdfs", {"private_fixture"}),
    ("office", {"external_app"}),
    ("ocr", {"ocr"}),
]
_HEAVY = {"gui", "windows", "external_app", "ocr", "private_fixture"}


def categories_for(path: str, name: str) -> set[str]:
    module = os.path.basename(path)
    cats = set(_MODULE_CATEGORIES.get(module, set()))
    if f"{os.sep}ui{os.sep}" in path or "/ui/" in path.replace(os.sep, "/"):
        cats.add("gui")
    lname = name.lower()
    for key, extra in _NAME_CATEGORIES:
        if key in lname:
            cats |= extra
    if not cats & _HEAVY:
        cats.add("portable")
    return cats


def pytest_configure(config):
    for name, text in CATEGORY_HELP.items():
        config.addinivalue_line("markers", f"{name}: {text}")
    config._monograph_categories = {}  # noqa: SLF001
    config._monograph_outcomes = {}  # noqa: SLF001


def pytest_collection_modifyitems(config, items):
    for item in items:
        cats = categories_for(str(item.path), item.name)
        for cat in sorted(cats):
            item.add_marker(getattr(pytest.mark, cat))
        config._monograph_categories[item.nodeid] = cats  # noqa: SLF001


def pytest_runtest_logreport(report):
    cfg = getattr(pytest_runtest_logreport, "_config", None)
    if cfg is None:
        return
    outcomes = cfg._monograph_outcomes  # noqa: SLF001
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed") or (
            report.when == "teardown" and report.outcome == "failed"):
        prev = outcomes.get(report.nodeid)
        if prev != "failed":
            outcomes[report.nodeid] = report.outcome


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    pytest_runtest_logreport._config = session.config  # type: ignore[attr-defined]
    # The small generated sample PDFs (tests/samples, not in git) must exist before collection:
    # some modules read them at import time. A fresh checkout (CI) has none of them.
    from pathlib import Path

    if not (Path(__file__).resolve().parent / "samples" / "sample_text.pdf").is_file():
        from tests.fixtures.make_samples import main as make_samples

        make_samples()


def category_summary(categories: dict, outcomes: dict) -> list[tuple[str, int, int, int, str]]:
    rows = []
    for cat in CATEGORY_HELP:
        ids = [n for n, cats in categories.items() if cat in cats]
        if not ids:
            continue
        passed = sum(outcomes.get(n) == "passed" for n in ids)
        failed = sum(outcomes.get(n) == "failed" for n in ids)
        skipped = sum(outcomes.get(n) == "skipped" for n in ids)
        status = "FAIL" if failed else ("PASS" if passed else "NOT VERIFIED")
        rows.append((cat, passed, failed, skipped, status))
    return rows


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    rows = category_summary(config._monograph_categories, config._monograph_outcomes)  # noqa: SLF001
    if not rows:
        return
    tr = terminalreporter
    tr.write_sep("-", "test categories")
    for cat, passed, failed, skipped, status in rows:
        tr.write_line(f"{cat:16s} {status:13s} passed {passed:5d}  failed {failed:3d}  skipped {skipped:4d}")
    out = os.environ.get("MONOGRAPH_TEST_CATEGORY_REPORT")
    if out:
        lines = ["| Category | Status | Passed | Failed | Skipped |", "| :--- | :--- | ---: | ---: | ---: |"]
        lines += [f"| {c} | {s} | {p} | {f} | {k} |" for c, p, f, k, s in rows]
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
