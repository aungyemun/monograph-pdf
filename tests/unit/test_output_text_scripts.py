"""Outputs keep every script: Japanese in text boxes, headers, footers, page numbers and
watermarks; text boxes keep their font look; working files are cleaned up."""

from __future__ import annotations

import os
import time
from pathlib import Path

import fitz

from core.document import open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.text_box import TextAlign
from engines.bake_edits import bake_via_backend


def _blank(path: Path, pages: int = 1) -> Path:
    d = fitz.open()
    for _ in range(pages):
        d.new_page()
    d.save(path)
    d.close()
    return path


def test_text_box_saves_japanese_bold_underline_and_alignment(tmp_path):
    pdf = open_document(_blank(tmp_path / "in.pdf"))
    edit = EditableDocument(pdf)
    box = edit.create_text_box(0, Rect(60, 80, 260, 60), text="Bold 東京 ＡＢ１２\nsecond line", auto_match=False)
    style = box.style.copy()
    style.bold, style.underline, style.font_size = True, True, 14
    edit.change_style(box.object_id, style=style, align=TextAlign.CENTER)
    times = edit.create_text_box(0, Rect(60, 200, 220, 40), text="Italic Times", auto_match=False)
    style = times.style.copy()
    style.italic, style.font_family = True, "Times New Roman"
    edit.change_style(times.object_id, style=style)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        page = d[0]
        text = page.get_text()
        assert "Bold 東京 ＡＢ１２" in text and "second line" in text  # never "?" for Japanese
        assert "Italic Times" in text
        fonts = {f[3] for f in page.get_fonts(full=True)}
        # Times New Roman Italic is now embedded when installed (core/editing/system_fonts.py); the built-in face remains the fallback
        assert any("Times-Italic" in f or "TimesItalic" in f or "TimesNewRoman" in f.replace(" ", "") for f in fonts), fonts
        assert page.get_drawings(), "underline missing"
        line = next(b for b in page.get_text("dict")["blocks"] if "Bold" in str(b))
        cx = (line["bbox"][0] + line["bbox"][2]) / 2
        assert abs(cx - (60 + 4 + (260 - 8) / 2)) < 6  # centred in the box
        assert out.stat().st_size < 300_000  # only the used Japanese glyphs are embedded


def test_new_text_box_has_no_frame_or_fill(tmp_path):
    pdf = open_document(_blank(tmp_path / "in.pdf"))
    edit = EditableDocument(pdf)
    edit.create_text_box(0, Rect(60, 80, 200, 40), text="Plain", auto_match=False)
    out = tmp_path / "out.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(out) as d:
        assert not [p for p in d[0].get_drawings() if p.get("fill") or p.get("color")], "unexpected frame / fill"


def test_header_footer_page_numbers_and_watermark_keep_japanese(tmp_path):
    from core.convert import apply_headers_footers, apply_page_numbers, apply_watermark

    doc = open_document(_blank(tmp_path / "in.pdf", pages=2))
    out = apply_headers_footers(doc, tmp_path / "hf.pdf", header="見出し Header", footer="フッター Footer")
    with fitz.open(out) as d:
        t = d[0].get_text()
        assert "見出し Header" in t and "フッター Footer" in t
    out = apply_page_numbers(doc, tmp_path / "pn.pdf", fmt="{page} / {total} ページ")
    with fitz.open(out) as d:
        assert "2 / 2 ページ" in d[1].get_text()
    out = apply_watermark(doc, tmp_path / "wm.pdf", text="社外秘 CONFIDENTIAL")
    with fitz.open(out) as d:
        assert "社外秘 CONFIDENTIAL" in d[0].get_text()


def test_startup_cleanup_removes_abandoned_working_files(tmp_path, monkeypatch):
    import core.organize.temputil as tu

    temp, sessions = tmp_path / "temp", tmp_path / "sessions"
    (temp / "converted" / "abc").mkdir(parents=True)
    (temp / "organize").mkdir(parents=True)
    old_conv = temp / "converted" / "abc"
    (old_conv / "photo.pdf").write_bytes(b"%PDF")
    stray = temp / "print-bake-1.pdf"
    stray.write_bytes(b"%PDF")
    fresh = temp / "print-bake-2.pdf"
    fresh.write_bytes(b"%PDF")
    sessions.mkdir()
    old_session, new_session = sessions / "old.json", sessions / "new.json"
    old_session.write_text("{}")
    new_session.write_text("{}")
    long_ago = time.time() - 40 * 24 * 3600
    for p in (old_conv, stray, old_session):
        os.utime(p, (long_ago, long_ago))
    monkeypatch.setattr(tu, "TEMP_DIR", temp)
    monkeypatch.setattr(tu, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(tu, "ORGANIZE_TEMP_DIR", temp / "organize")
    monkeypatch.setattr(tu, "ORGANIZE_CACHE_DIR", tmp_path / "cache" / "organize")
    tu.cleanup_abandoned_temps()
    assert not old_conv.exists() and not stray.exists() and not old_session.exists()
    assert fresh.exists() and new_session.exists() and (temp / "organize").is_dir()


def test_crop_dialog_uses_margins_in_mm(qtbot=None):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from ui.organize_dialogs import CropDialog

    dlg = CropDialog(595.0, 842.0)
    dlg.left.setValue(10)
    dlg.top.setValue(20)
    x0, y0, x1, y1 = dlg.crop_tuple()
    mm = 72 / 25.4
    assert abs(x0 - 10 * mm) < 0.01 and abs(y0 - 20 * mm) < 0.01 and x1 == 595.0 and y1 == 842.0
    dlg.left.setValue(dlg.left.maximum())
    dlg.right.setValue(dlg.right.maximum())
    assert not dlg._ok.isEnabled()  # noqa: SLF001 — nothing left of the page


def test_watermark_opacity_applies_to_latin_and_japanese(tmp_path):
    from core.convert import apply_watermark

    doc = open_document(_blank(tmp_path / "in.pdf"))
    shades = []
    for i, text in enumerate(("CONFIDENTIAL", "社外秘 CONFIDENTIAL")):
        out = apply_watermark(doc, tmp_path / f"wm{i}.pdf", text=text, opacity=0.25)
        with fitz.open(out) as d:
            shades.append(min(d[0].get_pixmap(dpi=40).samples))
    assert all(s > 200 for s in shades), shades  # light grey, not the full 55 % grey


def test_move_into_place_across_drives(tmp_path, monkeypatch):
    """Merge / Split work in runtime\\temp (C:) and save to another drive (D:): a plain rename
    fails there (Windows error 17), so the result is copied into place instead."""
    import os

    import core.organize.temputil as tu

    src = tmp_path / "work" / "out.pdf"
    src.parent.mkdir()
    src.write_bytes(b"%PDF-1.7 result")
    dest = tmp_path / "other" / "final.pdf"
    real_replace = os.replace

    def cross_drive(a, b):
        if Path(a) == src:
            raise OSError(17, "The system cannot move the file to a different disk drive")
        return real_replace(a, b)

    monkeypatch.setattr(os, "replace", cross_drive)
    tu.move_into_place(src, dest)
    assert dest.read_bytes() == b"%PDF-1.7 result" and not src.exists()
    assert not list(dest.parent.glob("*.part"))
