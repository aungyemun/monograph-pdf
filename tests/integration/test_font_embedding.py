"""Fonts picked for text boxes are embedded in the saved PDF (when installed and licensed for it), keep the
text searchable with real spaces, are subset, and are reported when they cannot be embedded.

Compared: A editor appearance (Qt text of the same family and size), B saved PDF, C the saved PDF opened and
saved again. Font resources are read with PyMuPDF from the written file, not from the app's own state."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from core.document import open_document  # noqa: E402
from core.editing import system_fonts  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from core.editing.text_box import TextBox  # noqa: E402
from engines.bake_edits import bake_into_document  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("win"), reason="system fonts are located through the Windows registry")

LATIN = "Hello World 123 (ABC) α β ± × ÷ – “quoted”"
MIXED = "Order 2026-17 注文番号 Hello"
EMBEDDABLE = ["Arial", "Times New Roman", "Calibri", "Courier New", "Segoe UI"]


@pytest.fixture(scope="module", autouse=True)
def _qt():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _blank(tmp: Path) -> Path:
    d = fitz.open()
    d.new_page(width=420, height=200)
    p = tmp / "blank.pdf"
    d.save(p.as_posix())
    d.close()
    return p


def _bake(tmp: Path, family: str, text: str, *, bold=False, italic=False, size=14.0, name="out") -> Path:
    system_fonts.take_notes()
    pdf = open_document(_blank(tmp))
    try:
        edit = EditableDocument(pdf)
        box = TextBox(page_index=0, rect=Rect(20, 30, 380, 60), text=text)
        box.style.font_family, box.style.font_size = family, size
        box.style.bold, box.style.italic = bold, italic
        edit.add_object(box)
        out = tmp / f"{name}.pdf"
        bake_into_document(edit, out)
        return out
    finally:
        pdf.close()


def _fonts(path: Path):
    d = fitz.open(path.as_posix())
    try:
        return [(f[3], f[1]) for f in d[0].get_fonts(full=True)], d[0].get_text().replace("\n", " ").strip()
    finally:
        d.close()


def _ink_width(pix: fitz.Pixmap) -> float:
    xs = [x for y in range(pix.height) for x in range(pix.width) if sum(pix.pixel(x, y)[:3]) < 300]
    return float(max(xs) - min(xs)) if xs else 0.0


@pytest.mark.parametrize("family", EMBEDDABLE)
def test_picked_font_is_embedded_subset_with_real_spaces(tmp_path: Path, family: str):
    if system_fonts.find_font_file(family) is None:
        pytest.skip(f"{family} is not installed")
    out = _bake(tmp_path, family, LATIN)
    fonts, text = _fonts(out)
    names = " ".join(n for n, _ in fonts)
    assert family.replace(" ", "").lower() in names.replace(" ", "").lower(), fonts  # the real font resource is there
    assert all(ext != "n/a" for _, ext in fonts), f"font not embedded: {fonts}"
    assert system_fonts.take_notes() == {}
    assert text == LATIN  # exact text, ordinary spaces (no U+00A0)
    d = fitz.open(out.as_posix())
    assert d[0].search_for("Hello World 123")
    big = system_fonts.find_font_file(family).stat().st_size
    for f in d[0].get_fonts(full=True):  # subset: far smaller than the installed font file
        assert len(d.extract_font(f[0])[3]) < big * 0.5
    d.close()


@pytest.mark.parametrize("family", EMBEDDABLE)
def test_editor_saved_and_resaved_appearance_agree(tmp_path: Path, family: str):
    """A: Qt's rendering of the family at the size; B: the saved PDF; C: saved again after reopening."""
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    if system_fonts.find_font_file(family) is None:
        pytest.skip(f"{family} is not installed")
    size, zoom, text = 14.0, 3.0, "Hamburgefonstiv 0123456789"
    out = _bake(tmp_path, family, text, size=size)
    d = fitz.open(out.as_posix())
    saved_w = _ink_width(d[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False))
    d.close()
    img = QImage(int(420 * zoom), int(200 * zoom), QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    f = QFont(family)
    f.setPixelSize(int(size * zoom))
    p.setFont(f)
    p.setPen(QColor("black"))
    p.drawText(int(24 * zoom), int(30 * zoom + size * zoom), text)
    p.end()
    xs = [x for y in range(img.height()) for x in range(img.width()) if QColor(img.pixel(x, y)).value() < 100]
    editor_w = float(max(xs) - min(xs))
    assert saved_w == pytest.approx(editor_w, rel=0.06), (family, editor_w, saved_w)
    pdf = open_document(out)  # C: reopen, save again without edits: the same font resources remain
    try:
        again = tmp_path / "again.pdf"
        bake_into_document(EditableDocument(pdf), again)
    finally:
        pdf.close()
    assert [n for n, _ in _fonts(again)[0]] == [n for n, _ in _fonts(out)[0]]


@pytest.mark.parametrize("bold,italic", [(True, False), (False, True), (True, True)])
def test_bold_italic_use_the_matching_installed_file(tmp_path: Path, bold: bool, italic: bool):
    if system_fonts.find_font_file("Arial", bold, italic) is None:
        pytest.skip("Arial variant not installed")
    out = _bake(tmp_path, "Arial", "Styled text", bold=bold, italic=italic)
    names = " ".join(n for n, _ in _fonts(out)[0])
    assert ("Bold" in names) == bold and ("Italic" in names) == italic, names


def test_japanese_and_mixed_text_keep_content_and_font(tmp_path: Path):
    if system_fonts.find_font_file("Yu Mincho") is None:
        pytest.skip("Yu Mincho not installed")
    for family in ("Yu Mincho", "Arial"):
        out = _bake(tmp_path, family, MIXED, name=f"jp_{family.replace(' ', '')}")
        fonts, text = _fonts(out)
        assert text == MIXED, (family, text)
        assert family.replace(" ", "").lower() in " ".join(n for n, _ in fonts).replace(" ", "").lower()
        assert all(ext != "n/a" for _, ext in fonts)


def test_font_from_a_collection_is_embedded_without_a_warning(tmp_path: Path):
    """MS Mincho is installed as msmincho.ttc. 0.4.0 and earlier replaced it with a built-in font and
    said "font collections (.ttc) are not embedded"; its face is now embedded (subset)."""
    if system_fonts.find_font_file("MS Mincho") is None:
        pytest.skip("MS Mincho not installed")
    system_fonts.take_notes()
    out = _bake(tmp_path, "MS Mincho", "日本語 text")
    notes = system_fonts.take_notes()
    assert "MS Mincho" not in notes, notes
    fonts, text = _fonts(out)
    assert text == "日本語 text"
    assert any("msmincho" in n.replace(" ", "").replace("-", "").lower() for n, _ in fonts), fonts
    assert all(ext != "n/a" for _, ext in fonts)


@pytest.mark.parametrize("family", ["MS Mincho", "MS Gothic"])
def test_japanese_text_box_keeps_full_width_spacing_when_saved(tmp_path: Path, family):
    """0.4.1 RC1: saved MS Mincho / MS Gothic text was spaced at half width (characters overlapped)."""
    if system_fonts.find_font_file(family) is None:
        pytest.skip(f"{family} not installed")
    out = _bake(tmp_path, family, "東浦町大府市", size=10.0, name=family.replace(" ", ""))
    d = fitz.open(out.as_posix())
    try:
        xs = [c[2][0] for span in d[0].get_texttrace() for c in span["chars"]]
    finally:
        d.close()
    assert len(xs) == 6
    steps = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    assert all(abs(st - 10.0) < 0.05 for st in steps), steps


def test_missing_font_is_reported_not_silent(tmp_path: Path):
    out = _bake(tmp_path, "Totally Missing Font", "Plain text")
    notes = system_fonts.take_notes()
    assert "Totally Missing Font" in notes and "not installed" in notes["Totally Missing Font"]
    assert _fonts(out)[1] == "Plain text"


def test_license_restricted_font_is_never_embedded(tmp_path: Path, monkeypatch):
    from fontTools.ttLib import TTFont

    src = system_fonts.find_font_file("Arial")
    if src is None:
        pytest.skip("Arial not installed")
    for fs in (2, 0x100, 4):
        font = TTFont(src.as_posix())
        font["OS/2"].fsType = fs
        copy = tmp_path / f"restricted_{fs}.ttf"
        font.save(copy.as_posix())
        system_fonts.embedding_verdict.cache_clear()
        monkeypatch.setattr(system_fonts, "find_font_file", lambda family, bold=False, italic=False, p=copy: p)
        out = _bake(tmp_path, "Restricted Test", "Plain text", name=f"r{fs}")
        notes = system_fonts.take_notes()
        assert "Restricted Test" in notes, (fs, notes)
        assert not any("Restricted" in n or "Arial" in n for n, _ in _fonts(out)[0])
    system_fonts.embedding_verdict.cache_clear()


def test_generic_names_need_no_warning(tmp_path: Path):
    _bake(tmp_path, "sans-serif", "Plain text")
    assert system_fonts.take_notes() == {}


def test_form_field_entry_is_drawn_with_the_embedded_font_and_value_is_unchanged(tmp_path: Path):
    gold = Path(__file__).resolve().parents[1] / "fixtures" / "golden_documents" / "pdf" / "acroform.pdf"
    if system_fonts.find_font_file("Arial") is None:
        pytest.skip("Arial not installed")
    system_fonts.take_notes()
    pdf = open_document(gold)
    try:
        edit = EditableDocument(pdf)
        field = next(f for f in edit.fields.values() if f.name == "full_name")
        field.value, field.font_family, field.font_size = "Field Hello 日本", "Arial", 12.0
        field.value_dirty = field.style_dirty = field.appearance_dirty = True
        out = tmp_path / "form.pdf"
        bake_into_document(edit, out)
    finally:
        pdf.close()
    d = fitz.open(out.as_posix())
    try:
        w = next(x for x in d[0].widgets() if x.field_name == "full_name")
        assert w.field_value == "Field Hello 日本"  # the value itself is never altered
        # the entry's appearance stream carries its own font resources (page fonts do not list them)
        names = " ".join(
            d.xref_get_key(x, "BaseFont")[1] for x in range(1, d.xref_length()) if d.xref_get_key(x, "BaseFont")[0] != "null"
        )
        assert "Arial" in names, names
        embedded = [x for x in range(1, d.xref_length()) if d.xref_get_key(x, "FontFile2")[0] != "null"]
        assert embedded, "no embedded TrueType program in the file"
        assert "Field Hello 日本" in d[0].get_text().replace("\n", " ")
    finally:
        d.close()
    assert system_fonts.take_notes() == {}
