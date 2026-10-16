"""Release documentation and installer rules: User Guide structure and wording, no development
paths in installed docs, uninstall.exe and a complete, safe uninstall in the Inno Setup script."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "USER_GUIDE.md"
ISS = ROOT / "installer" / "MonographPDF.iss"
INSTALLED_DOCS = [GUIDE, ROOT / "README.md", ROOT / "LICENSE.md", ROOT / "THIRD_PARTY_NOTICES.md",
                  ROOT / "SECURITY.md", ROOT / "CHANGELOG.md", ROOT / "INSTALLATION.md"]

SECTIONS = [
    "Contents", "Getting started", "The Monograph PDF window", "Viewing", "Password-protected PDFs", "Saving",
    "Editing", "Forms, tables and layout", "OCR (text recognition)", "Organize pages", "Convert", "Page design",
    "Protect, redact and sign", "Printing", "Keyboard shortcuts", "Current limitations", "Troubleshooting",
    "Additional documentation",
]


def _guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def test_user_guide_sections_in_order():
    headings = re.findall(r"^## (.+)$", _guide(), flags=re.M)
    assert headings == SECTIONS


def test_user_guide_contents_links_resolve():
    text = _guide()
    anchors = {_slug(h) for h in re.findall(r"^#{2,3} (.+)$", text, flags=re.M)}
    links = re.findall(r"\]\(#([^)]+)\)", text)
    assert len(links) >= len(SECTIONS) - 1
    assert not [a for a in links if a not in anchors]


def test_user_guide_is_end_user_text():
    text = _guide()
    for dev in ("dev_launch", "setup_env", "python -m", "project folder", "Getting help (contributors)",
                "confidence-gated", "foundation", "inspector", "runtime/sessions", "runtime/temp", "sidecar",
                "contributors"):
        assert dev not in text, dev
    assert "— —" not in text and not re.search(r"\w ?-- ?\w", text)  # doubled dashes between words
    assert not re.search(r"\b(\w+) \1\b", text, flags=re.I), re.search(r"\b(\w+) \1\b", text, flags=re.I)
    assert "→" not in text  # menu paths use ▸
    assert "colour" not in text and "centre" not in text  # US spelling, as in the app
    for term in ("Start menu", "File Explorer", "Properties panel", "Navigation panel", "context toolbar", "Save As"):
        assert term in text, term
    assert "Start Menu" not in text and "properties panel" not in text


def test_user_guide_keeps_key_information():
    text = _guide()
    for fact in (
        "does not collect usage data", "Opening a PDF never changes it", "visual** signatures",
        "not certificate-based", "AES-256", "Protection is never removed without the correct password",
        "truly removes the content", "never downloaded" if "never downloaded" in text else "Nothing is downloaded",
        "do **not** need to disable antivirus", "SmartScreen", "Japanese vertical writing",
        "Windows 10 and Windows 11 (64-bit)", "Ctrl+Shift+M", "F11", "Ctrl+/", "macros are never run",
        "uninstall.exe", "Your own documents", "remove your **settings**",
    ):
        assert fact in text, fact


def test_installed_docs_have_no_development_paths():
    pattern = re.compile(r"[A-Za-z]:\\Users\\(?!Public)|Software[ ]testing|/home/|/root/|\\\\wsl")
    for doc in INSTALLED_DOCS:
        hits = pattern.findall(doc.read_text(encoding="utf-8"))
        assert not hits, (doc.name, hits)


def _iss() -> str:
    return ISS.read_text(encoding="utf-8-sig")


def _section(name: str) -> list[str]:
    text = _iss()
    m = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[\w+\]\s*$)", text, flags=re.M | re.S)
    assert m, name
    return [ln for ln in m.group(1).splitlines() if ln.strip() and not ln.lstrip().startswith(";")]


def test_installer_ships_and_registers_uninstall_exe():
    files = "\n".join(_section("Files"))
    assert 'DestName: "uninstall.exe"' in files
    code = _iss()
    assert "'UninstallString', '\"' + Exe + '\"'" in code
    assert "'QuietUninstallString'" in code
    launcher = (ROOT / "installer" / "uninstall_launcher.cs").read_text(encoding="utf-8")
    assert "unins000.exe" in launcher and "WaitForExit" in launcher and "process.ExitCode" in launcher


def test_start_menu_has_guide_and_no_uninstall_shortcut():
    icons = _section("Icons")
    assert not [ln for ln in icons if "{uninstallexe}" in ln]
    guide = [ln for ln in icons if "User Guide" in ln]
    assert guide and 'Parameters: "--user-guide"' in guide[0] and "USER_GUIDE.md" not in guide[0]
    # Earlier versions' Start menu entries are removed on upgrade
    install_delete = "\n".join(_section("InstallDelete"))
    assert "Uninstall {#AppName}.lnk" in install_delete and "User Guide.lnk" in install_delete


def test_every_registry_entry_is_removed_on_uninstall():
    text = _iss()
    lines = [ln for ln in _section("Registry") if ln.startswith("Root:")]
    # Entries generated by the OtherExt macro
    macro = re.findall(r"'(Root: HKA;.*?)'\s*\+\s*NewLine", text)
    macro = [m.replace("' + AppExe + '", "{#AppExe}").replace("' + CapKey + '", "{#CapKey}")
              .replace("' + Ext + '", ".ext").replace("' + ProgIdOther + '", "{#ProgIdOther}") for m in macro]
    assert len(macro) == 3
    entries = []
    for ln in lines + macro:
        subkey = re.search(r'Subkey: "([^"]+)"', ln).group(1)
        subkey = subkey.replace("{#CapKey}", r"Software\Monograph PDF\Capabilities").replace("{#AppRegKey}", r"Software\Monograph PDF")
        flags = (re.search(r"Flags: ([^;]+)", ln) or [None, ""])[1]
        entries.append((subkey, flags))
    deleted_keys = [k for k, f in entries if "uninsdeletekey" in f and "ifempty" not in f]
    orphans = [k for k, f in entries
               if "uninsdelete" not in f and not any(k == d or k.startswith(d + "\\") for d in deleted_keys)]
    assert not orphans, orphans


def test_uninstall_handles_running_app_user_data_and_failures():
    code = _iss()
    assert "function InitializeUninstall" in code and "RunningCopies(False)" in code and "UninstallSilent" in code
    assert "/REMOVEUSERDATA" in code and "RemoveFolder(ExpandConstant('{userappdata}\\') + DataFolderName)" in code
    assert "Do you also want to remove your Monograph PDF settings?" in code and "MB_DEFBUTTON2" in code
    assert "recent_files.json" in code and "'\\runtime'" in code and "'\\Cache'" in code
    assert "RemoveTempLeftovers" in code and "NotRemoved" in code and "could not be deleted" in code
    # never deletes a folder that contains the installation folder
    assert "IsInside(ExpandConstant('{app}'), Folder)" in code


def test_smoke_test_checks_ocr_and_cleans_up(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    from app.smoke_test import run_smoke_test

    report = tmp_path / "report.json"
    run_smoke_test(["--smoke-test", "--report", str(report)])
    import json

    data = json.loads(report.read_text(encoding="utf-8"))
    assert "ocr" in data["checks"] and data["checks"]["ocr"].get("required", True)
    assert data["checks"]["create_pdf"]["ok"] and data["checks"]["main_window"]["ok"]
    assert not list(tmp_path.glob("monographpdf-smoke-*")), "self-check left its sample folder behind"
