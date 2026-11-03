"""Live native-UI runs: the GUI tests on the real window system (Cocoa, Windows, X11/Wayland).

Off unless ``MONOGRAPH_PDF_LIVE_UI=1`` (CI and normal runs use the offscreen platform, where the app
itself skips modal questions). In a live run the app asks real questions — unsaved changes, "that is
the open document itself", passwords — and nobody is at the keyboard. This plugin:

* photographs every modal dialog still unanswered after 2 s (message boxes) or 6 s (other dialogs;
  progress dialogs are left alone) — tests answer their own dialogs sooner — with ``QWidget.grab``
  (only Monograph PDF's own windows, never the rest of the screen), logs its title / text / buttons,
  and answers it with the choice that writes nothing: Don't Save / Discard, else Cancel / No, else
  the only button (OK);
* photographs the app's visible windows after each test, for visual inspection.

Output folder: ``MONOGRAPH_PDF_LIVE_UI_DIR`` (``dialogs.jsonl``, ``*.png``).

    MONOGRAPH_PDF_LIVE_UI=1 MONOGRAPH_PDF_LIVE_UI_DIR=out QT_QPA_PLATFORM=cocoa MONOGRAPH_PDF_HEADLESS=0 \\
        env/bin/python -m pytest tests/ui
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

ENABLED = os.environ.get("MONOGRAPH_PDF_LIVE_UI") == "1"
_state = {"test": "", "count": 0}


def _out() -> Path:
    path = Path(os.environ.get("MONOGRAPH_PDF_LIVE_UI_DIR") or "tests/outputs/live_ui")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[-120:]


def _choose(box):
    """The answer that writes nothing and keeps every change: Don't Save > Cancel/No > single button."""
    from PySide6.QtWidgets import QMessageBox

    buttons = box.buttons()
    role = box.buttonRole
    for wanted in (QMessageBox.ButtonRole.DestructiveRole, QMessageBox.ButtonRole.RejectRole,
                   QMessageBox.ButtonRole.NoRole):
        for b in buttons:
            if role(b) == wanted:
                return b
    return buttons[0] if len(buttons) == 1 else None


def _answer_modal() -> None:
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QProgressDialog

    w = QApplication.activeModalWidget()
    if w is None or not w.isVisible() or w.property("liveUiSeen"):
        return
    # Progress dialogs end by themselves; tests answer their own dialogs within milliseconds —
    # step in only for a dialog nobody has answered for a while (a real person would be asked).
    if isinstance(w, QProgressDialog) or "Progress" in type(w).__name__:
        return
    first = w.property("liveUiFirstSeen")
    if first is None:
        w.setProperty("liveUiFirstSeen", time.monotonic())
        return
    if time.monotonic() - float(first) < (2.0 if isinstance(w, QMessageBox) else 6.0):
        return
    w.setProperty("liveUiSeen", True)
    _state["count"] += 1
    shot = f"{_state['count']:04d}_dialog_{_slug(_state['test'])}.png"
    w.grab().save(str(_out() / shot))
    entry = {"test": _state["test"], "class": type(w).__name__, "title": w.windowTitle(), "shot": shot}
    if isinstance(w, QMessageBox):
        chosen = _choose(w)
        entry.update(text=w.text(), informative=w.informativeText(),
                     buttons=[b.text() for b in w.buttons()], chosen=chosen.text() if chosen else "reject()")
        if chosen is not None:
            chosen.click()
        else:
            w.reject()
    elif isinstance(w, QDialog):
        entry["chosen"] = "reject()"
        w.reject()
    else:
        entry["chosen"] = "close()"
        w.close()
    with open(_out() / "dialogs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@pytest.fixture(autouse=True)
def _live_ui_dialogs(request):
    if not ENABLED:
        yield
        return
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    _state["test"] = request.node.nodeid
    timer = None
    if QApplication.instance() is not None:
        timer = QTimer()
        timer.setInterval(250)
        timer.timeout.connect(_answer_modal)
        timer.start()
    request.node._live_ui_timer = timer  # noqa: SLF001 — started late if the test creates the app
    yield
    if timer is not None:
        timer.stop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if ENABLED and getattr(item, "_live_ui_timer", 1) is None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            timer = QTimer()
            timer.setInterval(250)
            timer.timeout.connect(_answer_modal)
            timer.start()
            item._live_ui_timer = timer  # noqa: SLF001
    yield
    if not ENABLED:
        return
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    app.processEvents()
    for i, w in enumerate(app.topLevelWidgets()):
        if w.isVisible() and w.width() > 200 and w.height() > 150:
            _state["count"] += 1
            w.grab().save(str(_out() / f"{_state['count']:04d}_window{i}_{_slug(item.nodeid)}.png"))
