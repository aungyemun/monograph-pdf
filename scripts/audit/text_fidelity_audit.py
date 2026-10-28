"""Text fidelity audit (developer harness, not shipped): typed and filled text survives Save / Save As
and re-editing exactly — same text, font, size and colour; fully visible (not clipped); no old text
left under new text; readable by an independent PDF reader.

Usage::

    env\\Scripts\\python.exe scripts\\audit\\text_fidelity_audit.py <out_dir> [form.pdf ...]

Without PDFs only the synthetic text-box checks run. Given PDFs are copied into <out_dir> first; the
originals are never opened for writing. Results: <out_dir>/text_fidelity.json and a summary on stdout.

Every check reads the saved file with PyMuPDF directly (not through Monograph PDF's own model). Field
appearances are checked by flattening a *copy* in memory (``Document.bake``) and reading the words
inside the field: what any PDF reader that shows the stored appearance displays.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MONOGRAPH_PDF_USER_DATA_DIR", tempfile.mkdtemp(prefix="mpdf_fid_"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import fitz  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(["monograph-pdf-text-fidelity"])  # fonts resolve as in the app

from core.document import open_document  # noqa: E402
from core.editing.edit_model import EditableDocument  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from core.forms.fields import FieldType  # noqa: E402
from engines.bake_edits import bake_via_backend  # noqa: E402

RESULTS: list[dict] = []

# Values per script; the n-th text field gets VALUES[n % len]. Second round = re-modification.
VALUES = ["Alice Smith", "山田 太郎", "Ünïcødé – café №5", "2026-10-28", "東京都千代田区1-2-3", "TNF-α 10 µM"]
REVISED = ["Bob", "佐藤", "Zoë", "1999-01-01", "大阪", "IL-1β"]
LONG = "This is a deliberately long entry to see whether the saved field shows all of it 0123456789"
SHORT = ["12", "３", "7", "A"]  # for narrow boxes (year, month, a single character …)


def _value_for(f, n: int, revised: bool = False) -> str:
    """A value that a person could really type into this field (fits its width at its font size)."""
    if f.rect.w < 70:  # also "date" boxes that only hold a month, a day or an age
        return SHORT[(n + (1 if revised else 0)) % len(SHORT)]
    if f.field_type == FieldType.DATE:
        return "1999-01-01" if revised else "2026-10-28"
    pool = REVISED if revised else VALUES
    return pool[n % len(pool)]


def check(area: str, name: str, ok: bool, detail: object = "") -> bool:
    safe = str(detail)[:300].encode("utf-8", "backslashreplace").decode("utf-8")  # raw PDF names
    RESULTS.append({"area": area, "check": name.encode("utf-8", "backslashreplace").decode("utf-8"),
                    "ok": bool(ok), "detail": safe})
    return ok


def _norm(s: str) -> str:
    return "".join((s or "").split())


def _visible_text(path: Path, page_index: int, rect: fitz.Rect, pad: float = 0.5) -> tuple[str, list]:
    """Words a reader shows inside ``rect`` (appearance streams flattened in a copy)."""
    with fitz.open(path) as d:
        mem = fitz.open("pdf", d.tobytes())
    try:
        mem.bake(annots=True, widgets=True)
        page = mem[page_index]
        r = fitz.Rect(rect) + (-pad, -pad, pad, pad)
        # only words drawn by the field itself (centre inside it), not printed labels next to it
        words = [w for w in page.get_text("words", clip=r + (-20, -20, 20, 20))
                 if r.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))]
        # words sticking out sideways are cut off on screen / paper (word boxes include the font's
        # ascent and descent, so a small vertical overhang is normal and not checked here; text cut
        # off at the bottom shows up as missing words instead)
        outside = [w[4] for w in words if w[0] < r.x0 - 1 or w[2] > r.x1 + 1]
        return "".join(w[4] for w in words), outside
    finally:
        mem.close()


def _widgets(path: Path) -> dict[tuple[int, str], fitz.Widget]:
    out = {}
    with fitz.open(path) as d:
        for page in d:
            for w in page.widgets() or []:
                out[(page.number, w.field_name or "")] = (w.field_type, w.field_value, w.text_font,
                                                          w.text_fontsize, tuple(w.text_color or ()),
                                                          fitz.Rect(w.rect))
    return out


# ---------------------------------------------------------------------------------------------- forms
def audit_form(src: Path, out: Path) -> None:
    area = f"form:{src.name}"
    before = _widgets(src)
    pdf = open_document(src)
    edit = EditableDocument(pdf)
    kinds = (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE)
    text_fields = [f for f in edit.fields.values() if f.is_acroform and f.field_type in kinds and not f.readonly]
    checks_fields = [f for f in edit.fields.values() if f.is_acroform and f.field_type == FieldType.CHECKBOX
                     and not f.readonly]
    expected: dict[tuple[int, str], str] = {}
    long_done = False
    for n, f in enumerate(text_fields):
        v = _value_for(f, n)
        auto = before.get((f.page_index, f.name), (None,) * 4)[3] in (0, None)
        if not long_done and (f.field_type == FieldType.MULTILINE or auto) and f.rect.w > 120:
            v, long_done = LONG, True  # long text only where the field can wrap or shrink it
        edit.set_field_value(f.object_id, v)
        expected[(f.page_index, f.name)] = v
    check(area, f"{len(text_fields)} text/multi-line/date fields recognised", len(text_fields) > 0,
          {k.value: sum(1 for f in text_fields if f.field_type == k) for k in kinds})
    for f in checks_fields:
        edit.set_field_value(f.object_id, checked=True)
    first = out / f"{src.stem}-filled.pdf"
    bake_via_backend(edit, first, flatten=False)
    pdf.close()
    check(area, "saved file opens", fitz.open(first).page_count > 0)

    after = _widgets(first)
    lost = [k for k in before if k not in after]
    check(area, "every field still a field after Save As", not lost, lost[:5])
    _verify_fields(area, "fill", first, before, after, expected, src=src)
    for f in checks_fields:
        k = (f.page_index, f.name)
        check(area, f"checkbox {f.name!r} saved as ticked", k in after and after[k][1] not in ("", "Off", None),
              after.get(k, ("missing",))[1] if k in after else "missing")

    # reopen in Monograph PDF, values intact, then re-modify (shorter values: nothing of the old may remain)
    pdf2 = open_document(first)
    edit2 = EditableDocument(pdf2)
    by_key = {(f.page_index, f.name): f for f in edit2.fields.values() if f.is_acroform}
    wrong = [(k, by_key[k].value, v) for k, v in expected.items() if k in by_key and by_key[k].value != v]
    check(area, "reopened values identical in Monograph PDF", not wrong, wrong[:3])
    revised: dict[tuple[int, str], str] = {}
    for n, (k, _v) in enumerate(expected.items()):
        if k in by_key:
            nv = _value_for(by_key[k], n, revised=True)
            edit2.set_field_value(by_key[k].object_id, nv)
            revised[k] = nv
    second = out / f"{src.stem}-remodified.pdf"
    bake_via_backend(edit2, second, flatten=False)
    pdf2.close()
    _verify_fields(area, "re-modify", second, before, _widgets(second), revised, old=expected, src=src)


def _verify_fields(area: str, stage: str, path: Path, before: dict, after: dict, expected: dict,
                   old: dict | None = None, src: Path | None = None) -> None:
    bad_value, bad_style, clipped, invisible, remnants = [], [], [], [], []
    for k, v in expected.items():
        if k not in after:
            bad_value.append((k[1], "field missing"))
            continue
        ftype, value, font, size, color, rect = after[k]
        if value != v:
            bad_value.append((k[1], value, v))
        b = before.get(k)
        if b is not None and (b[2], round(b[3] or 0, 1), b[4]) != (font, round(size or 0, 1), color):
            bad_style.append((k[1], (b[2], b[3], b[4]), (font, size, color)))
        shown, outside = _visible_text(path, k[0], rect)
        if _norm(v) and _norm(v) not in _norm(shown):
            (clipped if _norm(shown) and _norm(v).startswith(_norm(shown)[:3]) else invisible).append(
                (k[1], v, shown))
        printed = set(_visible_text(src, k[0], rect)[1]) if (outside and src is not None) else set()
        outside = [w for w in outside if w not in printed]  # the form's own printed "( )" or "-"
        if outside:
            clipped.append((k[1], "outside field", outside[:3]))
        if old is not None:
            o = _norm(old.get(k, ""))
            if o and o != _norm(v) and o in _norm(shown):
                remnants.append((k[1], old[k], shown))
    n = len(expected)
    check(area, f"{stage}: {n} values stored exactly", not bad_value, bad_value[:3])
    check(area, f"{stage}: field font, size and colour unchanged", not bad_style, bad_style[:3])
    check(area, f"{stage}: every value visible in the saved appearance", not invisible, invisible[:3])
    check(area, f"{stage}: no value cut off", not clipped, clipped[:3])
    if old is not None:
        check(area, f"{stage}: no earlier value left visible under the new one", not remnants, remnants[:3])


# ------------------------------------------------------------------------------------------ text boxes
BOXES = [  # family, size, colour, text
    ("Arial", 12, "#c0392b", "Arial 12 red — Ünïcødé café"),
    ("Times New Roman", 16, "#1f4e79", "Times New Roman 16 blue"),
    ("MS Gothic", 11, "#000000", "ＭＳ ゴシック 日本語テキスト 123"),
    ("Yu Gothic", 14, "#2e7d32", "游ゴシック 緑 14pt"),
    ("Meiryo", 10, "#6a1b9a", "メイリオ Meiryo 混在 mixed"),
    ("MS Mincho", 18, "#000000", "明朝体 見出し"),
]


def _spans_in(path: Path, page_index: int, rect: fitz.Rect) -> list[dict]:
    with fitz.open(path) as d:
        out = []
        for b in d[page_index].get_text("dict", clip=rect + (-2, -2, 2, 2))["blocks"]:
            for line in b.get("lines", []):
                out.extend(s for s in line["spans"] if s["text"].strip())
        # reading order on the page (a replacement is drawn later but sits where the original was)
        return sorted(out, key=lambda s: (round(s["bbox"][1] / 4), s["bbox"][0]))


def _font_ok(family: str, font: str) -> bool:
    want = family.lower().replace(" ", "")
    got = font.lower().replace(" ", "").replace("-", "")
    aliases = {"msgothic": ("msgothic", "ｍｓゴシック"), "msmincho": ("msmincho", "ｍｓ明朝"),
               "yugothic": ("yugothic", "游ゴシック"), "timesnewroman": ("timesnewroman", "times")}
    return any(a in got for a in aliases.get(want, (want,)))


def audit_text_boxes(src: Path, out: Path, area: str) -> None:
    """Text boxes in several fonts, sizes and colours on a blank page added to (a copy of) ``src``;
    Save; re-edit the first word of each saved box as existing page text; Save again."""
    base = out / f"{src.stem}+page.pdf"
    with fitz.open(src) as d:
        d.new_page(width=595, height=842)
        d.save(base)
    pdf = open_document(base)
    pg = pdf.page_count - 1
    edit = EditableDocument(pdf)
    placed = []
    for i, (family, size, color, text) in enumerate(BOXES):
        r = Rect(40, 40 + i * 80, 420, size * 1.6 + 8)
        box = edit.create_text_box(pg, r, text=text, auto_match=False)
        st = box.style.to_dict()
        st.update({"font_family": family, "font_size": float(size), "text_color": color})
        edit.apply_style_dict(box.object_id, {"style": st})
        b = edit.objects[box.object_id]
        placed.append((fitz.Rect(b.rect.x, b.rect.y, b.rect.x + b.rect.w, b.rect.y + b.rect.h),
                       family, size, color, text))
    first = out / f"{src.stem}-boxes.pdf"
    bake_via_backend(edit, first, flatten=False)
    pdf.close()
    _verify_boxes(area, "save", first, pg, placed)

    # Re-edit the first word of every saved box as existing page text (Edit Text on the page)
    pdf2 = open_document(first)
    edit2 = EditableDocument(pdf2)
    spans = edit2.extract_native_spans(pg)
    revised, old_words = [], {}
    for rect, family, size, color, text in placed:
        inside = [s for s in spans if rect.intersects(fitz.Rect(s.rect.x, s.rect.y, s.rect.x + s.rect.w,
                                                                 s.rect.y + s.rect.h))]
        sp = min(inside, key=lambda s: (round(s.rect.y), s.rect.x), default=None)
        if not check(area, f"saved {family} box is editable page text", sp is not None, text):
            continue
        # change the first word of the run, as a person editing the line would (longer than before)
        first = sp.text.split()[0] if sp.text.split() else sp.text
        if any(ord(c) > 0x2E80 for c in first):
            first = first[:2]
        new_word = "改訂版" if any(ord(c) > 0x2E80 for c in first) else "Edited"
        new_run = sp.text.replace(first, new_word, 1)
        edit2.begin_native_edit(sp, new_run)
        new_text = text.replace(sp.text, new_run, 1)
        revised.append((rect, family, size, color, new_text))
        if first not in new_text:
            old_words[new_text] = first
    second = out / f"{src.stem}-boxes-reedited.pdf"
    bake_via_backend(edit2, second, flatten=False)
    pdf2.close()
    _verify_boxes(area, "re-edit", second, pg, revised, old=old_words)


def _verify_boxes(area: str, stage: str, path: Path, pg: int, items: list, old: dict | None = None) -> None:
    for rect, family, size, color, text in items:
        clip = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 30)  # the box may grow downwards
        spans = _spans_in(path, pg, clip)
        got = "".join(s["text"] for s in spans)
        label = f"{stage}: {family} {size}pt"
        check(area, f"{label}: text exact", _norm(text) == _norm(got), got)
        if not spans:
            continue
        fonts = {s["font"] for s in spans}
        check(area, f"{label}: font kept", all(_font_ok(family, f) for f in fonts), fonts)
        check(area, f"{label}: size kept", all(abs(s["size"] - size) < 0.3 for s in spans),
              sorted({round(s["size"], 2) for s in spans}))
        want = int(color.lstrip("#"), 16)
        check(area, f"{label}: colour kept", all(s["color"] == want for s in spans),
              sorted({f"#{s['color']:06x}" for s in spans}))
        cut = [s["text"] for s in spans if s["bbox"][2] > rect.x1 + 1.5 or s["bbox"][0] < rect.x0 - 1.5]
        check(area, f"{label}: inside its box (not cut off)", not cut, cut)
        if old is not None and old.get(text):
            check(area, f"{label}: replaced word removed (no overlap)", _norm(old[text]) not in _norm(got), got)
        # one layer of text only: no two spans drawn on top of each other
        boxes = [fitz.Rect(s["bbox"]) for s in spans]
        overlap = [(spans[i]["text"], spans[j]["text"]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
                   if (boxes[i] & boxes[j]).get_area() > 0.3 * min(boxes[i].get_area(), boxes[j].get_area())]
        check(area, f"{label}: no overlapping text", not overlap, overlap[:3])


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build" / "text-fidelity"
    shutil.rmtree(out, ignore_errors=True)
    (out / "inputs").mkdir(parents=True)
    base = out / "inputs" / "blank_a4.pdf"
    d = fitz.open()
    d.new_page(width=595, height=842)
    d.save(base)
    d.close()
    audit_text_boxes(base, out, "textboxes:blank")
    for arg in sys.argv[2:]:
        src = Path(arg)
        copy = out / "inputs" / src.name
        shutil.copyfile(src, copy)  # never touch the original
        try:
            audit_form(copy, out)
        except Exception as exc:  # noqa: BLE001
            check(f"form:{src.name}", "audit ran", False, repr(exc))
        try:
            audit_text_boxes(copy, out, f"textboxes:{src.name}")
        except Exception as exc:  # noqa: BLE001
            check(f"textboxes:{src.name}", "audit ran", False, repr(exc))
    (out / "text_fidelity.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"CHECKS {len(RESULTS)}  FAILED {len(failed)}")
    for r in failed:
        print(f"  [{r['area']}] {r['check']}: {r['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
