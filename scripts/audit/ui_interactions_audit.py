"""UI interaction audit (developer harness, not shipped): zoom, resizing and moving objects with the
mouse, multi-selection, compression presets and password-protected PDFs — checked against the
document model and the saved files, with timings for smoothness.

Usage::

    env\\Scripts\\python.exe scripts\\audit\\ui_interactions_audit.py <out_dir>

Runs the real main window (on screen; settings and recent files in a temporary folder, your own are
never touched). Results: <out_dir>/ui_interactions.json and a summary on stdout.
"""

from __future__ import annotations

import io
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build" / "ui-interactions"
OUT.mkdir(parents=True, exist_ok=True)
_work = Path(tempfile.mkdtemp(prefix="mpdf_ui_"))
os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(_work / "settings")
os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] = str(_work / "runtime")
os.environ["MONOGRAPH_PDF_MULTI_INSTANCE"] = "1"

import fitz  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.editing.edit_model import EditTool  # noqa: E402
from core.editing.geometry import Rect  # noqa: E402
from core.editing.image_box import ImageBox  # noqa: E402
from ui.main_window import MainWindow, create_application  # noqa: E402
from ui.pdf_canvas import ZoomMode  # noqa: E402

RESULTS: list[dict] = []
TIMES: dict[str, list[float]] = {}


def check(area: str, name: str, ok: bool, detail: object = "") -> bool:
    RESULTS.append({"area": area, "check": name, "ok": bool(ok),
                    "detail": str(detail)[:300].encode("utf-8", "backslashreplace").decode()})
    return ok


def pump(ms: float = 30) -> None:
    end = time.perf_counter() + ms / 1000
    while True:
        QApplication.processEvents()
        if time.perf_counter() >= end:
            break
        time.sleep(0.003)


app = create_application(["monograph-pdf-ui-interactions"])
W = MainWindow()
W.resize(1300, 900)
W.show()
pump(400)
CANVAS = W._canvas  # noqa: SLF001
INNER = CANVAS._canvas  # noqa: SLF001


def edit():
    return W._edit  # noqa: SLF001


def make_doc(name: str = "interactions.pdf") -> Path:
    path = _work / name
    d = fitz.open()
    for i in range(3):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 72), f"Page {i + 1} — Lorem ipsum dolor sit amet", fontsize=14)
        p.insert_textbox(fitz.Rect(72, 520, 523, 800), "Consectetur adipiscing elit. " * 20, fontsize=10)
    d.save(path)
    d.close()
    return path


def picture() -> Path:
    path = _work / "picture.png"
    im = Image.new("RGB", (600, 400), (240, 240, 250))
    ImageDraw.Draw(im).rectangle((40, 40, 560, 360), outline=(30, 60, 160), width=12)
    im.save(path)
    return path


# ------------------------------------------------------------------------------------------- mouse
def _send(kind, pos: QPoint, buttons=Qt.MouseButton.NoButton, mods=Qt.KeyboardModifier.NoModifier) -> float:
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, QPointF(pos), QPointF(INNER.mapToGlobal(pos)), button, buttons, mods)
    t = time.perf_counter()
    QApplication.sendEvent(INNER, ev)
    return (time.perf_counter() - t) * 1000


def click(pos: QPoint, mods=Qt.KeyboardModifier.NoModifier) -> None:
    _send(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton, mods)
    _send(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.NoButton, mods)
    pump(40)


def drag(a: QPoint, b: QPoint, label: str, steps: int = 12) -> None:
    times = [_send(QEvent.Type.MouseButtonPress, a, Qt.MouseButton.LeftButton)]
    for i in range(1, steps + 1):
        p = QPoint(int(a.x() + (b.x() - a.x()) * i / steps), int(a.y() + (b.y() - a.y()) * i / steps))
        times.append(_send(QEvent.Type.MouseMove, p, Qt.MouseButton.LeftButton))
        QApplication.processEvents()
    times.append(_send(QEvent.Type.MouseButtonRelease, b))
    TIMES.setdefault(label, []).extend(times)
    pump(60)


