"""Check Phase 1 scenario outputs independently (pypdf + qpdf/pikepdf + Pillow; never PyMuPDF).

    <validator python> p1_check.py <out_dir>   -> <out_dir>/check.json, prints a summary
"""
import io
sys_reconf = None
import json
import re
import sys
from pathlib import Path

import pikepdf
import pypdf

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")
OUT = Path(sys.argv[1])
EXP = json.loads((OUT / "expectations.json").read_text(encoding="utf-8"))
results = {}


def norm(v):
    if v is None:
        return ""
    s = str(v)
    return "" if s in ("None",) else s


def all_objects_with(pdf: pikepdf.Pdf, needle: bytes):
    """Where ``needle`` occurs: decoded streams and string values (with the dictionary key)."""
    hits = []
    for obj in pdf.objects:
        try:
            if isinstance(obj, pikepdf.Stream):
                try:
                    data = obj.read_bytes()
                except Exception:  # noqa: BLE001
                    data = obj.read_raw_bytes()
                if needle in data:
                    hits.append(("stream", str(obj.get("/Subtype", obj.get("/Type", "")))))
            if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                for k, v in obj.items():
                    if isinstance(v, pikepdf.String) and needle in bytes(v):
                        hits.append(("key", str(k)))
        except Exception:  # noqa: BLE001
            continue
    try:
        for k, v in pdf.trailer.get("/Info", {}).items():
            if needle in bytes(v):
                hits.append(("key", str(k)))
    except Exception:  # noqa: BLE001
        pass
    return hits


