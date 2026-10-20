"""Open-check every PDF in a folder (default: the Windows Downloads folder) with the same engine the app uses.

Usage: env\\Scripts\\python.exe scripts\\check_pdfs.py [folder] [--password PW]

Read-only: originals are never modified. For each file it works on a temporary copy and reports pages, encryption,
text/scan status, rendering, a rotate+save round trip and the time taken. Exit code 0 unless a file that is a valid
PDF fails one of the checks (damaged files are reported as REFUSED, which is the expected outcome).
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from core.windows_paths import get_downloads_dir  # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_one(src: Path, password: str = "") -> dict:
    """Run the checks on a temporary copy of ``src``; returns a result dict (never raises)."""
    res: dict = {"file": src.name, "status": "PASS", "notes": []}
    before = _sha(src)
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "copy.pdf"
        shutil.copy2(src, copy)
        try:
            doc = fitz.open(copy.as_posix())
        except Exception as exc:  # noqa: BLE001
            res.update(status="REFUSED", notes=[f"cannot open: {exc}"])
            return res
        try:
            if doc.needs_pass and not doc.authenticate(password):
                res.update(status="LOCKED", notes=["password required"])
                return res
            res["pages"] = doc.page_count
            res["encrypted"] = bool(doc.is_encrypted)
            res["permissions_copy"] = bool(doc.permissions & fitz.PDF_PERM_COPY)
            n = min(doc.page_count, 5)
            chars = 0
            for i in range(n):
                pg = doc[i]
                chars += len(pg.get_text())
                pix = pg.get_pixmap(dpi=36)
                assert pix.width > 0 and pix.height > 0
            res["scanned_like"] = chars == 0 and any(doc[i].get_images() for i in range(n))
            res["fields"] = sum(1 for i in range(n) for _ in (doc[i].widgets() or []))
            if doc.page_count:
                doc[0].set_rotation((doc[0].rotation + 90) % 360)
                out = Path(td) / "rot.pdf"
                doc.save(out.as_posix(), garbage=1)
                chk = fitz.open(out.as_posix())
                assert chk.page_count == doc.page_count
                assert chk[0].rotation == doc[0].rotation
                chk.close()
        except Exception as exc:  # noqa: BLE001
            res.update(status="FAIL", notes=[f"{type(exc).__name__}: {exc}"])
        finally:
            doc.close()
    res["seconds"] = round(time.perf_counter() - t0, 2)
    if _sha(src) != before:
        res.update(status="FAIL", notes=res["notes"] + ["ORIGINAL WAS MODIFIED"])
    return res


def main(argv: list[str]) -> int:
    pw = ""
    if "--password" in argv:
        i = argv.index("--password")
        pw = argv[i + 1]
        del argv[i : i + 2]
    folder = Path(argv[0]) if argv else Path(get_downloads_dir())
    pdfs = sorted(folder.glob("*.pdf"))
    print(f"{len(pdfs)} PDF(s) in {folder}")
    bad = 0
    for p in pdfs:
        r = check_one(p, pw)
        extra = ", ".join(f"{k}={r[k]}" for k in ("pages", "encrypted", "scanned_like", "fields", "seconds") if k in r)
        print(f"{r['status']:8} {r['file']}  {extra}  {'; '.join(r['notes'])}")
        bad += r["status"] == "FAIL"
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