def wr(obj) -> object:
    return INNER.pdf_rect_to_widget(obj.page_index, obj.rect)


def obj(oid: str):
    e = edit()
    return e.objects.get(oid) or e.shapes.get(oid) or e.images.get(oid)


def scale() -> float:
    return INNER._scale(0)[0]  # noqa: SLF001  widget px per PDF point


def rect_t(o) -> tuple[float, float, float, float]:
    r = o.rect
    return (r.x, r.y, r.x + r.w, r.y + r.h)


# -------------------------------------------------------------------------------------------- zoom
def audit_zoom() -> None:
    area = "zoom"
    vp = CANVAS.viewport()
    W._apply_fit_mode(ZoomMode.FIT_WIDTH)  # noqa: SLF001
    pump(300)
    lay = INNER._layouts[0]  # noqa: SLF001
    check(area, "Fit Width: page as wide as the window (±48 px)", abs(lay.width() - (vp.width() - 2 * INNER._side_pad)) <= 48,  # noqa: SLF001
          (lay.width(), vp.width()))
    W._apply_fit_mode(ZoomMode.FIT_PAGE)  # noqa: SLF001
    pump(300)
    lay = INNER._layouts[0]  # noqa: SLF001
    check(area, "Fit Page: whole page fits the window", lay.height() <= vp.height() and lay.width() <= vp.width(),
          (lay.size(), vp.size()))

    def settle(label: str) -> float:
        t = time.perf_counter()
        while time.perf_counter() - t < 3.0:
            pump(15)
            if not INNER._tiles_pending and INNER._cache.keys():  # noqa: SLF001
                break
        ms = (time.perf_counter() - t) * 1000
        TIMES.setdefault(label, []).append(ms)
        return ms

    zooms = [INNER.zoom]
    for _ in range(6):
        CANVAS.zoom_in()
        settle("zoom in → sharp page")
        zooms.append(INNER.zoom)
    check(area, "Zoom In: larger every step", all(b > a for a, b in zip(zooms, zooms[1:])), [round(z, 2) for z in zooms])
    label = W._zoom_label.text()  # noqa: SLF001
    check(area, "zoom percentage shown matches", label == f"{INNER.zoom * 100:.0f}%", (label, INNER.zoom))
    for _ in range(30):
        CANVAS.zoom_out()
        pump(10)
    settle("zoom out → sharp page")
    check(area, "Zoom Out stops at the minimum (no 0 or negative zoom)", 0.09 < INNER.zoom <= 0.5, INNER.zoom)
    for _ in range(40):
        CANVAS.zoom_in()
        pump(5)
    settle("zoom to maximum → sharp page")
    check(area, "Zoom In stops at the maximum (800 %)", INNER.zoom <= 8.0 + 1e-6 and INNER.zoom >= 4.0, INNER.zoom)

    # Ctrl + wheel keeps the point under the pointer in place
    W._apply_fit_mode(ZoomMode.FIT_WIDTH)  # noqa: SLF001
    pump(200)
    CANVAS.verticalScrollBar().setValue(INNER.page_top(1) + 150)
    pump(200)
    pos = QPoint(int(vp.width() * 0.62), int(vp.height() * 0.4))
    worst = 0.0
    for delta in (120, 120, 120, -120, -120, -120):
        before = INNER.widget_to_pdf(INNER.mapFrom(vp, pos))
        ev = QWheelEvent(QPointF(pos), QPointF(vp.mapToGlobal(pos)), QPoint(0, 0), QPoint(0, delta),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
        t = time.perf_counter()
        QApplication.sendEvent(vp, ev)
        settle("Ctrl+wheel step → sharp page")
        TIMES.setdefault("Ctrl+wheel event handling", []).append((time.perf_counter() - t) * 1000)
        after = INNER.widget_to_pdf(INNER.mapFrom(vp, pos))
        if before and after and INNER._layouts[0].width() > vp.width():  # noqa: SLF001  (narrower pages are centred)
            d = 999.0 if before[0] != after[0] else ((before[1].x - after[1].x) ** 2 + (before[1].y - after[1].y) ** 2) ** 0.5
            worst = max(worst, d)
    check(area, "Ctrl+wheel zooms around the pointer (point under it moves ≤ 3 pt)", worst <= 3.0, round(worst, 2))
    worst_ms = max(TIMES["zoom in → sharp page"])
    check(area, "each zoom step shows the sharp page within 1.5 s", worst_ms < 1500, round(worst_ms))


# ----------------------------------------------------------------------------------------- objects
HANDLES = ["nw", "n", "ne", "w", "e", "sw", "s", "se"]
OUTWARD = {"nw": (-1, -1), "n": (0, -1), "ne": (1, -1), "w": (-1, 0), "e": (1, 0), "sw": (-1, 1), "s": (0, 1), "se": (1, 1)}


def audit_object(area: str, oid: str, keep_aspect_on_corners: bool = False) -> None:
    CANVAS.set_tool(EditTool.SELECT)
    o = obj(oid)
    click(wr(o).center())
    check(area, "click selects it", edit().selection == [oid], edit().selection)
    s = scale()
    px = 24
    for name in HANDLES:
        o = obj(oid)
        before = rect_t(o)
        r = wr(o)
        hp = dict(zip(HANDLES, INNER._handle_points(r)))[name]  # noqa: SLF001
        dx, dy = OUTWARD[name]
        drag(QPoint(int(hp[0]), int(hp[1])), QPoint(int(hp[0] + dx * px), int(hp[1] + dy * px)), f"{area} resize drag")
        after = rect_t(obj(oid))
        moved = [after[i] - before[i] for i in range(4)]  # x0, y0, x1, y1
        exp = px / s
        want = [dx * exp if dx < 0 else 0, dy * exp if dy < 0 else 0, dx * exp if dx > 0 else 0, dy * exp if dy > 0 else 0]
        if keep_aspect_on_corners:
            # pictures keep their proportions (Shift: free stretch): the side opposite the handle stays,
            # a side handle widens the other direction evenly about the centre
            grew = (after[2] - after[0]) > (before[2] - before[0]) and (after[3] - after[1]) > (before[3] - before[1])
            ratio_b = (before[2] - before[0]) / max(1e-6, before[3] - before[1])
            ratio_a = (after[2] - after[0]) / max(1e-6, after[3] - after[1])
            if len(name) == 2:
                fixed = [i for i in range(4) if want[i] == 0]
            else:
                fixed = [{"n": 3, "s": 1, "w": 2, "e": 0}[name]]
            ok = grew and abs(ratio_a - ratio_b) < 0.03 * ratio_b and all(abs(moved[i]) < 0.8 for i in fixed)
            check(area, f"handle {name}: grows outwards, keeps proportions, opposite side fixed", ok,
                  [round(m, 1) for m in moved])
        else:
            ok = all(abs(moved[i] - want[i]) <= 2.5 for i in range(4))  # ±2 px: press point rounding
            check(area, f"handle {name}: only the dragged edge(s) move, by the mouse distance", ok,
                  {"moved": [round(m, 1) for m in moved], "expected": [round(w, 1) for w in want]})
        edit().undo()
        pump(40)
        check(area, f"handle {name}: Undo restores the size", all(abs(a - b) < 0.05 for a, b in zip(rect_t(obj(oid)), before)),
              rect_t(obj(oid)))
        click(wr(obj(oid)).center())
    # move by dragging the middle
    o = obj(oid)
    before = rect_t(o)
    c = wr(o).center()
    drag(c, c + QPoint(40, 30), f"{area} move drag")
    after = rect_t(obj(oid))
    dxp, dyp = after[0] - before[0], after[1] - before[1]
    size_same = abs((after[2] - after[0]) - (before[2] - before[0])) < 0.05 and abs((after[3] - after[1]) - (before[3] - before[1])) < 0.05
    check(area, "drag moves it by the mouse distance, size unchanged",
          abs(dxp - 40 / s) <= 2.5 and abs(dyp - 30 / s) <= 2.5 and size_same, (round(dxp, 1), round(dyp, 1)))
    edit().undo()
    pump(40)
    # grabbing a handle a few pixels off its centre must not make the edge jump to the pointer
    click(wr(obj(oid)).center())
    o = obj(oid)
    before = rect_t(o)
    hp = dict(zip(HANDLES, INNER._handle_points(wr(o))))["e"]  # noqa: SLF001
    a = QPoint(int(hp[0]) - 4, int(hp[1]) + 3)
    drag(a, a + QPoint(1, 0), f"{area} handle grab", steps=1)
    jump = rect_t(obj(oid))[2] - before[2]
    check(area, "grabbing a handle off-centre: no jump (1 px move = ~1 px change)", abs(jump) <= 2.2 / s + 0.3,
          round(jump, 2))
    if rect_t(obj(oid)) != before:
        edit().undo()  # only when the grab changed something (never undo the object's creation)
        pump(40)


def audit_objects() -> dict[str, str]:
    e = edit()
    tb = e.create_text_box(0, Rect(90, 150, 170, 44), text="Resizable box", auto_match=False)
    e.editing_object_id = None
    rect = e.create_shape(0, Rect(320, 150, 130, 80), "rectangle")
    ell = e.create_shape(0, Rect(90, 290, 130, 80), "ellipse")
    img = ImageBox(page_index=0, rect=Rect(320, 290, 150, 100), source_path=str(picture()))
    e.add_image(img)
    e.clear_selection()
    pump(200)
    ids = {"text box": tb.object_id, "rectangle": rect.object_id, "ellipse": ell.object_id, "picture": img.object_id}
    for name, oid in ids.items():
        audit_object(f"object:{name}", oid, keep_aspect_on_corners=(name == "picture"))
    return ids


def audit_multiselect(ids: dict[str, str]) -> None:
    area = "multi-select"
    e = edit()
    a, b = ids["rectangle"], ids["ellipse"]
    click(wr(obj(a)).center())
    click(wr(obj(b)).center(), Qt.KeyboardModifier.ControlModifier)
    check(area, "Ctrl+click adds to the selection", set(e.selection) == {a, b}, e.selection)
    ra, rb = rect_t(obj(a)), rect_t(obj(b))
    c = wr(obj(a)).center()
    drag(c, c + QPoint(30, 20), "multi-select move drag")
    da = [rect_t(obj(a))[i] - ra[i] for i in range(2)]
    db = [rect_t(obj(b))[i] - rb[i] for i in range(2)]
    check(area, "dragging one moves all selected by the same distance",
          all(abs(x - y) < 0.05 for x, y in zip(da, db)) and abs(da[0]) > 1, (da, db))
    W._delete()  # noqa: SLF001  (Delete key / Edit ▸ Delete)
    pump(40)
    check(area, "Delete removes all selected", obj(a) is None and obj(b) is None)
    e.undo()
    pump(40)
    check(area, "Undo brings all of them back", obj(a) is not None and obj(b) is not None)
    e.clear_selection()
    pump(30)
    # keyboard nudge moves the selection 1 pt (Shift: 10 pt)
    click(wr(obj(a)).center())
    r0 = rect_t(obj(a))
    from PySide6.QtTest import QTest

    INNER.setFocus()
    QTest.keyClick(INNER, Qt.Key.Key_Right)
    QTest.keyClick(INNER, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    pump(40)
    r1 = rect_t(obj(a))
    check(area, "arrow keys nudge the selected object", r1[0] > r0[0] and r1[1] > r0[1], (r0[:2], r1[:2]))
    # rubber band on empty paper around every object: text box, shapes and the picture are selected
    e.clear_selection()
    pump(30)
    s0 = INNER.pdf_rect_to_widget(0, Rect(60, 120, 1, 1)).topLeft()
    s1 = INNER.pdf_rect_to_widget(0, Rect(520, 430, 1, 1)).topLeft()
    drag(s0, s1, "rubber band", steps=8)
    check(area, "rubber band selects text boxes, shapes and pictures", set(e.selection) == set(ids.values()),
          sorted(e.selection))


# ---------------------------------------------------------------------------------------- compress
def audit_compress() -> None:
    from core.convert import compress as cz

    area = "compress"
    src = _work / "photo.pdf"
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    im = Image.new("RGB", (1800, 1200))
    px = im.load()
    for y in range(1200):  # a smooth photo-like picture (JPEG-friendly), 600 ppi at 3 in wide
        for x in range(0, 1800, 3):
            px[x, y] = px[min(x + 1, 1799), y] = px[min(x + 2, 1799), y] = ((x * 7) % 256, (y * 5) % 256, (x + y) % 256)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    p.insert_image(fitz.Rect(72, 300, 72 + 216, 300 + 144), stream=buf.getvalue())
    p.insert_text((72, 100), "Text must stay text: Monograph PDF 0.5.0", fontsize=12)
    p.draw_rect(fitz.Rect(72, 120, 300, 160), color=(0, 0, 1), width=2)
    d.save(src)
    text0 = d[0].get_text()
    draws0 = len(d[0].get_drawings())
    d.close()
    data = src.read_bytes()

    def shown_ppi(out: bytes) -> tuple[float, str]:
        with fitz.open("pdf", out) as o:
            info = o[0].get_image_info(xrefs=True)[0]
            filt = o.xref_get_key(info["xref"], "Filter")[1]
            return info["width"] / ((info["bbox"][2] - info["bbox"][0]) / 72), filt

    for mode, kw, ppi in (("balanced", {}, 150), ("smallest", {}, 110), ("custom", {"ppi": 200, "quality": 80}, 200),
                          ("custom", {"ppi": 50, "quality": 10}, 100)):
        res = cz.compress(data, mode=mode, **kw)
        out = res.data if hasattr(res, "data") else res.best.data
        got, filt = shown_ppi(out)
        label = f"{mode} {kw or ''}".strip()
        check(area, f"{label}: picture at {ppi} ppi (±3)", abs(got - ppi) <= 3, round(got, 1))
        check(area, f"{label}: re-encoded as JPEG", "DCT" in filt, filt)
        with fitz.open("pdf", out) as o:
            check(area, f"{label}: text unchanged", o[0].get_text() == text0)
            check(area, f"{label}: vector drawing unchanged", len(o[0].get_drawings()) == draws0)
            check(area, f"{label}: smaller than the original", len(out) < len(data), (len(out), len(data)))
    # a reachable and an unreachable target size
    for target, reachable in ((len(data) // 3, True), (2_000, False)):
        res = cz.compress(data, mode="target", target_bytes=target)
        out = res.data if hasattr(res, "data") else res.best.data
        met = bool(getattr(res, "target_met", len(out) <= target))
        if reachable:
            check(area, f"target {target:,} B: met and really at or below it", met and len(out) <= target, (met, len(out)))
        else:
            check(area, f"target {target:,} B (impossible): reported as not met", not met and len(out) > target, (met, len(out)))


# ---------------------------------------------------------------------------------------- password
def audit_password() -> None:
    from core.document import open_document
    from core.security.ops import EncryptionSettings, PermissionFlags, apply_password_protection, remove_password_protection
    from ui import main_window as mw

    area = "password"
    src = make_doc("for-password.pdf")
    plain = open_document(src)
    prot = _work / "protected.pdf"
    apply_password_protection(plain, prot, EncryptionSettings(
        user_password="open-123", owner_password="owner-456",
        permissions=PermissionFlags(print=True, modify=False, copy=False, annotate=True, fill_forms=True,
                                    assemble=False, print_hq=False)))
    plain.close()
    with fitz.open(prot) as d:
        check(area, "protected copy needs a password", d.needs_pass)
        perms0 = d.permissions if d.authenticate("open-123") else None

    answers: list[str] = []

    class FakeDialog(mw.PasswordDialog):
        def exec(self):  # noqa: A003
            if not answers:
                return self.DialogCode.Rejected
            self._edit.setText(answers.pop(0))  # noqa: SLF001
            return self.DialogCode.Accepted

    real = mw.PasswordDialog
    mw.PasswordDialog = FakeDialog
    try:
        answers[:] = []
        ok = W.open_path(prot)
        pump(100)
        check(area, "Cancel at the password prompt opens nothing", not ok)
        answers[:] = ["wrong", "still-wrong", "owner-456"]
        ok = W.open_path(prot)
        pump(200)
        check(area, "wrong passwords are refused, the right one opens it", ok and not answers, answers)
        e = edit()
        e.create_text_box(0, Rect(72, 200, 200, 40), text="Added after unlocking", auto_match=False)
        e.mark_dirty()
        W.save_document()
        pump(300)
    finally:
        mw.PasswordDialog = real
    with fitz.open(prot) as d:
        check(area, "saved file still needs the open password", d.needs_pass)
        check(area, "wrong password still refused", not d.authenticate("nope"))
        level = d.authenticate("open-123")
        check(area, "open password still opens it", bool(level))
        check(area, "the edit is in the saved file", "Added after unlocking" in d[0].get_text())
        check(area, "permissions unchanged", d.permissions == perms0, (d.permissions, perms0))
    W.close_document(save_session=False)
    pump(100)
    doc = open_document(prot, password="owner-456")
    plain_out = _work / "unprotected.pdf"
    remove_password_protection(doc, plain_out, password="owner-456")
    doc.close()
    with fitz.open(plain_out) as d:
        check(area, "Remove Protection: opens without a password", not d.needs_pass and not d.is_encrypted)
        check(area, "Remove Protection: content kept", "Added after unlocking" in d[0].get_text())
    doc = open_document(prot, password="open-123")
    try:
        remove_password_protection(doc, _work / "should-not-exist.pdf", password="open-123")
        refused = False
    except Exception:  # noqa: BLE001
        refused = True
    doc.close()
    check(area, "Remove Protection with only the open password of a restricted PDF is refused",
          refused and not (_work / "should-not-exist.pdf").exists())


def main() -> int:
    path = make_doc()
    assert W.open_path(path)
    pump(400)
    for name, fn in (("zoom", audit_zoom), ("objects", None), ("compress", audit_compress), ("password", audit_password)):
        try:
            if name == "objects":
                ids = audit_objects()
                audit_multiselect(ids)
            else:
                fn()
        except Exception as exc:  # noqa: BLE001
            import traceback

            check(name, "audit ran", False, traceback.format_exc()[-600:])
    timing = {k: {"n": len(v), "median_ms": round(statistics.median(v), 1), "max_ms": round(max(v), 1)}
              for k, v in TIMES.items() if v}
    (OUT / "ui_interactions.json").write_text(json.dumps({"checks": RESULTS, "timing": timing},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"CHECKS {len(RESULTS)}  FAILED {len(failed)}")
    for r in failed:
        print(f"  [{r['area']}] {r['check']}: {r['detail']}")
    print("TIMING (ms):")
    for k, v in timing.items():
        print(f"  {k:42s} n={v['n']:4d} median={v['median_ms']:7.1f} max={v['max_ms']:7.1f}")
    for e in list(getattr(W, "_sessions", [])):
        e.edit.dirty = False
    W.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
