"""Compress PDF ▸ Custom: the picture resolution and JPEG quality you choose (within the safety floors)."""

from __future__ import annotations

import io

import fitz
import pytest


def _photo_pdf(tmp_path):
    from PIL import Image

    img = Image.new("RGB", (2400, 1600))
    px = img.load()
    for y in range(0, 1600, 2):
        for x in range(0, 2400, 2):
            px[x, y] = ((x * 7) % 255, (y * 3) % 255, (x + y) % 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(50, 50, 545, 380), stream=buf.getvalue())  # ~350 ppi as shown
    page.insert_text((60, 420), "Text stays text", fontsize=14)
    path = tmp_path / "photo.pdf"
    doc.save(path)
    doc.close()
    return path.read_bytes()


def test_lower_resolution_and_quality_give_a_smaller_file(tmp_path):
    from core.convert import compress as cz

    data = _photo_pdf(tmp_path)
    high = cz.compress(data, mode="custom", ppi=300, quality=90)
    low = cz.compress(data, mode="custom", ppi=120, quality=60)
    assert low.output_bytes < high.output_bytes < len(data)
    assert low.lossy and low.status().startswith("Custom:")
    with fitz.open("pdf", low.data) as d:
        assert "Text stays text" in d[0].get_text()  # text is never turned into a picture


def test_custom_settings_are_kept_within_the_safe_range(tmp_path):
    from core.convert import compress as cz

    data = _photo_pdf(tmp_path)
    res = cz.compress(data, mode="custom", ppi=10, quality=5)  # below the floors
    assert any(label.startswith("100 ppi / JPEG 40") for label, _size in res.tried)


def test_dialog_offers_custom_resolution_and_quality(qtbot, tmp_path):
    pytest.importorskip("pytestqt")
    from ui.compress_dialog import CompressDialog

    dlg = CompressDialog(_photo_pdf(tmp_path), doc_name="photo.pdf")
    qtbot.addWidget(dlg)
    assert not dlg.ppi_spin.isEnabled()
    dlg.mode_buttons["custom"].setChecked(True)
    assert dlg.ppi_spin.isEnabled() and dlg.quality_spin.isEnabled()
    dlg.ppi_spin.setValue(150)
    dlg.quality_spin.setValue(70)
    assert "150 ppi" in dlg.mode_note.text() and "quality 70" in dlg.mode_note.text()
    assert dlg._key() == ("custom", 150, 70)  # noqa: SLF001
    dlg._start(accept_after=False)  # noqa: SLF001  (runs synchronously offscreen)
    assert dlg.result_ is not None and dlg.result_.mode == "custom"
