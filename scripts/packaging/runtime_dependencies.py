"""Windows runtime dependency audit of a built Monograph PDF installation layout.

    python scripts/packaging/runtime_dependencies.py <install-layout folder> [--json OUT] [--check]

Reads the import table (normal and delay-load) of every program file (.exe .dll .pyd) in the layout
with ``pefile`` and classifies every imported DLL:

  bundled        a file of that name is shipped in the layout (the file's own folder, ``_internal``,
                 or the folder of the component that loads it)
  windows        part of every supported Windows (Windows 10 version 1809 or later, x64): an API set
                 (``api-ms-win-*``, ``ext-ms-*``), a core system DLL, or the Universal C Runtime,
                 which is a Windows component since Windows 10
  vc-runtime     Microsoft Visual C++ 2015-2022 runtime (vcruntime140*, msvcp140*, concrt140,
                 vcomp140): not part of Windows; must be bundled or installed with the VC++
                 Redistributable
  dotnet         .NET Framework 4 (mscoree.dll): part of Windows 10 and later (.NET Framework 4.8)
  unresolved     none of the above

With ``--check`` the exit status is 1 if any import is ``unresolved``, a ``vc-runtime`` DLL is
not bundled, or a library outside PySide6 finds a bundled VC++ runtime DLL only through another
package's folder (it would then load only if that package happened to be imported first) — that is,
if a clean supported Windows would need something that is not shipped where the loader looks.
``--place-app-local`` (build step) fixes the last case by copying the newest bundled copy into
``_internal``.
Also checks that every library the 64-bit program loads (``_internal``, ``engines``) is x64.
Nothing is executed. Paths in the output are relative to the layout.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

PE_SUFFIXES = {".exe", ".dll", ".pyd"}
IMAGE_FILE_MACHINE_AMD64 = 0x8664

VC_RUNTIME = ["vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll", "msvcp140.dll",
              "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
              "msvcp140_codecvt_ids.dll", "concrt140.dll", "vcomp140.dll", "vccorlib140.dll"]

# DLLs shipped with every Windows 10 (1809+) / Windows 11 x64 installation in System32. Kept to what
# Monograph PDF's binaries actually import; an import that is neither here nor bundled fails --check,
# so a new dependency is reviewed rather than assumed.
WINDOWS_DLLS = {
    "advapi32.dll", "authz.dll", "bcrypt.dll", "bcryptprimitives.dll", "cabinet.dll", "cfgmgr32.dll",
    "comctl32.dll", "comdlg32.dll", "crypt32.dll", "cryptbase.dll", "cryptnet.dll", "cryptui.dll",
    "d2d1.dll", "d3d11.dll", "d3d12.dll", "d3d9.dll", "d3dcompiler_47.dll", "dbghelp.dll",
    "dcomp.dll", "dnsapi.dll", "dwmapi.dll", "dwrite.dll", "dxgi.dll", "dxva2.dll", "gdi32.dll",
    "gdiplus.dll", "glu32.dll", "hid.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll",
    "kernelbase.dll", "mf.dll", "mfplat.dll", "mfreadwrite.dll", "mpr.dll", "msimg32.dll",
    "msvcrt.dll", "mswsock.dll", "ncrypt.dll", "netapi32.dll", "normaliz.dll", "ntdll.dll",
    "ole32.dll", "oleacc.dll", "oleaut32.dll", "opengl32.dll", "powrprof.dll", "propsys.dll",
    "psapi.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll", "shcore.dll", "shell32.dll",
    "shlwapi.dll", "sspicli.dll", "dwmapi.dll", "urlmon.dll", "user32.dll", "userenv.dll",
    "usp10.dll", "uxtheme.dll", "version.dll", "winhttp.dll", "wininet.dll", "winmm.dll",
    "winspool.drv", "wintrust.dll", "wldap32.dll", "ws2_32.dll", "wtsapi32.dll", "d3d10warp.dll",
    "dxcore.dll", "msvfw32.dll", "avicap32.dll", "avifil32.dll", "ksuser.dll", "mfuuid.dll",
    "comsupp.dll", "ucrtbase.dll", "credui.dll", "shfolder.dll", "imagehlp.dll", "esent.dll",
    "evr.dll", "mscms.dll", "uiautomationcore.dll", "dwrite.dll", "wevtapi.dll", "winusb.dll", "wsock32.dll",
}
API_SET_PATTERNS = ["api-ms-win-*.dll", "ext-ms-*.dll"]
DOTNET = {"mscoree.dll"}


def _imports(path: Path) -> tuple[set[str], int | None]:
    import pefile  # build-time only (installed with PyInstaller)

    try:
        pe = pefile.PE(str(path), fast_load=True)
    except pefile.PEFormatError:
        return set(), None
    try:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
        names = {e.dll.decode("ascii", "replace").lower() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
        names |= {e.dll.decode("ascii", "replace").lower() for e in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", [])}
        return names, pe.FILE_HEADER.Machine
    finally:
        pe.close()


def classify(dll: str, bundled: dict[str, list[str]]) -> str:
    if dll in bundled:
        return "bundled"
    if dll in VC_RUNTIME:
        return "vc-runtime"
    if dll in DOTNET:
        return "dotnet"
    if dll in WINDOWS_DLLS or any(fnmatch.fnmatch(dll, p) for p in API_SET_PATTERNS):
        return "windows"
    return "unresolved"


def audit(layout: Path) -> dict:
    files = sorted(p for p in layout.rglob("*") if p.is_file() and p.suffix.lower() in PE_SUFFIXES)
    bundled: dict[str, list[str]] = {}
    for p in files:
        bundled.setdefault(p.name.lower(), []).append(p.relative_to(layout).as_posix())
    per_file = {}
    not_x64 = []
    dll_users: dict[str, set[str]] = {}
    for p in files:
        rel = p.relative_to(layout).as_posix()
        names, machine = _imports(p)
        if machine is None:
            continue
        if machine != IMAGE_FILE_MACHINE_AMD64:
            not_x64.append(f"{rel} (machine 0x{machine:04x})")
        per_file[rel] = sorted(names)
        for n in names:
            dll_users.setdefault(n, set()).add(rel)
    imports = {}
    for dll, users in sorted(dll_users.items()):
        kind = classify(dll, bundled)
        imports[dll] = {"class": kind, "bundled_at": bundled.get(dll, []), "used_by": len(users),
                        "example_user": sorted(users)[0]}
    vc_users = {d: sorted(dll_users[d]) for d in dll_users if d in VC_RUNTIME}
    # Folders the Windows loader searches for a frozen Monograph PDF: the importing file's own folder
    # and _internal (PyInstaller adds it). Any other location is found only through a folder another
    # package adds at run time (PySide6 adds its own) or because a DLL of that name is already loaded.
    search_dependent: dict[str, list[str]] = {}
    for d, users in vc_users.items():
        homes = {str(Path(b).parent).replace("\\", "/") for b in bundled.get(d, [])}
        for u in users:
            folder = str(Path(u).parent).replace("\\", "/")
            if folder not in homes and "_internal" not in homes:
                search_dependent.setdefault(d, []).append(u)
    vc_unbundled = sorted(d for d in vc_users if d not in bundled)
    unresolved = sorted(d for d, v in imports.items() if v["class"] == "unresolved")
    return {
        "layout_program_files": len(per_file),
        "not_x64": not_x64,
        "imports": imports,
        "vc_runtime_imports": {d: {"bundled_at": bundled.get(d, []), "users": len(u)} for d, u in sorted(vc_users.items())},
        "vc_runtime_not_bundled": vc_unbundled,
        "vc_runtime_search_path_dependent": search_dependent,
        "unresolved": unresolved,
    }


def file_version(path: Path) -> tuple[int, int, int, int]:
    """FileVersion from VS_FIXEDFILEINFO (0.0.0.0 if absent)."""
    import pefile

    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        for fixed in getattr(pe, "VS_FIXEDFILEINFO", None) or []:
            ms, ls = fixed.FileVersionMS, fixed.FileVersionLS
            return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
        return (0, 0, 0, 0)
    finally:
        pe.close()


# Packages whose own folder is on the DLL search path whenever their files load (PySide6 adds its
# folder with os.add_dll_directory before Qt or a Qt plugin is loaded).
SELF_SEARCHING = ("_internal/PySide6/", "_internal/shiboken6/")


def risky_search_dependent(report: dict) -> dict[str, list[str]]:
    return {d: [u for u in users if not u.startswith(SELF_SEARCHING)]
            for d, users in report["vc_runtime_search_path_dependent"].items()
            if any(not u.startswith(SELF_SEARCHING) for u in users)}


def place_app_local(layout: Path) -> list[str]:
    """Copy each VC++ runtime DLL that a library outside PySide6 needs but finds only through another
    package's folder into ``_internal`` (on PyInstaller's search path), using the newest bundled copy.
    Returns the placed files. Nothing is downloaded; only files already in the layout are used."""
    import shutil

    placed = []
    for dll in sorted(risky_search_dependent(audit(layout))):
        copies = [p for p in layout.rglob("*") if p.is_file() and p.name.lower() == dll]
        if not copies:
            continue
        best = max(copies, key=lambda p: (file_version(p), p.as_posix()))
        target = layout / "_internal" / best.name
        shutil.copy2(best, target)
        placed.append(f"{target.relative_to(layout).as_posix()} (from {best.relative_to(layout).as_posix()}, "
                      f"version {'.'.join(map(str, file_version(best)))})")
    return placed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("layout", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--place-app-local", action="store_true",
                    help="copy VC++ runtime DLLs needed outside PySide6 into _internal (build step)")
    a = ap.parse_args(argv)
    if not a.layout.is_dir():
        print(f"not a folder: {a.layout}", file=sys.stderr)
        return 2
    if a.place_app_local:
        for line in place_app_local(a.layout):
            print(f"placed {line}")
    r = audit(a.layout)
    if a.json:
        a.json.write_text(json.dumps(r, indent=2, sort_keys=True), encoding="utf-8")
    counts: dict[str, int] = {}
    for v in r["imports"].values():
        counts[v["class"]] = counts.get(v["class"], 0) + 1
    print(f"program files: {r['layout_program_files']}; imported DLLs by class: "
          + ", ".join(f"{k} {counts[k]}" for k in sorted(counts)))
    for d, v in r["vc_runtime_imports"].items():
        print(f"  VC++ runtime {d}: used by {v['users']} file(s); bundled at {', '.join(v['bundled_at']) or 'NOT BUNDLED'}")
    for d, users in r["vc_runtime_search_path_dependent"].items():
        print(f"  {d} is not next to {len(users)} user(s) nor in _internal, e.g. {users[0]}")
    for d in r["unresolved"]:
        print(f"  UNRESOLVED {d} (e.g. {r['imports'][d]['example_user']})")
    for f in r["not_x64"]:
        print(f"  NOT x64: {f}")
    # The launcher-level helpers (uninstall.exe, MonographPDFUpdater.exe: .NET AnyCPU; unins000.exe:
    # Inno Setup's 32-bit uninstaller) may be 32-bit images; libraries the 64-bit program loads may not.
    lib_not_x64 = [f for f in r["not_x64"] if f.startswith(("_internal/", "engines/"))]
    risky = risky_search_dependent(r)
    for d, users in risky.items():
        print(f"  {d}: found only through another package's folder by {', '.join(users)}")
    bad = bool(r["unresolved"] or r["vc_runtime_not_bundled"] or lib_not_x64 or risky)
    if a.check and bad:
        print("runtime dependency check FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
