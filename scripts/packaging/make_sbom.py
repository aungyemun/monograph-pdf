"""Software bill of materials (CycloneDX 1.5 JSON) for a Monograph PDF release.

    python scripts/packaging/make_sbom.py --out build/installer/MonographPDF_X.Y.Z_SBOM.cdx.json
        [--layout dist/MonographPDF] [--commit <sha>]
    python scripts/packaging/make_sbom.py --check <sbom.json>

Built only from the project's own machine-readable records — no network, no new dependency:

* Python packages shipped in the program: the pins in ``requirements.txt`` / ``requirements-ci.txt``
  (versions) and the license table below (cross-checked against licenses/DEPENDENCY_INVENTORY.md by
  the tests); package URLs ``pkg:pypi/...``;
* corresponding-source components: ``scripts/packaging/third_party_sources.json`` (versions,
  licenses, SHA-256 of the source archives in the source ZIP);
* the OCR engine and language data: ``scripts/ci/ocr_engine_pins.json`` (SHA-256 of every file);
* the runtime parts that come with Python and the wheels (Python, OpenSSL, libffi, the Microsoft
  C/C++ runtime), the PyInstaller bootloader, Inno Setup, the bundled fonts;
* with ``--layout``: SHA-256 of Monograph PDF's own program files in that build.

The document is deterministic for a commit: serial number derived from version and commit, timestamp
from the commit time (or SOURCE_DATE_EPOCH). License identifiers are SPDX where one exists;
``LicenseRef-`` names otherwise (Microsoft's redistributable runtime, the Inno Setup License).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = "1.5"

# Python distributions inside MonographPDF.exe's _internal folder -> SPDX license expression
PYPI_LICENSES = {
    "PySide6": "LGPL-3.0-only", "PyMuPDF": "AGPL-3.0-only", "packaging": "Apache-2.0 OR BSD-2-Clause",
    "python-docx": "MIT", "openpyxl": "MIT", "python-pptx": "MIT", "Pillow": "MIT-CMU", "pdf2docx": "GPL-3.0-only",
    "opencv-python-headless": "Apache-2.0", "numpy": "BSD-3-Clause", "fonttools": "MIT", "fire": "Apache-2.0",
    "termcolor": "MIT", "lxml": "BSD-3-Clause", "typing_extensions": "PSF-2.0", "et_xmlfile": "MIT",
    "XlsxWriter": "BSD-2-Clause", "colorama": "BSD-3-Clause",
}
# Build and test tools (never shipped) are not part of the SBOM of the release.
NOT_SHIPPED = {"pytest", "pytest-qt", "pyinstaller", "pytest-timeout", "pyinstaller-hooks-contrib", "altgraph",
               "pefile", "pywin32-ctypes", "pluggy", "iniconfig", "cryptography", "cffi", "pycparser"}

RUNTIME_PARTS = [
    # name, version, SPDX / LicenseRef, supplier, purl, description
    ("Python", "3.11.9", "PSF-2.0", "Python Software Foundation", "pkg:generic/python@3.11.9", "language runtime"),
    ("OpenSSL (libcrypto, libssl)", "3.0.13", "Apache-2.0", "The OpenSSL Project", "pkg:generic/openssl@3.0.13",
     "hashlib; HTTPS for update checks and approved problem reports"),
    ("libffi", "3.4", "MIT", "libffi authors", "pkg:generic/libffi@3.4", "ctypes"),
    ("Microsoft Visual C++ / Universal C runtime", "14.x", "LicenseRef-Microsoft-VC-Redistributable", "Microsoft",
     None, "C/C++ runtime DLLs shipped by Python, PySide6 and NumPy wheels (system libraries)"),
    ("PyInstaller bootloader", "6.11.1", "GPL-2.0-or-later WITH Bootloader-exception", "PyInstaller team",
     "pkg:pypi/pyinstaller@6.11.1", "MonographPDF.exe launcher"),
    ("Inno Setup", "6.7.1", "LicenseRef-Inno-Setup", "Jordan Russell, Martijn Laan", None,
     "Setup.exe and the uninstaller unins000.exe"),
    ("Noto Sans, Noto Serif, Noto Sans CJK JP", "", "OFL-1.1", "Google LLC, Adobe", None, "fallback fonts"),
]
OWN_FILES = ["MonographPDF.exe", "uninstall.exe", "MonographPDFUpdater.exe"]


def _pins(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([\w.]+)", line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _license(expr: str) -> list[dict]:
    if expr.startswith("LicenseRef-"):
        return [{"license": {"name": expr}}]
    if " " not in expr:
        return [{"license": {"id": expr}}]
    return [{"expression": expr}]


def _spdx_like(text: str) -> str:
    """third_party_sources.json licenses are SPDX already, some with a note in parentheses."""
    return re.sub(r"\s*\(.*?\)\s*$", "", text).strip()


def build(version: str, commit: str, epoch: int, layout: Path | None) -> dict:
    pins = {**_pins(ROOT / "requirements-ci.txt"), **_pins(ROOT / "requirements.txt")}
    components: list[dict] = []
    for name, lic in sorted(PYPI_LICENSES.items(), key=lambda kv: kv[0].lower()):
        ver = pins[name]
        components.append({"type": "library", "bom-ref": f"pkg:pypi/{name.lower()}@{ver}", "name": name, "version": ver,
                           "purl": f"pkg:pypi/{name.lower()}@{ver}", "licenses": _license(lic), "scope": "required"})
    sources = json.loads((ROOT / "scripts" / "packaging" / "third_party_sources.json").read_text(encoding="utf-8"))
    for comp in sources["components"]:
        if comp["id"] in ("monograph-pdf", "pymupdf", "pdf2docx", "pyside6"):
            continue  # the application itself / already listed as Python packages
        version_text = str(comp.get("version", "")).split(" ")[0]
        entry = {"type": "library", "bom-ref": f"source:{comp['id']}", "name": comp["name"], "version": version_text,
                 "licenses": _license(_spdx_like(comp["license"])), "scope": "required"}
        hashes = [{"alg": "SHA-256", "content": f["sha256"]} for f in comp.get("files", []) if f.get("sha256")]
        if hashes:
            entry["externalReferences"] = [{"type": "source-distribution", "url": u, "hashes": hashes}
                                           for f in comp["files"] for u in f.get("urls", [])[:1]]
        components.append(entry)
    pins_ocr = json.loads((ROOT / "scripts" / "ci" / "ocr_engine_pins.json").read_text(encoding="utf-8"))
    components.append({
        "type": "application", "bom-ref": "ocr:tesseract", "name": "Tesseract OCR (Windows x64, MSYS2 MinGW-w64 build)",
        "version": pins_ocr["tesseract_version"], "licenses": _license("Apache-2.0"), "scope": "required",
        "description": "engines/ocr; libraries keep their own licenses (THIRD_PARTY_NOTICES.md)",
        "components": [{"type": "file", "bom-ref": f"ocr:engine/{n}", "name": f"engines/ocr/{n}",
                        "hashes": [{"alg": "SHA-256", "content": h}]} for n, h in sorted(pins_ocr["engine"].items())],
    })
    components.append({
        "type": "data", "bom-ref": "ocr:tessdata_fast", "name": "tessdata_fast (eng, jpn, osd)", "version": "4.1.0",
        "licenses": _license("Apache-2.0"), "scope": "required",
        "components": [{"type": "file", "bom-ref": f"ocr:tessdata/{n}", "name": f"models/tessdata/{n}",
                        "hashes": [{"alg": "SHA-256", "content": h}]} for n, h in sorted(pins_ocr["tessdata"].items())],
    })
    for name, ver, lic, supplier, purl, desc in RUNTIME_PARTS:
        entry = {"type": "library" if "Setup" not in name else "application", "bom-ref": "runtime:" + re.sub(r"\W+", "-", name.lower()).strip("-"),
                 "name": name, "supplier": {"name": supplier}, "licenses": _license(lic), "description": desc,
                 "scope": "required"}
        if ver:
            entry["version"] = ver
        if purl:
            entry["purl"] = purl
        components.append(entry)
    fonts = ROOT / "resources" / "fonts"
    for f in sorted(fonts.glob("*.[ot]tf")):
        components[-1].setdefault("components", []).append(
            {"type": "file", "bom-ref": f"font:{f.name}", "name": f"resources/fonts/{f.name}",
             "hashes": [{"alg": "SHA-256", "content": _sha256(f)}]})
    app = {"type": "application", "bom-ref": "monograph-pdf", "name": "Monograph PDF", "version": version,
           "supplier": {"name": "Aung Ye Mun"}, "licenses": _license("AGPL-3.0-or-later"),
           "purl": f"pkg:github/aungyemun/monograph-pdf@v{version}",
           "externalReferences": [{"type": "vcs", "url": "https://github.com/aungyemun/monograph-pdf"}]}
    if commit:
        app["properties"] = [{"name": "monograph:commit", "value": commit}]
    if layout is not None:
        app["components"] = [{"type": "file", "bom-ref": f"own:{n}", "name": n,
                              "hashes": [{"alg": "SHA-256", "content": _sha256(layout / n)}]}
                             for n in OWN_FILES if (layout / n).is_file()]
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/aungyemun/monograph-pdf/sbom/{version}/{commit}")
    return {
        "bomFormat": "CycloneDX", "specVersion": SPEC, "serialNumber": f"urn:uuid:{serial}", "version": 1,
        "metadata": {"timestamp": datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "tools": {"components": [{"type": "application", "name": "make_sbom.py",
                                               "description": "Monograph PDF release tooling"}]},
                     "component": app},
        "components": components,
        "dependencies": [{"ref": "monograph-pdf", "dependsOn": [c["bom-ref"] for c in components]}],
    }


def check(doc: dict) -> list[str]:
    """Structural checks of the CycloneDX document (the subset of the schema this tool produces)."""
    problems = []
    if doc.get("bomFormat") != "CycloneDX" or doc.get("specVersion") != SPEC:
        problems.append("not a CycloneDX 1.5 document")
    if not re.fullmatch(r"urn:uuid:[0-9a-f-]{36}", str(doc.get("serialNumber", ""))):
        problems.append("serialNumber must be a urn:uuid")
    meta = doc.get("metadata", {})
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", str(meta.get("timestamp", ""))):
        problems.append("metadata.timestamp must be an ISO 8601 UTC time")
    refs: list[str] = []

    def walk(items, where):
        for c in items:
            ref = c.get("bom-ref")
            if not ref:
                problems.append(f"{where}: component without bom-ref ({c.get('name')})")
            refs.append(ref)
            if not c.get("name") or c.get("type") not in ("application", "library", "file", "data", "framework"):
                problems.append(f"{where}: {ref}: name and a valid type are required")
            for h in c.get("hashes", []):
                if h.get("alg") != "SHA-256" or not re.fullmatch(r"[0-9a-f]{64}", h.get("content", "")):
                    problems.append(f"{ref}: invalid hash")
            if c.get("type") in ("application", "library", "data") and not c.get("licenses"):
                problems.append(f"{ref}: no license")
            for lic in c.get("licenses", []):
                if not (("license" in lic and ("id" in lic["license"] or "name" in lic["license"])) or "expression" in lic):
                    problems.append(f"{ref}: malformed license entry")
            walk(c.get("components", []), ref)

    app = meta.get("component", {})
    walk([app], "metadata")
    walk(doc.get("components", []), "components")
    dupes = sorted({r for r in refs if refs.count(r) > 1})
    if dupes:
        problems.append(f"duplicate bom-ref: {dupes}")
    known = set(refs)
    for dep in doc.get("dependencies", []):
        for r in [dep.get("ref")] + dep.get("dependsOn", []):
            if r not in known:
                problems.append(f"dependency on unknown bom-ref {r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--layout", type=Path)
    ap.add_argument("--commit")
    ap.add_argument("--check", type=Path)
    a = ap.parse_args(argv)
    if a.check:
        problems = check(json.loads(a.check.read_text(encoding="utf-8")))
        print("SBOM check " + ("FAILED:\n  " + "\n  ".join(problems) if problems else "passed"))
        return 1 if problems else 0
    if not a.out:
        ap.error("--out or --check is required")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    commit = a.commit or _git("rev-parse", "HEAD")
    epoch_text = _git("show", "-s", "--format=%ct", commit) if commit else ""
    epoch = int(epoch_text) if epoch_text.isdigit() else int(os.environ.get("SOURCE_DATE_EPOCH", "315532800"))
    doc = build(version, commit, epoch, a.layout)
    problems = check(doc)
    if problems:
        print("SBOM FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    n = sum(1 for _ in _iter(doc["components"]))
    print(f"wrote {a.out} (CycloneDX {SPEC}, {len(doc['components'])} components, {n} entries incl. files)")
    return 0


def _iter(items):
    for c in items:
        yield c
        yield from _iter(c.get("components", []))


if __name__ == "__main__":
    sys.exit(main())
