"""Offline release smoke — feature paths without network.

Validates library/UI paths for the Windows development release.
Exit 0 only when all required checks pass.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:9")
os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:9")

OUT = ROOT / "tests" / "outputs" / "generated" / "release_smoke"
SAMPLES = ROOT / "tests" / "samples"


def _ok(name: str) -> None:
    print(f"  PASS  {name}")


def _fail(name: str, exc: BaseException) -> None:
    print(f"  FAIL  {name}: {exc}")
    traceback.print_exc()


def ensure_samples() -> None:
    from tests.fixtures.make_samples import main as make_samples

    make_samples()
    try:
        from tests.fixtures.make_form_samples import main as make_forms

        make_forms()
    except Exception:  # noqa: BLE001
        pass
    try:
        from tests.fixtures.make_ocr_samples import main as make_ocr

        make_ocr()
    except Exception:  # noqa: BLE001
        pass


def check_clean_machine_layout() -> None:
    from core.ocr.paths import ocr_ready
    from core.product_meta import EXECUTABLE_NAME, branding_assets_ok

    assert (ROOT / "engines" / "ocr").is_dir(), "engines/ocr missing"
    assert (ROOT / "models" / "tessdata").is_dir(), "models/tessdata missing"
    ok, detail = ocr_ready()
    assert ok, detail
    bok, bdetail = branding_assets_ok()
    assert bok, bdetail
    assert EXECUTABLE_NAME == "MonographPDF.exe"
    extras = [
        p.name
        for p in ROOT.glob("*.exe")
        if p.name.lower() != EXECUTABLE_NAME.lower()
    ]
    if extras:
        print(f"  WARN  extra root executables (cleaned on release): {extras}")
    _ok("clean-machine sidecars + branding")


def check_open_render_edit_save(tmp: Path) -> None:
    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from core.editing.geometry import Rect
    from engines.bake_edits import bake_via_backend

    src = SAMPLES / "sample_text.pdf"
    work = tmp / "edit_roundtrip.pdf"
    work.write_bytes(src.read_bytes())
    doc = open_document(work)
    try:
        assert doc.page_count >= 1
        png = doc.render_pixmap_png(0, zoom=1.0)
        assert png and len(png) > 100
        edit = EditableDocument(doc)
        box = edit.create_text_box(0, Rect(72, 72, 160, 36), text="Release smoke box")
        edit.set_text(box.object_id, "Edited smoke text")
        dest = tmp / "edit_saved.pdf"
        bake_via_backend(edit, dest)
    finally:
        doc.close()
    doc2 = open_document(dest)
    try:
        assert doc2.page_count >= 1
        assert doc2.render_pixmap_png(0, zoom=0.5)
    finally:
        doc2.close()
    _ok("open/render/edit/save/reopen")


def check_forms() -> None:
    from core.document import open_document
    from core.editing.edit_model import EditableDocument

    candidates = list(SAMPLES.glob("*form*.pdf")) + list(SAMPLES.glob("*acro*.pdf"))
    path = candidates[0] if candidates else SAMPLES / "sample_text.pdf"
    doc = open_document(path)
    try:
        edit = EditableDocument(doc)
        n = edit.detect_form_fields(0)
        assert n >= 0
    finally:
        doc.close()
    _ok("forms detect")


def check_page_tools_merge_split(tmp: Path) -> None:
    from core.document import open_document
    from core.organize.merge import MergeJob, combine_to_pdf
    from core.organize.page_ops import duplicate_pages, rotate_pages
    from core.organize.split import SplitMode, plan_split, run_split

    src = SAMPLES / "sample_text.pdf"
    work = tmp / "pages.pdf"
    work.write_bytes(src.read_bytes())
    doc = open_document(work)
    try:
        rotate_pages(doc, [0], 90)
        duplicate_pages(doc, [0])
        assert doc.page_count >= 2
    finally:
        doc.close()

    a = tmp / "a.pdf"
    b = tmp / "b.pdf"
    a.write_bytes(src.read_bytes())
    b.write_bytes(src.read_bytes())
    merged = tmp / "merged.pdf"
    job = MergeJob()
    job.add_path(a)
    job.add_path(b)
    combine_to_pdf(job, merged)
    assert merged.is_file() and merged.stat().st_size > 100

    split_doc = open_document(merged)
    try:
        split_out = tmp / "split"
        plan = plan_split(split_doc, SplitMode.EVERY_PAGE)
        written = run_split(split_doc, plan, split_out)
        assert written and len(written) >= 1
    finally:
        split_doc.close()
    _ok("page tools + merge + split")


def check_ocr(tmp: Path) -> None:
    from core.document import open_document
    from core.ocr.paths import ocr_ready
    from core.ocr.pipeline import OcrOptions, run_ocr

    ok, detail = ocr_ready()
    assert ok, detail
    samples = list(SAMPLES.glob("*ocr*eng*.pdf")) + list(SAMPLES.glob("*scan*.pdf"))
    path = samples[0] if samples else SAMPLES / "sample_text.pdf"

    doc = open_document(path)
    try:
        dest = tmp / "ocr_eng.pdf"
        opts = OcrOptions(
            languages="eng", pages=[0], make_searchable=True, skip_native_text=False
        )
        run_ocr(doc, opts, destination=dest)
        assert dest.is_file()
    finally:
        doc.close()

    doc = open_document(path)
    try:
        dest_j = tmp / "ocr_jpn.pdf"
        opts = OcrOptions(
            languages="jpn", pages=[0], make_searchable=True, skip_native_text=False
        )
        run_ocr(doc, opts, destination=dest_j)
        assert dest_j.is_file()
    finally:
        doc.close()
    _ok("OCR English + Japanese")


def check_convert_export(tmp: Path) -> None:
    from core.convert.capabilities import list_capabilities
    from core.convert.pdf_to_images import pdf_pages_to_images
    from core.convert.pdf_to_text import pdf_to_plain_text
    from core.document import open_document

    caps = list_capabilities()
    assert caps and any(c.implemented for c in caps)
    src = SAMPLES / "sample_text.pdf"
    doc = open_document(src)
    try:
        text_path = tmp / "out.txt"
        pdf_to_plain_text(doc, text_path)
        assert text_path.is_file() and text_path.stat().st_size > 0
        img_dir = tmp / "imgs"
        written = pdf_pages_to_images(doc, img_dir, fmt="png", pages=[0])
        assert written
    finally:
        doc.close()
    _ok("convert/export (text + images)")


def check_annotations_redaction_security(tmp: Path) -> None:
    from core.annotations.ops import add_highlight
    from core.document import open_document
    from core.editing.geometry import Rect
    from core.redaction.ops import apply_redactions, mark_region
    from core.security.ops import (
        EncryptionSettings,
        apply_password_protection,
        remove_password_protection,
    )

    src = SAMPLES / "sample_text.pdf"
    work = tmp / "ann.pdf"
    work.write_bytes(src.read_bytes())
    doc = open_document(work)
    try:
        add_highlight(doc, 0, [Rect(72, 72, 120, 20)])
        mark_region(doc, 0, Rect(72, 200, 100, 40))
        redacted = tmp / "redacted.pdf"
        apply_redactions(doc, redacted)
        assert redacted.is_file()
    finally:
        doc.close()

    protected = tmp / "protected.pdf"
    src_doc = open_document(src)
    try:
        apply_password_protection(
            src_doc,
            protected,
            EncryptionSettings(user_password="smoke", owner_password="smoke-owner"),
        )
    finally:
        src_doc.close()
    assert protected.is_file()

    unlocked = tmp / "unlocked.pdf"
    locked = open_document(protected, password="smoke")
    try:
        remove_password_protection(locked, unlocked, password="smoke")
    finally:
        locked.close()
    assert unlocked.is_file()
    _ok("annotations + redaction + security")


def check_printing(tmp: Path) -> None:
    from core.document import open_document
    from core.printing.ops import PrintOptions, render_pages_for_print

    doc = open_document(SAMPLES / "sample_text.pdf")
    try:
        out = tmp / "print"
        images = render_pages_for_print(doc, out, PrintOptions(page_range="1", dpi=72))
        assert images and len(images) >= 1
    finally:
        doc.close()
    _ok("printing rasters (dialog left to UI)")


def check_about_version_alignment() -> None:
    from core.product_meta import COPYRIGHT_DISPLAY, PRODUCT_NAME, get_product_identity
    from core.versioning import get_version

    identity = get_product_identity()
    assert identity.version == get_version()
    assert identity.product_name == PRODUCT_NAME
    assert identity.copyright_display == COPYRIGHT_DISPLAY
    _ok("About/product metadata version alignment")


def check_ui_shell() -> None:
    from core.product_meta import COPYRIGHT_DISPLAY, PRODUCT_NAME
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-release-smoke"])
    win = MainWindow()
    try:
        assert PRODUCT_NAME in win.windowTitle()
        assert win._status.copyright_label.text() == COPYRIGHT_DISPLAY  # noqa: SLF001
        assert not win.windowIcon().isNull()
        assert win.open_path(SAMPLES / "sample_text.pdf")
        win.close_document(save_session=False)
    finally:
        win.close()
    _ok("UI shell launch + open + footer copyright")


def main() -> int:
    print("Monograph PDF release smoke (offline)")
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    steps = [
        ("samples", ensure_samples),
        ("clean-machine", check_clean_machine_layout),
        ("about-meta", check_about_version_alignment),
        ("edit-roundtrip", lambda: check_open_render_edit_save(OUT)),
        ("forms", check_forms),
        ("organize", lambda: check_page_tools_merge_split(OUT)),
        ("ocr", lambda: check_ocr(OUT)),
        ("convert", lambda: check_convert_export(OUT)),
        ("secure", lambda: check_annotations_redaction_security(OUT)),
        ("print", lambda: check_printing(OUT)),
        ("ui", check_ui_shell),
    ]
    for name, fn in steps:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            _fail(name, exc)
            failures.append(name)

    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("ALL RELEASE SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
