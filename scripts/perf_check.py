"""UI speed and memory check (Windows): is Monograph PDF smooth on an ordinary 8 GB PC?

Runs the real window (not offscreen) with generated documents in a temporary folder and a
temporary settings folder (your own settings, recent files and documents are never touched):

* a 300-page text document and a 40-page scanned-style document (one 300-dpi picture per page)
* start-up, opening, scrolling every page, zooming to 200 % and 400 %, scrolling the thumbnails
* memory (working set) after each step, the peak, and after minimizing (memory-saving mode)

Usage::

    python scripts/perf_check.py [--out tests/outputs/logs/perf_check.json]

Frame budget: 16.7 ms is one frame at 60 Hz; under 50 ms feels immediate; over 100 ms is visible lag.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _make_docs(folder: Path) -> tuple[Path, Path]:
    import io

    import fitz
    from PIL import Image, ImageDraw

    text = folder / "text_300_pages.pdf"
    d = fitz.open()
    para = ("Monograph PDF performance check. " * 12).strip()
    for i in range(300):
        page = d.new_page(width=595, height=842)
        page.insert_text((72, 60), f"Page {i + 1}", fontsize=16)
        page.insert_textbox(fitz.Rect(72, 90, 523, 780), "\n\n".join([para] * 6), fontsize=10)
        page.draw_rect(fitz.Rect(72, 790, 523, 800), color=(0.2, 0.3, 0.6), fill=(0.85, 0.9, 1))
    d.save(text, garbage=3, deflate=True)
    d.close()

    scan = folder / "scan_40_pages.pdf"
    d = fitz.open()
    for i in range(40):
        im = Image.new("RGB", (2480, 3508), (250, 249, 245))
        draw = ImageDraw.Draw(im)
        for y in range(200, 3300, 60):
            draw.line((200, y, 2280, y), fill=(40, 40, 40), width=6)
        draw.rectangle((200, 100, 1400, 180), fill=(30, 30, 30))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        page = d.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())
    d.save(scan, garbage=3, deflate=True)
    d.close()
    return text, scan


def _mb(n: int | None) -> float | None:
    return None if n is None else round(n / 1024 / 1024, 1)


def _peak_mb() -> float | None:
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes

    class C(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
                   [(f"x{i}", ctypes.c_size_t) for i in range(6)]

    c = C()
    c.cb = ctypes.sizeof(c)
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.WinDLL("psapi").GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()), ctypes.byref(c), c.cb)
    return _mb(c.PeakWorkingSetSize)


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {}
    s = sorted(samples)
    return {"n": len(s), "median_ms": round(statistics.median(s), 1),
            "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 1), "max_ms": round(s[-1], 1),
            "over_100ms": sum(1 for x in s if x > 100)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "tests" / "outputs" / "logs" / "perf_check.json"))
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="mpdf_perf_"))
    os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(work / "settings")
    os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"  # never hand over to a copy the user has open
    result: dict = {"documents": {}}

    t0 = time.perf_counter()
    from core.memory_saver import working_set_bytes
    from ui.main_window import MainWindow, create_application

    app = create_application(["monograph-pdf-perf"])
    from PySide6.QtWidgets import QApplication

    def pump(ms: float = 0) -> None:
        end = time.perf_counter() + ms / 1000
        while True:
            QApplication.processEvents()
            if time.perf_counter() >= end:
                break
            time.sleep(0.005)

    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    pump(300)
    result["startup_to_window_s"] = round(time.perf_counter() - t0, 2)
    result["memory_idle_mb"] = _mb(working_set_bytes())
    text, scan = _make_docs(work)

    canvas = w._canvas  # noqa: SLF001
    bar = canvas.verticalScrollBar()
    for label, path in (("text_300_pages", text), ("scan_40_pages", scan)):
        r: dict = {}
        t = time.perf_counter()
        assert w.open_path(path)
        pump(50)
        r["open_s"] = round(time.perf_counter() - t, 2)
        r["memory_after_open_mb"] = _mb(working_set_bytes())

        def scroll_all(step: int, limit: int | None = None) -> list[float]:
            times = []
            bar.setValue(0)
            pump(100)
            n = 0
            while bar.value() < bar.maximum() and (limit is None or n < limit):
                t1 = time.perf_counter()
                bar.setValue(min(bar.maximum(), bar.value() + step))
                canvas._canvas._render_visible()  # noqa: SLF001 — what the idle render does
                QApplication.processEvents()
                times.append((time.perf_counter() - t1) * 1000)
                n += 1
            return times

        canvas.set_zoom_mode(type(canvas._canvas.zoom_mode).FIT_WIDTH)  # noqa: SLF001
        pump(200)
        r["scroll_fit_width"] = _stats(scroll_all(max(40, bar.pageStep() // 2)))
        r["memory_after_scroll_mb"] = _mb(working_set_bytes())
        for zoom in (2.0, 4.0):
            t = time.perf_counter()
            canvas.set_manual_zoom(zoom)
            pump(0)
            canvas._canvas._render_visible()  # noqa: SLF001
            QApplication.processEvents()
            r[f"zoom_{int(zoom * 100)}_switch_ms"] = round((time.perf_counter() - t) * 1000, 1)
            r[f"scroll_zoom_{int(zoom * 100)}"] = _stats(scroll_all(max(40, bar.pageStep() // 2), limit=80))
            r[f"memory_zoom_{int(zoom * 100)}_mb"] = _mb(working_set_bytes())
        thumbs = w._left.thumbs  # noqa: SLF001
        tb = thumbs.verticalScrollBar()
        times = []
        tb.setValue(0)
        while tb.value() < tb.maximum():
            t1 = time.perf_counter()
            tb.setValue(min(tb.maximum(), tb.value() + tb.pageStep()))
            QApplication.processEvents()
            times.append((time.perf_counter() - t1) * 1000)
        pump(1500)
        r["thumbnail_scroll"] = _stats(times)
        r["thumbnails_in_memory"] = sum(1 for i in range(thumbs.count()) if not thumbs.item(i).icon().isNull())
        r["memory_before_minimize_mb"] = _mb(working_set_bytes())
        w.showMinimized()
        pump(w.ECO_DELAY_MS + 1200)
        r["memory_minimized_mb"] = _mb(working_set_bytes())
        r["efficiency_mode_on"] = bool(getattr(w, "_eco_qos", False))
        t = time.perf_counter()
        w.showNormal()
        w.activateWindow()
        pump(0)
        canvas._canvas._render_visible()  # noqa: SLF001
        QApplication.processEvents()
        r["restore_ms"] = round((time.perf_counter() - t) * 1000, 1)
        pump(300)
        r["memory_after_restore_mb"] = _mb(working_set_bytes())
        result["documents"][label] = r
        w.close_document(save_session=False)
        pump(200)
    result["peak_memory_mb"] = _peak_mb()
    w.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
