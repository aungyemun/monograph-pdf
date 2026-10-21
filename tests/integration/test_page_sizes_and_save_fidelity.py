"""Page sizes and save fidelity: standard and custom sizes, mixed-size documents, portrait/landscape,
/Rotate, CropBox/TrimBox and UserUnit; Open -> (Modify) -> Save -> Reopen -> Compare (geometry, text,
images, colour values, annotations, rendered appearance)."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document import open_document  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from engines.bake_edits import bake_via_backend  # noqa: E402

MM = 72 / 25.4
SIZES = {
    "A0": (841 * MM, 1189 * MM), "A1": (594 * MM, 841 * MM), "A2": (420 * MM, 594 * MM),
    "A3": (297 * MM, 420 * MM), "A4": (210 * MM, 297 * MM), "A5": (148 * MM, 210 * MM),
    "A6": (105 * MM, 148 * MM), "Letter": (612, 792), "Legal": (612, 1008), "Tabloid": (792, 1224),
    "Executive": (522, 756), "B4": (250 * MM, 353 * MM), "B5": (176 * MM, 250 * MM), "Custom": (333.3, 777.7),
}


def _rgb_jpeg(w=64, h=48):
    import io

    from PIL import Image

    im = Image.new("RGB", (w, h))
    for x in range(w):
        for y in range(h):
            im.putpixel((x, y), (x * 4 % 256, y * 5 % 256, 128))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _cmyk_jpeg():
    import io

    from PIL import Image

    im = Image.new("CMYK", (40, 40), (0, 200, 200, 0))  # red in CMYK
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _fixture(path: Path) -> Path:
    doc = fitz.open()
    for name, (w, h) in SIZES.items():
        page = doc.new_page(width=w, height=h)
        page.insert_text((36, 60), f"{name} page", fontsize=18)
        page.draw_rect(fitz.Rect(36, 80, 136, 130), color=None, fill=(0.0, 0.5, 1.0))
    # landscape A4, rotated A4, CropBox/TrimBox, UserUnit
    land = doc.new_page(width=842, height=595)
    land.insert_text((36, 60), "landscape page", fontsize=18)
    rot = doc.new_page(width=595, height=842)
    rot.insert_text((36, 60), "rotated page", fontsize=18)
    rot.set_rotation(90)
    crop = doc.new_page(width=600, height=800)
    crop.insert_text((80, 120), "cropped page", fontsize=18)
    crop.set_cropbox(fitz.Rect(50, 60, 550, 700))
    crop.set_trimbox(fitz.Rect(60, 70, 540, 690))
    crop.set_bleedbox(fitz.Rect(55, 65, 545, 695))
    crop.set_artbox(fitz.Rect(70, 80, 530, 680))
    # images: RGB JPEG, CMYK JPEG, grey PNG with alpha (soft mask)
    img = doc.new_page(width=595, height=842)
    img.insert_image(fitz.Rect(36, 36, 236, 186), stream=_rgb_jpeg())
    img.insert_image(fitz.Rect(300, 36, 400, 136), stream=_cmyk_jpeg())
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 30, 30), True)
    pix.clear_with(128)
    img.insert_image(fitz.Rect(36, 300, 136, 400), pixmap=pix)
    img.add_text_annot((400, 400), "A note").update()
    img.insert_text((36, 500), "日本語 テキスト α β γ ∑ x² 1.2×10⁻³", fontsize=14, fontname="japan")
    doc.save(path)
    doc.close()
    uu = fitz.open(path)
    up = uu.new_page(width=300, height=400)
    up.insert_text((30, 60), "user unit page", fontsize=12)
    uu.xref_set_key(up.xref, "UserUnit", "2")
    uu.saveIncr()
    uu.close()
    return path


@pytest.fixture(scope="module")
def fixture_pdf(tmp_path_factory) -> Path:
    return _fixture(tmp_path_factory.mktemp("sizes") / "sizes.pdf")


def test_every_standard_and_custom_size_is_read_as_is(fixture_pdf):
    pdf = open_document(fixture_pdf)
    try:
        for i, (name, (w, h)) in enumerate(SIZES.items()):
            info = pdf.page(i)
            assert abs(info.display_width_pt - w) < 0.5 and abs(info.display_height_pt - h) < 0.5, name
        n = len(SIZES)
        assert (round(pdf.page(n).display_width_pt), round(pdf.page(n).display_height_pt)) == (842, 595)
        rot = pdf.page(n + 1)
        assert rot.rotation == 90 and (round(rot.display_width_pt), round(rot.display_height_pt)) == (842, 595)
        crop = pdf.page(n + 2)
        assert (round(crop.display_width_pt), round(crop.display_height_pt)) == (500, 640)  # the CropBox is shown
        uu = pdf.page(pdf.page_count - 1)
        assert (round(uu.display_width_pt), round(uu.display_height_pt)) == (600, 800)  # UserUnit 2
    finally:
        pdf.close()


def _page_state(doc: fitz.Document) -> list[tuple]:
    out = []
    for p in doc:
        out.append((round(p.mediabox.width, 1), round(p.mediabox.height, 1), p.rotation,
                    tuple(round(v, 1) for v in p.cropbox), tuple(round(v, 1) for v in p.trimbox),
                    doc.xref_get_key(p.xref, "UserUnit")[1]))
    return out


def _images(doc: fitz.Document) -> list[tuple]:
    out = []
    for p in doc:
        for info in p.get_images(full=True):
            xref = info[0]
            ext = doc.extract_image(xref)
            out.append((p.number, ext["width"], ext["height"], ext["ext"], ext["colorspace"], info[1] != 0))
    return out


def test_save_without_changes_keeps_geometry_text_images_colours_and_annotations(fixture_pdf, tmp_path):
    pdf = open_document(fixture_pdf)
    edit = EditableDocument(pdf)
    out = tmp_path / "unchanged.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(fixture_pdf) as a, fitz.open(out) as b:
        assert _page_state(a) == _page_state(b)
        assert [p.get_text() for p in a] == [p.get_text() for p in b]
        assert _images(a) == _images(b)  # same pixel size, encoding (JPEG stays JPEG), colour space, masks
        ia = a[len(SIZES) + 3]
        ib = b[len(SIZES) + 3]
        assert [x.info["content"] for x in ia.annots()] == [x.info["content"] for x in ib.annots()]
        # CMYK image stays CMYK (no conversion on save)
        assert any(c == 4 for (*_r, c, _m) in _images(b))
        # rendered appearance identical
        for i in (0, len(SIZES) + 1, len(SIZES) + 3, a.page_count - 1):
            pa = a[i].get_pixmap(dpi=50)
            pb = b[i].get_pixmap(dpi=50)
            assert (pa.width, pa.height) == (pb.width, pb.height) and pa.samples == pb.samples, i
        # vector fill colour value kept exactly
        fills = [d["fill"] for d in b[0].get_drawings() if d.get("fill")]
        assert fills and tuple(round(c, 3) for c in fills[0]) == (0.0, 0.5, 1.0)


@pytest.mark.parametrize("which", ["A0", "Legal", "rotated", "cropped", "userunit"])
def test_overlays_land_where_placed_on_every_kind_of_page(fixture_pdf, tmp_path, which):
    pdf = open_document(fixture_pdf)
    names = list(SIZES)
    index = {"A0": 0, "Legal": names.index("Legal"), "rotated": len(SIZES) + 1, "cropped": len(SIZES) + 2,
             "userunit": None}[which]
    if index is None:
        index = pdf.page_count - 1
    edit = EditableDocument(pdf)
    edit.create_text_box(index, Rect(100, 150, 220, 30), text="PLACED HERE")
    out = tmp_path / f"{which}.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    from core.page_space import rect_to_display

    with fitz.open(out) as d:
        page = d[index]
        words = [w for w in page.get_text("words") if w[4] in ("PLACED", "HERE")]
        assert words, "overlay text missing"
        r = rect_to_display(page, fitz.Rect(words[0][:4]))
        assert abs(r.x0 - 100) < 6 and 150 <= r.y0 <= 185, (which, r)
    with fitz.open(fixture_pdf) as a, fitz.open(out) as b:
        assert _page_state(a) == _page_state(b)  # geometry unchanged by editing


def test_modify_save_reopen_keeps_unaffected_pages_identical(fixture_pdf, tmp_path):
    pdf = open_document(fixture_pdf)
    edit = EditableDocument(pdf)
    edit.create_text_box(2, Rect(50, 300, 200, 30), text="Only on page three")
    out = tmp_path / "modified.pdf"
    bake_via_backend(edit, out)
    pdf.close()
    with fitz.open(fixture_pdf) as a, fitz.open(out) as b:
        assert a.page_count == b.page_count
        for i in range(a.page_count):
            pa, pb = a[i].get_pixmap(dpi=40), b[i].get_pixmap(dpi=40)
            if i == 2:
                assert pa.samples != pb.samples and "Only on page three" in b[i].get_text()
            else:
                assert pa.samples == pb.samples, f"page {i + 1} changed"
