"""Generate the golden documents and their expected-property manifest.

The manifest is written from the SPEC below — what each document is *declared* to contain — not
measured back from the generated files, so a generator or renderer bug cannot silently become the
expectation. ``tests/integration/test_golden_documents.py`` then checks every file against the
manifest with independent code (PyMuPDF objects, raw bytes) and against the reference renders.

Reference renders (``reference/*.png``, 40 dpi grey) are committed. They are never rewritten by a
test run. To change them, review the new renders and run

    python tests/fixtures/golden_documents/make_golden.py --update-references --i-reviewed-the-renders

Only fonts shipped inside PyMuPDF are used (Base-14 and Droid Sans Fallback), so the files are
redistributable. No personal data. Usage: ``python make_golden.py`` (re)creates the PDFs and the
manifest but keeps existing references.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
PDF_DIR = HERE / "pdf"
REF_DIR = HERE / "reference"
A4 = (595.276, 841.89)
LETTER = (612.0, 792.0)
A3 = (841.89, 1190.551)
A5 = (419.528, 595.276)
PASSWORD = "golden-open"
REF_DPI = 40

JP = "日本語のテキスト見本"
JP_FONT = fitz.Font("cjk")


def _txt(page, text, x, y, size=12, font="helv", color=(0, 0, 0)):
    page.insert_text((x, y), text, fontsize=size, fontname=font, color=color)


def _jp(page, text, x, y, size=14):
    page.insert_font(fontname="jpf", fontbuffer=JP_FONT.buffer)
    page.insert_text((x, y), text, fontsize=size, fontname="jpf")


def _pixmap(w, h, rgb):
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pm.set_rect(pm.irect, rgb)
    return pm


# Each builder returns (document, spec). spec["pages"][i] lists expected facts for the page.
def b_a4_portrait():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _txt(p, "A4 portrait heading", 72, 90, 20)
    _txt(p, "Second line of body text", 72, 130, 12, "tiro")
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["A4 portrait heading", 72, 90], ["Second line of body text", 72, 130]]}]}


def b_a4_landscape():
    d = fitz.open()
    p = d.new_page(width=A4[1], height=A4[0])
    _txt(p, "A4 landscape heading", 72, 90, 20)
    return d, {"pages": [{"size": (A4[1], A4[0]), "rotate": 0, "texts": [["A4 landscape heading", 72, 90]]}]}


def b_letter():
    d = fitz.open()
    p = d.new_page(width=LETTER[0], height=LETTER[1])
    _txt(p, "US Letter heading", 72, 90, 20)
    return d, {"pages": [{"size": LETTER, "rotate": 0, "texts": [["US Letter heading", 72, 90]]}]}


def b_mixed_sizes():
    d = fitz.open()
    pages = []
    for size, name in ((A4, "A4"), (A3, "A3"), (A5, "A5"), ((A4[1], A4[0]), "A4L"), (LETTER, "LT")):
        p = d.new_page(width=size[0], height=size[1])
        _txt(p, f"Mixed page {name}", 60, 80, 18)
        pages.append({"size": size, "rotate": 0, "texts": [[f"Mixed page {name}", 60, 80]]})
    return d, {"pages": pages}


def b_multipage():
    d = fitz.open()
    pages = []
    for i in range(12):
        p = d.new_page(width=A4[0], height=A4[1])
        _txt(p, f"Multipage document page {i + 1} of 12", 72, 90, 14)
        pages.append({"size": A4, "rotate": 0, "texts": [[f"Multipage document page {i + 1} of 12", 72, 90]]})
    return d, {"pages": pages}


def b_rotated():
    d = fitz.open()
    pages = []
    for rot in (0, 90, 180, 270):
        p = d.new_page(width=300, height=500)
        _txt(p, f"Rotated {rot} anchor", 40, 80, 16)
        _txt(p, "Lower text", 40, 400, 12)
        p.set_rotation(rot)
        pages.append({"size": (300, 500), "rotate": rot, "texts": [[f"Rotated {rot} anchor", 40, 80], ["Lower text", 40, 400]]})
    return d, {"pages": pages}


def b_english():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    lines = ["The quick brown fox jumps over the lazy dog.", "Pack my box with five dozen liquor jugs.", "0123456789 punctuation: ; , . ! ?"]
    for i, t in enumerate(lines):
        _txt(p, t, 72, 100 + i * 24, 12)
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [[t, 72, 100 + i * 24] for i, t in enumerate(lines)]}]}


def b_japanese():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _jp(p, JP, 72, 100)
    _jp(p, "東京都千代田区", 72, 130)
    d.subset_fonts()
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [[JP, 72, 100], ["東京都千代田区", 72, 130]]}], "fonts_embedded": True}


def b_mixed_en_jp():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _txt(p, "Order number 2026-17", 72, 100, 12)
    _jp(p, "注文番号の確認", 72, 130)
    d.subset_fonts()
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Order number 2026-17", 72, 100], ["注文番号の確認", 72, 130]]}], "fonts_embedded": True}


def b_embedded_subset_fonts():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    p.insert_font(fontname="emb", fontbuffer=JP_FONT.buffer)
    p.insert_text((72, 100), "Embedded subset Latin text", fontsize=14, fontname="emb")
    d.subset_fonts()
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Embedded subset Latin text", 72, 100]]}], "fonts_embedded": True}


def b_table():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    x0, y0, cw, rh = 72, 150, 100, 26
    cells = []
    for r in range(5):
        for c in range(4):
            pass
            label = f"R{r}C{c}"
            _txt(p, label, x0 + c * cw + 8, y0 + r * rh + 17, 10)
            cells.append([label, x0 + c * cw + 8, y0 + r * rh + 17])
    for r in range(6):  # ruled grid drawn as line segments (the form the table detector reads)
        p.draw_line(fitz.Point(x0, y0 + r * rh), fitz.Point(x0 + 4 * cw, y0 + r * rh), color=(0, 0, 0), width=0.8)
    for c in range(5):
        p.draw_line(fitz.Point(x0 + c * cw, y0), fitz.Point(x0 + c * cw, y0 + 5 * rh), color=(0, 0, 0), width=0.8)
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": cells, "table": {"rows": 5, "cols": 4, "x": x0, "y": y0, "cw": cw, "rh": rh}}]}


def b_images():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    p.insert_image(fitz.Rect(72, 100, 272, 220), pixmap=_pixmap(200, 120, (200, 40, 40)))
    p.insert_image(fitz.Rect(300, 100, 400, 200), pixmap=_pixmap(50, 50, (40, 40, 200)))
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [], "images": [[200, 120], [50, 50]]}]}


def b_vector():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    p.draw_rect(fitz.Rect(60, 60, 300, 200), color=None, fill=(1, 0.9, 0.5))
    p.draw_circle(fitz.Point(420, 160), 50, color=(0, 0, 0.8), fill=(0.8, 0.9, 1), width=2)
    p.draw_line(fitz.Point(60, 260), fitz.Point(500, 300), color=(0.8, 0, 0), width=3)
    _txt(p, "Vector graphics on a coloured background", 72, 120, 12)
    _txt(p, "x = (-b ± √(b²-4ac)) / 2a   ∑ ∫ π", 72, 340, 12, "helv")
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Vector graphics on a coloured background", 72, 120]], "drawings_min": 3}]}


def b_annotations():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _txt(p, "Annotated sentence for highlight", 72, 120, 14)
    r = p.search_for("highlight")[0]
    p.add_highlight_annot(r)
    p.add_text_annot(fitz.Point(400, 120), "A note", icon="Note")
    p.add_underline_annot(p.search_for("Annotated")[0])
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Annotated sentence for highlight", 72, 120]], "annots": ["Highlight", "Text", "Underline"]}]}


def b_acroform():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _txt(p, "Name:", 72, 112, 12)
    _txt(p, "Subscribe:", 72, 152, 12)
    widgets = []
    for name, ftype, rect, val in (
        ("full_name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(160, 95, 400, 120), "Golden Name"),
        ("subscribe", fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.Rect(160, 138, 176, 154), None),
    ):
        w = fitz.Widget()
        w.field_type, w.field_name, w.rect = ftype, name, rect
        if val:
            w.field_value = val
        p.add_widget(w)
        widgets.append([name, [rect.x0, rect.y0, rect.x1, rect.y1], val])
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Name:", 72, 112], ["Subscribe:", 72, 152]], "widgets": widgets}]}


def b_scanned():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    scan = fitz.open()
    sp = scan.new_page(width=A4[0], height=300)
    sp.insert_text((40, 80), "SCANNED PAGE REFERENCE TEXT", fontsize=28, fontname="helv")
    pm = sp.get_pixmap(dpi=150, alpha=False)
    p.insert_image(fitz.Rect(0, 0, A4[0], 300), pixmap=pm)
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [], "images": [[pm.width, pm.height]], "scan_text": "SCANNED PAGE REFERENCE TEXT"}]}


def b_signature_field():
    d = fitz.open()
    p = d.new_page(width=A4[0], height=A4[1])
    _txt(p, "Signature field present (unsigned)", 72, 100, 12)
    w = fitz.Widget()
    w.field_type, w.field_name, w.rect = fitz.PDF_WIDGET_TYPE_SIGNATURE, "Sig1", fitz.Rect(72, 700, 272, 750)
    p.add_widget(w)
    return d, {"pages": [{"size": A4, "rotate": 0, "texts": [["Signature field present (unsigned)", 72, 100]]}], "has_signature_field": True,
               "note": "A signature FIELD only. No fixture here carries a cryptographic signature: creating a valid one needs a certificate and is not offered by the app."}


BUILDERS = {
    "a4_portrait": b_a4_portrait, "a4_landscape": b_a4_landscape, "us_letter": b_letter, "mixed_sizes": b_mixed_sizes,
    "multipage_12": b_multipage, "rotated_pages": b_rotated, "english_text": b_english, "japanese_text": b_japanese,
    "mixed_english_japanese": b_mixed_en_jp, "embedded_subset_fonts": b_embedded_subset_fonts, "table_grid": b_table,
    "images": b_images, "vector_graphics": b_vector, "annotations": b_annotations, "acroform": b_acroform,
    "scanned_page": b_scanned, "signature_field": b_signature_field,
}


def render_reference(pdf: Path, out: Path) -> None:
    d = fitz.open(pdf.as_posix())
    if d.needs_pass:
        d.authenticate(PASSWORD)
    pix = d[0].get_pixmap(dpi=REF_DPI, colorspace=fitz.csGRAY, alpha=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out.as_posix())
    d.close()


def main(argv: list[str]) -> int:
    update = "--update-references" in argv
    if update and "--i-reviewed-the-renders" not in argv:
        print("Refusing to rewrite reference renders without --i-reviewed-the-renders (review the images first).")
        return 2
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"reference_dpi": REF_DPI, "password": PASSWORD, "documents": {}}
    for name, build in BUILDERS.items():
        doc, spec = build()
        path = PDF_DIR / f"{name}.pdf"
        doc.save(path.as_posix(), garbage=3, deflate=True)
        doc.close()
        spec["file"] = f"pdf/{name}.pdf"
        manifest["documents"][name] = spec
        ref = REF_DIR / f"{name}.png"
        if update or not ref.exists():
            render_reference(path, ref)
    # password-protected copy of the English document
    src = fitz.open((PDF_DIR / "english_text.pdf").as_posix())
    prot = PDF_DIR / "password_protected.pdf"
    src.save(prot.as_posix(), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=PASSWORD, owner_pw=PASSWORD + "-owner")
    src.close()
    spec = json.loads(json.dumps(manifest["documents"]["english_text"]))
    spec.update({"file": "pdf/password_protected.pdf", "encrypted": True})
    manifest["documents"]["password_protected"] = spec
    ref = REF_DIR / "password_protected.png"
    if update or not ref.exists():
        render_reference(prot, ref)
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(manifest['documents'])} golden documents written to {PDF_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
