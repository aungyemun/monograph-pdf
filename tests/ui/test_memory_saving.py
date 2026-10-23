"""Memory-saving mode: a few seconds after the window is minimized, rendered pages, tiles, pictures
and thumbnails are released (the page in view is kept so restoring is instant), MuPDF's store is
emptied and Windows efficiency mode is switched on — but not while a background job runs. Restoring
the window switches efficiency mode off and draws again what is needed. Thumbnails far from view are
also released during normal use, so a very long document does not keep every thumbnail."""

from __future__ import annotations

import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-memory-saving"])
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    d.save(src)
    d.close()
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    assert w.open_path(src)
    qtbot.wait(300)
    yield w
    w.close_document(save_session=False)
    w.close()


@pytest.fixture
def calls(monkeypatch):
    from core import memory_saver

    seen: list = []
    monkeypatch.setattr(memory_saver, "set_efficiency_mode", lambda on: seen.append(("eco", on)) or True)
    monkeypatch.setattr(memory_saver, "trim_working_set", lambda: seen.append(("trim",)) or True)
    return seen


def test_minimized_window_releases_memory_and_restores(win, qtbot, monkeypatch, calls):
    from core import memory_saver

    inner = win._canvas._canvas  # noqa: SLF001
    inner._render_visible()  # noqa: SLF001
    assert len(inner._cache) >= 1  # noqa: SLF001
    monkeypatch.setattr(memory_saver, "background_work_running", lambda: False)
    monkeypatch.setattr(win, "isMinimized", lambda: True)
    win._enter_memory_saving()  # noqa: SLF001 — what the timer does a few seconds after minimizing
    assert len(inner._cache) <= 1 and not inner._tiles, "only the page in view is kept"  # noqa: SLF001
    thumbs = win._left.thumbs  # noqa: SLF001
    assert all(thumbs.item(i).icon().isNull() for i in range(thumbs.count()))
    assert ("eco", True) in calls and ("trim",) in calls
    monkeypatch.setattr(win, "isMinimized", lambda: False)
    win._leave_memory_saving()  # noqa: SLF001
    assert ("eco", False) in calls
    qtbot.waitUntil(lambda: any(not thumbs.item(i).icon().isNull() for i in range(thumbs.count())), timeout=5000)


def test_no_efficiency_mode_while_a_background_job_runs(win, monkeypatch, calls):
    from core import memory_saver

    monkeypatch.setattr(memory_saver, "background_work_running", lambda: True)
    monkeypatch.setattr(win, "isMinimized", lambda: True)
    win._enter_memory_saving()  # noqa: SLF001
    assert ("eco", True) not in calls, "a running OCR or conversion must not be slowed down"
    assert win._eco_timer.isActive(), "checks again later"  # noqa: SLF001


def test_quick_minimize_and_restore_changes_nothing(win, qtbot, calls):
    win.showMinimized()
    qtbot.wait(50)
    win.showNormal()
    qtbot.wait(50)
    assert not getattr(win, "_eco_active", False) and calls == []


def test_far_away_thumbnails_are_released_in_long_documents(qtbot, monkeypatch):
    from PySide6.QtGui import QIcon, QPixmap

    import ui.thumbnail_panel as tp

    panel = tp.ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.resize(160, 600)
    panel.show()
    for i in range(400):
        item = tp.QListWidgetItem(str(i + 1))
        item.setSizeHint(tp.QSize(132, 186))
        pm = QPixmap(20, 28)
        pm.fill()
        item.setIcon(QIcon(pm))
        panel.addItem(item)
    panel._limit_images()  # noqa: SLF001
    loaded = sum(1 for i in range(panel.count()) if not panel.item(i).icon().isNull())
    assert 0 < loaded <= tp.MAX_THUMB_IMAGES
    assert not panel.item(0).icon().isNull(), "the visible thumbnails stay"


def test_memory_helpers_never_raise():
    from core import memory_saver

    memory_saver.release_library_memory()
    assert isinstance(memory_saver.background_work_running(), bool)
    ws = memory_saver.working_set_bytes()
    assert ws is None or ws > 0
