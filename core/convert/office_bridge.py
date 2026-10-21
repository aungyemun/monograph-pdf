"""Bridge to an office suite already installed on this PC (Microsoft Office or LibreOffice).

Used for the conversions that need a real word-processor layout engine:

* Word / Excel / PowerPoint / RTF / ODF  ->  PDF   (native export/print path)
* PDF  ->  Word via Microsoft Word's own "PDF Reflow" (optional engine)

Nothing is downloaded and nothing leaves the computer. Microsoft Office is driven
through its COM automation interface from a hidden PowerShell process (no extra
Python packages); LibreOffice through ``soffice --headless``. When neither is
present the caller gets a clear ``UnsupportedConversionError``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core import app_env
from core.convert.capabilities import UnsupportedConversionError
from core.safe_paths import windows_tool

WORD_EXTS = (".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".txt", ".wpd", ".xml", ".htm", ".html", ".mht")
EXCEL_EXTS = (".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".csv")
POWERPOINT_EXTS = (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp")
OFFICE_EXTS = WORD_EXTS + EXCEL_EXTS + POWERPOINT_EXTS

_TIMEOUT_S = 600


@dataclass(frozen=True)
class OfficeAvailability:
    word: bool = False
    excel: bool = False
    powerpoint: bool = False
    libreoffice: str | None = None  # path to soffice

    @property
    def any(self) -> bool:
        return self.word or self.excel or self.powerpoint or bool(self.libreoffice)

    def can_convert(self, ext: str) -> bool:
        ext = ext.lower()
        if self.libreoffice and ext in OFFICE_EXTS:
            return True
        if ext in WORD_EXTS:
            return self.word
        if ext in EXCEL_EXTS:
            return self.excel
        if ext in POWERPOINT_EXTS:
            return self.powerpoint
        return False

    def describe(self) -> str:
        parts = []
        if self.word or self.excel or self.powerpoint:
            apps = [n for n, ok in (("Word", self.word), ("Excel", self.excel), ("PowerPoint", self.powerpoint)) if ok]
            parts.append("Microsoft " + " / ".join(apps))
        if self.libreoffice:
            parts.append("LibreOffice")
        return " and ".join(parts) if parts else "no office suite"


_cache: OfficeAvailability | None = None


def _com_registered(progid: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID"):
            return True
    except OSError:
        return False


def _registered_soffice() -> str | None:
    """soffice.exe of the LibreOffice that Windows has registered (machine-wide installations)."""
    try:
        import winreg
    except ImportError:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\LibreOffice\UNO\InstallPath", 0, winreg.KEY_READ | view) as key:
                folder, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        cand = Path(str(folder)) / "soffice.exe"
        if cand.is_absolute() and cand.is_file():
            return str(cand)
    return None


def _find_soffice() -> str | None:
    if sys.platform.startswith("win"):
        # Only LibreOffice's own installation folders: PATH and the current folder are not
        # searched, so a program named soffice.exe next to a document is never started.
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if not base:
                continue
            cand = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if cand.is_file():
                return str(cand)
        return _registered_soffice()
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return str(Path(found).resolve())
    if sys.platform == "darwin":
        cand = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if cand.is_file():
            return str(cand)
    return None


def office_availability(*, refresh: bool = False) -> OfficeAvailability:
    global _cache
    if _cache is None or refresh:
        if app_env.get("DISABLE_OFFICE") == "1":
            _cache = OfficeAvailability()
        else:
            _cache = OfficeAvailability(
                word=_com_registered("Word.Application"),
                excel=_com_registered("Excel.Application"),
                powerpoint=_com_registered("PowerPoint.Application"),
                libreoffice=_find_soffice(),
            )
    return _cache


# --------------------------------------------------------------------------- COM (PowerShell)

_PS_PREAMBLE = r"""
$ErrorActionPreference = 'Stop'
$src = $env:MONOGRAPH_PDF_SRC
$dst = $env:MONOGRAPH_PDF_DST
# AutomationSecurity = 3 (force-disable): macros never run in files opened for conversion.
function Release($o) { if ($o -ne $null) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($o) } }
"""

_PS_WORD_TO_PDF = _PS_PREAMBLE + r"""
$app = New-Object -ComObject Word.Application
try {
  $app.Visible = $false; $app.DisplayAlerts = 0; $app.AutomationSecurity = 3
  $doc = $app.Documents.Open($src, $false, $true, $false)
  try { $doc.ExportAsFixedFormat($dst, 17, $false, 0, 0, 0, 0, 0, $true, $true, 1, $true, $true, $false) }
  finally { $doc.Close(0); Release $doc }
} finally { $app.Quit(); Release $app }
"""

_PS_EXCEL_TO_PDF = _PS_PREAMBLE + r"""
$app = New-Object -ComObject Excel.Application
try {
  $app.Visible = $false; $app.DisplayAlerts = $false; $app.AutomationSecurity = 3
  $wb = $app.Workbooks.Open($src, 0, $true)
  try { $wb.ExportAsFixedFormat(0, $dst) }
  finally { $wb.Close($false); Release $wb }
} finally { $app.Quit(); Release $app }
"""

_PS_POWERPOINT_TO_PDF = _PS_PREAMBLE + r"""
$app = New-Object -ComObject PowerPoint.Application
try {
  $app.AutomationSecurity = 3
  $pres = $app.Presentations.Open($src, -1, 0, 0)
  try { $pres.SaveAs($dst, 32) }
  finally { $pres.Close(); Release $pres }
} finally { $app.Quit(); Release $app }
"""

_PS_PDF_TO_WORD = _PS_PREAMBLE + r"""
$app = New-Object -ComObject Word.Application
try {
  $app.Visible = $false; $app.DisplayAlerts = 0; $app.AutomationSecurity = 3
  $doc = $app.Documents.Open($src, $false, $true, $false)
  try { $doc.SaveAs2($dst, 16) }
  finally { $doc.Close(0); Release $doc }
} finally { $app.Quit(); Release $app }
"""


def _run_powershell(script: str, src: Path, dst: Path) -> None:
    env = dict(os.environ)
    env["MONOGRAPH_PDF_SRC"] = str(src)
    env["MONOGRAPH_PDF_DST"] = str(dst)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        # Full path to Windows PowerShell; -Command runs this fixed script text only (file names
        # are passed in environment variables, never pasted into the script), so no execution
        # policy change is needed.
        [windows_tool("powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        creationflags=flags,
    )
    if proc.returncode != 0 or not dst.is_file():
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = detail[-1] if detail else f"exit code {proc.returncode}"
        raise RuntimeError(f"Microsoft Office could not convert “{src.name}”: {msg}")


# A fresh, throw-away LibreOffice profile with macros switched off completely: Very High macro
# security with no trusted locations, and macro execution disabled (LibreOffice 6.4 and later).
_LO_NO_MACROS = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


def _run_soffice(soffice: str, src: Path, dst: Path, target: str) -> None:
    with tempfile.TemporaryDirectory(prefix="monographpdf-lo-") as tmp:
        profile = Path(tmp) / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(_LO_NO_MACROS, encoding="utf-8")
        cmd = [
            soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--convert-to",
            target,
            "--outdir",
            tmp,
            str(src),
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, creationflags=flags, cwd=tmp)
        produced = list(Path(tmp).glob(f"{src.stem}.*"))
        produced = [p for p in produced if p.suffix.lower() == "." + target.split(":")[0]]
        if proc.returncode != 0 or not produced:
            raise RuntimeError(f"LibreOffice could not convert “{src.name}”: {(proc.stderr or proc.stdout).strip()[:300]}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced[0]), str(dst))


def convert_office_file_to_pdf(source: Path, destination: Path) -> Path:
    """Word/Excel/PowerPoint/ODF/RTF → PDF with the original print layout."""
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    ext = source.suffix.lower()
    avail = office_availability()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the destination under a temporary name and swapped in only when complete: an
    # existing file of that name is kept if the conversion fails.
    import uuid

    part = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex[:8]}.part.pdf")
    try:
        if ext in WORD_EXTS and avail.word:
            _run_powershell(_PS_WORD_TO_PDF, source, part)
        elif ext in EXCEL_EXTS and avail.excel:
            _run_powershell(_PS_EXCEL_TO_PDF, source, part)
        elif ext in POWERPOINT_EXTS and avail.powerpoint:
            _run_powershell(_PS_POWERPOINT_TO_PDF, source, part)
        elif avail.libreoffice and ext in OFFICE_EXTS:
            _run_soffice(avail.libreoffice, source, part, "pdf")
        else:
            raise UnsupportedConversionError(unavailable_message(ext))
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
    return destination


def convert_pdf_to_docx_with_word(source_pdf: Path, destination: Path) -> Path:
    """PDF → DOCX using Microsoft Word's built-in PDF Reflow (best for flowing text)."""
    avail = office_availability()
    source_pdf = Path(source_pdf).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    if avail.word:
        _run_powershell(_PS_PDF_TO_WORD, source_pdf, destination)
    else:
        raise UnsupportedConversionError("Microsoft Word is not installed on this computer.")
    return destination


def unavailable_message(ext: str = "") -> str:
    kind = {
        **{e: "Microsoft Word" for e in WORD_EXTS},
        **{e: "Microsoft Excel" for e in EXCEL_EXTS},
        **{e: "Microsoft PowerPoint" for e in POWERPOINT_EXTS},
    }.get(ext.lower(), "Microsoft Office")
    return (
        f"Converting this file to PDF needs {kind} or LibreOffice installed on this computer, "
        "and neither was found. Install one of them, or use “Save as PDF” in the application "
        "that created the file."
    )
