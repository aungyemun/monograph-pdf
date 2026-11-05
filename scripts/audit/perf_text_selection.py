"""Measure the Select Text tool on generated documents (0.6.0 audit; synthetic documents only).

    python scripts/audit/perf_text_selection.py <out.json> [--pages 10,100,500,1000]

For each document (text-heavy and image-heavy, N pages): open time, private/resident memory before
and after, the first selection on a page (text extraction + hit testing), Ctrl+A + copy of one page,
a drag over 3 pages, repaint time of the visible view with and without a selection, and the number of
pages extracted (the cache must not read the whole document). Runs offscreen with isolated settings.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
WORK = Path(tempfile.mkdtemp(prefix="mpdf_perf_sel_"))
for n in ("RUNTIME_DIR", "UPDATES_DIR", "DIAGNOSTICS_DIR", "USER_DATA_DIR"):
    os.environ["MONOGRAPH_PDF_" + n] = str(WORK / n.lower())
os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

import fitz  # noqa: E402


def memory_mb() -> float:
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return float("nan")
            return pmc.PagefileUsage / 2**20  # private bytes
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:  # noqa: BLE001
        pass
    return float("nan")


LOREM = ("Monograph PDF selection benchmark text with ordinary English words and numbers 12345, "
         "and a little Japanese 日本語のテキスト as well. ")


def make_doc(path: Path, pages: int, kind: str) -> Path:
    d = fitz.open()
    pix, xref = None, 0
    if kind == "image":
        # a noisy 1200 x 1600 picture (5.8 MB decoded) shown on every page: each page must decode it
        pix = fitz.Pixmap(fitz.csRGB, 1200, 1600, os.urandom(1200 * 1600 * 3), False)
    for i in range(pages):
        page = d.new_page(width=595, height=842)
        if kind == "image":
            if xref:
                page.insert_image(page.rect, xref=xref)
            else:
                xref = page.insert_image(page.rect, pixmap=pix)
            page.insert_text((60, 60), f"Image page {i + 1} caption", fontsize=12, fontname="japan")
        else:
            page.insert_textbox(fitz.Rect(50, 50, 545, 800), (LOREM * 22)[:3500], fontsize=9, fontname="japan")
    d.save(path, garbage=3, deflate=True)
    d.close()
    return path


def main() -> int:
    out = Path(sys.argv[1])
    counts = [10, 100, 500, 1000]
    if "--pages" in sys.argv:
        counts = [int(x) for x in sys.argv[sys.argv.index("--pages") + 1].split(",")]
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.editing.geometry import Point
    from ui.main_window import MainWindow, create_application

    app = create_application(["perf-select"])
    results = []
    for kind in ("text", "image"):
        for n in counts:
            src = make_doc(WORK / f"{kind}_{n}.pdf", n, kind)
            w = MainWindow()
            w.resize(1300, 950)
            w.show()
            app.processEvents()
            m0 = memory_mb()
            t = time.perf_counter()
            assert w.open_path(src)
            for _ in range(5):
                app.processEvents()
            t_open = time.perf_counter() - t
            w.act_text_select_tool.trigger()
            inner = w._canvas._canvas  # noqa: SLF001
            sel = inner.text_select
            mid = n // 2
            w._canvas.go_to_page(mid)  # noqa: SLF001
            for _ in range(5):
                app.processEvents()

            def send(kind_, p, held):
                ev = QMouseEvent(kind_, QPointF(p), inner.mapToGlobal(QPointF(p)), Qt.MouseButton.LeftButton, held,
                                 Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(inner, ev)

            a = inner.pdf_to_widget_f(mid, Point(60, 70))
            b = inner.pdf_to_widget_f(mid, Point(400, 300))
            t = time.perf_counter()
            send(QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton)
            t_first = time.perf_counter() - t
            moves = []
            for k in range(1, 21):
                p = QPointF(a.x() + (b.x() - a.x()) * k / 20, a.y() + (b.y() - a.y()) * k / 20)
                t = time.perf_counter()
                send(QEvent.Type.MouseMove, p, Qt.MouseButton.LeftButton)
                moves.append(time.perf_counter() - t)
            send(QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)
            # drag over three pages
            last = min(n - 1, mid + 2)
            c = inner.pdf_to_widget_f(last, Point(400, 300))
            t = time.perf_counter()
            send(QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton)
            send(QEvent.Type.MouseMove, c, Qt.MouseButton.LeftButton)
            send(QEvent.Type.MouseButtonRelease, c, Qt.MouseButton.NoButton)
            t_multi = time.perf_counter() - t
            t = time.perf_counter()
            text_multi = sel.selected_text()
            t_multi_text = time.perf_counter() - t
            # repaint of the visible view with the selection
            t = time.perf_counter()
            inner.repaint()
            t_paint_sel = time.perf_counter() - t
            sel.clear()
            t = time.perf_counter()
            inner.repaint()
            t_paint_plain = time.perf_counter() - t
            # Ctrl+A + Ctrl+C of one page
            t = time.perf_counter()
            w._select_all()  # noqa: SLF001
            w._copy()  # noqa: SLF001
            t_copy = time.perf_counter() - t
            copied = len(QApplication.clipboard().text())
            m1 = memory_mb()
            results.append({
                "kind": kind, "pages": n, "file_mb": round(src.stat().st_size / 2**20, 1),
                "open_s": round(t_open, 3), "first_press_ms": round(t_first * 1000, 1),
                "drag_move_ms_median": round(sorted(moves)[len(moves) // 2] * 1000, 2),
                "drag_move_ms_max": round(max(moves) * 1000, 2),
                "drag_3_pages_ms": round(t_multi * 1000, 1), "text_3_pages_ms": round(t_multi_text * 1000, 1),
                "chars_3_pages": len(text_multi), "repaint_with_selection_ms": round(t_paint_sel * 1000, 1),
                "repaint_without_ms": round(t_paint_plain * 1000, 1), "select_page_and_copy_ms": round(t_copy * 1000, 1),
                "chars_copied": copied, "pages_extracted": sel.cache.extractions, "cached_pages": len(sel.cache),
                "memory_before_mb": round(m0, 1), "memory_after_mb": round(m1, 1),
                "dirty": bool(w._edit.dirty),  # noqa: SLF001
            })
            print(json.dumps(results[-1]), flush=True)
            w._edit.dirty = False  # noqa: SLF001
            w.close_document(save_session=False)
            w.close()
            w.deleteLater()
            app.processEvents()
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
