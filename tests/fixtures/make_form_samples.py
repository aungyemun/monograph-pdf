"""Representative form/table fixtures (synthetic — no confidential user data)."""

from __future__ import annotations

import os
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"


def write_english_invitation_form(path: Path) -> None:
    """English invitation RSVP-style fillable form."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 60), "Invitation RSVP (Sample)", fontsize=16)
    page.insert_text((72, 90), "Event: Community Open Day — fictional sample only", fontsize=10)

    labels = [
        (72, 130, "Full Name"),
        (72, 180, "Email"),
        (72, 230, "Guests"),
        (72, 280, "Attendance Date"),
        (72, 330, "Notes"),
    ]
    for x, y, label in labels:
        page.insert_text((x, y), label + ":", fontsize=11)

    # Draw empty rectangles (non-fillable look) + real AcroForm widgets
    boxes = [
        (200, 115, 480, 145),
        (200, 165, 480, 195),
        (200, 215, 320, 245),
        (200, 265, 360, 295),
        (200, 315, 480, 390),
    ]
    for x0, y0, x1, y1 in boxes:
        page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0.3, 0.3, 0.3), width=0.8)

    def add_text(name: str, rect: fitz.Rect, multiline: bool = False) -> None:
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = name
        w.rect = rect
        w.text_fontsize = 11
        if multiline:
            w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
        page.add_widget(w)

    add_text("full_name", fitz.Rect(*boxes[0]))
    add_text("email", fitz.Rect(*boxes[1]))
    add_text("guests", fitz.Rect(*boxes[2]))
    add_text("attendance_date", fitz.Rect(*boxes[3]))
    add_text("notes", fitz.Rect(*boxes[4]), multiline=True)

    # Checkbox
    page.insert_text((72, 420), "Vegetarian meal", fontsize=11)
    page.draw_rect(fitz.Rect(200, 408, 214, 422), color=(0.2, 0.2, 0.2), width=0.8)
    cb = fitz.Widget()
    cb.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    cb.field_name = "vegetarian"
    cb.rect = fitz.Rect(200, 408, 214, 422)
    page.add_widget(cb)

    # Dropdown
    page.insert_text((72, 460), "Seat preference", fontsize=11)
    combo = fitz.Widget()
    combo.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    combo.field_name = "seat"
    combo.rect = fitz.Rect(200, 445, 360, 470)
    combo.choice_values = ["Any", "Aisle", "Window"]
    page.add_widget(combo)

    # Visual signature field (not cryptographic)
    page.insert_text((72, 520), "Signature (visual placeholder)", fontsize=11)
    page.draw_rect(fitz.Rect(72, 540, 300, 600), color=(0.4, 0.4, 0.4), width=0.8)
    sig = fitz.Widget()
    sig.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    sig.field_name = "guest_signature"
    sig.rect = fitz.Rect(72, 540, 300, 600)
    page.add_widget(sig)

    doc.save(path.as_posix())
    doc.close()


def write_japanese_admin_form(path: Path) -> None:
    """Japanese administrative-style form (synthetic labels only)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 50), "申請書サンプル（架空）", fontsize=14)
    page.insert_text((72, 72), "Japanese administrative form sample — fictional", fontsize=9)

    rows = [
        (72, 110, "氏名", "shimei"),
        (72, 160, "住所", "jusho"),
        (72, 210, "電話番号", "tel"),
        (72, 260, "生年月日", "seinengappi"),
        (72, 310, "申請内容", "naiyo"),
    ]
    for x, y, label, name in rows:
        page.insert_text((x, y), label, fontsize=11)
        page.draw_rect(fitz.Rect(160, y - 14, 520, y + 16), color=(0.2, 0.2, 0.2), width=0.7)
        # Underline-style empty zone for detector
        page.draw_line(fitz.Point(160, y + 18), fitz.Point(520, y + 18), color=(0.5, 0.5, 0.5), width=0.5)
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = name
        w.rect = fitz.Rect(160, y - 14, 520, y + 16)
        if name == "naiyo":
            w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
            w.rect = fitz.Rect(160, y - 14, 520, y + 70)
            page.draw_rect(w.rect, color=(0.2, 0.2, 0.2), width=0.7)
        page.add_widget(w)

    page.insert_text((72, 420), "同意する", fontsize=11)
    page.draw_rect(fitz.Rect(160, 408, 174, 422), color=(0.2, 0.2, 0.2), width=0.8)
    cb = fitz.Widget()
    cb.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    cb.field_name = "doi"
    cb.rect = fitz.Rect(160, 408, 174, 422)
    page.add_widget(cb)

    page.insert_text((72, 460), "署名欄（視覚のみ）", fontsize=11)
    page.draw_rect(fitz.Rect(72, 480, 280, 560), color=(0.3, 0.3, 0.3), width=0.8)

    doc.save(path.as_posix())
    doc.close()


