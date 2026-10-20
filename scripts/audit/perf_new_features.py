"""Timing of this audit's new/changed operations on a 200-page document (developer harness).

Usage: python scripts/audit/perf_new_features.py <out.json> [repeats]
Median and worst of ``repeats`` runs after one warm-up. Synthetic input only.
"""
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402
from PIL import Image  # noqa: E402

from core.convert.images_to_pdf import images_to_pdf  # noqa: E402
from core.convert.page_marks import (  # noqa: E402
    BackgroundSpec, HeaderFooterSpec, WatermarkSpec, apply_page_marks, remove_page_marks, render_preview)
from core.document import open_document  # noqa: E402
from core.organize.merge import MergeJob, combine_to_pdf  # noqa: E402
from core.redaction import apply_redactions_report, mark_text  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="monograph_perf_new_"))
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 else 3


def make(n: int, path: Path) -> Path:
    d = fitz.open()
    for i in range(n):
        p = d.new_page()
        p.insert_text((72, 100), f"Page {i + 1} SECRET-TERM body text " * 2, fontsize=11)
        if i % 3 == 0:
            p.set_rotation(90)
    d.set_toc([[1, f"Chapter {k + 1}", k * 20 + 1] for k in range(n // 20)])
    d.save(path)
    return path


def measure(name, fn, results):
    fn()  # warm-up
    times = []
    for _ in range(REPEATS):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    results[name] = {"median_ms": round(statistics.median(times), 1), "worst_ms": round(max(times), 1), "runs": REPEATS}
    print(f"{name:55s} median {results[name]['median_ms']:9.1f} ms   worst {results[name]['worst_ms']:9.1f} ms")


def main() -> None:
    out = Path(sys.argv[1])
    results: dict = {}
    big = make(200, work / "big.pdf")
    small = make(3, work / "small.pdf")
    logo = work / "logo.png"
    Image.new("RGBA", (600, 300), (20, 90, 200, 255)).save(logo)
    doc = open_document(big)
    hf = HeaderFooterSpec(header_center="Report {date}", footer_right="{page} / {total}")
    measure("header+footer, 200 pages", lambda: apply_page_marks(doc, work / "hf.pdf", header_footer=hf), results)
    measure("text watermark, 200 pages", lambda: apply_page_marks(doc, work / "wm.pdf", watermark=WatermarkSpec(text="CONFIDENTIAL")), results)
    measure("picture watermark behind, 200 pages", lambda: apply_page_marks(
        doc, work / "wmi.pdf", watermark=WatermarkSpec(image_path=logo, behind=True)), results)
    measure("background colour, 200 pages", lambda: apply_page_marks(doc, work / "bg.pdf", background=BackgroundSpec()), results)
    measure("live preview render of one page (40 dpi)", lambda: render_preview(doc, 7, dpi=40, header_footer=hf,
                                                                             watermark=WatermarkSpec(text="X")), results)
    doc.close()
    marked = open_document(work / "hf.pdf")
    measure("remove header/footer, 200 pages", lambda: remove_page_marks(marked, work / "plain.pdf"), results)
    marked.close()

    def merge():
        job = MergeJob()
        job.add_path(big)
        job.add_path(small)
        combine_to_pdf(job, work / "merged.pdf")
    measure("merge 200 + 3 pages with bookmarks", merge, results)

    def redact():
        d = open_document(big)
        try:
            for i in range(d.page_count):
                mark_text(d, i, "SECRET-TERM")
            apply_redactions_report(d, work / "red.pdf")
        finally:
            d.close()
    measure("mark text on 200 pages + apply + residue scan", redact, results)
    photos = []
    for k in range(10):
        p = work / f"p{k}.jpg"
        ex = Image.Exif()
        ex[0x0112] = 6
        Image.new("RGB", (2000, 1500), (200, 100, 50)).save(p, exif=ex.tobytes(), quality=90)
        photos.append(p)
    measure("images to PDF, 10 photos 2000x1500 (metadata removed)", lambda: images_to_pdf(photos, work / "ph.pdf"), results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
