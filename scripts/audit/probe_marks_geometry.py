"""Probe: where do watermark / header / footer / page numbers land on rotated and mixed pages?

Builds a 4-page PDF (A4 portrait, A4 page with /Rotate 90, Letter landscape, A4 /Rotate 180),
applies each tool, then reports for every page the *displayed* position of the added text
(via get_text 'words', which PyMuPDF returns in displayed/unrotated? -> we convert explicitly)
and whether it reads upright (line direction).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from core.convert.watermark import apply_headers_footers, apply_page_numbers, apply_watermark  # noqa: E402
from core.document import open_document  # noqa: E402


def make(path: Path) -> None:
    d = fitz.open()
    for (w, h, rot) in [(595, 842, 0), (595, 842, 90), (792, 612, 0), (595, 842, 180)]:
        p = d.new_page(width=w, height=h)
        p.insert_text((100, 400), "BODY", fontsize=20)
        p.set_rotation(rot)
    d.save(path)


def where(path: Path, needle: str) -> list[dict]:
    out = []
    with fitz.open(path) as d:
        for p in d:
            disp = p.rect
            hits = []
            for b in p.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(s["text"] for s in l["spans"])
                    if needle in t:
                        r = fitz.Rect(l["bbox"]) * p.rotation_matrix  # unrotated -> displayed
                        r.normalize()
                        dx, dy = l["dir"]
                        # direction in displayed space
                        v = fitz.Point(dx, dy) * fitz.Matrix(p.rotation_matrix.a, p.rotation_matrix.b,
                                                             p.rotation_matrix.c, p.rotation_matrix.d, 0, 0)
                        hits.append({"text": t, "disp_rect": [round(x) for x in r],
                                     "disp_dir": [round(v.x, 2), round(v.y, 2)],
                                     "inside_page": bool(disp.contains(r))})
            out.append({"page": p.number, "rotation": p.rotation, "disp_size": [round(disp.width), round(disp.height)],
                        "hits": hits})
    return out


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "src.pdf"
    make(src)
    res = {}
    doc = open_document(src)
    apply_headers_footers(doc, tmp / "hf.pdf", header="HEADERTEXT", footer="FOOTERTEXT")
    apply_page_numbers(doc, tmp / "pn.pdf", fmt="PAGE {page} OF {total}")
    apply_watermark(doc, tmp / "wm.pdf", text="WATERMARKX", rotate=45)
    apply_watermark(doc, tmp / "wm0.pdf", text="FLATMARK", rotate=0)
    doc.close()
    res["header"] = where(tmp / "hf.pdf", "HEADERTEXT")
    res["footer"] = where(tmp / "hf.pdf", "FOOTERTEXT")
    res["page_numbers"] = where(tmp / "pn.pdf", "PAGE")
    res["watermark45"] = where(tmp / "wm.pdf", "WATERMARKX")
    res["watermark0"] = where(tmp / "wm0.pdf", "FLATMARK")
    if len(sys.argv) > 1:  # optional: save a contact sheet of displayed renders
        out = Path(sys.argv[1])
        out.mkdir(parents=True, exist_ok=True)
        for name in ("hf", "pn", "wm"):
            with fitz.open(tmp / f"{name}.pdf") as d:
                for p in d:
                    p.get_pixmap(dpi=30).save(out / f"{name}_p{p.number}_rot{p.rotation}.png")
    for k, v in res.items():
        for p in v:
            print(k, p["page"], "rot", p["rotation"], "disp", p["disp_size"],
                  [(h["disp_rect"], h["disp_dir"], h["inside_page"]) for h in p["hits"]])


if __name__ == "__main__":
    main()