def write_table_itinerary(path: Path) -> None:
    """Table-heavy itinerary with drawn grid lines."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 50), "Sample Itinerary (fictional)", fontsize=14)
    page.insert_text((72, 70), "Synthetic schedule — no real personal data", fontsize=9)

    # 5x4 table grid
    x0, y0 = 72, 100
    col_w = [70, 120, 120, 140]
    row_h = [24, 24, 24, 24, 24]
    xs = [x0]
    for w in col_w:
        xs.append(xs[-1] + w)
    ys = [y0]
    for h in row_h:
        ys.append(ys[-1] + h)

    # Draw grid
    for y in ys:
        page.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y), width=0.7)
    for x in xs:
        page.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]), width=0.7)

    headers = ["Day", "From", "To", "Activity"]
    data = [
        ["1", "Tokyo", "Kyoto", "Travel"],
        ["2", "Kyoto", "Kyoto", "Temple visit"],
        ["3", "Kyoto", "Osaka", "Transit"],
        ["4", "Osaka", "Tokyo", "Return"],
    ]
    for i, h in enumerate(headers):
        page.insert_text((xs[i] + 6, ys[0] + 16), h, fontsize=10)
    for r, row in enumerate(data):
        for c, val in enumerate(row):
            page.insert_text((xs[c] + 6, ys[r + 1] + 16), val, fontsize=10)

    doc.save(path.as_posix())
    doc.close()


def write_hybrid_xfa_like_form(path: Path) -> None:
    """
    Synthetic hybrid-style form whose widget names mimic Adobe LiveCycle SOM paths.

    Used to regression-test that internal names such as topmostSubform[0].Page1[0]...
    are never painted as field contents. Includes a minimal /XFA entry on AcroForm
    so capability detection classifies the file as hybrid when widgets exist.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 48), "行政行程表サンプル（架空・合成）", fontsize=14)
    page.insert_text((72, 68), "Hybrid AcroForm/XFA-like fixture — fictional itinerary", fontsize=9)

    # Light-blue table cells (appearance stands in for empty form backgrounds)
    rows = [
        (100, "氏名", "topmostSubform[0].Page1[0].shimei[0]"),
        (150, "日付", "topmostSubform[0].Page1[0].hizuke[0]"),
        (200, "行程", "topmostSubform[0].Page1[0].koutei[0]"),
        (250, "備考", "topmostSubform[0].Page1[0].bikou[0]"),
    ]
    for y, label, som in rows:
        page.insert_text((72, y), label, fontsize=11)
        rect = fitz.Rect(160, y - 16, 520, y + 14)
        page.draw_rect(rect, color=(0.45, 0.62, 0.85), fill=(0.82, 0.90, 0.98), width=0.6)
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = som
        w.rect = rect
        w.text_fontsize = 11
        # Deliberately leave value empty — name must not appear as content
        page.add_widget(w)

    # One populated field with a real value (not a SOM path)
    page.insert_text((72, 310), "確認番号", fontsize=11)
    rect = fitz.Rect(160, 294, 360, 324)
    page.draw_rect(rect, color=(0.45, 0.62, 0.85), fill=(0.82, 0.90, 0.98), width=0.6)
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = "topmostSubform[0].Page1[0].kakunin[0]"
    w.rect = rect
    w.field_value = "A-1001"
    w.text_fontsize = 11
    page.add_widget(w)

    page.insert_text((72, 360), "同意", fontsize=11)
    cb = fitz.Widget()
    cb.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    cb.field_name = "topmostSubform[0].Page1[0].doi[0]"
    cb.rect = fitz.Rect(160, 348, 174, 362)
    page.add_widget(cb)

    # Attach a minimal /XFA stream on AcroForm (hybrid marker). Stub, not full LiveCycle.
    # PyMuPDF often keeps AcroForm inline — promote to an indirect object first.
    try:
        doc.save(path.as_posix(), deflate=True)
        cat = doc.pdf_catalog()
        af = doc.xref_get_key(cat, "AcroForm")
        xml = (
            b'<?xml version="1.0"?>'
            b'<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/">'
            b"<template><subform name=\"topmostSubform\"/></template>"
            b"<datasets><data/></datasets>"
            b"</xdp:xdp>"
        )
        stream_xref = doc.get_new_xref()
        doc.update_object(stream_xref, "<<>>")
        doc.update_stream(stream_xref, xml)
        if af and af[0] == "xref":
            af_xref = int(str(af[1]).split()[0])
            doc.xref_set_key(af_xref, "XFA", f"{stream_xref} 0 R")
        elif af and af[0] == "dict":
            body = str(af[1]).strip()
            if body.startswith("<<") and body.endswith(">>"):
                body = body[2:-2].strip()
            af_xref = doc.get_new_xref()
            doc.update_object(af_xref, f"<< {body} /XFA {stream_xref} 0 R >>")
            doc.xref_set_key(cat, "AcroForm", f"{af_xref} 0 R")
        doc.save(path.as_posix(), deflate=True, incremental=False)
    except Exception:  # noqa: BLE001
        try:
            doc.save(path.as_posix(), deflate=True)
        except Exception:  # noqa: BLE001
            pass

    doc.close()


def main(*, force: bool | None = None) -> int:
    """Create form fixtures. Existing files are kept unless force / MONOGRAPH_REGEN_SAMPLES."""
    if force is None:
        force = os.environ.get("MONOGRAPH_REGEN_SAMPLES", "").strip().lower() in ("1", "true", "yes")
    SAMPLES.mkdir(parents=True, exist_ok=True)
    targets = [
        (SAMPLES / "sample_invitation_form.pdf", write_english_invitation_form),
        (SAMPLES / "sample_jp_admin_form.pdf", write_japanese_admin_form),
        (SAMPLES / "sample_itinerary_table.pdf", write_table_itinerary),
        (SAMPLES / "sample_hybrid_xfa_itinerary.pdf", write_hybrid_xfa_like_form),
    ]
    wrote = 0
    for path, writer in targets:
        if force or not path.is_file() or path.stat().st_size <= 0:
            try:
                writer(path)
                wrote += 1
            except OSError as exc:
                if path.is_file():
                    print(f"keep existing {path.name} (locked: {exc})")
                else:
                    raise
        else:
            print(f"keep existing {path.name}")
    print(f"Wrote {wrote} form fixture(s) to {SAMPLES} (force={force})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
