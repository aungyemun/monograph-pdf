"""Performance smoke: startup, large-ish PDF open, thumbs, zoom/pan, close release."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
fitz = pytest.importorskip("fitz")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
OUT = Path(__file__).resolve().parents[1] / "outputs" / "generated"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()
    OUT.mkdir(parents=True, exist_ok=True)


def _make_multipage_pdf(path: Path, pages: int = 40) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Perf page {i + 1}", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def test_startup_main_window_under_budget(qtbot):
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-perf-startup"])
    t0 = time.perf_counter()
    window = MainWindow()
    qtbot.addWidget(window)
    elapsed = time.perf_counter() - t0
    # Offscreen CI budget — fail loudly if shell construction regresses badly
    assert elapsed < 8.0, f"MainWindow startup too slow: {elapsed:.2f}s"
    window.close()


def test_open_multipage_zoom_close_releases_cache(qtbot, tmp_path):
    from ui.main_window import MainWindow, create_application
    from ui.pdf_canvas import ZoomMode

    pdf = _make_multipage_pdf(tmp_path / "perf40.pdf", pages=40)
    create_application(["monograph-pdf-perf-open"])
    window = MainWindow()
    qtbot.addWidget(window)

    t0 = time.perf_counter()
    assert window.open_path(pdf)
    open_elapsed = time.perf_counter() - t0
    assert open_elapsed < 12.0, f"Open 40-page PDF too slow: {open_elapsed:.2f}s"

    canvas = window._canvas  # noqa: SLF001
    t1 = time.perf_counter()
    canvas.set_zoom_mode(ZoomMode.ACTUAL_SIZE)
    canvas.zoom_in()
    canvas.zoom_out()
    canvas.go_to_page(min(20, window._document.page_count - 1))  # noqa: SLF001
    qtbot.wait(50)
    zoom_elapsed = time.perf_counter() - t1
    assert zoom_elapsed < 6.0, f"Zoom/pan smoke too slow: {zoom_elapsed:.2f}s"

    # Thumbnails scheduled without blocking UI thread excessively
    left = window._left  # noqa: SLF001
    assert left.thumbs.count() == 40
    t2 = time.perf_counter()
    left.thumbs._schedule_visible()  # noqa: SLF001
    qtbot.wait(100)
    thumb_elapsed = time.perf_counter() - t2
    assert thumb_elapsed < 3.0

    # Close must clear render cache on the inner canvas widget
    cache = canvas._canvas._cache  # noqa: SLF001
    window.close_document(save_session=False)
    assert len(cache) == 0
    assert window._document is None  # noqa: SLF001
    window.close()


def test_live_text_edit_undo_responsive(qtbot, tmp_path):
    from core.editing.geometry import Rect
    from ui.main_window import MainWindow, create_application

    src = tmp_path / "edit_perf.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    create_application(["monograph-pdf-perf-edit"])
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.open_path(src)

    t0 = time.perf_counter()
    for i in range(25):
        window._edit.create_text_box(0, Rect(40, 40 + i * 4, 100, 24), text=f"b{i}")  # noqa: SLF001
    for _ in range(25):
        window._edit.undo()  # noqa: SLF001
    elapsed = time.perf_counter() - t0
    assert elapsed < 4.0, f"Live text create/undo too slow: {elapsed:.2f}s"
    window.close_document(save_session=False)
    window.close()
