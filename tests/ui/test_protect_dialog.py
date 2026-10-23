"""Protect with Password: AES-256 by default, document information encrypted (or removed), and a
watermark added by Monograph PDF can be locked into the pages."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def app():
    from ui.main_window import create_application

    return create_application(["monograph-pdf-protect"])


def _watermarked(tmp_path):
    from core.convert.page_marks import WatermarkSpec, apply_page_marks
    from core.document import open_document

    src = tmp_path / "src.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 100), "Body text", fontsize=12)
    d.set_metadata({"title": "Secret plan", "author": "Aung"})
    d.save(src)
    d.close()
    doc = open_document(src)
    try:
        marked = tmp_path / "marked.pdf"
        apply_page_marks(doc, marked, watermark=WatermarkSpec(text="CONFIDENTIAL"))
    finally:
        doc.close()
    return marked


def test_defaults_and_metadata_hint(app, qtbot):
    from ui.security_dialogs import PasswordProtectDialog

    dlg = PasswordProtectDialog(None, watermark_pages=0)
    qtbot.addWidget(dlg)
    assert dlg.algo.currentData() == "AES-256"
    assert not dlg.lock_wm.isEnabled()
    assert "anyone" in dlg.meta_status.text().lower()
    dlg.user_pw.setText("open-1")
    assert "encrypted" in dlg.meta_status.text().lower()
    assert dlg.sizeHint().height() < 760, "fits a 768-pixel-high screen"


def test_watermark_locked_and_metadata_removed(app, qtbot, tmp_path):
    from core.convert.page_marks import KIND_WATERMARK, count_marks
    from core.document import open_document
    from core.security import apply_password_protection
    from ui.security_dialogs import PasswordProtectDialog

    marked = _watermarked(tmp_path)
    doc = open_document(marked)
    try:
        pages = count_marks(doc).get(KIND_WATERMARK, 0)
        assert pages == 1
        dlg = PasswordProtectDialog(None, watermark_pages=pages)
        qtbot.addWidget(dlg)
        assert dlg.lock_wm.isChecked() and not dlg.perm_modify.isChecked()
        dlg.owner_pw.setText("owner-pw-123")
        dlg.strip_meta.setChecked(True)
        out = tmp_path / "protected.pdf"
        apply_password_protection(doc, out, dlg.settings())
    finally:
        doc.close()
    with fitz.open(out) as res:
        assert res.is_encrypted or res.needs_pass or res.metadata.get("encryption")
        res.authenticate("owner-pw-123")
        assert not (res.metadata or {}).get("title"), "document information removed"
        assert "CONFIDENTIAL" in res[0].get_text(), "the watermark is still on the page"
        assert count_marks(res).get(KIND_WATERMARK, 0) == 0, "no longer an identifiable, removable mark"
        assert not res.get_ocgs(), "no layer left that would hide it"
