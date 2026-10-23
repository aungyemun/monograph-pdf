"""Document Properties lists the PDF's permissions in plain words: what is allowed and what is not."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


def _rows(dlg) -> dict[str, str]:
    from PySide6.QtWidgets import QFormLayout, QLabel

    rows = {}
    for form in dlg.findChildren(QFormLayout):
        for r in range(form.rowCount()):
            label = form.itemAt(r, QFormLayout.ItemRole.LabelRole)
            field = form.itemAt(r, QFormLayout.ItemRole.FieldRole)
            if label is not None and field is not None and isinstance(field.widget(), QLabel):
                rows[label.widget().text()] = field.widget().text()
    return rows


def test_permissions_are_listed_in_plain_words(qtbot, tmp_path):
    from core.document import open_document
    from ui.app_dialogs import DocumentPropertiesDialog
    from ui.main_window import create_application

    create_application(["monograph-pdf-properties"])
    src = tmp_path / "restricted.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Restricted", fontsize=12)
    doc.save(src, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="",
             permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY)
    doc.close()
    document = open_document(src)
    try:
        dlg = DocumentPropertiesDialog(document)
        qtbot.addWidget(dlg)
        rows = _rows(dlg)
        assert "Printing" in rows.get("Allowed:", ""), rows
        denied = rows.get("Not allowed:", "")
        assert "Copying text and images" in denied, rows
        assert "_" not in rows.get("Allowed:", "") + denied, "raw permission keys must not be shown"
    finally:
        document.close()
