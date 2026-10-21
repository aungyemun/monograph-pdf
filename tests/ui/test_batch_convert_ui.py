"""Batch Convert dialog: add files (as a drop would), convert on a worker thread, per-file status."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("pytestqt")


def _pdf(path: Path) -> Path:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), f"Hello from {path.stem}")
    doc.save(path)
    doc.close()
    return path


def test_batch_dialog_converts_and_reports_each_file(qtbot, tmp_path):
    from ui.batch_dialog import BatchConvertDialog
    from ui.main_window import create_application

    create_application(["monograph-pdf-batch"])
    dlg = BatchConvertDialog()
    qtbot.addWidget(dlg)
    a, b = _pdf(tmp_path / "a.pdf"), _pdf(tmp_path / "b.pdf")
    note = tmp_path / "notes.txt"
    note.write_text("not convertible")
    dlg.add_paths([a, b, note, a])  # duplicates and unsupported types are not added
    assert dlg.table.rowCount() == 2
    assert dlg.output.text() == str(tmp_path / "Converted")
    dlg.format.setCurrentIndex(dlg.format.findData("txt"))
    assert dlg.start_btn.isEnabled() and not dlg.cancel_btn.isEnabled()
    dlg.start()
    # the worker thread can end before its queued status signals reach the dialog: wait for both
    qtbot.waitUntil(lambda: not dlg._running() and dlg.close_btn.isEnabled()  # noqa: SLF001
                    and all(dlg.table.item(r, 1).text() not in ("Waiting", "Converting…") for r in range(2)),
                    timeout=30000)
    assert [dlg.table.item(r, 1).text() for r in range(2)] == ["Done", "Done"]
    assert "2 done, 0 failed" in dlg.counts.text()
    assert sorted(p.name for p in (tmp_path / "Converted").iterdir()) == ["a.txt", "b.txt"]
    assert dlg.close_btn.isEnabled()


def test_folder_drop_and_format_notes(qtbot, tmp_path):
    from ui.batch_dialog import BatchConvertDialog
    from ui.main_window import create_application

    create_application(["monograph-pdf-batch"])
    dlg = BatchConvertDialog()
    qtbot.addWidget(dlg)
    folder = tmp_path / "in"
    folder.mkdir()
    _pdf(folder / "x.pdf")
    (folder / "pic.png").write_bytes(b"\x89PNG\r\n")
    dlg.add_paths([folder])
    assert dlg.table.rowCount() == 2
    dlg.format.setCurrentIndex(dlg.format.findData("docx"))
    assert "1 file(s) cannot be converted" in dlg.note.text()
    dlg.format.setCurrentIndex(dlg.format.findData("png"))
    assert dlg.dpi.isEnabled() and dlg.pages.isEnabled()
    dlg.format.setCurrentIndex(dlg.format.findData("image_pdf"))
    assert not dlg.pages.isEnabled()