for path, exp in EXP.items():
    p = Path(path); r = {"checks": [], "ok": True}
    def ck(cond, what, detail=""):
        r["checks"].append({"ok": bool(cond), "what": what, "detail": str(detail)[:300]})
        if not cond:
            r["ok"] = False
    if not p.exists():
        ck(False, "output exists"); results[path] = r; continue
    pw = exp.get("password", "")
    # qpdf structural check
    try:
        with pikepdf.open(p, password=pw) as pdf:
            problems = pdf.check()
            ck(not problems, "qpdf --check finds no problems", problems[:5])
            if "encryption_bits" in exp:
                enc = pdf.encryption
                ck(pdf.is_encrypted and enc.bits == exp["encryption_bits"] and enc.R >= 6, f"encrypted AES-{exp['encryption_bits']}",
                   f"R={enc.R} bits={enc.bits} {enc.stream_method}")
            if exp.get("raw_absent"):
                hits = all_objects_with(pdf, exp["raw_absent"].encode())
                allowed = set(exp.get("allow_raw_in", []))
                bad = [h for h in hits if not (h[0] == "key" and h[1] in allowed)]
                ck(not bad, f"'{exp['raw_absent']}' absent from page content and objects", bad)
                if hits and not bad:
                    r["residue_reported_only"] = hits
            if exp.get("no_xmp"):
                ck("/Metadata" not in pdf.Root, "no XMP metadata stream")
            if exp.get("no_metadata"):
                info = {str(k): str(v) for k, v in pdf.trailer.get("/Info", {}).items()}
                personal = {k: v for k, v in info.items() if k in ("/Title", "/Author", "/Subject", "/Keywords", "/Creator")}
                ck(not personal, "no personal document properties", personal)
            if exp.get("no_attachments"):
                names = pdf.Root.get("/Names", {})
                ef = names.get("/EmbeddedFiles") if names else None
                ck(not ef or not ef.get("/Names"), "no embedded files")
            if exp.get("no_javascript"):
                js = [h for h in all_objects_with(pdf, b"JavaScript")] + [("openaction", "")] * ("/OpenAction" in pdf.Root)
                ck(not js, "no JavaScript / OpenAction", js)
            if exp.get("no_annots"):
                n = sum(len(pg.get("/Annots", [])) for pg in pdf.pages)
                ck(n == 0, "no annotations, links or fields left", n)
            if exp.get("no_stale_text"):
                for fname, stale in exp["no_stale_text"].items():
                    found = False
                    for pg in pdf.pages:
                        for a in pg.get("/Annots", []):
                            if str(a.get("/T", "")) == fname and "/AP" in a:
                                n_ap = a.AP.get("/N")
                                if isinstance(n_ap, pikepdf.Stream) and stale.encode() in n_ap.read_bytes():
                                    found = True
                    ck(not found, f"cleared field '{fname}' shows no stale appearance text")
            if "image_region_not_red" in exp:
                from PIL import Image
                spec = exp["image_region_not_red"]; pg = pdf.pages[spec["page"]]
                imgs = list(pg.images.values())
                ck(bool(imgs), "page still has its picture")
                if imgs:
                    im = pikepdf.PdfImage(imgs[0]).as_pil_image().convert("RGB")
                    sx, sy = im.width / 595.0, im.height / 842.0
                    x0, y0, x1, y1 = spec["rect"]
                    box = im.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)))
                    px = list(box.getdata())[::37]
                    red = sum(1 for (rr, g, b) in px if rr > 150 and g < 90 and b < 90) / max(1, len(px))
                    ck(red < 0.02, "redacted picture area holds no original pixels", f"red fraction {red:.3f}")
    except pikepdf.PasswordError:
        ck(False, "opens with the expected password")
    except Exception as e:  # noqa: BLE001
        ck(False, "opens in qpdf", f"{type(e).__name__}: {e}")
    if exp.get("wrong_password"):
        try:
            pikepdf.open(p, password=exp["wrong_password"]).close(); ck(False, "wrong password is rejected")
        except pikepdf.PasswordError:
            ck(True, "wrong password is rejected")
    # pypdf semantic checks
    try:
        rd = pypdf.PdfReader(str(p), strict=False)
        if rd.is_encrypted:
            ck(bool(rd.decrypt(pw)), "pypdf decrypts with the expected password")
        if "pages" in exp:
            ck(len(rd.pages) == exp["pages"], f"page count {exp['pages']}", len(rd.pages))
        for idx, deg in (exp.get("rotate") or {}).items():
            ck(int(rd.pages[int(idx)].get("/Rotate", 0) or 0) % 360 == deg, f"page {int(idx) + 1} rotated {deg}", rd.pages[int(idx)].get("/Rotate"))
        for idx, kinds in (exp.get("annots_on") or {}).items():
            have = [str(a.get_object().get("/Subtype")) for a in (rd.pages[int(idx)].get("/Annots") or [])]
            ck(all(k in have for k in kinds), f"page {int(idx) + 1} annotations {kinds}", have)
        if "outline_top_level" in exp:
            ck(len(rd.outline) == exp["outline_top_level"], "bookmarks kept", len(rd.outline))
        if "min_links" in exp:
            n = sum(1 for pg in rd.pages for a in (pg.get("/Annots") or []) if str(a.get_object().get("/Subtype")) == "/Link")
            ck(n >= exp["min_links"], f"at least {exp['min_links']} links kept", n)
        if "fields" in exp:  # before text extraction, whose font problems must not hide these checks
            got = {k: norm(v.get("/V")) for k, v in (rd.get_fields() or {}).items()}
            for name, want in exp["fields"].items():
                have = got.get(name)
                if want.startswith("!"):
                    ok = have is not None and have != want[1:] and have != ""
                elif "|" in want:
                    ok = have is not None and re.fullmatch(want.replace("/", r"\/"), have) is not None
                else:
                    ok = (have or "") == want
                ck(ok, f"field '{name}' = {want!r}", have)
            exp = {k: v for k, v in exp.items() if k != "fields"}
        for idx, needle in (exp.get("text_has") or {}).items():
            t = rd.pages[int(idx)].extract_text() or ""
            ck(needle.replace(" ", "") in t.replace(" ", "").replace("\n", ""), f"page {int(idx) + 1} text contains '{needle}'", t[:120])
        if exp.get("text_absent"):
            t = " ".join((pg.extract_text() or "") for pg in rd.pages)
            ck(exp["text_absent"] not in t, f"extracted text has no '{exp['text_absent']}'")
        if "fields" in exp:
            got = {k: norm(v.get("/V")) for k, v in (rd.get_fields() or {}).items()}
            for name, want in exp["fields"].items():
                have = got.get(name)
                if want.startswith("!"):
                    ok = have is not None and have != want[1:] and have != ""
                elif "|" in want:
                    ok = have is not None and re.fullmatch(want.replace("/", r"\/"), have) is not None
                else:
                    ok = (have or "") == want
                ck(ok, f"field '{name}' = {want!r}", have)
    except Exception as e:  # noqa: BLE001
        ck(False, "pypdf reads the file", f"{type(e).__name__}: {e}")
    results[path] = r

(OUT / "check.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
n_ok = sum(1 for r in results.values() if r["ok"])
print(f"outputs checked {len(results)}; all checks passed in {n_ok}")
for path, r in results.items():
    for c in r["checks"]:
        if not c["ok"]:
            print(" FAIL", Path(path).name, "|", c["what"], "|", c["detail"])
    if r.get("residue_reported_only"):
        print(" note", Path(path).name, "| residue only in", r["residue_reported_only"])
