"""Phase 1 reliability scenarios (audit harness; real MainWindow, offscreen, isolated profile).

Writes outputs and expectations to <out>/; expectations are checked independently (pypdf / qpdf) by
p1_check.py. Synthetic fixtures only; nothing outside the temporary work folder is written.
    env\\Scripts\\python.exe -u -I p1_scenarios.py <out_dir>
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(os.environ["MPDF_ROOT"]); sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="mpdf_p1_"))
for n in ("RUNTIME_DIR", "UPDATES_DIR", "DIAGNOSTICS_DIR", "USER_DATA_DIR"):
    os.environ["MONOGRAPH_PDF_" + n] = str(WORK / n.lower())
os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

import fitz  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from core.editing.geometry import Rect  # noqa: E402
from ui.main_window import MainWindow, create_application  # noqa: E402

app = create_application(["p1"])
RESULTS: list[dict] = []
EXPECT: dict[str, dict] = {}
ERRORS: list[tuple[str, str]] = []
SAVE_QUEUE: list[str] = []
MSG_ANSWERS: list = []
JP_FONT = next((p for p in (r"C:\Windows\Fonts\msgothic.ttc", r"C:\Windows\Fonts\YuGothM.ttc", r"C:\Windows\Fonts\meiryo.ttc")
                if os.path.exists(p)), None)


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# --- dialogs answered by the harness ----------------------------------------------------------
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (SAVE_QUEUE.pop(0) if SAVE_QUEUE else "", "PDF Files (*.pdf)"))
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: (MSG_ANSWERS.pop(0) if MSG_ANSWERS else QMessageBox.StandardButton.Yes))
QMessageBox.question = staticmethod(lambda *a, **k: (MSG_ANSWERS.pop(0) if MSG_ANSWERS else QMessageBox.StandardButton.Yes))
_real_exec = QMessageBox.exec
QMessageBox.exec = lambda self: (MSG_ANSWERS.pop(0) if MSG_ANSWERS else QMessageBox.StandardButton.Cancel)
MainWindow.report_error = lambda self, title, msg, **k: ERRORS.append((title, str(msg)))
MainWindow.report_unexpected = lambda self, title, exc, *a, **k: ERRORS.append((title, f"{type(exc).__name__}: {exc}"))


# --- fixtures ------------------------------------------------------------------------------------
def fx_form(path: Path) -> Path:
    d = fitz.open(); p = d.new_page(width=595, height=842)
    if JP_FONT:
        p.insert_font(fontname="jp", fontfile=JP_FONT)
        p.insert_text((72, 60), "申請書 Application form", fontname="jp", fontsize=14)
    else:
        p.insert_text((72, 60), "Application form", fontsize=14)
    specs = [
        ("name", fitz.PDF_WIDGET_TYPE_TEXT, (72, 90, 300, 112), {}),
        ("notes", fitz.PDF_WIDGET_TYPE_TEXT, (72, 120, 300, 180), {"field_flags": 1 << 12}),
        ("agree", fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 190, 86, 204), {}),
        ("colour", fitz.PDF_WIDGET_TYPE_COMBOBOX, (72, 215, 200, 233), {"choice_values": ["Alpha", "Beta", "Gamma"], "field_value": "Alpha"}),
        ("size", fitz.PDF_WIDGET_TYPE_LISTBOX, (220, 215, 320, 270), {"choice_values": ["One", "Two", "Three"], "field_value": "One"}),
        ("fixed", fitz.PDF_WIDGET_TYPE_TEXT, (72, 280, 300, 300), {"field_value": "read only value", "field_flags": 1}),
        ("required", fitz.PDF_WIDGET_TYPE_TEXT, (72, 310, 300, 330), {"field_flags": 2}),
        ("prefilled", fitz.PDF_WIDGET_TYPE_TEXT, (72, 340, 300, 360), {"field_value": "OLDVALUE-123"}),
    ]
    for name, typ, rect, extra in specs:
        w = fitz.Widget(); w.field_name = name; w.field_type = typ; w.rect = fitz.Rect(rect)
        for k, v in extra.items():
            setattr(w, k, v)
        if typ == fitz.PDF_WIDGET_TYPE_TEXT and "field_value" not in extra:
            w.field_value = ""
        p.add_widget(w)
    for i, x in enumerate((72, 120)):  # radio group "plan" with two buttons
        w = fitz.Widget(); w.field_name = "plan"; w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        w.rect = fitz.Rect(x, 380, x + 14, 394); w.field_value = False; w.button_caption = None
        p.add_widget(w)
    d.save(path); d.close(); return path


def fx_text(path: Path, pages: int = 4, *, secret: str = "SECRET-ALPHA", jp: bool = False) -> Path:
    d = fitz.open()
    for i in range(pages):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 72), f"Page {i + 1} heading", fontsize=18)
        p.insert_text((72, 110), f"Body text on page {i + 1} with {secret} inside.", fontsize=11)
        if JP_FONT and jp:
            p.insert_font(fontname="jp", fontfile=JP_FONT)
            p.insert_text((72, 140), "日本語の本文テキストです。", fontname="jp", fontsize=11)
    for i in range(pages - 1):  # links to the next page (after every page exists)
        p = d[i]
        p.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 160, 200, 175), "page": i + 1})
        p.insert_text((72, 172), "next page link", fontsize=10)
    d.set_toc([[1, f"Chapter {i + 1}", i + 1] for i in range(pages)])
    d.set_metadata({"title": f"Report {secret}", "author": "Audit Author", "subject": "synthetic"})
    d.save(path, garbage=3, deflate=True); d.close(); return path


def fx_hidden(path: Path) -> Path:
    d = fitz.open(); p = d.new_page(width=595, height=842)
    p.insert_text((72, 72), "Visible text stays.", fontsize=12)
    p.insert_text((72, 100), "INVISIBLE-LAYER-TEXT", fontsize=12, render_mode=3)
    p.add_text_annot((300, 300), "A private comment")
    d.embfile_add("private.txt", b"private attachment content")
    d.set_metadata({"title": "Hidden info test", "author": "Private Person", "keywords": "internal"})
    d.set_xml_metadata('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/></x:xmpmeta><?xpacket end="w"?>')
    d.save(path)
    d.close()
    d = fitz.open(path)  # an OpenAction with JavaScript
    js = d.get_new_xref(); d.update_object(js, "<< /S /JavaScript /JS (app.alert\\('hi'\\);) >>")
    d.xref_set_key(d.pdf_catalog(), "OpenAction", f"{js} 0 R")
    d.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP); d.close()
    return path


def fx_encrypted(path: Path) -> Path:
    src = fx_form(WORK / "enc_src.pdf")
    d = fitz.open(src)
    d.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u-pass", owner_pw="o-pass",
           permissions=int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM))
    d.close(); return path


def fx_malformed(path: Path) -> Path:
    good = fx_text(WORK / "mal_src.pdf", pages=2)
    data = good.read_bytes()
    cut = data.rfind(b"startxref")
    path.write_bytes(data[:cut] + b"startxref\n999999\n%%EOF\n")  # broken xref offset: needs repair
    return path


def fx_scan(path: Path) -> Path:
    from PIL import Image, ImageDraw
    import io
    d = fitz.open()
    for i in range(2):
        im = Image.new("RGB", (1240, 1754), (250, 250, 245)); dr = ImageDraw.Draw(im)
        dr.rectangle((100, 100, 700, 160), fill=(20, 20, 20)); dr.rectangle((100, 900, 1100, 1300), fill=(200, 30, 30))
        b = io.BytesIO(); im.save(b, "JPEG", quality=85)
        d.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=b.getvalue())
    d.save(path); d.close(); return path


# --- harness -------------------------------------------------------------------------------------
W = MainWindow(); W.resize(1300, 900); W.show(); app.processEvents()


def pump(n=6):
    for _ in range(n):
        app.processEvents()


def fresh(name: str, maker, *a, **k) -> Path:
    p = WORK / "docs" / name; p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    return maker(p, *a, **k)


def scenario(name):
    def deco(fn):
        def run():
            ERRORS.clear(); SAVE_QUEUE.clear(); MSG_ANSWERS.clear()
            rec = {"name": name, "ok": True, "notes": [], "errors": []}
            try:
                fn(rec)
            except Exception as e:  # noqa: BLE001
                rec["ok"] = False; rec["exception"] = f"{type(e).__name__}: {e}"; rec["trace"] = traceback.format_exc()[-1500:]
            rec["errors"] = list(ERRORS)
            try:
                while W._sessions:  # noqa: SLF001
                    W._sessions[0].edit.dirty = False  # noqa: SLF001
                    W.close_document(save_session=False)
            except Exception as e:  # noqa: BLE001
                rec["notes"].append(f"cleanup: {e}")
            RESULTS.append(rec)
            print(("OK  " if rec["ok"] else "FAIL"), name, rec.get("exception", ""), rec["notes"][:3], flush=True)
        run.__name__ = name
        STEPS.append(run)
        return run
    return deco


STEPS: list = []


def check(rec, cond, what):
    if not cond:
        rec["ok"] = False; rec["notes"].append("FAILED: " + what)


def field(name):
    return next(f for f in W._edit.fields.values() if f.name == name)  # noqa: SLF001


def out(name: str) -> Path:
    return OUT / name


def expect(path: Path, **kw):
    EXPECT[str(path)] = kw


# --- P0: save / save as / copy with forms, annotations, page changes ------------------------------
@scenario("forms_fill_save_over_open_file")
def _(rec):
    p = fresh("form.pdf", fx_form); assert W.open_path(p); pump()
    e = W._edit  # noqa: SLF001
    e.set_field_value(field("name").object_id, "東京 Tokyo 123")
    e.set_field_value(field("notes").object_id, "line one\nline two")
    e.set_field_value(field("agree").object_id, checked=True)
    e.set_field_value(field("colour").object_id, "Beta")
    e.set_field_value(field("size").object_id, "Two")
    e.set_field_value(field("prefilled").object_id, "")  # cleared
    radios = [f for f in e.fields.values() if f.name == "plan"]
    e.set_field_value(radios[1].object_id, checked=True)
    e.mark_dirty(); W.save_document(); pump()
    check(rec, not ERRORS, f"save reported errors {ERRORS}")
    check(rec, not W._edit.dirty, "dirty after save")  # noqa: SLF001
    final = out("forms_saved.pdf"); final.write_bytes(p.read_bytes())
    expect(final, pages=1, fields={"name": "東京 Tokyo 123", "notes": "line one\nline two", "agree": "/Yes|/On|/0|/1", "colour": "Beta",
                                   "size": "Two", "fixed": "read only value", "prefilled": "", "plan": "!/Off"},
           no_stale_text={"prefilled": "OLDVALUE-123"})
    # reopen in the app: values come back
    assert W.open_path(p); pump()
    check(rec, field("name").value == "東京 Tokyo 123", f"reopened name={field('name').value!r}")
    check(rec, field("agree").checked, "reopened checkbox not checked")
    check(rec, field("prefilled").value == "", f"cleared field reopened as {field('prefilled').value!r}")
    check(rec, [f.checked for f in W._edit.fields.values() if f.name == "plan"] == [False, True], "radio state not persisted")  # noqa: SLF001


@scenario("forms_save_as_then_save_copy")
def _(rec):
    p = fresh("form2.pdf", fx_form); assert W.open_path(p); pump()
    W._edit.set_field_value(field("name").object_id, "Save As value"); W._edit.mark_dirty()  # noqa: SLF001
    dest = out("forms_save_as.pdf"); SAVE_QUEUE.append(str(dest)); W.save_as_dialog(); pump()
    check(rec, not ERRORS, f"errors {ERRORS}")
    check(rec, Path(W._document.path) == dest, "after Save As the window works on the new file")  # noqa: SLF001
    check(rec, sha(p) == sha(WORK / "docs" / "form2.pdf"), "source changed")
    expect(dest, fields={"name": "Save As value"})
    W._edit.set_field_value(field("name").object_id, "Copy value"); W._edit.mark_dirty()  # noqa: SLF001
    copy = out("forms_copy.pdf"); W.save_copy_dialog(copy); pump()
    check(rec, W._edit.dirty, "Save a Copy must leave the document modified")  # noqa: SLF001
    expect(copy, fields={"name": "Copy value"}); expect(dest, fields={"name": "Save As value"})


@scenario("undo_redo_then_save")
def _(rec):
    p = fresh("form3.pdf", fx_form); assert W.open_path(p); pump()
    e = W._edit  # noqa: SLF001
    e.set_field_value(field("name").object_id, "first"); e.set_field_value(field("required").object_id, "second")
    e.undo()  # undo "second"
    check(rec, field("required").value == "", f"undo: required={field('required').value!r}")
    e.set_field_value(field("notes").object_id, "third"); e.undo(); e.redo()
    check(rec, field("notes").value == "third", "redo did not restore 'third'")
    W.save_document(); pump()
    final = out("undo_redo_saved.pdf"); final.write_bytes(p.read_bytes())
    expect(final, fields={"name": "first", "required": "", "notes": "third"})


@scenario("annotations_page_ops_save")
def _(rec):
    from core.annotations.ops import add_rectangle, add_text_comment
    from core.editing.annot_commands import MarkupAnnotCommand
    p = fresh("text.pdf", fx_text, pages=5); assert W.open_path(p); pump()
    for kind in ("highlight", "underline", "strikeout", "squiggly"):
        W._edit.commands.execute(MarkupAnnotCommand(W._document, W._edit, 0, kind, [Rect(72, 98, 200, 16)], color=(1, 0.8, 0)))  # noqa: SLF001
        W._after_annotation(0, kind)  # noqa: SLF001
    from core.editing.geometry import Point
    add_text_comment(W._document, 1, Point(300, 300), "note text")  # noqa: SLF001
    add_rectangle(W._document, 1, Rect(100, 400, 120, 60))  # noqa: SLF001
    W._edit.mark_dirty()  # noqa: SLF001
    assert W._rotate_pages([2], 90)  # noqa: SLF001
    W._edit.mark_dirty(); W.save_document(); pump()  # noqa: SLF001
    check(rec, not ERRORS, f"errors {ERRORS}")
    final = out("annotations_pages_saved.pdf"); final.write_bytes(p.read_bytes())
    expect(final, pages=5, rotate={2: 90}, annots_on={0: ["/Highlight", "/Underline", "/StrikeOut", "/Squiggly"], 1: ["/Text", "/Square"]},
           outline_top_level=5, min_links=4, text_has={0: "SECRET-ALPHA"})


@scenario("encrypted_edit_save_keeps_aes256")
def _(rec):
    p = fresh("enc.pdf", fx_encrypted); assert W.open_path(p, password="u-pass"); pump()
    W._edit.set_field_value(field("name").object_id, "inside encrypted"); W._edit.mark_dirty()  # noqa: SLF001
    W._edit.create_text_box(0, Rect(300, 600, 200, 24), text="encrypted box text", auto_match=False)  # noqa: SLF001
    W.save_document(); pump()
    check(rec, not ERRORS, f"errors {ERRORS}")
    final = out("encrypted_saved.pdf"); final.write_bytes(p.read_bytes())
    expect(final, password="u-pass", wrong_password="nope", encryption_bits=256, fields={"name": "inside encrypted"},
           text_has={0: "encrypted box text"})


@scenario("redaction_text_and_residue")
def _(rec):
    from core.redaction import apply_redactions_report, mark_text
    p = fresh("redact.pdf", fx_text, pages=2)
    d = fitz.open(p); pg = d[0]
    a = pg.add_highlight_annot(fitz.Rect(300, 600, 400, 620)); a.set_info(content="note mentions SECRET-ALPHA"); a.update()
    pg.insert_text((72, 700), "SECRET-ALPHA hidden layer", fontsize=10, render_mode=3)
    d.saveIncr(); d.close()
    assert W.open_path(p); pump()
    for i in range(W._document.page_count):  # noqa: SLF001
        mark_text(W._document, i, "SECRET-ALPHA")  # noqa: SLF001
    dest = out("redacted.pdf")
    rep = apply_redactions_report(W._document, dest)  # noqa: SLF001
    rec["notes"].append(f"residue: {[(r.where, r.detail[:60]) for r in rep.residue]}")
    expect(dest, text_absent="SECRET-ALPHA", raw_absent="SECRET-ALPHA", pages=2,
           allow_raw_in=["/Title", "/Contents"])  # residue in metadata / comments is reported to the user, not removed


@scenario("redaction_image_area")
def _(rec):
    from core.redaction import apply_redactions_report, mark_region
    p = fresh("scan.pdf", fx_scan); assert W.open_path(p); pump()
    mark_region(W._document, 0, Rect(48, 435, 434, 193))  # noqa: SLF001  over the red block (page points)
    dest = out("redacted_image.pdf"); apply_redactions_report(W._document, dest)  # noqa: SLF001
    expect(dest, pages=2, image_region_not_red={"page": 0, "rect": [60, 450, 470, 610]})


@scenario("remove_hidden_everything")
def _(rec):
    from core.security.sanitize import SanitizeOptions, remove_hidden
    p = fresh("hidden.pdf", fx_hidden); assert W.open_path(p); pump()
    dest = out("cleaned.pdf"); remove_hidden(W._document, dest, SanitizeOptions.everything())  # noqa: SLF001
    expect(dest, no_metadata=True, no_xmp=True, no_attachments=True, no_javascript=True, no_annots=True,
           text_has={0: "Visible text stays"}, raw_absent="INVISIBLE-LAYER-TEXT")


@scenario("malformed_open_edit_save")
def _(rec):
    p = fresh("broken.pdf", fx_malformed); ok = W.open_path(p); pump()
    check(rec, ok, "malformed PDF did not open")
    if ok:
        W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="after repair", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
        dest = out("malformed_saved.pdf"); SAVE_QUEUE.append(str(dest)); W.save_as_dialog(); pump()
        check(rec, not ERRORS, f"errors {ERRORS}")
        expect(dest, pages=2, text_has={0: "after repair"})


@scenario("unicode_and_long_paths")
def _(rec):
    p = fresh("uni.pdf", fx_text, pages=2); assert W.open_path(p); pump()
    W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="unicode path", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
    jp = OUT / "テスト 資料（最終）" / "報告書 – 改訂版 ①.pdf"; jp.parent.mkdir(parents=True, exist_ok=True)
    SAVE_QUEUE.append(str(jp)); W.save_as_dialog(); pump()
    check(rec, not ERRORS and jp.exists(), f"Japanese path save: errors {ERRORS}")
    expect(jp, pages=2, text_has={0: "unicode path"})
    ERRORS.clear()
    deep = OUT / ("long_" + "x" * 60) / ("y" * 60) / ("z" * 60) / ("w" * 40)
    try:
        deep.mkdir(parents=True, exist_ok=True); made = True
    except OSError as e:
        made = False; rec["notes"].append(f"cannot even create long directory: {e}")
    long_dest = deep / ("long file name " * 3 + ".pdf")
    rec["notes"].append(f"long path length {len(str(long_dest))}")
    if made:
        W._edit.mark_dirty(); SAVE_QUEUE.append(str(long_dest)); W.save_as_dialog(); pump()  # noqa: SLF001
        if long_dest.exists():
            expect(long_dest, pages=2)
        else:
            check(rec, bool(ERRORS), "long path: no file and no error message (silent failure)")
            rec["notes"].append(f"long path not saved; message: {ERRORS[:1]}")


@scenario("save_as_onto_readonly_file")
def _(rec):
    import stat
    p = fresh("ro_src.pdf", fx_text, pages=1); assert W.open_path(p); pump()
    target = out("readonly_target.pdf"); fx_text(target, pages=3); before = sha(target)
    os.chmod(target, stat.S_IREAD)
    try:
        W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="x", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
        SAVE_QUEUE.append(str(target)); W.save_as_dialog(); pump()
        check(rec, bool(ERRORS), "no error shown for a read-only target")
        check(rec, sha(target) == before, "read-only target changed")
        check(rec, W._edit.dirty, "edits must still be unsaved")  # noqa: SLF001
        rec["notes"].append(f"message: {ERRORS[:1]}")
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
    expect(target, pages=3)


def _inject_disk_full(rec, label, action, target: Path, *, existed: bool):
    """Run ``action`` while every fitz save writes half a file and fails with ENOSPC."""
    real = fitz.Document.save

    def failing_save(self, filename, *a, **k):
        if not isinstance(filename, (str, os.PathLike)):
            return real(self, filename, *a, **k)  # in-memory copies (tobytes) are not disk writes
        name = os.fspath(filename)
        Path(name).write_bytes(b"%PDF-1.7\n% partial write before the disk filled up\n" * 50)
        raise OSError(errno.ENOSPC, "No space left on device", name)

    before = sha(target) if existed else None
    leftovers_before = set(target.parent.iterdir())
    fitz.Document.save = failing_save
    try:
        action()
    except Exception as e:  # noqa: BLE001
        rec["notes"].append(f"{label}: raised {type(e).__name__}: {e}"[:200])
    finally:
        fitz.Document.save = real
    pump()
    new_files = sorted(str(p.name) for p in set(target.parent.iterdir()) - leftovers_before)
    if existed:
        check(rec, target.exists() and sha(target) == before, f"{label}: existing destination damaged by the failed write")
    else:
        check(rec, not target.exists(), f"{label}: partial new file left at the destination")
    check(rec, not new_files, f"{label}: leftover files {new_files}")


@scenario("disk_full_every_writer")
def _(rec):
    from core.redaction import apply_redactions_report, mark_text
    from core.security.ops import EncryptionSettings, apply_password_protection
    from core.security.sanitize import SanitizeOptions, remove_hidden
    p = fresh("df.pdf", fx_text, pages=2); assert W.open_path(p); pump()
    W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="unsaved", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
    src_before = sha(p)
    _inject_disk_full(rec, "Save (over open file)", W.save_document, p, existed=True)
    check(rec, W._edit.dirty and W._document is not None, "Save: edits lost after disk-full")  # noqa: SLF001
    for label, mk in (("Save As onto existing file", lambda t: (SAVE_QUEUE.append(str(t)), W.save_as_dialog())),
                      ("Save a Copy onto existing file", lambda t: W.save_copy_dialog(t)),
                      ("Remove hidden info onto existing file", lambda t: remove_hidden(W._document, t, SanitizeOptions())),  # noqa: SLF001
                      ("Protect onto existing file", lambda t: apply_password_protection(W._document, t, EncryptionSettings(user_password="a", owner_password="b"))),  # noqa: SLF001
                      ("Apply redaction onto existing file", lambda t: (mark_text(W._document, 0, "SECRET-ALPHA"), apply_redactions_report(W._document, t)))):  # noqa: SLF001
        t = out("df_target_" + label.split()[0].lower() + ".pdf"); fx_text(t, pages=3)
        _inject_disk_full(rec, label, lambda mk=mk, t=t: mk(t), t, existed=True)
    for label, mk in (("Save As new file", lambda t: (SAVE_QUEUE.append(str(t)), W.save_as_dialog())),
                      ("Save a Copy new file", lambda t: W.save_copy_dialog(t))):
        t = out("df_new_" + label.split()[1].lower() + ".pdf")
        _inject_disk_full(rec, label, lambda mk=mk, t=t: mk(t), t, existed=False)
    check(rec, sha(p) == src_before, "the open document's file changed")


@scenario("close_with_unsaved_cancel_and_save")
def _(rec):
    p = fresh("close.pdf", fx_text, pages=1, jp=False); assert W.open_path(p); pump()
    W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="close save", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
    before = sha(p)
    W._is_headless_ui = lambda: False  # noqa: SLF001 — the real Save / Don't Save / Cancel question
    MSG_ANSWERS.append(QMessageBox.StandardButton.Cancel)
    W._close_document_interactive(); pump()  # noqa: SLF001
    check(rec, W._document is not None and W._edit.dirty, "Cancel must keep the document and edits")  # noqa: SLF001
    check(rec, sha(p) == before, "Cancel changed the file")
    MSG_ANSWERS.append(QMessageBox.StandardButton.Save)
    W._close_document_interactive(); pump()  # noqa: SLF001
    final = out("close_saved.pdf"); final.write_bytes(p.read_bytes())
    expect(final, text_has={0: "close save"})
    rec["notes"].append(f"after Close->Save document open: {W._document is not None}")  # noqa: SLF001
    del W._is_headless_ui  # noqa: SLF001


@scenario("japanese_embedded_font_document_roundtrip")
def _(rec):
    p = fresh("jpfont.pdf", fx_text, pages=2, jp=True); assert W.open_path(p); pump()
    W._edit.create_text_box(0, Rect(72, 500, 200, 20), text="edit", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
    dest = out("jp_font_doc_saved.pdf"); SAVE_QUEUE.append(str(dest)); W.save_as_dialog(); pump()
    expect(dest, pages=2, fixture_font_note=True)


@scenario("japanese_text_box_save")
def _(rec):
    p = fresh("jp.pdf", fx_text, pages=1, jp=False); assert W.open_path(p); pump()  # no fixture font: only the app embeds fonts
    W._edit.create_text_box(0, Rect(72, 500, 300, 30), text="日本語テキスト入力テスト", auto_match=False); W._edit.mark_dirty()  # noqa: SLF001
    dest = out("japanese_box.pdf"); SAVE_QUEUE.append(str(dest)); W.save_as_dialog(); pump()
    expect(dest, text_has={0: "日本語テキスト入力テスト"})


for step in STEPS:
    step()
(OUT / "expectations.json").write_text(json.dumps(EXPECT, indent=1, ensure_ascii=False), encoding="utf-8")
(OUT / "scenarios.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
print("scenarios", len(RESULTS), "failed", sum(1 for r in RESULTS if not r["ok"]), flush=True)
os._exit(0)
