"""Verify a macOS release folder made by scripts/package_macos.sh. Exit 1 on any FAIL.

    python scripts/packaging/verify_macos_release.py <release dir> [--mode development|production]

Every check is reported PASS / FAIL / SKIP (with the reason) and written to
<release dir>/verification.json. The app is checked as it comes out of each format: extracted from
the .zip, from the mounted .dmg and from the expanded .pkg payload.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import macos_installer as mi  # noqa: E402
import macos_ocr_sources as mos  # noqa: E402

IDENTIFIER = mi.IDENTIFIER
APP_NAME = "MonographPDF.app"


class Report:
    def __init__(self) -> None:
        self.results: list[dict] = []

    def add(self, area: str, name: str, ok: bool | None, detail: str = "") -> None:
        status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        self.results.append({"area": area, "check": name, "status": status, "detail": detail})
        print(f"[{status}] {area}: {name}" + (f" — {detail}" if detail else ""))

    @property
    def failed(self) -> bool:
        return any(r["status"] == "FAIL" for r in self.results)


def run(*cmd: str, check: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=check, env=env)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree(app: Path) -> dict[str, str]:
    """relative path → 'L:<target>' / 'F:<mode>' / 'D' (to compare formats exactly)."""
    out = {}
    for p in sorted(app.rglob("*")):
        rel = p.relative_to(app).as_posix()
        if p.is_symlink():
            out[rel] = "L:" + os.readlink(p)
        elif p.is_dir():
            out[rel] = "D"
        else:
            out[rel] = f"F:{oct(p.stat().st_mode & 0o777)}"
    return out


# --------------------------------------------------------------------------- app


def check_app(rep: Report, app: Path, where: str, version: str, mode: str) -> None:
    area = f"app ({where})"
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    rep.add(area, "bundle identifier", info.get("CFBundleIdentifier") == IDENTIFIER, info.get("CFBundleIdentifier", ""))
    rep.add(area, "version", info.get("CFBundleShortVersionString") == version, info.get("CFBundleShortVersionString", ""))
    rep.add(area, "base names match the bundle file name",
            info.get("CFBundleName") == "MonographPDF" and info.get("CFBundleDisplayName") == "MonographPDF")
    strings = app / "Contents" / "Resources" / "en.lproj" / "InfoPlist.strings"
    rep.add(area, "Finder / Spotlight name 'Monograph PDF'", info.get("LSHasLocalizedDisplayName") is True
            and strings.is_file() and '"CFBundleDisplayName" = "Monograph PDF";' in strings.read_text(encoding="utf-8"))
    rep.add(area, "minimum macOS", info.get("LSMinimumSystemVersion") == mi.MIN_MACOS, info.get("LSMinimumSystemVersion", ""))
    icon = info.get("CFBundleIconFile", "")
    rep.add(area, "app icon", bool(icon) and (app / "Contents" / "Resources" / icon).is_file(), icon)
    types = info.get("CFBundleDocumentTypes") or []
    rep.add(area, "opens PDF documents", any("com.adobe.pdf" in t.get("LSItemContentTypes", []) for t in types))
    exe = app / "Contents" / "MacOS" / info.get("CFBundleExecutable", "MonographPDF")
    archs = run("lipo", "-archs", str(exe)).stdout.split()
    rep.add(area, "architecture", mi.HOST_ARCH in archs, " ".join(archs))
    strict = run("codesign", "--verify", "--deep", "--strict", str(app))
    rep.add(area, "codesign --deep --strict", strict.returncode == 0, strict.stderr.strip()[-200:])
    meta = run("codesign", "-dvv", str(app)).stderr
    if mode == "production":
        rep.add(area, "Developer ID Application", "Authority=Developer ID Application" in meta)
        rep.add(area, "Hardened Runtime", re.search(r"flags=0x\w+\(.*runtime", meta) is not None)
        rep.add(area, "notarization ticket stapled", run("xcrun", "stapler", "validate", str(app)).returncode == 0)
        gk = run("spctl", "--assess", "--type", "execute", "-vv", str(app))
        rep.add(area, "Gatekeeper accepts", gk.returncode == 0, gk.stderr.strip()[-200:])
    else:
        rep.add(area, "ad-hoc signature (development)", "Signature=adhoc" in meta)
    dangling = [str(p.relative_to(app)) for p in app.rglob("*") if p.is_symlink() and not p.exists()]
    rep.add(area, "no dangling symlinks", not dangling, ", ".join(dangling[:5]))
    home = str(Path.home()) + "/"
    leak = run("grep", "-rlF", "--", home, str(app)).stdout.strip()
    rep.add(area, "no builder home path", not leak, leak[:200])
    ocr = app / "Contents" / "Resources" / "engines" / "ocr"
    inventory = ROOT / "scripts" / "packaging" / "macos_ocr_sources.json"
    problems = mos.check(ocr, inventory, None)
    if mode == "production":  # re-signed for notarization: bytes were checked before signing
        problems = [p for p in problems if "differs from the inventory" not in p]
    rep.add(area, "OCR inventory and licenses", not problems, "; ".join(problems[:3]))
    tessdata = app / "Contents" / "Resources" / "models" / "tessdata"
    env = {k: v for k, v in os.environ.items() if not k.startswith("DYLD_")}
    langs = run(str(ocr / "bin" / "tesseract"), "--list-langs", "--tessdata-dir", str(tessdata), env=env)
    found = set(langs.stdout.split()) if langs.returncode == 0 else set()
    rep.add(area, "bundled Tesseract runs (eng, jpn, osd)", {"eng", "jpn", "osd"} <= found, " ".join(sorted(found)))


# --------------------------------------------------------------------------- formats


def check_zip(rep: Report, zip_path: Path, version: str, mode: str, work: Path) -> Path | None:
    dest = work / "zip"
    dest.mkdir()
    ok = run("ditto", "-x", "-k", str(zip_path), str(dest)).returncode == 0
    app = dest / APP_NAME
    rep.add("zip", "extracts with ditto", ok and app.is_dir())
    if not app.is_dir():
        return None
    check_app(rep, app, "zip", version, mode)
    return app


def check_dmg(rep: Report, dmg: Path, version: str, mode: str, work: Path) -> Path | None:
    rep.add("dmg", "checksum valid (hdiutil verify)", run("hdiutil", "verify", str(dmg)).returncode == 0)
    mnt = work / "dmg_mnt"
    mnt.mkdir()
    att = run("hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mnt), str(dmg))
    if att.returncode != 0:
        rep.add("dmg", "mounts", False, att.stderr.strip())
        return None
    try:
        apps = mnt / "Applications"
        rep.add("dmg", "Applications shortcut", apps.is_symlink() and os.readlink(apps) == "/Applications")
        rep.add("dmg", "background artwork", (mnt / ".background" / "background.tiff").is_file())
        rep.add("dmg", "Finder window layout stored", (mnt / ".DS_Store").is_file())
        rep.add("dmg", "volume icon", (mnt / ".VolumeIcon.icns").is_file())
        visible = sorted(p.name for p in mnt.iterdir() if not p.name.startswith("."))
        rep.add("dmg", "only the app and Applications are visible", visible == ["Applications", APP_NAME], ", ".join(visible))
        copy = work / "dmg_app"
        copy.mkdir()
        run("ditto", str(mnt / APP_NAME), str(copy / APP_NAME), check=True)
    finally:
        run("hdiutil", "detach", str(mnt))
    if mode == "production":
        rep.add("dmg", "Developer ID signature", "Developer ID Application" in run("codesign", "-dvv", str(dmg)).stderr)
        rep.add("dmg", "notarization ticket stapled", run("xcrun", "stapler", "validate", str(dmg)).returncode == 0)
        gk = run("spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "-vv", str(dmg))
        rep.add("dmg", "Gatekeeper accepts", gk.returncode == 0, gk.stderr.strip()[-200:])
    check_app(rep, copy / APP_NAME, "dmg", version, mode)
    return copy / APP_NAME


def check_pkg(rep: Report, pkg: Path, version: str, mode: str, work: Path) -> Path | None:
    exp = work / "pkg"
    if run("pkgutil", "--expand-full", str(pkg), str(exp)).returncode != 0:
        rep.add("pkg", "expands", False)
        return None
    dist = ET.parse(exp / "Distribution").getroot()
    title = (dist.findtext("title") or "")
    rep.add("pkg", "title shows product and version", title == f"Monograph PDF {version}", title)
    for tag in ("welcome", "readme", "license", "conclusion", "background", "background-darkAqua"):
        el = dist.find(tag)
        present = el is not None and (exp / "Resources" / el.get("file", "")).is_file()
        rep.add("pkg", f"{tag} screen / artwork", present, el.get("file", "") if el is not None else "missing")
    lic = exp / "Resources" / "LICENSE.txt"
    rep.add("pkg", "license is the project license (AGPL-3.0)",
            lic.is_file() and "GNU AFFERO GENERAL PUBLIC LICENSE" in lic.read_text(encoding="utf-8", errors="replace"))
    os_min = dist.find("volume-check/allowed-os-versions/os-version")
    rep.add("pkg", "requires macOS 13+", os_min is not None and os_min.get("min") == mi.MIN_MACOS)
    opts = dist.find("options")
    rep.add("pkg", "Apple silicon host check", opts is not None and opts.get("hostArchitectures") == mi.HOST_ARCH)
    rep.add("pkg", "no install scripts required", opts is not None and opts.get("require-scripts") == "false")
    check = dist.find("installation-check")
    rep.add("pkg", "refuses to downgrade a newer installed app",
            check is not None and "compareVersions" in (dist.findtext("script") or ""))
    domains = dist.find("domains")
    rep.add("pkg", "installs for all users only (/Applications)",
            domains is not None and domains.get("enable_localSystem") == "true"
            and domains.get("enable_currentUserHome") == "false" and domains.get("enable_anywhere") == "false")
    refs = [r for r in dist.iter("pkg-ref") if r.get("installKBytes")]
    kb = int(refs[0].get("installKBytes")) if refs else 0
    rep.add("pkg", "required disk space declared", kb > 0, f"{kb / 1024:.0f} MB")
    comp = next(exp.glob("*.pkg"), None)
    info = ET.parse(comp / "PackageInfo").getroot() if comp else None
    rep.add("pkg", "package identifier", info is not None and info.get("identifier") == IDENTIFIER,
            info.get("identifier", "") if info is not None else "")
    rep.add("pkg", "package version", info is not None and info.get("version") == version)
    rep.add("pkg", "install location /", info is not None and info.get("install-location") == "/")
    rep.add("pkg", "no relocation into moved copies",
            info is not None and info.get("relocatable") == "false"
            and not list(info.find("relocate") if info.find("relocate") is not None else []))
    scripts = info.find("scripts") if info is not None else None
    rep.add("pkg", "no pre/postinstall scripts", scripts is None or len(list(scripts)) == 0)
    app_bundle = [b for b in (info.iter("bundle") if info is not None else [])
                  if b.get("path") == f"./Applications/{APP_NAME}" and b.get("id") == IDENTIFIER]
    upgrades = [b.get("id") for b in info.findall("upgrade-bundle/bundle")] if info is not None else []
    versioned = [b.get("id") for b in info.findall("bundle-version/bundle")] if info is not None else []
    rep.add("pkg", "upgrade replaces the installed app (no downgrade)",
            bool(app_bundle) and IDENTIFIER in upgrades and IDENTIFIER in versioned)
    payload = (comp / "Payload" / "Applications" / APP_NAME) if comp else None
    rep.add("pkg", "payload is /Applications/MonographPDF.app", payload is not None and payload.is_dir())
    sig = run("pkgutil", "--check-signature", str(pkg)).stdout
    if mode == "production":
        rep.add("pkg", "Developer ID Installer signature", "Developer ID Installer" in sig)
        rep.add("pkg", "notarization ticket stapled", run("xcrun", "stapler", "validate", str(pkg)).returncode == 0)
        gk = run("spctl", "--assess", "--type", "install", "-vv", str(pkg))
        rep.add("pkg", "Gatekeeper accepts", gk.returncode == 0, gk.stderr.strip()[-200:])
    else:
        rep.add("pkg", "unsigned (development)", "no signature" in sig)
    if payload is None or not payload.is_dir():
        return None
    check_app(rep, payload, "pkg payload", version, mode)
    return payload


def check_release_files(rep: Report, out: Path, version: str, mode: str) -> None:
    sums = out / "SHA256SUMS.txt"
    if not sums.is_file():
        rep.add("release", "SHA256SUMS.txt", False, "missing")
        return
    bad, listed = [], []
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        listed.append(name.strip())
        p = out / name.strip()
        if not p.is_file() or sha256(p) != digest:
            bad.append(name.strip())
    wanted = {f"MonographPDF_{version}_macOS.{ext}" for ext in ("zip", "dmg", "pkg")}
    rep.add("release", "SHA256SUMS.txt matches every file", not bad, ", ".join(bad))
    rep.add("release", "checksums cover pkg, dmg, zip", wanted <= set(listed))
    sources = out / f"MonographPDF_{version}_macOS_OCR_Corresponding_Source"
    inv = ROOT / "scripts" / "packaging" / "macos_ocr_sources.json"
    copyleft = [c for c in json.loads(inv.read_text(encoding="utf-8"))["components"] if c["copyleft"]]
    missing = [c["name"] for c in copyleft
               if not (sources / c["corresponding_source"]["archive"]).is_file()
               or sha256(sources / c["corresponding_source"]["archive"]) != c["corresponding_source"]["sha256"]]
    rep.add("release", "corresponding source for copyleft OCR libraries", not missing and bool(copyleft),
            ", ".join(missing) or ", ".join(c["name"] for c in copyleft))
    rep.add("release", "source inventory shipped with the source", (sources / "THIRD_PARTY_OCR_SOURCES.json").is_file())
    rep.add("release", "listed in SHA256SUMS.txt",
            all(f"{sources.name}/{c['corresponding_source']['archive']}" in listed for c in copyleft))


def verify(out: Path, mode: str) -> Report:
    rep = Report()
    version = (ROOT / "versions" / "macos.txt").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory(prefix="monographpdf-verify-") as tmp:
        work = Path(tmp)
        apps = {}
        for kind, fn in (("zip", check_zip), ("dmg", check_dmg), ("pkg", check_pkg)):
            path = out / f"MonographPDF_{version}_macOS.{kind}"
            if not path.is_file():
                rep.add(kind, "file present", False, path.name)
                continue
            apps[kind] = fn(rep, path, version, mode, work)
        trees = {k: tree(v) for k, v in apps.items() if v is not None}
        if len(trees) == 3:
            first = trees["zip"]
            same = all(t == first for t in trees.values())
            links = sum(1 for v in first.values() if v.startswith("L:"))
            rep.add("formats", "identical app in zip, dmg and pkg (files, modes, symlinks)", same, f"{links} symlinks")
        check_release_files(rep, out, version, mode)
    (out / "verification.json").write_text(json.dumps({"version": version, "mode": mode, "results": rep.results},
                                                      indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rep


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    mode = "development"
    if "--mode" in argv:
        mode = argv[argv.index("--mode") + 1]
    rep = verify(Path(argv[0]), mode)
    counts = {s: sum(r["status"] == s for r in rep.results) for s in ("PASS", "FAIL", "SKIP")}
    print(f"macOS release verification ({mode}): " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
