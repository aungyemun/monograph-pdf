"""Synthetic inputs for the real-GUI checks of page design, redaction, merge and Images to PDF.

Usage: python scripts/audit/make_gui_qa_inputs.py <output folder>
Everything is generated; no personal documents are used.
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz
from PIL import Image

SECRET = "ZEBRA-4711"


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    # 1. mixed / rotated pages
    d = fitz.open()
    for i, (w, h, rot) in enumerate([(595, 842, 0), (595, 842, 90), (792, 612, 0), (595, 842, 180)]):
        p = d.new_page(width=w, height=h)
        p.insert_text((80, 120), f"Page {i + 1} body text (rotation {rot})", fontsize=16)
        p.set_rotation(rot)
    d.save(out / "design_input.pdf")
    d.close()
    # 2. redaction input
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), f"Account {SECRET} is private", fontsize=14)
    p.insert_text((72, 140), "Unrelated line stays", fontsize=14)
    wdg = fitz.Widget()
    wdg.field_name, wdg.field_type = "account", fitz.PDF_WIDGET_TYPE_TEXT
    wdg.rect, wdg.field_value = fitz.Rect(72, 400, 320, 426), SECRET
    p.add_widget(wdg)
    p.add_text_annot((420, 300), f"note mentions {SECRET}")
    d.set_toc([[1, f"Section {SECRET}", 1]])
    d.set_metadata({"title": f"Report {SECRET}", "author": "QA"})
    d.embfile_add(f"notes-{SECRET}.txt", b"named after the secret")
    d.save(out / "redact_input.pdf")
    d.close()
    # 3. merge inputs with bookmarks
    for name, n in (("merge_A", 3), ("merge_B", 2)):
        d = fitz.open()
        for i in range(n):
            d.new_page().insert_text((72, 72), f"{name} page {i + 1}", fontsize=14)
        d.set_toc([[1, f"{name} start", 1], [2, f"{name} detail", n]])
        d.save(out / f"{name}.pdf")
        d.close()
    # 4. photo with EXIF orientation 6 and GPS, and a picture for watermark/background
    im = Image.new("RGB", (480, 240), (255, 255, 255))
    for x in range(120):
        for y in range(240):
            im.putpixel((x, y), (220, 30, 30))
    ex = Image.Exif()
    ex[0x0112] = 6
    ex[0x010F] = "PhoneMakerXYZ"
    ex[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0), 3: "E", 4: (139.0, 41.0, 0.0)}
    im.save(out / "photo_gps.jpg", exif=ex.tobytes(), dpi=(72, 72), quality=92)
    logo = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
    for x in range(300):
        for y in range(150):
            if (x - 150) ** 2 / 140 ** 2 + (y - 75) ** 2 / 65 ** 2 <= 1:
                logo.putpixel((x, y), (20, 90, 200, 255))
    logo.save(out / "logo.png")
    print("inputs written to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
