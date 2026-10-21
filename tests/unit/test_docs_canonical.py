"""Canonical documentation structure and link hygiene."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

CANONICAL = {
    "USER_GUIDE.md",
    "FEATURES.md",
    "FILE_FORMATS_AND_COMPATIBILITY.md",
    "ARCHITECTURE.md",
    "BUILD_AND_RUNTIME.md",
    "RELEASE_AND_VERSIONING.md",
    "SECURITY_AND_PRIVACY.md",
    "TESTING.md",
    "RELEASE_CHECKLIST.md",
    "CODE_SIGNING.md",
    # 0.3.0: secure updates, automatic upgrade, error reporting, international compatibility
    "SECURE_UPDATES.md",
    "AUTOMATIC_UPGRADE_AND_CLEANUP.md",
    "ERROR_REPORTING.md",
    "INTERNATIONAL_WINDOWS_COMPATIBILITY.md",
    # code-signing readiness
    "CODE_SIGNING_POLICY.md",
    "RELEASE_PROVENANCE.md",
    "OFFICIAL_DOWNLOAD_VERIFICATION.md",
    "PRIVACY_POLICY.md",
    # PDF <-> Office conversion, Save As and compression
    "PDF_TO_OFFICE_CONVERSION.md",
    "OFFICE_TO_PDF_CONVERSION.md",
    "CONVERSION_FIDELITY.md",
    "PDF_COMPRESSION.md",
    "SAVE_AS_AND_EXPORT.md",
    # rendering, colour, printing, save fidelity, performance
    "PDF_RENDERING_AND_PAGE_SIZES.md",
    "COLOR_AND_IMAGE_FIDELITY.md",
    "PRINTING_AND_PRINT_PREVIEW.md",
    "PDF_SAVE_AND_EXPORT_FIDELITY.md",
    "PERFORMANCE_AND_RENDERING.md",
    # Windows runtime, prerequisites and installation
    "WINDOWS_RUNTIME_DEPENDENCIES.md",
    "PREREQUISITE_MANAGEMENT.md",
    "INSTALLER_PACKAGE_CONTENTS.md",
    "CLEAN_WINDOWS_INSTALLATION.md",
}

STALE_FRAGMENTS = (
    "docs/user_guide/",
    "docs/changelogs/",
    "converting_documents.md",
    "protecting_and_signing.md",
    "security_antivirus.md",
    "docs/changelogs/CHANGELOG.md",
    "exact print layout",
    "Identical to *Save as PDF*",
    "passworded PDFs handled locally (qpdf/PyMuPDF later)",
    "explicit Office→PDF unsupported",
)


def test_docs_markdown_is_the_canonical_set():
    """Only the canonical documents, plus one release-notes file per version in docs/releases."""
    files = sorted(p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md"))
    notes = [f for f in files if f.startswith("releases/")]
    assert all(re.fullmatch(r"releases/v\d+\.\d+\.\d+\.md", f) for f in notes), notes
    assert set(files) - set(notes) == CANONICAL


def test_directory_structure_doc_removed():
    assert not (ROOT / "DIRECTORY_STRUCTURE.md").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "DIRECTORY_STRUCTURE.md" not in readme
    zipper = (ROOT / "scripts" / "packaging" / "create_release_zip.ps1").read_text(encoding="utf-8-sig")
    assert "DIRECTORY_STRUCTURE.md" not in zipper


def test_monograph_pdf_license_expression_is_agpl_or_later():
    from core.product_meta import PRODUCT_LICENSE

    assert PRODUCT_LICENSE == "AGPL-3.0-or-later"
    license_md = (ROOT / "LICENSE.md").read_text(encoding="utf-8")
    assert "Licensing rationale (AGPL-3.0-or-later)" in license_md
    assert "any later version" in license_md
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert 'license: "AGPL-3.0-or-later"' in citation
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    from core.versioning import get_version

    assert f"| Monograph PDF | {get_version()} | AGPL-3.0-or-later |" in notices


def test_child_user_guide_and_changelogs_removed():
    assert not (DOCS / "user_guide").exists()
    assert not (DOCS / "changelogs").exists()
    assert (ROOT / "CHANGELOG.md").is_file()


def test_no_stale_doc_paths_in_source_tree():
    roots = [
        ROOT / "README.md",
        ROOT / "INSTALLATION.md",
        ROOT / "SECURITY.md",
        ROOT / "LICENSE.md",
        ROOT / "CHANGELOG.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "CITATION.cff",
        DOCS,
        ROOT / "ui",
        ROOT / "core",
        ROOT / "scripts",
        ROOT / "installer" / "MonographPDF.iss",
        ROOT / "installer" / "_t_normal.iss",
    ]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".py", ".ps1", ".iss", ".txt", ".cff"}:
                continue
            # Skip vendored / generated trees
            if any(part in {"env", "_internal", "dist", "build", "release"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for frag in STALE_FRAGMENTS:
                if frag in text:
                    offenders.append(f"{path.relative_to(ROOT)} :: {frag}")
    assert not offenders, "Stale documentation references:\n" + "\n".join(offenders)


def test_testing_doc_office_wording():
    text = (DOCS / "TESTING.md").read_text(encoding="utf-8")
    assert "Office→PDF supported when Microsoft Office or LibreOffice" in text
    assert "explicit Office→PDF unsupported" not in text


def test_security_privacy_password_wording():
    text = (DOCS / "SECURITY_AND_PRIVACY.md").read_text(encoding="utf-8")
    assert "Encrypted PDFs are handled locally" in text or "encrypted PDFs are handled locally" in text.lower()
    assert "qpdf/PyMuPDF later" not in text
