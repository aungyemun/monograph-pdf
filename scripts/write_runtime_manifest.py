"""Write deterministic offline runtime manifest under dist/ (and optionally beside exe)."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dependency_audit import list_accepted  # noqa: E402
from core.product_meta import (  # noqa: E402
    COPYRIGHT_DISPLAY,
    COPYRIGHT_OWNER,
    EXECUTABLE_NAME,
    PRODUCT_DESCRIPTION,
    PRODUCT_NAME,
)
from core.versioning import get_version  # noqa: E402
from engines.probe import probe_all  # noqa: E402


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001
        return None


def build_manifest(*, exe_path: Path | None = None) -> dict:
    version = get_version()
    exe = exe_path or (ROOT / EXECUTABLE_NAME)
    probes = {p.name: {"available": p.available, "detail": p.detail} for p in probe_all()}

    tess_langs = {}
    try:
        from core.ocr.paths import language_files_present, tessdata_dir, tesseract_exe

        tess_langs = language_files_present()
        ocr_exe = tesseract_exe()
        tessdata = tessdata_dir()
    except Exception as exc:  # noqa: BLE001
        ocr_exe, tessdata = None, None
        probes["Tesseract"] = {"available": False, "detail": str(exc)}

    convert_caps = []
    try:
        from core.convert.capabilities import list_capabilities

        convert_caps = [
            {
                "key": c.key,
                "title": c.title,
                "fidelity": getattr(c.fidelity, "value", str(c.fidelity)),
                "implemented": c.implemented,
                "notes": c.notes,
            }
            for c in list_capabilities()
        ]
    except Exception as exc:  # noqa: BLE001
        convert_caps = [{"error": str(exc)}]

    deps = {
        "PySide6": _pkg_version("PySide6"),
        "PyMuPDF": _pkg_version("PyMuPDF"),
        "Pillow": _pkg_version("Pillow"),
        "python-docx": _pkg_version("python-docx"),
        "openpyxl": _pkg_version("openpyxl"),
        "python-pptx": _pkg_version("python-pptx"),
        "packaging": _pkg_version("packaging"),
        "pyinstaller": _pkg_version("pyinstaller"),
    }

    return {
        "product": PRODUCT_NAME,
        "version": version,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "executable": EXECUTABLE_NAME,
        "executable_path": str(exe.relative_to(ROOT)) if exe.is_relative_to(ROOT) else str(exe),
        "copyright": COPYRIGHT_DISPLAY,
        "copyright_owner": COPYRIGHT_OWNER,
        "product_description": PRODUCT_DESCRIPTION,
        "python_runtime_version": platform.python_version(),
        "qt_pyside_version": deps.get("PySide6"),
        "pdf_engines": {
            "PyMuPDF": probes.get("PyMuPDF"),
            "qpdf": probes.get("qpdf"),
        },
        "ocr": {
            "engine": probes.get("Tesseract"),
            "tesseract_exe": str(ocr_exe) if ocr_exe else None,
            "tessdata_dir": str(tessdata) if tessdata else None,
            "languages": tess_langs,
        },
        "conversion_components": convert_caps,
        "dependency_versions": deps,
        "licenses": [
            {
                "name": d.name,
                "license": d.license,
                "redistributable": d.redistributable,
                "offline_ok": d.offline_ok,
            }
            for d in list_accepted()
        ],
        "license_inventory_doc": "licenses/DEPENDENCY_INVENTORY.md",
        "checksums": {
            EXECUTABLE_NAME: _sha256(exe),
        },
        "offline_runtime": True,
        "no_system_python_required": True,
        "bundled_sidecars": {
            "engines/ocr": (ROOT / "engines" / "ocr" / "tesseract.exe").is_file()
            or (ROOT / "engines" / "ocr" / "bin" / "tesseract.exe").is_file(),
            "models/tessdata": (ROOT / "models" / "tessdata").is_dir(),
        },
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_probes": probes,
    }


def main() -> int:
    dist = ROOT / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    exe = ROOT / EXECUTABLE_NAME
    if not exe.is_file():
        alt = dist / EXECUTABLE_NAME
        if alt.is_file():
            exe = alt
    manifest = build_manifest(exe_path=exe)
    out = dist / "runtime_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Stable copy named by version for release staging
    staged = dist / f"runtime_manifest-{manifest['version']}-windows.json"
    staged.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(out)
    print(staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
