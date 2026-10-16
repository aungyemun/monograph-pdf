"""Measure cold startup phases (dev entry). Writes tests/outputs/logs/startup-*.json."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
os.environ["MONOGRAPH_PDF_STARTUP_TIMING"] = "1"


def main() -> int:
    from core.startup_timing import mark, reset, snapshot, write_log

    reset()
    mark("measure_begin")
    from app.bootstrap import main as boot_main
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    # Run bootstrap path pieces mirroring production, then quit after first frame
    def _run() -> None:
        # Invoke same entry as packaged app but quit quickly
        argv = ["monograph-pdf-startup-measure"]
        from app.paths import ensure_runtime_layout
        from app import __version__
        from core.product_meta import COPYRIGHT_OWNER, PRODUCT_NAME
        from core.user_prefs import UserPreferences
        from ui.branding import apply_application_icon
        from ui.main_window import MainWindow, create_application
        from ui.theme import apply_theme
        from core.startup_timing import mark

        mark("measure_imports_done")
        ensure_runtime_layout()
        app = create_application(argv)
        app.setApplicationName(PRODUCT_NAME)
        app.setOrganizationName(COPYRIGHT_OWNER)
        app.setApplicationVersion(__version__)
        apply_theme(app, UserPreferences.load().theme)
        apply_application_icon(app)
        mark("measure_app_ready")
        win = MainWindow()
        mark("measure_window")
        win.show()
        app.processEvents()
        mark("first_visible")
        path = write_log(tag="startup")
        print(snapshot())
        if path:
            print(path)
        win.close()
        app.quit()

    # Avoid full boot_main deferred warm to isolate first paint
    _run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
