"""Capture the main window, toolbars, side panels, menus and context toolbars for a visual review.

Usage (from the project folder):
    env\\Scripts\\python.exe scripts\\audit\\ui_visual_capture.py <out_dir> [--theme light|dark|both]

Run it on the real display (QT_QPA_PLATFORM unset on Windows) to see icons at the display's own scaling,
or set QT_SCALE_FACTOR (e.g. 1.25, 1.5, 1.75) to emulate other scalings. Uses throw-away settings
(your own settings and recent files are never touched) and the template PDFs in
tests/fixtures/templates/pdf. Writes PNG captures made by Qt itself (no screen recording, so other
windows never appear) and ``captures.json`` with each capture's device-pixel ratio.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(tempfile.mkdtemp(prefix="monograph_ui_capture_"))
os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(WORK / "userdata")
os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] = str(WORK / "runtime")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QWidget  # noqa: E402

TEMPLATES = ROOT / "tests" / "fixtures" / "templates" / "pdf"


def main(argv: list[str]) -> int:
    out = Path(argv[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    themes = ["light", "dark"]
    if "--theme" in argv:
        t = argv[argv.index("--theme") + 1]
        themes = ["light", "dark"] if t == "both" else [t]

    from core.editing.geometry import Rect
    from ui.main_window import MainWindow, create_application

    app = create_application(["ui-visual-capture"])
    records: list[dict] = []

    def pump(n: int = 12) -> None:
        for _ in range(n):
            app.processEvents()

    def open_doc(w, path) -> None:
        if w._edit is not None:  # noqa: SLF001 — the capture's own edits are throw-away: no "Save changes?" prompt
            w._edit.dirty = False  # noqa: SLF001
        w.open_path(path)
        pump(40)

    def shot(widget: QWidget, name: str) -> None:
        pump()
        pm = widget.grab()
        path = out / f"{len(records):03d}-{name}.png"
        pm.save(str(path))
        records.append({"file": path.name, "widget": type(widget).__name__, "logical": [widget.width(), widget.height()],
                        "dpr": pm.devicePixelRatio()})

    for theme in themes:
        w = MainWindow()
        w.resize(1366, 820)
        w._set_theme(theme)  # noqa: SLF001
        w.show()
        pump(30)
        shot(w, f"{theme}-start")
        work = WORK / theme
        work.mkdir(exist_ok=True)
        docs = {}
        for name in ("lab_protocol_figures_tables", "review_comment_threads", "application_form_acroform",
                     "slide_deck_mixed_aspect"):
            docs[name] = work / f"{name}.pdf"
            shutil.copy(TEMPLATES / f"{name}.pdf", docs[name])

        open_doc(w, docs["lab_protocol_figures_tables"])
        shot(w, f"{theme}-document")
        shot(w._main_bar, f"{theme}-main-toolbar")  # noqa: SLF001
        shot(w._left, f"{theme}-left-panel")  # noqa: SLF001
        if w._inspector.isVisible():  # noqa: SLF001
            shot(w._inspector, f"{theme}-right-panel")  # noqa: SLF001
        shot(w.statusBar(), f"{theme}-status")
        edit = w._edit  # noqa: SLF001
        box = edit.create_text_box(0, Rect(72, 420, 260, 40), text="Context toolbar check", auto_match=False)
        edit.selection = [box.object_id if hasattr(box, "object_id") else box]
        w._update_context_toolbar()  # noqa: SLF001
        w._refresh_inspector()  # noqa: SLF001
        shot(w._context_bar, f"{theme}-context-text")  # noqa: SLF001
        if w._inspector.isVisible():  # noqa: SLF001
            shot(w._inspector, f"{theme}-right-panel-text")  # noqa: SLF001
        edit.selection = []
        w._update_context_toolbar()  # noqa: SLF001
        shot(w._context_bar, f"{theme}-context-page")  # noqa: SLF001

        # every menu, opened for real
        for act in w.menuBar().actions():
            menu = act.menu()
            if not isinstance(menu, QMenu):
                continue
            geo = w.menuBar().actionGeometry(act)
            menu.popup(w.menuBar().mapToGlobal(QPoint(geo.x(), geo.bottom())))
            pump(10)
            shot(menu, f"{theme}-menu-{act.text().replace('&', '').lower()}")
            menu.hide()

        # left panel tabs
        for i in range(w._left.count()):  # noqa: SLF001
            if not w._left.isTabVisible(i):  # noqa: SLF001 — e.g. Files when there are no attachments
                continue
            w._left.setCurrentIndex(i)  # noqa: SLF001
            shot(w._left, f"{theme}-left-tab{i}")  # noqa: SLF001

        open_doc(w, docs["review_comment_threads"])
        shot(w, f"{theme}-comments-doc")
        open_doc(w, docs["application_form_acroform"])
        fields = list(w._edit.fields.values())  # noqa: SLF001
        if fields:
            w._edit.field_selection = [fields[0].object_id]  # noqa: SLF001
            w._update_context_toolbar()  # noqa: SLF001
            shot(w._context_bar, f"{theme}-context-field")  # noqa: SLF001
        w.resize(1100, 720)
        pump(20)
        shot(w, f"{theme}-narrow-window")
        if w._edit is not None:  # noqa: SLF001
            w._edit.dirty = False  # noqa: SLF001
        w.close_document(save_session=False)
        w.close()
        pump()

    (out / "captures.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    print(f"{len(records)} captures written to {out}")
    QTimer.singleShot(0, app.quit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
