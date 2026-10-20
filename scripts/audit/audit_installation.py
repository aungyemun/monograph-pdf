"""Read-only audit of an installed Monograph PDF copy against a build output.

Usage:
    python scripts/audit/audit_installation.py --installed "C:/Program Files/Monograph PDF"
        --build dist/MonographPDF --out reports/audit/qa_evidence/<dir>/installation_audit.json

Nothing is modified: files are hashed, the registry is read, shortcuts are resolved.
Windows only for the registry / shortcut sections (skipped elsewhere).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

INSTALLER_ONLY = {"unins000.exe", "unins000.dat", "uninstall.exe", "installed_files.txt"}
TEXT_EXT = {".txt", ".json", ".md", ".cfg", ".ini", ".toml", ".spec", ".py", ".xml", ".qss", ".conf"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _dev_path_re() -> re.Pattern[bytes]:
    """The development checkout's own path (in either slash style) or a personal user folder."""
    root = str(PROJECT_ROOT)
    forms = {root, root.replace("\\", "/"), root.replace("\\", "\\\\")}
    alts = [re.escape(f.encode("utf-8")) for f in forms if f]
    alts.append(rb"[A-Za-z]:\\\\?Users\\\\?[^\\\\\"/]+\\\\?(?:Downloads|Desktop|Documents)")
    return re.compile(b"|".join(alts), re.I)


