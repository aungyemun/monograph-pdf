"""Offline self-check used by the installer (``MonographPDF.exe --smoke-test``).

Exercises the bundled stack without showing a window: PDF engine, rendering,
saving, encryption, PDF→Word conversion, OCR (English + Japanese data) and the
main window. Writes a JSON report and returns 0 when everything required passed.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import traceback
from pathlib import Path


def run_smoke_test(argv: list[str] | None = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from core import app_env

    app_env.set("HEADLESS", "1")
    from app.paths import RUNTIME_DIR, ensure_runtime_layout
    from core.versioning import get_version

    ensure_runtime_layout()
    report: dict = {"version": get_version(), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}
    required_ok = True

    def check(name: str, fn, *, required: bool = True) -> None:
        nonlocal required_ok
        t0 = time.perf_counter()
        try:
            detail = fn()
            report["checks"][name] = {"ok": True, "ms": round((time.perf_counter() - t0) * 1000), "detail": detail}
        except Exception as exc:  # noqa: BLE001
            report["checks"][name] = {
                "ok": False,
                "required": required,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-1500:],
            }
            if required:
                required_ok = False

    # Offline check: any attempt to open a network connection or look up a host name during
    # the self-check is recorded (and refused) and fails the "no_network" check below.
    from app.offline_guard import NetworkAttempts

    network = NetworkAttempts().install()

    tmp = Path(tempfile.mkdtemp(prefix="monographpdf-smoke-"))
    # Keep the self-check away from the user's real settings and recent-files list
    app_env.set("USER_DATA_DIR", str(tmp / "userdata"))
    sample = tmp / "smoke.pdf"

    def make_pdf():
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Monograph PDF smoke test", fontsize=16)
        page.insert_text((72, 100), "Offline self-check page.", fontsize=11)
        doc.save(sample)
        doc.close()
        return sample.stat().st_size

    def open_render():
        from core.document import open_document

        d = open_document(sample)
        try:
            png = d.render_pixmap_png(0, zoom=1.0)
            assert "smoke test" in d.page_text(0)
            return len(png)
        finally:
            d.close()

    def protect_unlock():
        from core.document import open_document
        from core.security import apply_password_protection, remove_password_protection
        from core.security.ops import EncryptionSettings

        d = open_document(sample)
        try:
            apply_password_protection(d, tmp / "locked.pdf", EncryptionSettings(user_password="u", owner_password="o"))
        finally:
            d.close()
        d = open_document(tmp / "locked.pdf", password="o")
        try:
            remove_password_protection(d, tmp / "unlocked.pdf", password="o")
        finally:
            d.close()
        return "ok"

    def pdf_to_word():
        from core.convert.pdf_to_docx import layout_engine_available, pdf_to_docx
        from core.document import open_document

        if not layout_engine_available():
            raise RuntimeError("pdf2docx layout engine missing from the bundle")
        d = open_document(sample)
        try:
            out = pdf_to_docx(d, tmp / "smoke.docx", engine="layout")
        finally:
            d.close()
        return out.stat().st_size

    def ocr():
        import fitz

        from core.ocr.engine import OcrEngine

        engine = OcrEngine()  # tesseract.exe + eng / jpn / osd data present
        png = tmp / "ocr.png"
        with fitz.open(sample) as d:
            d[0].get_pixmap(dpi=200, clip=fitz.Rect(60, 50, 400, 110)).save(png)
        words = " ".join(t.text for t in engine.run_tsv(png, lang="eng+jpn", psm=6)).lower()
        if "smoke" not in words:
            raise RuntimeError(f"OCR did not read the test page (got {words[:80]!r})")
        return words[:60]

    def bundle_imports():
        # Every Monograph PDF module and conversion library imports from the bundle (a file the
        # build left out, or a library it should not have removed, fails here)
        import importlib
        import pkgutil

        import core
        import engines
        import ui

        names = []
        for pkg in (core, engines, ui):
            for info in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
                names.append(info.name)
        names += ["pdf2docx", "docx", "openpyxl", "pptx", "cv2", "numpy", "fontTools", "PIL.Image",
                  "PySide6.QtPrintSupport"]
        failed = []
        for name in names:
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {type(exc).__name__}: {exc}")
        if failed:
            raise RuntimeError("; ".join(failed[:5]))
        return f"{len(names)} modules"

    def no_network():
        if network.attempts:
            raise RuntimeError("network use during the self-check: " + "; ".join(network.attempts[:5]))
        return "no connection attempts"

    def office_detect():
        from core.convert.office_bridge import office_availability

        return office_availability().describe()

    def main_window():
        from app.qt_app import create_application
        from ui.main_window import MainWindow
        from ui.theme import apply_theme

        app = create_application(["MonographPDF.exe"])
        apply_theme(app, "light")
        win = MainWindow()
        assert win.open_path(sample)
        n = len(win.menuBar().actions())
        win.close_document(save_session=False)
        win.close()
        return f"{n} menus"

    check("create_pdf", make_pdf)
    check("open_render", open_render)
    check("protect_unlock", protect_unlock)
    check("pdf_to_word", pdf_to_word)
    check("ocr", ocr)
    check("office_detect", office_detect, required=False)
    check("main_window", main_window)
    check("bundle_imports", bundle_imports)
    check("no_network", no_network)
    network.uninstall()

    report["passed"] = required_ok
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)  # sample files and the throw-away settings folder
    out_dir = RUNTIME_DIR / "logs"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "smoke_test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        pass
    target = None
    if argv:
        for i, a in enumerate(argv):
            if a == "--report" and i + 1 < len(argv):
                target = Path(argv[i + 1])
    if target is not None:
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if required_ok else 1
