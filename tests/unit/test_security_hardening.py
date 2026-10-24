"""Security regressions (0.1.5 audit): untrusted input, programs started, macros, PDF JavaScript,
safe output paths, installer/uninstaller boundaries, release contents and offline behavior."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = [ROOT / d for d in ("app", "core", "engines", "ui")]
ISS = (ROOT / "installer" / "MonographPDF.iss").read_text(encoding="utf-8-sig")
LAUNCHER = (ROOT / "installer" / "uninstall_launcher.cs").read_text(encoding="utf-8")

fitz = pytest.importorskip("fitz")


def _sources():
    for d in SOURCE_DIRS:
        for p in d.rglob("*.py"):
            if "__pycache__" not in p.parts:
                yield p, p.read_text(encoding="utf-8")


# ----------------------------------------------------------------- safe output paths


@pytest.mark.parametrize("name", ["../evil.pdf", "..\\evil.pdf", "sub/evil.pdf", "C:\\Windows\\evil.pdf", "..", "."])
def test_safe_child_rejects_folder_parts(tmp_path, name):
    from core.safe_paths import UnsafePathError, safe_child

    with pytest.raises(UnsafePathError):
        safe_child(tmp_path, name)


def test_safe_child_cleans_names_and_never_overwrites(tmp_path):
    from core.safe_paths import safe_child

    assert safe_child(tmp_path, "CON.pdf").name == "_CON.pdf"
    assert safe_child(tmp_path, 'a<b>:c"|?*.pdf').name == "a_b__c____.pdf"
    first = safe_child(tmp_path, "part.pdf")
    first.write_bytes(b"user file")
    second = safe_child(tmp_path, "part.pdf")
    assert second.name == "part (2).pdf" and second.parent == tmp_path
    assert first.read_bytes() == b"user file"


def _doc_with_bookmarks(path: Path) -> Path:
    doc = fitz.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), f"page {i + 1}")
    doc.set_toc([[1, "../../escape", 1], [1, "C:\\Windows\\System32\\x", 2], [1, "CON", 3]])
    doc.save(path)
    doc.close()
    return path


def test_split_by_bookmarks_stays_in_folder_and_keeps_existing_files(tmp_path):
    from core.document import open_document
    from core.organize.split import SplitMode, plan_split, run_split

    src = _doc_with_bookmarks(tmp_path / "src.pdf")
    out = tmp_path / "out"
    out.mkdir()
    doc = open_document(src)
    try:
        plan = plan_split(doc, SplitMode.BOOKMARKS)
        assert len(plan.groups) == 3
        first = run_split(doc, plan, out)
        second = run_split(doc, plan, out)
    finally:
        doc.close()
    for p in first + second:
        assert p.parent == out, p
    assert not set(first) & set(second)  # the second run never replaced the first
    assert len(list(out.iterdir())) == len(first) + len(second)
    assert not list(tmp_path.glob("escape*"))


def test_pdf_to_images_never_replaces_existing_files(tmp_path):
    from core.convert.pdf_to_images import pdf_pages_to_images
    from core.document import open_document

    src = _doc_with_bookmarks(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        a = pdf_pages_to_images(doc, tmp_path / "img", pages=[0], dpi=36)
        b = pdf_pages_to_images(doc, tmp_path / "img", pages=[0], dpi=36)
    finally:
        doc.close()
    assert a[0] != b[0] and a[0].exists() and b[0].exists()


# ----------------------------------------------------------------- programs started


def test_no_program_started_by_bare_name():
    """Windows looks for a bare program name in the current folder first, so every program
    Monograph PDF starts must be given by full path (``windows_tool`` or a bundled path)."""
    bare = re.compile(r"""(?:Popen|run|call|check_output|setProgram|start)\(\s*\[?\s*["'][A-Za-z0-9_.-]+(?:\.exe)?["']""")
    offenders = []
    for path, text in _sources():
        for m in bare.finditer(text):
            line = text[: m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}: {m.group(0)}")
    assert not offenders, offenders


def test_windows_tool_gives_full_system_paths(monkeypatch):
    import core.safe_paths as sp

    monkeypatch.setattr(sp, "_WINDOWS", True)
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    assert sp.windows_tool("explorer.exe").replace("/", "\\") == r"C:\Windows\explorer.exe"
    assert sp.windows_tool("rundll32.exe").replace("/", "\\") == r"C:\Windows\System32\rundll32.exe"
    assert sp.windows_tool("powershell.exe").replace("/", "\\").endswith(r"System32\WindowsPowerShell\v1.0\powershell.exe")


def test_no_shell_true_and_no_dynamic_code():
    for path, text in _sources():
        assert "shell=True" not in text, path
        assert not re.search(r"(?<![\w.])(?:eval|exec)\(\s*(?!\))", text.replace(".exec(", ".EXEC(")), path


def test_office_powershell_scripts_force_macros_off_before_opening():
    from core.convert import office_bridge as ob

    scripts = {k: v for k, v in vars(ob).items() if k.startswith("_PS_") and k != "_PS_PREAMBLE"}
    assert scripts
    for name, script in scripts.items():
        assert "AutomationSecurity = 3" in script, name
        assert script.index("AutomationSecurity = 3") < script.index(".Open("), name
        assert "$env:MONOGRAPH_PDF_SRC" in ob._PS_PREAMBLE and "{src" not in script  # names never in script text


def test_office_powershell_receives_file_names_only_in_environment(tmp_path, monkeypatch):
    from core.convert import office_bridge as ob

    seen = {}

    class Done:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs.get("env", {})
        (tmp_path / "out.pdf").write_bytes(b"%PDF-1.7")
        return Done()

    monkeypatch.setattr(ob.subprocess, "run", fake_run)
    evil = tmp_path / "x'; Remove-Item C:\\ -Recurse; '.docx"
    ob._run_powershell(ob._PS_WORD_TO_PDF, evil, tmp_path / "out.pdf")
    assert not any(str(evil) in part for part in seen["cmd"])
    assert seen["env"]["MONOGRAPH_PDF_SRC"] == str(evil)
    assert "Bypass" not in seen["cmd"] and "-NoProfile" in seen["cmd"]


def test_libreoffice_profile_disables_macros_and_is_not_found_in_current_folder(tmp_path, monkeypatch):
    from core.convert import office_bridge as ob

    assert "DisableMacrosExecution" in ob._LO_NO_MACROS and ">true<" in ob._LO_NO_MACROS
    assert re.search(r'MacroSecurityLevel".*?<value>3</value>', ob._LO_NO_MACROS, re.S)
    # Windows: a soffice.exe in the current folder or on PATH is never used
    (tmp_path / "soffice.exe").write_bytes(b"MZ")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setattr(ob.sys, "platform", "win32")
    monkeypatch.setattr(ob, "_registered_soffice", lambda: None)
    assert ob._find_soffice() is None


def test_ocr_engine_is_only_the_bundled_tesseract():
    text = (ROOT / "core" / "ocr" / "paths.py").read_text(encoding="utf-8")
    assert '"runtime"' not in text and "which(" not in text and "environ" not in text


# ----------------------------------------------------------------- untrusted PDFs


def _js_pdf(path: Path) -> Path:
    """A PDF whose scripts would change a field, open a URL and launch a program if run."""
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_name, w.field_type = "total", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 72, 300, 100), "original"
    w.script_calc = 'event.value = "SCRIPT RAN";'
    w.script_format = 'event.value = "SCRIPT RAN";'
    page.add_widget(w)
    doc.save(path)
    doc.close()
    doc = fitz.open(path)
    cat = doc.pdf_catalog()
    js = doc.get_new_xref()
    doc.update_object(js, '<< /Type /Action /S /JavaScript /JS (app.launchURL\\("http://example.invalid/"\\); this.getField\\("total"\\).value = "SCRIPT RAN";) >>')
    doc.xref_set_key(cat, "OpenAction", f"{js} 0 R")
    doc.saveIncr()
    doc.close()
    return path


def test_pdf_javascript_is_never_run(tmp_path):
    import pymupdf
    import pymupdf.mupdf as m

    from core.document import open_document
    from core.editing.edit_model import EditableDocument
    from engines.bake_edits import bake_via_backend

    src = _js_pdf(tmp_path / "js.pdf")
    doc = open_document(src)
    try:
        live = doc._backend._doc  # noqa: SLF001
        assert not m.pdf_js_supported(pymupdf._as_pdf_document(live))
        doc.render_pixmap_png(0, zoom=1.0)
        edit = EditableDocument(doc)
        field = next(f for f in edit.fields.values() if f.name == "total")
        assert field.value == "original"
        edit.set_field_value(field.object_id, "typed")
        bake_via_backend(edit, tmp_path / "saved.pdf")
        assert not m.pdf_js_supported(pymupdf._as_pdf_document(live))
    finally:
        doc.close()
    with fitz.open(tmp_path / "saved.pdf") as saved:
        values = {w.field_name: w.field_value for w in saved[0].widgets()}
        assert values["total"] == "typed"
        assert "SCRIPT RAN" not in saved[0].get_text()


@pytest.mark.parametrize(
    "content",
    [b"", b"\x00" * 64, b"%PDF-1.7\n", b"<html><body>not a pdf</body></html>", os.urandom(4096),
     b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 99999999 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF"],
)
def test_malformed_files_fail_safely_and_are_not_changed(tmp_path, content):
    from core.document import InvalidPdfError, PasswordRequiredError, open_document

    bad = tmp_path / "bad.pdf"
    bad.write_bytes(content)
    try:
        doc = open_document(bad)
    except (InvalidPdfError, PasswordRequiredError):
        pass
    else:
        try:
            for i in range(min(doc.page_count, 3)):
                try:
                    doc.render_pixmap_png(i, zoom=0.5)
                except Exception:  # noqa: BLE001 - a broken page may fail; the app shows an error
                    pass
        finally:
            doc.close()
    assert bad.read_bytes() == content


def test_truncated_sample_fails_safely(tmp_path):
    from core.document import InvalidPdfError, open_document

    sample = ROOT / "tests" / "samples" / "sample_text.pdf"
    if not sample.is_file():
        pytest.skip("samples not generated")
    cut = tmp_path / "cut.pdf"
    cut.write_bytes(sample.read_bytes()[: len(sample.read_bytes()) // 3])
    try:
        open_document(cut).close()
    except InvalidPdfError:
        pass


def test_attachments_are_listed_never_extracted_or_opened():
    for path, text in _sources():
        assert "embfile_get" not in text and "embfile_save" not in text, path


# ----------------------------------------------------------------- offline


# Since 0.3.0 exactly two modules may use the network, each for one user-controlled purpose:
#   core/updates/net.py        update checks (user-initiated, or automatic only after the user turns
#                              them on) and the download the user approved with Update Now;
#   core/diagnostics/client.py one problem report, only after the user clicked Send to Developer.
# From 0.5.0 core/ocr/language_download.py uses core/updates/net.py (no network code of its own) for
# one OCR language file, only after the user clicked Download and Install.
# Everything else — viewing, editing, saving, OCR, conversion, printing — stays offline.
NETWORK_MODULES = {"core/updates/net.py", "core/diagnostics/client.py"}
_NET = re.compile(r"^\s*(?:import|from)\s+(?:socket|ssl|urllib(?!\.parse\b)|http|requests|httpx|aiohttp|ftplib|smtplib|webbrowser|xmlrpc)\b"
                  r"|QtNetwork|QNetworkAccessManager|QWebEngine", re.M)


def test_application_code_has_no_network_code_outside_the_two_network_modules():
    found = set()
    for path, text in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if path.name == "offline_guard.py":
            continue
        if _NET.search(text):
            found.add(rel)
    assert found == NETWORK_MODULES


def test_network_modules_are_used_only_by_the_update_and_report_workflows():
    imports = re.compile(r"^\s*(?:from\s+core\.updates\s+import\s+[^\n]*\bnet\b|from\s+core\.updates\.net\s+import|"
                         r"import\s+core\.updates\.net|from\s+core\.diagnostics\s+import\s+[^\n]*\bclient\b|"
                         r"from\s+core\.diagnostics\.client\s+import|import\s+core\.diagnostics\.client)", re.M)
    users = {}
    for path, text in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if imports.search(text) and rel not in NETWORK_MODULES:
            users.setdefault(rel, imports.findall(text))
    assert set(users) <= {"core/updates/manager.py", "ui/error_report_dialog.py", "core/ocr/language_download.py"}, users
    # the PDF, OCR, conversion and printing code never imports the update or report packages
    for path, text in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "core/ocr/language_download.py":
            continue  # Download and Install (user-initiated, see above)
        if rel.startswith(("core/convert", "core/ocr", "core/printing", "core/editing", "core/forms", "engines/",
                           "core/document.py", "core/organize", "core/security", "core/redaction")):
            assert "core.updates" not in text and "core.diagnostics.client" not in text, rel


def test_offline_guard_refuses_and_records():
    import socket

    from app.offline_guard import NetworkAttempts

    with NetworkAttempts() as guard:
        with pytest.raises(OSError):
            socket.create_connection(("example.invalid", 80), timeout=1)
        with pytest.raises(OSError):
            socket.getaddrinfo("example.invalid", 443)
    assert len(guard.attempts) == 2
    assert socket.getaddrinfo.__name__ != "blocked"  # restored


def test_self_check_reports_network_use_and_bundle_imports():
    text = (ROOT / "app" / "smoke_test.py").read_text(encoding="utf-8")
    assert 'check("no_network", no_network)' in text and 'check("bundle_imports", bundle_imports)' in text


def test_frozen_app_does_not_import_modules_from_its_folder():
    text = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8")
    assert 'if not getattr(sys, "frozen", False) and str(_ROOT) not in sys.path' in text


# ----------------------------------------------------------------- storage locations


def test_installed_copy_keeps_working_files_in_localappdata(tmp_path, monkeypatch):
    import app.paths as paths
    from core.platform_paths import user_local_base

    if sys.platform.startswith("win"):
        install = tmp_path / "Program Files" / "Monograph PDF"
        install.mkdir(parents=True)
        (install / "unins000.exe").write_bytes(b"MZ")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(paths, "ROOT", install)
        assert paths._project_layout() is False  # noqa: SLF001
        assert not (install / "runtime").exists()  # no write probe into the installation folder
        monkeypatch.setattr(paths, "_PROJECT_LAYOUT", False)
        monkeypatch.delenv("MONOGRAPH_PDF_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
        runtime = paths._resolve_runtime_dir()  # noqa: SLF001
        assert runtime == tmp_path / "Local" / "Monograph PDF" / "runtime"
        assert install not in runtime.parents
        return

    # macOS / Unix: an installed .app keeps runtime under Application Support (user_local_base).
    install = tmp_path / "MonographPDF.app" / "Contents" / "MacOS"
    install.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths, "ROOT", install)
    monkeypatch.setattr(paths, "is_macos_app_bundle", lambda: True)
    monkeypatch.setattr(paths, "_PROJECT_LAYOUT", False)
    monkeypatch.delenv("MONOGRAPH_PDF_RUNTIME_DIR", raising=False)
    runtime = paths._resolve_runtime_dir()  # noqa: SLF001
    assert runtime == user_local_base() / "runtime"
    assert install not in runtime.parents


# ----------------------------------------------------------------- installer / uninstaller


def _section(name: str) -> str:
    m = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[[A-Za-z]+\]\s*$|\Z)", ISS, flags=re.M | re.S)
    return m.group(1) if m else ""


def test_installer_creates_no_persistence_or_unrelated_registrations():
    lower = ISS.lower()
    for bad in ("currentversion\\run", "runonce", "schtasks", "sc.exe", "netsh", "firewall", "services\\",
                "policies", "winlogon", "shell\\open\\command\"; valuetype: string; valuename: \"\"; valuedata: \"cmd"):
        assert bad not in lower, bad
    reg = _section("Registry")
    keys = set(re.findall(r'Subkey: "([^"]+)"', reg))
    allowed = ("Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\", "Software\\Classes\\", "{#AppRegKey}",
               "{#CapKey}", "Software\\RegisteredApplications", "' + CapKey")
    assert keys and all(k.startswith(allowed) for k in keys), [k for k in keys if not k.startswith(allowed)]
    run = _section("Run")
    assert "runonce" not in run.lower() and "postinstall" in run  # only optional post-install launch / Settings


def test_installer_keeps_the_installation_folder_for_program_files_only():
    assert "{app}\\logs" not in _section("Code").replace("Type: filesandordirs", "")
    assert "{localappdata}\\' + DataFolderName + '\\logs'" in ISS
    assert "PrivilegesRequiredOverridesAllowed=dialog" in ISS


def test_uninstall_removal_is_bounded():
    code = _section("Code")
    assert "function IsOwnDataFolder" in code and "if not IsOwnDataFolder(Folder) then" in code
    assert "function IsReparsePoint" in code and "if IsReparsePoint(Folder) then" in code
    assert "IsInside(ExpandConstant('{app}'), Folder)" in code
    assert "(Rec.Attributes and $400) = 0" in code  # %TEMP% links are never followed
    # DelTree only in the bounded helpers
    funcs = re.split(r"^(?:procedure|function) ", code, flags=re.M)
    users = [f.split("(")[0].split(";")[0].strip() for f in funcs if "DelTree(" in f]
    assert set(users) <= {"RemoveFolder", "RemoveTempMatches", "RemoveDeselectedShortcuts", "RemoveOwnedRelUnder"}, users
    for call in re.findall(r"RemoveFolder\((ExpandConstant[^;]+)\);", code):
        # DataFolderName / LegacyDataFolderName, or the folder name passed to ClearHistoryIn
        assert "DataFolderName" in call or "+ Folder +" in call, call
    # PDF Editor's folders only when Monograph PDF migrated them for this user
    assert "LegacyDataAllowed and InNamedDataFolder(Folder, LegacyDataFolderName)" in code
    assert "LegacyMigrationRecord" in code and "not LegacyAppStillPresent()" in code
    # temporary folders: only Monograph PDF's and PDF Editor's own names
    assert "(Pos('monographpdf', N) = 1) or (N = 'monograph-pdf-theme')" in code
    assert "(Pos('pdfeditor', N) = 1) or (N = 'pdf-editor-theme')" in code


def test_uninstall_launcher_starts_programs_by_full_path_and_restores_from_memory():
    assert 'new ProcessStartInfo("cmd.exe"' not in LAUNCHER
    assert 'Path.Combine(system, "cmd.exe")' in LAUNCHER and 'Path.Combine(system, "PING.EXE")' in LAUNCHER
    assert "File.WriteAllBytes(self, original)" in LAUNCHER
    assert "MoveFileEx(parked, self" not in LAUNCHER


# ----------------------------------------------------------------- release contents


def _check_release():
    sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
    try:
        import check_release

        return check_release
    finally:
        sys.path.pop(0)


def _layout(tmp_path: Path) -> Path:
    base = tmp_path / "MonographPDF"
    for rel in ("MonographPDF.exe", "_internal/python311.dll", "_internal/PySide6/Qt6Core.dll",
                "_internal/pymupdf/_mupdf.pyd", "engines/ocr/tesseract.exe", "_internal/VCRUNTIME140.dll"):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"MZ")
    return base


def test_release_check_accepts_known_components(tmp_path):
    cr = _check_release()
    assert cr.check(_layout(tmp_path), None, tmp_path / "inv.json") == 0


@pytest.mark.parametrize(
    "rel, data",
    [
        ("_internal/unknown_helper.dll", b"MZ"),
        ("_internal/PySide6/Qt6Network.dll", b"MZ"),  # removed by the build: must not come back
        ("_internal/PySide6/plugins/tls/qopensslbackend.dll", b"MZ"),
        (".env", b"TOKEN=x"),
        ("secrets/server.pem", b"-----BEGIN " + b"PRIVATE KEY-----"),
        ("docs/NOTES.md", b"see D:\\Software" + b" testing\\Monograph PDF\\build"),
        ("docs/KEYS.txt", b"api_key = '" + b"ABCDEFGHIJKLMNOPQRSTUVWX'"),
        ("tests/test_x.py", b"x"),
        ("PDF_editor.exe", b"MZ"),  # the predecessor's program must not ship
        ("_internal/resources/icons/windows/pdf_editor.ico", b"\0"),  # nor its icon
        ("_internal/resources/icons/source/PDF_logo.png", b"\x89PNG"),
    ],
)
def test_release_check_rejects_unknown_or_sensitive_files(tmp_path, rel, data):
    cr = _check_release()
    base = _layout(tmp_path)
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    assert cr.check(base, None, None) == 1


def test_prune_removes_network_and_unused_parts(tmp_path):
    cr = _check_release()
    base = _layout(tmp_path)
    for rel in ("_internal/PySide6/plugins/tls/qschannelbackend.dll", "_internal/PySide6/Qt6Network.dll",
                "_internal/cv2/opencv_videoio_ffmpeg4100_64.dll", "_internal/_ssl.pyd", "_internal/libssl-3.dll",
                "_internal/libssl-3-x64.dll", "_internal/libcrypto-3-x64.dll"):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"MZ")
    assert cr.prune(base) == 0
    # Qt's network/TLS stack and OpenSSL copies picked up from PATH are removed ...
    assert not (base / "_internal/PySide6/plugins/tls").exists() and not (base / "_internal/PySide6/Qt6Network.dll").exists()
    assert not list(base.rglob("*ffmpeg*")) and not list(base.rglob("*-x64.dll"))
    # ... Python's own ssl module stays (0.3.0: HTTPS for update checks and approved problem reports)
    assert (base / "_internal/_ssl.pyd").exists() and (base / "_internal/libssl-3.dll").exists()
    assert (base / "_internal/PySide6/Qt6Core.dll").exists()


def test_inventory_and_notices_cover_every_shipped_component():
    cr = _check_release()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()
    inventory = (ROOT / "licenses" / "DEPENDENCY_INVENTORY.md").read_text(encoding="utf-8").lower()
    for comp, (_patterns, notice) in cr.RELEASE_COMPONENTS.items():
        assert notice.lower() in notices, comp
    pins = re.findall(r"^([A-Za-z0-9_.-]+)==([\w.]+)", (ROOT / "requirements.txt").read_text(encoding="utf-8"), re.M)
    assert pins
    for name, version in pins:
        key = name.lower().replace("opencv-python-headless", "opencv-python-headless")
        assert key in inventory or name.lower().split("-")[0] in inventory, name
        assert version in inventory, f"{name} {version} not in DEPENDENCY_INVENTORY.md"
    assert "ffmpeg is not included in the headless build" not in notices  # was wrong before 0.1.5
    assert "| qpdf |" not in notices
