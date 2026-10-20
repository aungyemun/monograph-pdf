"""Release-set verification (scripts/packaging/verify_release.py) and the portable Installer ZIP
writer (zip_folder.py), on a small synthetic release."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))
import verify_release as vr  # noqa: E402
import zip_folder as zf  # noqa: E402

V = "9.8.7"
DATE = "2031-02-03"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_zip(path: Path, *, extra: dict[str, str] | None = None, version: str = V) -> None:
    top = f"MonographPDF_{V}_Source/monograph-pdf/"
    files = {
        "VERSION": f"{version}\n",
        "CITATION.cff": f'cff-version: 1.2.0\nversion: "{version}"\n',
        "THIRD_PARTY_NOTICES.md": f"| Monograph PDF | {version} | AGPL-3.0-or-later |\n",
        "licenses/DEPENDENCY_INVENTORY.md": f"# Dependency inventory (Monograph PDF {version})\n",
        "CHANGELOG.md": f"# Changelog\n\n## [{version}] — {DATE}\n",
        "scripts/packaging/third_party_sources.json": json.dumps(
            {"release": version, "archive": f"MonographPDF_{version}_Source.zip"}),
        "app/main.py": "print('hello')\n",
    }
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as z:
        for rel, text in files.items():
            z.writestr(top + rel, text)


def make_release(tmp: Path, **kw) -> Path:
    out = tmp / "release"
    stage = tmp / "stage"
    out.mkdir()
    (stage / "docs").mkdir(parents=True)
    (stage / "licenses").mkdir()
    (stage / "runtime" / "ocr").mkdir(parents=True)
    (stage / "runtime" / "fonts").mkdir(parents=True)
    setup = b"MZ fake setup"
    (out / f"MonographPDF_{V}_Setup.exe").write_bytes(setup)
    (stage / "Setup.exe").write_bytes(setup)
    src = out / f"MonographPDF_{V}_Source.zip"
    _source_zip(src, extra=kw.get("source_extra"), version=kw.get("source_version", V))
    for rel in vr.INSTALLER_ZIP_REQUIRED:
        f = stage / rel
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("text\n", encoding="utf-8")
    (stage / "CITATION.cff").write_text(f'version: "{V}"\n', encoding="utf-8")
    (stage / "CHANGELOG.md").write_text(f"## [{V}] — {DATE}\n", encoding="utf-8")
    (stage / "SHA256SUMS.txt").write_text(
        f"Monograph PDF {V}\n\n{_sha(setup)}  Setup.exe\n{_sha(src.read_bytes())}  {src.name}\n", encoding="utf-8")
    zf.zip_folder(stage, out / f"MonographPDF_{V}_Installer.zip")
    return out


def _notes(release: Path) -> str:
    sums = "\n".join(f"{_sha((release / n).read_bytes())}  {n}" for n in vr.vrn.expected_artifacts(V))
    return (f"Monograph PDF {V}, released {DATE}.\n\n## Download\n\n```\n{sums}\n```\n\n"
            "## Verification for this release\n\n- Tests: 10 passed, 0 failed, 1 skipped (private fixtures).\n"
            "- Installer test: 5 passed, 0 failed.\n\n## Known limitations\n\n- Not code-signed.\n")


def run(release: Path, *extra: str) -> tuple[int, str]:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = vr.main(["--dir", str(release), "--version", V, *extra])
    return code, buf.getvalue()


def test_zip_folder_writes_portable_sorted_reproducible_names(tmp_path):
    (tmp_path / "f" / "docs").mkdir(parents=True)
    (tmp_path / "f" / "docs" / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "f" / "Setup.exe").write_bytes(b"x")
    (tmp_path / "f" / "x_Source.zip").write_bytes(b"skip")
    zf.zip_folder(tmp_path / "f", tmp_path / "one.zip", ["*_Source.zip"])
    zf.zip_folder(tmp_path / "f", tmp_path / "two.zip", ["*_Source.zip"])
    with zipfile.ZipFile(tmp_path / "one.zip") as z:
        raw = [i.orig_filename for i in z.infolist()]
    assert raw == ["Setup.exe", "docs/a.md"]
    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()


def test_complete_release_passes(tmp_path):
    release = make_release(tmp_path)
    notes = tmp_path / "notes.md"
    notes.write_text(_notes(release), encoding="utf-8")
    code, out = run(release, "--notes", str(notes), "--tests", "10,0,1")
    assert code == 0, out
    assert "RESULT: PASS" in out and "FAIL" not in out


def test_without_notes_is_not_verified_rather_than_passed(tmp_path):
    code, out = run(make_release(tmp_path))
    assert code == 0 and "NOT VERIFIED  notes" in out


def test_backslash_entry_names_fail(tmp_path):
    release = make_release(tmp_path)
    inst = release / f"MonographPDF_{V}_Installer.zip"
    with zipfile.ZipFile(inst, "a") as z:
        info = zipfile.ZipInfo("docs/extra.md")
        info.filename = "docs\\extra.md"  # what Windows PowerShell's Compress-Archive writes
        z.writestr(info, "x")
    code, out = run(release)
    assert code == 1 and "non-portable entry name" in out


def test_tampered_or_mislabelled_files_fail(tmp_path):
    release = make_release(tmp_path)
    (release / f"MonographPDF_{V}_Setup.exe").write_bytes(b"MZ different")
    (release / "MonographPDF_9.8.6_Setup.exe").write_bytes(b"old")
    code, out = run(release)
    assert code == 1
    assert "Setup.exe differs" in out and "file of another release here" in out


def test_version_mismatch_and_missing_notice_fail(tmp_path):
    release = make_release(tmp_path, source_version="9.8.6")
    code, out = run(release)
    assert code == 1 and "VERSION is '9.8.6'" in out


def test_private_paths_and_excluded_files_fail(tmp_path):
    release = make_release(tmp_path, source_extra={
        "docs/notes.md": "see C:\\Users\\someone\\Downloads\\report.pdf",
        "tests/integration/test_user_real_pdfs.py": "x = 1\n",
    })
    code, out = run(release)
    assert code == 1
    assert "private path" in out and "should not be published" in out


def test_notes_with_placeholders_fail(tmp_path):
    release = make_release(tmp_path)
    notes = tmp_path / "notes.md"
    notes.write_text(_notes(release).replace("(private fixtures)", "(__SKIP_REASONS__)"), encoding="utf-8")
    code, out = run(release, "--notes", str(notes))
    assert code == 1 and "__SKIP_REASONS__" in out


@pytest.mark.parametrize("missing", ["LICENSE.md", "licenses/GPL-3.0.txt", "runtime/ocr/TESSERACT_NOTICE.txt"])
def test_missing_notices_fail(tmp_path, missing):
    release = make_release(tmp_path)
    inst = release / f"MonographPDF_{V}_Installer.zip"
    with zipfile.ZipFile(inst) as z:
        items = {i.filename: z.read(i) for i in z.infolist() if i.filename != missing}
    with zipfile.ZipFile(inst, "w") as z:
        for name, data in items.items():
            z.writestr(name, data)
    code, out = run(release)
    assert code == 1 and f"lacks {missing}" in out


def test_unreleased_changelog_only_with_allow_unreleased(tmp_path):
    release = make_release(tmp_path)
    inst = release / f"MonographPDF_{V}_Installer.zip"
    with zipfile.ZipFile(inst) as z:
        items = {i.filename: z.read(i) for i in z.infolist()}
    items["CHANGELOG.md"] = f"## [{V}] — Unreleased\n".encode()
    with zipfile.ZipFile(inst, "w") as z:
        for name, data in items.items():
            z.writestr(name, data)
    code, out = run(release)
    assert code == 1 and "no dated entry" in out
    code, out = run(release, "--allow-unreleased")
    assert code == 0, out


# ---- check_release.py superseded: earlier versions' files leave installer\ only if archived ----
import check_release as cr  # noqa: E402


def _superseded_layout(tmp_path):
    inst, arch, dest = tmp_path / "installer", tmp_path / "releases", tmp_path / "superseded"
    inst.mkdir()
    for name, data in (("MonographPDF_9.8.6_Setup.exe", b"old setup"), ("MonographPDF_9.8.6_Source.zip", b"old src"),
                       (f"MonographPDF_{V}_Setup.exe", b"new setup"), ("MonographPDF.iss", b"script")):
        (inst / name).write_bytes(data)
    return inst, arch, dest


def test_archived_earlier_release_files_are_moved_not_deleted(tmp_path):
    inst, arch, dest = _superseded_layout(tmp_path)
    (arch / "MonographPDF_9.8.6").mkdir(parents=True)
    (arch / "MonographPDF_9.8.6" / "MonographPDF_9.8.6_Setup.exe").write_bytes(b"old setup")
    (arch / "MonographPDF_9.8.6" / "MonographPDF_9.8.6_Source.zip").write_bytes(b"old src")
    assert cr.superseded(inst, V, arch, dest) == 0
    assert sorted(p.name for p in inst.iterdir()) == ["MonographPDF.iss", f"MonographPDF_{V}_Setup.exe"]
    assert (dest / "9.8.6" / "MonographPDF_9.8.6_Setup.exe").read_bytes() == b"old setup"


@pytest.mark.parametrize("archived", [None, b"different bytes"])
def test_unarchived_or_different_earlier_files_stop_the_build(tmp_path, archived):
    inst, arch, dest = _superseded_layout(tmp_path)
    if archived is not None:
        (arch / "MonographPDF_9.8.6").mkdir(parents=True)
        (arch / "MonographPDF_9.8.6" / "MonographPDF_9.8.6_Setup.exe").write_bytes(archived)
        (arch / "MonographPDF_9.8.6" / "MonographPDF_9.8.6_Source.zip").write_bytes(b"old src")
    assert cr.superseded(inst, V, arch, dest) == 1
    assert (inst / "MonographPDF_9.8.6_Setup.exe").is_file() and not dest.exists()  # nothing moved
