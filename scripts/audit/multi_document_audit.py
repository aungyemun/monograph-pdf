"""Several PDFs open in tabs (developer harness, not shipped): unsaved edits and page operations in
each, switching between them, saving one at a time — every file on disk must contain exactly its own
changes, and files that were not saved must be unchanged.

Usage::

    env\\Scripts\\python.exe scripts\\audit\\multi_document_audit.py <out_dir> [form.pdf]

Runs the real main window (settings in a temporary folder). Results: <out_dir>/multi_document.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build" / "multi-document"
FORM = Path(sys.argv[2]) if len(sys.argv) > 2 else None
OUT.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="mpdf_multi_"))
os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(WORK / "settings")
os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] = str(WORK / "runtime")
os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"

import fitz  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from core.editing.geometry import Rect  # noqa: E402
from ui.main_window import MainWindow, create_application  # noqa: E402

RESULTS: list[dict] = []
SAVE_AS: list[str] = []
ASKED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> bool:
    RESULTS.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    return ok


def pump(ms: float = 40) -> None:
    end = time.perf_counter() + ms / 1000
    while True:
        QApplication.processEvents()
        if time.perf_counter() >= end:
            break
        time.sleep(0.003)


# answers instead of dialogs: Save As goes to the queued path; "unsaved changes" questions are recorded
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (SAVE_AS.pop(0) if SAVE_AS else "", "PDF Files (*.pdf)"))


def _box_exec(self):
    ASKED.append(self.text())
    return int(QMessageBox.StandardButton.Cancel.value)


QMessageBox.exec = _box_exec


def make(name: str, pages: int) -> Path:
    p = WORK / name
    d = fitz.open()
    for i in range(pages):
        d.new_page(width=595, height=842).insert_text((72, 72), f"{p.stem} page {i + 1}", fontsize=16)
    d.save(p)
    d.close()
    return p


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pages_text(p: Path) -> list[str]:
    with fitz.open(p) as d:
        return [pg.get_text().strip().replace("\n", " ") for pg in d]


def rotations(p: Path) -> list[int]:
    with fitz.open(p) as d:
        return [pg.rotation for pg in d]


app = create_application(["monograph-pdf-multi-document"])
W = MainWindow()
W.resize(1300, 900)
W.show()
pump(300)


def current() -> Path:
    return Path(W._document.path)  # noqa: SLF001


def activate(path: Path) -> None:
    for i, s in enumerate(W._sessions):  # noqa: SLF001
        if Path(s.document.path) == path:
            W._activate_session(i)  # noqa: SLF001
            pump(120)
            return
    raise AssertionError(f"{path.name} not open")


def select_pages(indices: list[int]) -> None:
    thumbs = W._left.thumbs  # noqa: SLF001
    thumbs.clearSelection()
    for i in indices:
        thumbs.item(i).setSelected(True)
    pump(30)


def add_box(text: str, page: int = 0) -> None:
    e = W._edit  # noqa: SLF001
    e.create_text_box(page, Rect(72, 300, 260, 40), text=text, auto_match=False)
    e.editing_object_id = None
    e.mark_dirty()
    pump(60)


def main() -> int:
    A, B, C = make("Alpha.pdf", 3), make("Bravo.pdf", 2), make("Charlie.pdf", 4)
    D = None
    if FORM and FORM.exists():
        D = WORK / "Form copy.pdf"
        shutil.copyfile(FORM, D)
    orig = {p: sha(p) for p in (A, B, C)}

    for p in (A, B, C):
        check(f"open {p.name}", W.open_path(p))
        pump(150)
    check("three tabs", W._doc_tabs.count() == 3, W._doc_tabs.count())  # noqa: SLF001

    # A: text box + turn page 2, not saved
    activate(A)
    add_box("edit in Alpha")
    select_pages([1])
    W._rotate_selected(90)  # noqa: SLF001
    pump(100)
    check("Alpha has unsaved changes", W._edit.dirty)  # noqa: SLF001

    # B (A unsaved): its own model, its own edit, insert a blank page
    activate(B)
    texts_b = [o.text for o in W._edit.all_objects()]  # noqa: SLF001
    check("Bravo does not show Alpha's text box", "edit in Alpha" not in texts_b, texts_b)
    add_box("edit in Bravo")
    W._insert_blank_page(at=1)  # noqa: SLF001
    pump(100)
    check("Bravo: blank page inserted (3 pages)", W._document.page_count == 3, W._document.page_count)  # noqa: SLF001

    # C: delete two selected pages, duplicate, reorder, undo / redo
    activate(C)
    select_pages([1, 2])
    W._delete_selected_pages()  # noqa: SLF001
    pump(100)
    check("Charlie: two selected pages deleted", W._document.page_count == 2, W._document.page_count)  # noqa: SLF001
    select_pages([0])
    W._duplicate_selected_pages()  # noqa: SLF001
    pump(100)
    check("Charlie: page duplicated", W._document.page_count == 3, W._document.page_count)  # noqa: SLF001
    W._on_thumbs_reordered([2, 0, 1])  # noqa: SLF001
    pump(100)
    W._edit.undo()  # noqa: SLF001
    pump(100)
    W._edit.redo()  # noqa: SLF001
    pump(100)

    # open a fourth file while three have unsaved changes; re-opening an open file only focuses it
    if D is not None:
        check("open a form while others are unsaved", W.open_path(D))
        pump(200)
        fields = [f for f in W._edit.fields.values() if f.field_type.value == "text"]  # noqa: SLF001
        if fields:
            W._edit.set_field_value(fields[0].object_id, "filled in the form tab")  # noqa: SLF001
    n_tabs = W._doc_tabs.count()  # noqa: SLF001
    W.open_path(A)
    pump(150)
    check("opening an open file switches to its tab (no second copy)", W._doc_tabs.count() == n_tabs and current() == A,
          (W._doc_tabs.count(), current().name))  # noqa: SLF001

    # A still has its own unsaved state
    texts_a = [o.text for o in W._edit.all_objects()]  # noqa: SLF001
    check("Alpha kept its unsaved text box", "edit in Alpha" in texts_a and "edit in Bravo" not in texts_a, texts_a)
    check("Alpha kept its turned page", W._document.page(1).rotation % 360 == 90)  # noqa: SLF001

    # nothing written to disk yet
    check("nothing saved yet: all files unchanged on disk", all(sha(p) == h for p, h in orig.items()))

    # save Alpha only
    W.save_document()
    pump(300)
    ta = pages_text(A)
    check("Alpha saved: its text box", "edit in Alpha" in " ".join(ta), ta)
    check("Alpha saved: no text from other tabs", "edit in Bravo" not in " ".join(ta))
    check("Alpha saved: page 2 turned 90°", rotations(A) == [0, 90, 0], rotations(A))
    check("Bravo and Charlie still unchanged on disk", sha(B) == orig[B] and sha(C) == orig[C])

    # Charlie: save
    activate(C)
    W.save_document()
    pump(300)
    tc = pages_text(C)
    # 1 2 3 4 → delete 2, 3 → 1 4 → duplicate 1 → 1 1 4 → new order [2, 0, 1] → 4 1 1
    check("Charlie saved: 3 pages in the reordered order", [t.split()[-1] for t in tc] == ["4", "1", "1"]
          and len(tc) == 3, tc)

    # Bravo: Save As to a new file; the original stays untouched
    activate(B)
    B2 = WORK / "Bravo edited.pdf"
    SAVE_AS.append(str(B2))
    W.save_as_dialog()
    pump(300)
    check("Bravo Save As wrote the new file", B2.exists())
    if B2.exists():
        tb = pages_text(B2)
        check("Bravo Save As: 3 pages, blank page 2, its own text box", len(tb) == 3 and tb[1] == ""
              and "edit in Bravo" in " ".join(tb) and "edit in Alpha" not in " ".join(tb), tb)
    check("Bravo original untouched", sha(B) == orig[B])
    check("Bravo tab now edits the new file", current() == B2, current().name)

    if D is not None:
        activate(D)
        W.save_document()
        pump(300)
        with fitz.open(D) as d:
            vals = [w.field_value for pg in d for w in (pg.widgets() or [])]
        check("form tab saved its own value", "filled in the form tab" in vals)

    # all saved: closing tabs asks nothing
    ASKED.clear()
    while W._document is not None:  # noqa: SLF001
        W._close_document_interactive()  # noqa: SLF001
        pump(80)
    check("closing saved tabs asks no question", not ASKED, ASKED)

    (OUT / "multi_document.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"CHECKS {len(RESULTS)}  FAILED {len(failed)}")
    for r in failed:
        print(f"  {r['check']}: {r['detail']}")
    W.close()
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        (OUT / "multi_document.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"CHECKS {len(RESULTS)} (aborted)  FAILED {sum(not r['ok'] for r in RESULTS)}")
        for r in RESULTS:
            if not r["ok"]:
                print(f"  {r['check']}: {r['detail']}")
        raise SystemExit(2)
