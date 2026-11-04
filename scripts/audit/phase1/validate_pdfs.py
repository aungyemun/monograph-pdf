"""Independent PDF validation (pypdf + qpdf via pikepdf), never PyMuPDF.

    <validators venv python> validate_pdfs.py <folder or file> [...] [--password PW ...] --json out.json

For each PDF: qpdf structural check (errors / warnings), open + page count + page sizes + rotations,
encryption (method, key length), AcroForm fields (name, type, value), annotations per page (subtype),
outline count, link count, text sample per page (pypdf extraction).
"""
import json, sys, traceback
from pathlib import Path

import pikepdf
import pypdf

args = sys.argv[1:]
out = Path(args[args.index("--json") + 1]); passwords = []
i = 0
targets = []
while i < len(args):
    a = args[i]
    if a == "--json":
        i += 2; continue
    if a == "--password":
        passwords.append(args[i + 1]); i += 2; continue
    targets.append(Path(a)); i += 1
files = []
for t in targets:
    files += sorted(t.rglob("*.pdf")) if t.is_dir() else [t]


def qpdf_check(p):
    for pw in [""] + passwords:
        try:
            with pikepdf.open(p, password=pw) as pdf:
                problems = pdf.check()
                enc = pdf.encryption if pdf.is_encrypted else None
                return {"opened": True, "password_used": bool(pw), "problems": [str(x) for x in problems][:20],
                        "encrypted": pdf.is_encrypted,
                        "encryption": None if enc is None else {"R": enc.R, "V": enc.V, "bits": enc.bits,
                                                                 "stream": str(enc.stream_method), "string": str(enc.string_method)},
                        "pages": len(pdf.pages)}
        except pikepdf.PasswordError:
            continue
        except Exception as e:  # noqa: BLE001
            return {"opened": False, "error": f"{type(e).__name__}: {e}"[:300]}
    return {"opened": False, "error": "password required"}


def pypdf_info(p):
    try:
        r = pypdf.PdfReader(str(p), strict=False)
        if r.is_encrypted:
            ok = False
            for pw in [""] + passwords:
                try:
                    if r.decrypt(pw):
                        ok = True; break
                except Exception:  # noqa: BLE001
                    pass
            if not ok:
                return {"opened": True, "decrypted": False}
        pages = []
        for n, pg in enumerate(r.pages):
            annots = []
            for a in (pg.get("/Annots") or []):
                try:
                    annots.append(str(a.get_object().get("/Subtype")))
                except Exception:  # noqa: BLE001
                    annots.append("?")
            try:
                text = (pg.extract_text() or "")[:300]
            except Exception as e:  # noqa: BLE001
                text = f"<extract failed: {type(e).__name__}>"
            mb = pg.mediabox
            pages.append({"size": [round(float(mb.width), 1), round(float(mb.height), 1)], "rotate": int(pg.get("/Rotate", 0) or 0),
                          "annots": annots, "text": text})
        fields = {}
        try:
            for name, f in (r.get_fields() or {}).items():
                fields[name] = {"type": str(f.get("/FT")), "value": str(f.get("/V")) if f.get("/V") is not None else None}
        except Exception as e:  # noqa: BLE001
            fields = {"<error>": str(e)}
        try:
            outline = len(r.outline)
        except Exception:  # noqa: BLE001
            outline = None
        links = sum(1 for p_ in pages for a in p_["annots"] if a == "/Link")
        return {"opened": True, "decrypted": True, "page_count": len(r.pages), "pages": pages, "fields": fields,
                "outline_top_level": outline, "links": links, "metadata": {k: str(v) for k, v in (r.metadata or {}).items()},
                "has_xmp": r.xmp_metadata is not None, "attachments": list((r.attachments or {}).keys())}
    except Exception as e:  # noqa: BLE001
        return {"opened": False, "error": f"{type(e).__name__}: {e}"[:300], "trace": traceback.format_exc()[-400:]}


report = {}
for f in files:
    report[str(f)] = {"bytes": f.stat().st_size, "qpdf": qpdf_check(f), "pypdf": pypdf_info(f)}
out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
bad = [k for k, v in report.items() if not v["qpdf"].get("opened") or not v["pypdf"].get("opened") or v["qpdf"].get("problems")]
print(f"validated {len(report)} PDFs; problems in {len(bad)}")
for k in bad:
    v = report[k]
    print(" -", Path(k).name, "| qpdf:", v["qpdf"].get("error") or v["qpdf"].get("problems"), "| pypdf:", v["pypdf"].get("error", "ok"))
