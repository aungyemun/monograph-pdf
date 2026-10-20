"""Headers/footers, page numbers, watermarks and backgrounds (core/convert/page_marks.py).

Positions are checked on the *rendered* page (displayed orientation): the mark's ink is found by
comparing a render with and without the mark, so the checks do not rely on PyMuPDF's text
coordinates. Text direction is checked with the extracted line direction turned into displayed
space.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import zlib
from pathlib import Path

import fitz
import pytest

from core.convert.page_marks import (
    KIND_BACKGROUND,
    KIND_HEADER_FOOTER,
    KIND_WATERMARK,
    BackgroundSpec,
    HeaderFooterSpec,
    WatermarkSpec,
    apply_page_marks,
    count_marks,
    remove_page_marks,
    render_preview,
)
from core.document import open_document

DPI = 36
SCALE = DPI / 72.0
# (width, height, rotation) — displayed sizes: A4 portrait, A4 shown landscape, Letter landscape, upside down, 270
PAGES = [(595, 842, 0), (595, 842, 90), (792, 612, 0), (595, 842, 180), (595, 842, 270)]


def _make(path: Path, pages=PAGES, *, crop_offset: bool = False) -> Path:
    d = fitz.open()
    for w, h, rot in pages:
        p = d.new_page(width=w, height=h)
        p.insert_text((200, 300), "BODY TEXT", fontsize=14)
        p.set_rotation(rot)
    if crop_offset:  # a page whose visible area does not start at (0, 0)
        p = d.new_page(width=700, height=900)
        p.insert_text((150, 400), "CROPPED BODY", fontsize=14)
        p.set_cropbox(fitz.Rect(50, 40, 645, 882))
    d.save(path)
    d.close()
    return path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _diff_bbox(before: fitz.Page, after: fitz.Page) -> tuple[float, float, float, float] | None:
    """Bounding box (displayed points) of pixels that differ between two renders of one page."""
    a = before.get_pixmap(dpi=DPI, alpha=False)
    b = after.get_pixmap(dpi=DPI, alpha=False)
    assert (a.width, a.height) == (b.width, b.height)
    sa, sb, n = a.samples, b.samples, a.n
    xs, ys = [], []
    for y in range(a.height):
        row = y * a.stride
        for x in range(a.width):
            i = row + x * n
            if abs(sa[i] - sb[i]) + abs(sa[i + 1] - sb[i + 1]) + abs(sa[i + 2] - sb[i + 2]) > 30:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs) / SCALE, min(ys) / SCALE, (max(xs) + 1) / SCALE, (max(ys) + 1) / SCALE)


def _displayed_dir(page: fitz.Page, needle: str) -> tuple[float, float]:
    m = page.rotation_matrix
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            if needle in "".join(s["text"] for s in line["spans"]):
                dx, dy = line["dir"]
                v = fitz.Point(dx, dy) * fitz.Matrix(m.a, m.b, m.c, m.d, 0, 0)
                return round(v.x, 2), round(v.y, 2)
    raise AssertionError(f"{needle!r} not found on page {page.number}")


def _single_slot(tmp_path: Path, slot: str, text: str, src: Path) -> Path:
    spec = HeaderFooterSpec(**{slot: text})
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / f"{slot}.pdf", header_footer=spec)
    finally:
        doc.close()
    return tmp_path / f"{slot}.pdf"


@pytest.mark.parametrize("slot", ["header_left", "header_center", "header_right",
                                  "footer_left", "footer_center", "footer_right"])
def test_each_slot_lands_on_its_edge_and_reads_upright_on_every_rotation(tmp_path, slot):
    src = _make(tmp_path / "src.pdf", crop_offset=True)
    out = _single_slot(tmp_path, slot, "SLOTMARK", src)
    where, align = slot.split("_")
    with fitz.open(src) as before, fitz.open(out) as after:
        for pb, pa in zip(before, after):
            w, h = pa.rect.width, pa.rect.height
            box = _diff_bbox(pb, pa)
            assert box is not None, f"page {pa.number}: nothing drawn"
            x0, y0, x1, y1 = box
            ctx = f"page {pa.number} rot {pa.rotation} size {w:.0f}x{h:.0f} box {[round(v) for v in box]}"
            # vertical: header in the top band, footer in the bottom band
            if where == "header":
                assert y1 <= 40, ctx
            else:
                assert y0 >= h - 36, ctx
            # horizontal alignment (36 pt margins)
            if align == "left":
                assert 30 <= x0 <= 44, ctx
            elif align == "right":
                assert w - 44 <= x1 <= w - 30, ctx
            else:
                assert abs((x0 + x1) / 2 - w / 2) <= 6, ctx
            assert _displayed_dir(pa, "SLOTMARK") == (1.0, 0.0), ctx  # left to right, upright
            assert pa.rotation == pb.rotation and pa.rect == pb.rect, ctx


def test_tokens_numbering_range_and_date(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)] * 5)
    spec = HeaderFooterSpec(footer_center="Page {page} of {total}", header_right="{date}",
                            start_number=3, date=dt.date(2026, 10, 20))
    doc = open_document(src)
    try:
        res = apply_page_marks(doc, tmp_path / "o.pdf", header_footer=spec, pages=[1, 3])
    finally:
        doc.close()
    assert res.pages_marked == 2
    with fitz.open(tmp_path / "o.pdf") as d:
        texts = [p.get_text() for p in d]
    assert "Page" not in texts[0] and "Page" not in texts[2] and "Page" not in texts[4]
    assert "Page 4 of 7" in texts[1] and "Page 6 of 7" in texts[3]  # start number 3 -> pages 3..7
    assert "2026-10-20" in texts[1]


def test_braces_that_are_not_tokens_stay_literal(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)])
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", header_footer=HeaderFooterSpec(header_left="{x} {page}"))
    finally:
        doc.close()
    with fitz.open(tmp_path / "o.pdf") as d:
        assert "{x} 1" in d[0].get_text()


def test_japanese_header_and_long_text_shrinks_to_fit(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(300, 400, 0)])
    long = "社外秘 Confidential " * 6
    doc = open_document(src)
    try:
        res = apply_page_marks(doc, tmp_path / "o.pdf", header_footer=HeaderFooterSpec(header_center=long))
    finally:
        doc.close()
    assert res.font_size_reduced_on == [0]
    with fitz.open(src) as b, fitz.open(tmp_path / "o.pdf") as a:
        x0, _y0, x1, _y1 = _diff_bbox(b[0], a[0])
        assert x0 >= 30 and x1 <= 270
        assert "社外秘" in a[0].get_text()


@pytest.mark.parametrize("angle,expected", [(45, (0.71, -0.71)), (0, (1.0, 0.0)), (90, (0.0, -1.0)), (-45, (0.71, 0.71))])
def test_watermark_direction_and_centre_on_rotated_pages(tmp_path, angle, expected):
    src = _make(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", watermark=WatermarkSpec(text="WMTEXT", rotation=angle))
    finally:
        doc.close()
    with fitz.open(src) as before, fitz.open(tmp_path / "o.pdf") as after:
        for pb, pa in zip(before, after):
            w, h = pa.rect.width, pa.rect.height
            x0, y0, x1, y1 = _diff_bbox(pb, pa)
            ctx = f"page {pa.number} rot {pa.rotation}"
            assert abs((x0 + x1) / 2 - w / 2) <= 8 and abs((y0 + y1) / 2 - h / 2) <= 8, ctx
            assert x0 >= 0 and y0 >= 0 and x1 <= w and y1 <= h, ctx
            assert _displayed_dir(pa, "WMTEXT") == expected, ctx


def test_watermark_opacity_position_and_layer(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)])
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf",
                         watermark=WatermarkSpec(text="TOPMARK", rotation=0, position="top", opacity=0.3))
    finally:
        doc.close()
    with fitz.open(src) as b, fitz.open(tmp_path / "o.pdf") as a:
        _x0, y0, _x1, y1 = _diff_bbox(b[0], a[0])
        assert (y0 + y1) / 2 < 842 * 0.3
        raw = b"".join(a.xref_object(x).encode() for x in range(1, a.xref_length()))
        assert b"/ca .3" in raw or b"/ca 0.3" in raw
        assert any(v["name"] == "Monograph PDF: Watermark" for v in a.get_ocgs().values())
        assert count_marks(a)[KIND_WATERMARK] == 1


def _png(path: Path, size=(200, 100), color=(200, 0, 0, 255)) -> Path:
    from PIL import Image

    Image.new("RGBA", size, color).save(path)
    return path


def test_image_watermark_behind_content_keeps_text_visible(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)])
    img = _png(tmp_path / "logo.png", size=(400, 400), color=(0, 0, 255, 255))
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf",
                         watermark=WatermarkSpec(image_path=img, image_scale=0.9, rotation=0, opacity=1.0, behind=True))
    finally:
        doc.close()
    with fitz.open(tmp_path / "o.pdf") as d:
        page = d[0]
        contents = page.get_contents()
        assert d.xref_stream(contents[0]).strip().endswith(b"Do Q")  # the mark comes first (underneath)
        pix = page.get_pixmap(dpi=72, alpha=False)
        r, g, bl = pix.pixel(300, 421)
        assert bl > 200 and r < 50  # blue picture visible in the middle
        # body text is still drawn on top (dark pixels inside the text box)
        tb = page.search_for("BODY TEXT")[0]
        dark = sum(1 for x in range(int(tb.x0), int(tb.x1)) for y in range(int(tb.y0), int(tb.y1))
                   if sum(pix.pixel(x, y)) < 150)
        assert dark > 10


def test_image_watermark_turned_stays_on_page(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 90)])
    img = _png(tmp_path / "wide.png", size=(1000, 200), color=(0, 128, 0, 255))
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf",
                         watermark=WatermarkSpec(image_path=img, image_scale=1.0, rotation=30, opacity=0.5))
    finally:
        doc.close()
    with fitz.open(src) as b, fitz.open(tmp_path / "o.pdf") as a:
        x0, y0, x1, y1 = _diff_bbox(b[0], a[0])
        w, h = a[0].rect.width, a[0].rect.height
        assert x0 >= 0 and y0 >= 0 and x1 <= w + 1 and y1 <= h + 1
        assert abs((x0 + x1) / 2 - w / 2) <= 8


def test_background_colour_is_behind_text(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 90)])
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", background=BackgroundSpec(color=(1.0, 0.9, 0.6)))
    finally:
        doc.close()
    with fitz.open(tmp_path / "o.pdf") as d:
        pix = d[0].get_pixmap(dpi=72, alpha=False)
        for px in (pix.pixel(10, 10), pix.pixel(pix.width - 5, pix.height - 5)):
            assert all(abs(a - b) <= 2 for a, b in zip(px, (255, 230, 153))), px
        tb = d[0].search_for("BODY TEXT")[0] * d[0].rotation_matrix
        tb.normalize()
        dark = sum(1 for x in range(int(tb.x0), int(tb.x1)) for y in range(int(tb.y0), int(tb.y1))
                   if sum(pix.pixel(x, y)) < 200)
        assert dark > 10


def test_background_image_fit_keeps_proportions(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(600, 800, 0)])
    img = _png(tmp_path / "sq.png", size=(100, 100), color=(255, 0, 0, 255))
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", background=BackgroundSpec(color=None, image_path=img))
    finally:
        doc.close()
    with fitz.open(src) as b, fitz.open(tmp_path / "o.pdf") as a:
        x0, y0, x1, y1 = _diff_bbox(b[0], a[0])
        assert abs((x1 - x0) - (y1 - y0)) <= 4  # square
        assert abs(x1 - x0 - 600) <= 4


def test_replace_existing_and_independent_kinds(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)] * 2)
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "a.pdf", header_footer=HeaderFooterSpec(header_left="FIRSTHDR"),
                         watermark=WatermarkSpec(text="KEEPWM"))
    finally:
        doc.close()
    a = open_document(tmp_path / "a.pdf")
    try:
        res = apply_page_marks(a, tmp_path / "b.pdf", header_footer=HeaderFooterSpec(header_left="SECONDHDR"))
        apply_page_marks(a, tmp_path / "c.pdf", header_footer=HeaderFooterSpec(header_left="SECONDHDR"),
                         replace_existing=False)
    finally:
        a.close()
    assert res.removed.get("replaced") == 2
    with fitz.open(tmp_path / "b.pdf") as d:
        t = d[0].get_text()
        assert "SECONDHDR" in t and "FIRSTHDR" not in t and "KEEPWM" in t
        assert count_marks(d) == {KIND_HEADER_FOOTER: 2, KIND_WATERMARK: 2, KIND_BACKGROUND: 0}
    with fitz.open(tmp_path / "c.pdf") as d:
        t = d[0].get_text()
        assert "SECONDHDR" in t and "FIRSTHDR" in t


def _all_stream_bytes(d: fitz.Document) -> bytes:
    out = []
    for x in range(1, d.xref_length()):
        try:
            if d.xref_is_stream(x):
                out.append(d.xref_stream(x) or b"")
        except Exception:  # noqa: BLE001
            pass
    return b"".join(out)


def test_remove_only_the_chosen_kind_and_its_data(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0), (595, 842, 90)])
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "m.pdf", header_footer=HeaderFooterSpec(footer_right="FOOTKEEP"),
                         watermark=WatermarkSpec(text="SECRETMARK"),
                         background=BackgroundSpec(color=(0.9, 0.9, 1.0)))
    finally:
        doc.close()
    m = open_document(tmp_path / "m.pdf")
    try:
        res = remove_page_marks(m, tmp_path / "r.pdf", {KIND_WATERMARK})
    finally:
        m.close()
    assert res.removed == {KIND_WATERMARK: 2} and res.retained_objects == 0
    with fitz.open(tmp_path / "r.pdf") as d:
        assert count_marks(d) == {KIND_HEADER_FOOTER: 2, KIND_WATERMARK: 0, KIND_BACKGROUND: 2}
        assert all("SECRETMARK" not in p.get_text() for p in d)
        assert all("FOOTKEEP" in p.get_text() and "BODY TEXT" in p.get_text() for p in d)
        # the watermark's glyph stream is gone from the file, not only hidden
        blob = _all_stream_bytes(d)
        with fitz.open(tmp_path / "m.pdf") as before:
            assert len(_all_stream_bytes(before)) > len(blob)


def test_remove_all_restores_the_original_look(tmp_path):
    src = _make(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "m.pdf", header_footer=HeaderFooterSpec(header_center="H"),
                         watermark=WatermarkSpec(text="W"), background=BackgroundSpec())
    finally:
        doc.close()
    m = open_document(tmp_path / "m.pdf")
    try:
        remove_page_marks(m, tmp_path / "r.pdf")
    finally:
        m.close()
    with fitz.open(src) as a, fitz.open(tmp_path / "r.pdf") as b:
        for pa, pb in zip(a, b):
            assert _diff_bbox(pa, pb) is None


def test_shared_resources_are_hidden_but_reported_as_retained(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)] * 2)
    with fitz.open(src) as d:  # make both pages share one indirect /Resources dictionary
        kind, val = d.xref_get_key(d[0].xref, "Resources")
        if kind == "xref":
            ref = val
        else:
            x = d.get_new_xref()
            d.update_object(x, val)
            ref = f"{x} 0 R"
        d.xref_set_key(d[0].xref, "Resources", ref)
        d.xref_set_key(d[1].xref, "Resources", ref)
        d.save(tmp_path / "shared.pdf")
    doc = open_document(tmp_path / "shared.pdf")
    try:
        apply_page_marks(doc, tmp_path / "m.pdf", watermark=WatermarkSpec(text="SHAREDWM"))
    finally:
        doc.close()
    m = open_document(tmp_path / "m.pdf")
    try:
        r = remove_page_marks(m, tmp_path / "r.pdf")
    finally:
        m.close()
    assert r.removed.get(KIND_WATERMARK) == 2
    assert r.retained_objects == 2  # honest: hidden, but the shared dictionary still holds the objects
    with fitz.open(tmp_path / "r.pdf") as d:
        assert all("SHAREDWM" not in p.get_text() for p in d)
        assert all("BODY TEXT" in p.get_text() for p in d)


def test_source_unchanged_and_annotations_and_fields_kept(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)])
    with fitz.open(src) as d:
        d[0].add_highlight_annot(fitz.Rect(195, 285, 300, 305))
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect = "f1", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 500, 300, 524)
        w.field_value = "value"
        d[0].add_widget(w)
        d.save(tmp_path / "rich.pdf")
    before = _sha(tmp_path / "rich.pdf")
    doc = open_document(tmp_path / "rich.pdf")
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", header_footer=HeaderFooterSpec(footer_center="{page}"),
                         watermark=WatermarkSpec(text="X"), background=BackgroundSpec())
    finally:
        doc.close()
    assert _sha(tmp_path / "rich.pdf") == before
    with fitz.open(tmp_path / "o.pdf") as d:
        assert [a.type[1] for a in d[0].annots()] == ["Highlight"]
        assert [(w.field_name, w.field_value) for w in d[0].widgets()] == [("f1", "value")]


def test_invalid_inputs_are_refused(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0)])
    bogus = tmp_path / "not_an_image.png"
    bogus.write_bytes(b"this is not a picture")
    doc = open_document(src)
    try:
        with pytest.raises(ValueError):
            apply_page_marks(doc, tmp_path / "a.pdf", header_footer=HeaderFooterSpec())
        with pytest.raises(ValueError):
            apply_page_marks(doc, tmp_path / "b.pdf", watermark=WatermarkSpec(text="x"), pages=[3])
        with pytest.raises(Exception):
            apply_page_marks(doc, tmp_path / "c.pdf", watermark=WatermarkSpec(image_path=bogus))
    finally:
        doc.close()
    assert not (tmp_path / "a.pdf").exists() and not (tmp_path / "b.pdf").exists() and not (tmp_path / "c.pdf").exists()


def test_preview_matches_the_written_page(tmp_path):
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0), (595, 842, 90), (595, 842, 0)])
    spec = dict(header_footer=HeaderFooterSpec(footer_center="{page}/{total}"), watermark=WatermarkSpec(text="PV"))
    doc = open_document(src)
    try:
        pix = render_preview(doc, 1, dpi=36, **spec)
        apply_page_marks(doc, tmp_path / "o.pdf", **spec)
    finally:
        doc.close()
    with fitz.open(tmp_path / "o.pdf") as d:
        ref = d[1].get_pixmap(dpi=36, alpha=False)
        assert "2/3" in d[1].get_text()
    assert (pix.width, pix.height) == (ref.width, ref.height)
    diff = sum(abs(a - b) for a, b in zip(pix.samples, ref.samples)) / len(ref.samples)
    assert diff < 1.0


def test_legacy_functions_now_correct_on_rotated_pages(tmp_path):
    from core.convert.watermark import apply_headers_footers, apply_page_numbers

    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 90)])
    doc = open_document(src)
    try:
        apply_headers_footers(doc, tmp_path / "hf.pdf", header="LEGACYHDR", footer="LEGACYFTR")
        apply_page_numbers(doc, tmp_path / "pn.pdf", fmt="{page} / {total}")
    finally:
        doc.close()
    with fitz.open(src) as b, fitz.open(tmp_path / "hf.pdf") as a:
        _x0, _y0, _x1, y1 = _diff_bbox(b[0], a[0]) or (0, 0, 0, 999)
        assert _displayed_dir(a[0], "LEGACYHDR") == (1.0, 0.0)
        assert _displayed_dir(a[0], "LEGACYFTR") == (1.0, 0.0)
    with fitz.open(src) as b, fitz.open(tmp_path / "pn.pdf") as a:
        x0, y0, x1, y1 = _diff_bbox(b[0], a[0])
        assert x1 <= a[0].rect.width and y0 >= a[0].rect.height - 40 and x0 > a[0].rect.width / 2


@pytest.mark.parametrize("angle", [0, 45])
def test_marks_share_fonts_and_pictures_across_pages(tmp_path, angle):
    """A 30-page document gets one copy of the picture and of each font, not one per page."""
    src = _make(tmp_path / "src.pdf", pages=[(595, 842, 0), (595, 842, 90)] * 15)
    logo = _png(tmp_path / "logo.png", size=(300, 150))
    doc = open_document(src)
    try:
        apply_page_marks(doc, tmp_path / "o.pdf", header_footer=HeaderFooterSpec(footer_center="{page} 頁"),
                         watermark=WatermarkSpec(image_path=logo, rotation=angle))
    finally:
        doc.close()
    with fitz.open(tmp_path / "o.pdf") as d:
        images = {x[0] for p in d for x in p.get_images(full=True)}
        fonts = {f[0] for p in d for f in p.get_fonts(full=True)}
        assert len(images) == 1, images
        assert len(fonts) <= 3, fonts  # body Helvetica + mark Helvetica + CJK subset
        assert all(f"{i + 1} 頁" in d[i].get_text() for i in range(d.page_count))
    assert (tmp_path / "o.pdf").stat().st_size < 120_000