DEV_PATH_RE = _dev_path_re()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def tree(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def registry_section() -> dict:
    if sys.platform != "win32":
        return {"skipped": "not Windows"}
    import winreg

    out: dict = {}
    hives = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}

    def dump(hive, sub, depth=3):
        try:
            k = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            return None
        res = {"values": {}, "keys": {}}
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
                res["values"][n or "(default)"] = v if isinstance(v, (str, int)) else repr(v)
                i += 1
            except OSError:
                break
        if depth:
            i = 0
            while True:
                try:
                    n = winreg.EnumKey(k, i)
                    res["keys"][n] = dump(hive, sub + "\\" + n, depth - 1)
                    i += 1
                except OSError:
                    break
        return res

    for hn, h in hives.items():
        sec = {}
        for view in ("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
                     "Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"):
            d = dump(h, view, depth=1)
            if not d:
                continue
            for name, body in d["keys"].items():
                vals = (body or {}).get("values", {})
                dn = str(vals.get("DisplayName", ""))
                if "Monograph" in dn or "PDF Editor" in dn or "64FC0D97" in name:
                    sec[f"{view}\\{name}"] = vals
        for sub in ("Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\MonographPDF.exe",
                    "Software\\Classes\\Applications\\MonographPDF.exe",
                    "Software\\Classes\\.pdf\\OpenWithProgids",
                    "Software\\Monograph PDF",
                    "Software\\Aung Ye Mun"):
            d = dump(h, sub)
            if d:
                sec[sub] = d
        try:
            ck = winreg.OpenKey(h, "Software\\Classes", 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    n = winreg.EnumKey(ck, i)
                    if n.lower().startswith(("monograph", "pdfeditor", "pdf_editor")):
                        sec["Software\\Classes\\" + n] = dump(h, "Software\\Classes\\" + n)
                    i += 1
                except OSError:
                    break
        except OSError:
            pass
        reg_apps = dump(h, "Software\\RegisteredApplications", depth=0)
        if reg_apps:
            sec["RegisteredApplications"] = {k: v for k, v in reg_apps["values"].items()
                                             if "Monograph" in k or "PDF Editor" in k}
        out[hn] = sec
    return out


def shortcut_section() -> dict:
    if sys.platform != "win32":
        return {"skipped": "not Windows"}
    import subprocess

    roots = [os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%PUBLIC%\Desktop"),
             os.path.join(os.path.expanduser("~"), "Desktop"),
             os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")]
    found = []
    for r in roots:
        rp = Path(r)
        if not rp.exists():
            continue
        for lnk in rp.rglob("*.lnk"):
            s = str(lnk).lower()
            if "monograph" in s or "pdf editor" in lnk.name.lower():
                found.append(str(lnk))
    resolved = []
    if found:
        # Paths are handed over through an environment variable: extra arguments after
        # -Command would be concatenated into the script text, not bound to $args.
        ps = ("$s=New-Object -ComObject WScript.Shell; foreach($p in ($env:MPDF_LNKS -split '\\|')){"
              "$l=$s.CreateShortcut($p); [pscustomobject]@{path=$p;target=$l.TargetPath;args=$l.Arguments;"
              "workdir=$l.WorkingDirectory;icon=$l.IconLocation} | ConvertTo-Json -Compress}")
        env = dict(os.environ, MPDF_LNKS="|".join(found))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, env=env)
        if not r.stdout.strip():
            resolved.append({"error": r.stderr.strip()[:500], "found": found})
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                d = json.loads(line)
                d["target_exists"] = Path(d["target"]).exists() if d.get("target") else False
                resolved.append(d)
    return {"shortcuts": resolved}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--installed", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    inst, build = Path(a.installed), Path(a.build)
    it, bt = tree(inst), tree(build)
    report: dict = {"installed": str(inst), "build": str(build)}

    only_inst = sorted(set(it) - set(bt))
    only_build = sorted(set(bt) - set(it))
    differing = []
    for rel in sorted(set(it) & set(bt)):
        pi, pb = it[rel], bt[rel]
        if pi.stat().st_size != pb.stat().st_size or sha256(pi) != sha256(pb):
            differing.append(rel)
    report["file_compare"] = {
        "installed_count": len(it), "build_count": len(bt),
        "only_in_installed": only_inst,
        "only_in_installed_unexpected": [r for r in only_inst if r not in INSTALLER_ONLY],
        "only_in_build": only_build, "content_differs": differing,
        "installed_bytes": sum(p.stat().st_size for p in it.values()),
    }

    man = inst / "installed_files.txt"
    if man.exists():
        listed = [l.strip() for l in man.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
        report["owned_manifest"] = {
            "listed": len(listed),
            "listed_but_missing": [l for l in listed if l not in it],
            "present_not_listed": [r for r in it if r not in listed and r not in INSTALLER_ONLY],
        }

    byname = defaultdict(list)
    for rel, p in it.items():
        if p.suffix.lower() in (".dll", ".pyd"):
            byname[p.name.lower()].append(rel)
    dups = {}
    for n, rels in byname.items():
        if len(rels) > 1:
            hashes = {r: sha256(it[r]) for r in rels}
            dups[n] = {"paths": rels, "identical": len(set(hashes.values())) == 1,
                       "bytes_each": [it[r].stat().st_size for r in rels]}
    report["duplicate_binaries"] = dups
    report["duplicate_binaries_identical_extra_bytes"] = sum(
        sum(v["bytes_each"]) - max(v["bytes_each"]) for v in dups.values() if v["identical"])

    report["openssl_dlls"] = [r for r in it if re.search(r"lib(crypto|ssl)", r, re.I)]
    report["qt_plugin_dirs"] = sorted({r.split("/")[3] for r in it
                                       if r.startswith("_internal/PySide6/plugins/") and r.count("/") >= 4})
    report["qt_translations"] = len([r for r in it if "/translations/" in r])
    report["ocr"] = {
        "tesseract_exe": [r for r in it if r.lower().endswith("tesseract.exe")],
        "traineddata": sorted(r for r in it if r.endswith(".traineddata")),
    }
    report["licenses_dir_files"] = len([r for r in it if r.startswith("licenses/")])

    leaks = []
    for rel, p in it.items():
        if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 5_000_000:
            m = DEV_PATH_RE.search(p.read_bytes())
            if m:
                leaks.append({"file": rel, "match": m.group(0).decode("utf-8", "replace")})
    report["dev_path_leaks_in_text"] = leaks

    report["largest_files"] = sorted(((r, p.stat().st_size) for r, p in it.items()), key=lambda x: -x[1])[:25]
    top = defaultdict(int)
    for r, p in it.items():
        parts = r.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        top[key] += p.stat().st_size
    report["size_by_component"] = sorted(top.items(), key=lambda x: -x[1])[:30]

    report["registry"] = registry_section()
    report["shortcuts"] = shortcut_section()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    fc = report["file_compare"]
    print(f"installed={fc['installed_count']} build={fc['build_count']} only_inst={len(fc['only_in_installed'])} "
          f"unexpected={len(fc['only_in_installed_unexpected'])} only_build={len(fc['only_in_build'])} "
          f"differ={len(fc['content_differs'])} dups={len(dups)} leaks={len(leaks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
