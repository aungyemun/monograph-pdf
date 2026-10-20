"""Independent checks of the files saved during the real-GUI session (PyMuPDF only, read-only).

Usage: python scripts/audit/verify_gui_qa_outputs.py <folder> [--json out.json]
Each check prints PASS / FAIL / MISSING. Files that were not produced are reported as MISSING.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.convert.page_marks import count_marks  # noqa: E402

SECRET = "ZEBRA-4711"
results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})


def missing(name: str, path: Path) -> bool:
    if not path.exists():
        results.append({"check": name, "status": "MISSING", "detail": path.name})
        return True
    return False


def displayed_dir(page: fitz.Page, needle: str):
    m = page.rotation_matrix
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            if needle in "".join(s["text"] for s in line["spans"]):
                v = fitz.Point(*line["dir"]) * fitz.Matrix(m.a, m.b, m.c, m.d, 0, 0)
                r = fitz.Rect(line["bbox"]) * m
                r.normalize()
                return (round(v.x, 2), round(v.y, 2)), r
    return None, None


def all_bytes(path: Path) -> bytes:
    parts = [path.read_bytes()]
    with fitz.open(path) as d:
        for x in range(1, d.xref_length()):
            try:
                parts.append(d.xref_object(x).encode("latin-1", "replace"))
                if d.xref_is_stream(x) and not d.xref_get_key(x, "Type")[1] == "/EmbeddedFile":
                    parts.append(d.xref_stream(x) or b"")
            except Exception:  # noqa: BLE001
                pass
    return b"".join(parts)


def main(folder: Path) -> None:
    f = folder / "design_hf.pdf"
    if not missing("header/footer file", f):
        with fitz.open(f) as d:
            for p in d:
                dir_, r = displayed_dir(p, "GUIHEADER")
                check(f"header upright on page {p.number + 1} (rot {p.rotation})", dir_ == (1.0, 0.0), str(dir_))
                check(f"header in top band, centred, page {p.number + 1}",
                      r is not None and r.y1 <= 45 and abs((r.x0 + r.x1) / 2 - p.rect.width / 2) < 8, str(r))
                check(f"page number on page {p.number + 1}", f"{p.number + 1} / {d.page_count}" in p.get_text())
            check("header/footer tagged", count_marks(d)["HeaderFooter"] == d.page_count)
    f = folder / "design_wm.pdf"
    if not missing("watermark file", f):
        with fitz.open(f) as d:
            check("picture watermark on every page", count_marks(d)["Watermark"] == d.page_count)
            check("watermark has a picture", all(p.get_images(full=True) for p in d))
    f = folder / "design_bg.pdf"
    if not missing("background file", f):
        with fitz.open(f) as d:
            px = d[0].get_pixmap(dpi=20, alpha=False).pixel(2, 2)
            check("background colour behind page 1", px != (255, 255, 255), str(px))
            check("body text still present", "body text" in d[0].get_text())
    f = folder / "design_removed.pdf"
    if not missing("removal file", f):
        with fitz.open(f) as d:
            c = count_marks(d)
            check("removal left no Monograph marks", sum(c.values()) == 0, str(c))
            check("body text kept after removal", all("body text" in p.get_text() for p in d))
    f = folder / "redacted.pdf"
    if not missing("redacted file", f):
        with fitz.open(f) as d:
            check("secret gone from page text", all(SECRET not in p.get_text() for p in d))
            check("form field under the mark removed", not any(w.field_value == SECRET for p in d for w in p.widgets()))
            check("unrelated text kept", "Unrelated line stays" in d[0].get_text())
            check("bookmark scrubbed", all(SECRET not in t for _l, t, _p in d.get_toc()), str(d.get_toc()))
            check("properties scrubbed", SECRET not in (d.metadata.get("title") or ""), d.metadata.get("title"))
            check("named attachment removed", not any(SECRET in n for n in d.embfile_names()), str(d.embfile_names()))
        check("secret absent from objects and page streams", SECRET.encode() not in all_bytes(f))
    f = folder / "merged.pdf"
    if not missing("merged file", f):
        with fitz.open(f) as d:
            check("merged page count", d.page_count == 5, str(d.page_count))
            toc = d.get_toc()
            check("merged bookmarks kept and re-pointed",
                  toc == [[1, "merge_A start", 1], [2, "merge_A detail", 3], [1, "merge_B start", 4],
                          [2, "merge_B detail", 5]], str(toc))
    f = folder / "photo.pdf"
    if not missing("images-to-pdf file", f):
        with fitz.open(f) as d:
            p = d[0]
            check("photo page upright (portrait)", p.rect.width < p.rect.height or p.rotation in (90, 270),
                  f"{p.rect} rot {p.rotation}")
        b = f.read_bytes()
        check("no EXIF/GPS/camera data in PDF", b"PhoneMakerXYZ" not in b and b"Exif\x00\x00" not in b)
    width = max(len(r["check"]) for r in results) if results else 10
    for r in results:
        print(f"{r['status']:8s} {r['check']:{width}s} {r['detail']}")
    print("summary:", {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "MISSING")})
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
