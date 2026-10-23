"""Application bootstrap: show UI early; defer nonessential work after first frame."""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path when run from source. The built app imports only the modules
# bundled inside it, never .py files placed beside MonographPDF.exe.
_ROOT = Path(__file__).resolve().parents[1]
if not getattr(sys, "frozen", False) and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main(argv: list[str] | None = None) -> int:
    """Start the Qt application and show the main window. Returns process exit code."""
    argv = list(sys.argv if argv is None else argv)
    # The installer passes --runtime-dir so its self-check never writes into Program Files.
    if "--runtime-dir" in argv:
        i = argv.index("--runtime-dir")
        if i + 1 < len(argv):
            from core import app_env

            app_env.set("RUNTIME_DIR", argv[i + 1])
            del argv[i : i + 2]
    if "--smoke-test" in argv:
        from app.smoke_test import run_smoke_test

        return run_smoke_test(argv)
    # The update helper restarts the new version with --update-finished <id>; the result itself is
    # read from the update status folder, so the argument only has to be removed here.
    if "--update-finished" in argv:
        i = argv.index("--update-finished")
        del argv[i : i + 2]

    # One Monograph PDF per session: a second start passes its file to the running window and exits
    # (before Qt is loaded, so it is quick and uses almost no memory).
    from app import single_instance

    primary = single_instance.is_disabled(argv) or single_instance.acquire()
    if not primary:
        return single_instance.hand_over(argv)
    if "--new-instance" in argv:
        argv.remove("--new-instance")

    from core.startup_timing import mark, reset, write_log

    reset()
    mark("process_entry")

    from app.paths import ensure_runtime_layout
    from app import __version__

    mark("paths_version")

    # Minimal UI stack first — heavy PDF/OCR/convert imports deferred after show.
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QLabel

    from app.qt_app import create_application
    from core.product_meta import COPYRIGHT_OWNER, PRODUCT_NAME
    from core.user_prefs import UserPreferences
    from ui.branding import apply_application_icon
    from ui.theme import apply_theme

    mark("pyside_import")

    ensure_runtime_layout()
    mark("runtime_layout")

    # First start after replacing an earlier internal build (<= 0.1.5): copy this user's settings,
    # recent files and recovery sessions (never deletes the earlier internal AppData folders)
    from core.legacy_migration import migrate_at_startup

    migrate_at_startup()
    mark("legacy_migration")

    # Problem reports: unhandled exceptions, Qt critical errors, unexpected termination (nothing is
    # sent unless the user approves a report)
    from core.diagnostics import EventId, crash, diagnostics

    session = crash.SessionGuard()
    diagnostics.record(EventId.APP_STARTED)
    window_ref: list = []
    crash.install_hooks(lambda rep: bool(window_ref) and window_ref[0].offer_report(
        rep, "<b>Monograph PDF ran into an unexpected problem.</b><br>You can keep working; save your work if "
             "anything behaves strangely."))

    app = create_application(argv)
    crash.install_qt_message_handler()
    app.aboutToQuit.connect(session.end)
    mark("qapplication")
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName(COPYRIGHT_OWNER)
    app.setApplicationVersion(__version__)
    apply_theme(app, UserPreferences.load().theme)
    apply_application_icon(app)
    mark("theme_icon")

    # Start menu "User Guide": the guide alone, in Monograph PDF's own viewer (no .md app needed)
    if "--user-guide" in argv:
        from ui.app_dialogs import UserGuideDialog

        guide = UserGuideDialog()
        guide.setWindowTitle(f"{PRODUCT_NAME} User Guide")
        guide.exec()
        return 0

    # Brief splash while the editor shell imports (onedir avoids onefile extract delay).
    splash = QLabel(PRODUCT_NAME)
    splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
    splash.setFixedSize(300, 110)
    splash.setStyleSheet(
        "background-color:#1c2430;color:#e7eef8;font-size:17px;font-weight:600;"
        "border:1px solid #2e3a4a;"
    )
    splash.setWindowFlags(
        Qt.WindowType.SplashScreen
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )
    splash.show()
    app.processEvents()
    mark("splash_visible")

    from ui.main_window import MainWindow

    mark("main_window_import")

    session.start()
    window = MainWindow()
    window_ref.append(window)
    mark("mainwindow_ctor")
    window.show()
    splash.close()
    app.processEvents()
    mark("first_visible")
    if not single_instance.is_disabled(argv):
        try:
            window._instance_server = single_instance.InstanceServer(window)  # noqa: SLF001
        except Exception:  # noqa: BLE001 — the program works without the handover
            pass
    app.aboutToQuit.connect(single_instance.release)
    write_log(tag="startup")

    # Defer nonessential probes, temp cleanup, and warm imports
    def _deferred_warmup() -> None:
        mark("deferred_warmup_start")
        try:
            from core.organize.temputil import cleanup_abandoned_temps

            cleanup_abandoned_temps()
        except Exception:  # noqa: BLE001
            pass
        # Warm frozen-collected modules without blocking first paint
        for mod in (
            "engines.mupdf_backend",
            "engines.bake_edits",
            "core.forms.acroform",
            "core.tables.detect",
            "core.organize",
            "core.convert",
            "core.annotations",
            "core.security",
            "core.redaction",
            "core.signatures",
        ):
            try:
                __import__(mod)
            except Exception:  # noqa: BLE001
                pass
        mark("deferred_warmup_done")
        write_log(tag="startup")

    QTimer.singleShot(0, _deferred_warmup)
    # Update results, staging cleanup, earlier problem reports, automatic update check (if enabled)
    QTimer.singleShot(1500, window.after_startup)
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
