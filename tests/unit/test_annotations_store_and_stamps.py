"""Undoable annotations of any type, the stamp library, squiggly markup and visual-signature pictures.

Each check saves the document and reopens it: what the user sees after Undo/Redo is what the file holds.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.annotations import add_callout, add_squiggly, add_text_comment, list_annotations  # noqa: E402
from core.annotations import store  # noqa: E402
from core.annotations.stamps import PRESETS, StampSpec, add_custom_stamp, stamp_spec, update_stamp  # noqa: E402
from core.document import open_document  # noqa: E402
from core.editing.annot_commands import AnnotCreateCommand, AnnotModifyCommand, AnnotRemoveCommand  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Point, Rect  # noqa: E402


@pytest.fixture()
def opened(tmp_path: Path):
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Some text to mark up", fontsize=14)
    doc.save(src)
    doc.close()
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    yield pdf, edit, tmp_path
    pdf.close()


def _save_copy(pdf, out: Path) -> None:
    """Save as the application does: from a copy of the live document (bake works on a copy; garbage
    collection on the live document itself would renumber its objects)."""
    copy = fitz.open("pdf", pdf._backend._doc.tobytes(garbage=0))  # noqa: SLF001
    copy.save(out, garbage=3, deflate=True)
    copy.close()


def _saved(pdf, tmp_path: Path, name: str = "out.pdf") -> list[tuple[str, str]]:
    out = tmp_path / name
    _save_copy(pdf, out)
    with fitz.open(out) as d:
        return [(a.type[1], (a.info or {}).get("content", "")) for a in d[0].annots()]


def test_sticky_note_create_undo_redo_survives_save(opened):
    pdf, edit, tmp = opened
    cmd = AnnotCreateCommand(pdf, edit, 0, lambda: add_text_comment(pdf, 0, Point(100, 100), "Check this",
                                                                    color=(1, 0.8, 0.1), author="Reviewer"))
    edit.commands.execute(cmd)
    assert _saved(pdf, tmp, "a.pdf") == [("Text", "Check this")]
    edit.undo()
    assert _saved(pdf, tmp, "b.pdf") == []
    edit.redo()
    assert _saved(pdf, tmp, "c.pdf") == [("Text", "Check this")]
    info = [a for a in list_annotations(pdf) if a.kind == "Text"][0]
    assert info.author == "Reviewer" and info.xref == cmd.xrefs[0] and info.color == "#ffcc19"


def test_callout_creates_and_undoes_both_parts(opened):
    pdf, edit, tmp = opened
    edit.commands.execute(AnnotCreateCommand(pdf, edit, 0, lambda: add_callout(
        pdf, 0, Rect(200, 200, 150, 40), "Callout", callout_point=Point(150, 220))))
    assert sorted(k for k, _c in _saved(pdf, tmp, "a.pdf")) == ["FreeText", "Line"]
    edit.undo()
    assert _saved(pdf, tmp, "b.pdf") == []


def test_editing_and_deleting_any_annotation_is_undoable(opened):
    pdf, edit, tmp = opened
    xref = add_text_comment(pdf, 0, Point(100, 100), "Original")

    def change():
        page, annot = store.find_live(pdf, 0, xref)
        annot.set_info(content="Edited")
        annot.set_colors(stroke=(0, 0, 1))
        annot.set_opacity(0.4)
        annot.update()

    edit.commands.execute(AnnotModifyCommand(pdf, edit, 0, xref, change))
    assert _saved(pdf, tmp, "a.pdf") == [("Text", "Edited")]
    edit.undo()
    assert _saved(pdf, tmp, "b.pdf") == [("Text", "Original")]
    page, annot = store.find_live(pdf, 0, xref)
    assert annot.opacity in (-1, 1.0)
    edit.redo()
    page, annot = store.find_live(pdf, 0, xref)
    assert annot.info["content"] == "Edited" and abs(annot.opacity - 0.4) < 0.01
    edit.commands.execute(AnnotRemoveCommand(pdf, edit, 0, xref))
    assert _saved(pdf, tmp, "c.pdf") == []
    edit.undo()
    assert _saved(pdf, tmp, "d.pdf") == [("Text", "Edited")]


def test_imported_annotations_keep_their_position_in_the_stacking_order(opened):
    pdf, edit, tmp = opened
    a = add_text_comment(pdf, 0, Point(100, 100), "first")
    b = add_text_comment(pdf, 0, Point(150, 100), "second")
    c = add_text_comment(pdf, 0, Point(200, 100), "third")
    page = pdf._backend._doc[0]  # noqa: SLF001
    before = store.annots_refs(pdf._backend._doc, page.xref)  # noqa: SLF001
    edit.commands.execute(AnnotRemoveCommand(pdf, edit, 0, b))
    edit.undo()
    assert store.annots_refs(pdf._backend._doc, page.xref) == before  # noqa: SLF001
    assert {a, b, c} <= set(before)


def test_squiggly_markup_with_opacity(opened):
    pdf, edit, tmp = opened
    xref = add_squiggly(pdf, 0, [Rect(72, 86, 150, 18)], opacity=0.6)
    page, annot = store.find_live(pdf, 0, xref)
    assert annot.type[1] == "Squiggly" and abs(annot.opacity - 0.6) < 0.01


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.label)
def test_every_preset_stamp_is_a_stamp_annotation_with_its_label(opened, preset):
    pdf, edit, tmp = opened
    xref = add_custom_stamp(pdf, 0, fitz.Rect(100, 300, 300, 350), StampSpec(text=preset.label, color=preset.color))
    out = tmp / "s.pdf"
    _save_copy(pdf, out)
    with fitz.open(out) as d:
        page = d[0]
        (annot,) = list(page.annots())
        assert annot.type[1] == "Stamp" and annot.info["content"] == preset.label
        # the appearance is drawn in the stamp's colour
        pix = page.get_pixmap(clip=annot.rect, dpi=72)
        r, g, b = (int(preset.color[i:i + 2], 16) for i in (1, 3, 5))
        colours = {pix.pixel(x, y)[:3] for x in range(pix.width) for y in range(pix.height)}
        assert any(abs(c[0] - r) < 40 and abs(c[1] - g) < 40 and abs(c[2] - b) < 40 for c in colours)
    assert stamp_spec(pdf, xref)[0].text == preset.label


def test_stamp_move_opacity_rotation_and_unicode_text(opened):
    pdf, edit, tmp = opened
    xref = add_custom_stamp(pdf, 0, fitz.Rect(100, 300, 300, 360), StampSpec(text="承認 APPROVED", color="#b91c1c",
                                                                             subtitle="2026-10-21"))

    def change():
        spec, _size = stamp_spec(pdf, xref)
        update_stamp(pdf, 0, xref, spec=StampSpec(**{**spec.__dict__, "opacity": 0.5, "rotation": 90.0}),
                     center=(300, 500))

    edit.commands.execute(AnnotModifyCommand(pdf, edit, 0, xref, change))
    page, annot = store.find_live(pdf, 0, xref)
    r = annot.rect
    assert abs((r.x0 + r.x1) / 2 - 300) < 1 and abs((r.y0 + r.y1) / 2 - 500) < 1
    assert abs(r.width - 60) < 1 and abs(r.height - 200) < 1  # turned a quarter: width and height swap
    assert abs(annot.opacity - 0.5) < 0.01
    edit.undo()
    page, annot = store.find_live(pdf, 0, xref)
    assert abs(annot.rect.width - 200) < 1 and stamp_spec(pdf, xref)[0].rotation == 0


def test_picture_stamp(opened):
    from PIL import Image

    pdf, edit, tmp = opened
    pic = tmp / "logo.png"
    Image.new("RGBA", (80, 40), (0, 128, 0, 255)).save(pic)
    xref = add_custom_stamp(pdf, 0, fitz.Rect(100, 300, 260, 380), StampSpec(text="Logo", image_path=str(pic)))
    out = tmp / "p.pdf"
    _save_copy(pdf, out)
    with fitz.open(out) as d:
        page = d[0]
        annot = next(page.annots())
        pix = page.get_pixmap(clip=annot.rect, dpi=72)
        assert (0, 128, 0) in {pix.pixel(x, y)[:3] for x in range(pix.width) for y in range(pix.height)}
    assert stamp_spec(pdf, xref)[0].image_path == str(pic)


def test_stamp_library_keeps_custom_and_picture_stamps(tmp_path, monkeypatch):
    from PIL import Image

    from core.annotations import stamp_library as lib

    monkeypatch.setenv("MONOGRAPH_PDF_USER_DATA_DIR", str(tmp_path / "data"))
    src = tmp_path / "scan.png"
    im = Image.new("RGB", (100, 50), (255, 255, 255))
    for x in range(20, 80):
        im.putpixel((x, 25), (10, 10, 120))
    im.save(src)
    stored = lib.import_picture(src, remove_white=True)
    assert stored.parent == tmp_path / "data" / "stamps"
    with Image.open(stored) as out:
        assert out.mode == "RGBA" and out.getpixel((5, 5))[3] == 0 and out.getpixel((50, 25))[3] == 255
    lib.save_entries([lib.LibraryEntry(kind="text", text="CHECKED", color="#123456"),
                      lib.LibraryEntry(kind="picture", picture=stored.name)])
    assert [e.text or e.picture for e in lib.load_entries()] == ["CHECKED", stored.name]
    stored.unlink()
    assert [e.kind for e in lib.load_entries()] == ["text"]  # a missing picture is skipped


def test_drawn_signature_png_is_transparent_and_fits_its_box():
    import io

    from PIL import Image

    from core.signatures.ops import fit_rect, strokes_to_png

    png = strokes_to_png([[(0, 0), (100, 30), (200, 0)], [(50, 40)]])
    with Image.open(io.BytesIO(png)) as im:
        assert im.mode == "RGBA" and im.getpixel((0, im.height - 1))[3] == 0
        assert any(im.getpixel((x, y))[3] > 200 for x in range(im.width) for y in range(0, im.height, 3))
    r = fit_rect(200, 100, Rect(0, 0, 100, 100))
    assert (r.w, r.h, r.y) == (100, 50, 25)
    click = fit_rect(200, 100, Rect(300, 300, 1, 1), default=(180, 60))
    assert abs(click.w / click.h - 2) < 1e-6 and abs((click.x + click.w / 2) - 300.5) < 1e-6
