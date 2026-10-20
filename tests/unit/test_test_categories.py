"""The test-category rules in tests/conftest.py (used by CI to report PASS / FAIL / NOT VERIFIED)."""

from __future__ import annotations

import os

from tests.conftest import categories_for, category_summary


def _p(*parts: str) -> str:
    return os.sep.join(("repo", "tests") + parts)


def test_modules_and_names_get_their_categories():
    assert categories_for(_p("ui", "test_ui_polish.py"), "test_x") == {"gui"}
    assert categories_for(_p("integration", "test_round6_real_pdfs.py"), "test_x") == {"private_fixture"}
    assert categories_for(_p("integration", "test_office_to_pdf.py"), "test_x") == {"external_app", "windows"}
    assert "private_fixture" in categories_for(_p("integration", "test_templates.py"),
                                               "test_downloads_pdfs_open_and_originals_untouched")
    assert categories_for(_p("unit", "test_password_strength.py"), "test_x") == {"security", "portable"}
    assert categories_for(_p("unit", "test_paths.py"), "test_x") == {"portable"}
    assert "ocr" in categories_for(_p("unit", "test_convert.py"), "test_ocr_round_trip")


def test_summary_marks_all_skipped_categories_not_verified():
    cats = {"a": {"portable"}, "b": {"portable"}, "c": {"private_fixture"}, "d": {"gui"}}
    outcomes = {"a": "passed", "b": "skipped", "c": "skipped", "d": "failed"}
    rows = {r[0]: r for r in category_summary(cats, outcomes)}
    assert rows["portable"] == ("portable", 1, 0, 1, "PASS")
    assert rows["private_fixture"] == ("private_fixture", 0, 0, 1, "NOT VERIFIED")
    assert rows["gui"] == ("gui", 0, 1, 0, "FAIL")
