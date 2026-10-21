"""Code-signing readiness: signing-provider abstraction and the production approval gate, version
metadata, SBOM, build provenance, workflow permissions, and independence of update trust."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "signing"))
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))

import make_sbom  # noqa: E402
import provenance  # noqa: E402
import signing  # noqa: E402

THUMB = "0123456789abcdef0123456789abcdef01234567"
SIGNTOOL_ENV = {"MONOGRAPH_SIGN_CERT_SHA1": THUMB, "MONOGRAPH_SIGN_TIMESTAMP_URL": "http://timestamp.example.test"}


def _repo(tmp_path: Path, version: str = "0.3.0") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "t@example.test")
    run("config", "user.name", "Test")
    (repo / "VERSION").write_text(version + "\n", encoding="utf-8")
    run("add", "VERSION")
    run("commit", "-q", "-m", "v")
    return repo


# ------------------------------------------------------------------ signing gate


def test_default_provider_signs_nothing_and_cannot_be_used_for_production(tmp_path):
    f = tmp_path / "MonographPDF.exe"
    f.write_bytes(b"MZ")
    res = signing.sign_files("none", "0.3.0", [f], production=False)
    assert res.signed == [] and res.unsigned == [str(f)]
    with pytest.raises(signing.SigningError, match="production release must name a signing provider"):
        signing.sign_files("none", "0.3.0", [f], production=True)


def test_real_providers_need_production_and_an_approval(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "Setup.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(signing.SigningError, match="only done for an approved production release"):
        signing.sign_files("signtool", "0.3.0", [f], production=False, env=SIGNTOOL_ENV, root=repo)
    with pytest.raises(signing.SigningError, match="no signing approval"):
        signing.sign_files("signtool", "0.3.0", [f], production=True, env=SIGNTOOL_ENV, root=repo, dry_run=True)


def test_approval_requires_the_exact_typed_confirmation_and_a_clean_commit(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(signing.SigningError, match="not confirmed"):
        signing.create_approval("0.3.0", "Aung Ye Mun", "yes", root=repo)
    with pytest.raises(signing.SigningError, match="not confirmed"):
        signing.create_approval("0.3.0", "Aung Ye Mun", signing.confirmation_phrase("0.3.1"), root=repo)
    (repo / "VERSION").write_text("0.3.0-dirty\n", encoding="utf-8")
    with pytest.raises(signing.SigningError, match="uncommitted"):
        signing.create_approval("0.3.0", "Aung Ye Mun", signing.confirmation_phrase("0.3.0"), root=repo)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "VERSION"], check=True)
    path = signing.create_approval("0.3.0", "Aung Ye Mun", signing.confirmation_phrase("0.3.0"), root=repo)
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["version"] == "0.3.0" and rec["approver"] == "Aung Ye Mun" and len(rec["commit"]) == 40
    assert path.parent == repo / "build" / "signing"


def test_approval_binds_version_commit_and_clean_tree(tmp_path):
    repo = _repo(tmp_path)
    signing.create_approval("0.3.0", "A", signing.confirmation_phrase("0.3.0"), root=repo)
    assert signing.check_approval("0.3.0", root=repo)["approver"] == "A"
    with pytest.raises(signing.SigningError):
        signing.check_approval("0.3.1", root=repo)  # no approval for another version
    (repo / "VERSION").write_text("0.3.0\n# edit\n", encoding="utf-8")
    with pytest.raises(signing.SigningError, match="uncommitted"):
        signing.check_approval("0.3.0", root=repo)
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "later change"], check=True)
    with pytest.raises(signing.SigningError, match="not HEAD"):
        signing.check_approval("0.3.0", root=repo)


def test_signtool_provider_uses_a_store_certificate_and_timestamps(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "MonographPDF.exe"
    f.write_bytes(b"MZ")
    signing.create_approval("0.3.0", "A", signing.confirmation_phrase("0.3.0"), root=repo)
    res = signing.sign_files("signtool", "0.3.0", [f], production=True, env=SIGNTOOL_ENV, root=repo, dry_run=True)
    cmd = res.commands[0]
    assert cmd[:3] == ["signtool.exe", "sign", "/sha1"] and THUMB in cmd
    assert cmd[cmd.index("/fd") + 1] == "SHA256" and cmd[cmd.index("/td") + 1] == "SHA256" and "/tr" in cmd
    assert not any(a.lower() in ("/f", "/p") for a in cmd)  # never a key file or a password
    with pytest.raises(signing.SigningError, match="thumbprint"):
        signing.provider("signtool", {}).check_configuration()


def test_signpath_provider_is_configuration_only_and_never_signs_locally():
    with pytest.raises(signing.SigningError, match="not configured"):
        signing.provider("signpath", {}).check_configuration()
    env = {k: "x" for k in signing.SignPathProvider.KEYS}
    signing.provider("signpath", env).check_configuration()
    with pytest.raises(signing.SigningError, match="never sent from a local build"):
        signing.provider("signpath", env).sign([Path("Setup.exe")])
    with pytest.raises(signing.SigningError, match="unknown signing provider"):
        signing.provider("magic")


def test_release_build_signs_only_through_the_gate():
    ps = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    assert '[string]$SigningProvider = "none"' in ps
    gate = ps.index("check-approval")
    assert gate < ps.index("# ---- 1. Tests ----")  # refused before any work
    assert ps.index("Sign-Files @($AppExe, $UninstallExe, $UpdaterExe)") < ps.index("& $Iscc")
    assert ps.index("Sign-Files @($Setup)") < ps.index("create_release_zip.ps1")
    assert "check_metadata.py" in ps and "make_sbom.py" in ps and "provenance.py" in ps
    for secret_word in ("password", "/p ", ".pfx", "-----BEGIN"):
        assert secret_word not in ps.lower()


# ------------------------------------------------------------------ update trust is independent


def test_update_trust_does_not_depend_on_code_signing():
    for f in (ROOT / "core" / "updates").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "scripts.signing" not in text and "signtool" not in text.lower() and "signpath" not in text.lower(), f
    sign_src = (ROOT / "scripts" / "signing" / "signing.py").read_text(encoding="utf-8")
    assert "ed25519" not in sign_src and "update_config" not in sign_src and "update-signing" not in sign_src
    cfg = json.loads((ROOT / "resources" / "update" / "update_config.json").read_text(encoding="utf-8"))
    assert cfg["require_authenticode"] is False  # releases are unsigned; manifests alone carry update trust
    assert not any("sign" in k and k != "require_authenticode" for k in cfg)


def test_manifest_verification_ignores_authenticode_unless_required(tmp_path, monkeypatch):
    import threading

    from core.updates import authenticode, manager
    from core.updates.install_target import InstallTarget
    from core.updates.manifest import parse_and_verify
    from tests.fixtures.update_fixtures import make_config, manifest_bytes, setup_bytes, signed_fields

    monkeypatch.setenv("MONOGRAPH_PDF_UPDATES_DIR", str(tmp_path / "Updates"))
    data = setup_bytes()
    rel = parse_and_verify(manifest_bytes(signed_fields(data=data)), make_config())

    def dl(cfg, url, dest, size, cancel, progress=None):
        dest.write_bytes(data)

    target = InstallTarget(True, install_dir=tmp_path, mode="user", version="0.3.0")
    monkeypatch.setattr(authenticode, "check", lambda p: authenticode.UNSIGNED)
    assert manager.download_and_verify(make_config(), rel, target, threading.Event(), downloader=dl).installer.exists()
    from dataclasses import replace

    with pytest.raises(manager.UpdateError, match="signature check failed"):
        manager.download_and_verify(replace(make_config(), require_authenticode=True), rel, target, threading.Event(),
                                    downloader=dl)


# ------------------------------------------------------------------ metadata


def test_every_own_binary_carries_one_product_name_and_version():
    for cs in ("uninstall_launcher.cs", "update_helper.cs"):
        text = (ROOT / "installer" / cs).read_text(encoding="utf-8")
        assert "AssemblyInformationalVersion(MonographPdf" in text and "BuildInfo.ProductVersion)" in text, cs
        assert 'AssemblyProduct("Monograph PDF")' in text, cs
    ps = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    assert ps.count("public const string ProductVersion = `\"$Version`\"") == 2
    iss = (ROOT / "installer" / "MonographPDF.iss").read_text(encoding="utf-8-sig")
    assert "VersionInfoProductName={#AppName}" in iss and "VersionInfoProductVersion={#AppVersion}" in iss
    from core.product_meta import version_resource_strings

    s = version_resource_strings("0.3.0")
    assert s["ProductName"] == "Monograph PDF" and s["ProductVersion"] == "0.3.0"


def test_metadata_check_reports_unreadable_files(tmp_path):
    pytest.importorskip("pefile")
    import check_metadata

    bad = tmp_path / "x.exe"
    bad.write_bytes(b"not a program")
    assert "unreadable" in check_metadata.problems_for(bad, "0.3.0")[0]


def test_metadata_of_built_binaries_when_a_build_is_present():
    pytest.importorskip("pefile")
    import check_metadata

    built = [p for p in (ROOT / "build" / "e2e" / "out").glob("MonographPDF_*_Setup.exe")] if (ROOT / "build").is_dir() else []
    if not built:
        pytest.skip("no local test build (build/e2e/out)")
    for setup in built:
        version = setup.name.split("_")[1]
        assert check_metadata.problems_for(setup, version) == []


# ------------------------------------------------------------------ SBOM


@pytest.fixture(scope="module")
def sbom():
    return make_sbom.build("0.3.0", "a" * 40, 1_800_000_000, None)


def _all(items):
    for c in items:
        yield c
        yield from _all(c.get("components", []))


def test_sbom_is_valid_cyclonedx_and_deterministic(sbom):
    assert make_sbom.check(sbom) == []
    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.5"
    assert make_sbom.build("0.3.0", "a" * 40, 1_800_000_000, None) == sbom
    assert sbom["serialNumber"] != make_sbom.build("0.3.0", "b" * 40, 1_800_000_000, None)["serialNumber"]
    app = sbom["metadata"]["component"]
    assert app["name"] == "Monograph PDF" and app["version"] == "0.3.0"
    assert app["licenses"] == [{"license": {"id": "AGPL-3.0-or-later"}}]
    assert {"name": "monograph:commit", "value": "a" * 40} in app["properties"]


def test_sbom_lists_every_shipped_python_package_at_its_pinned_version(sbom):
    pins = {**make_sbom._pins(ROOT / "requirements-ci.txt"), **make_sbom._pins(ROOT / "requirements.txt")}
    listed = {c["name"]: c["version"] for c in sbom["components"] if c.get("purl", "").startswith("pkg:pypi/")
              and c["name"] != "PyInstaller bootloader"}
    shipped = {n for n in pins if n not in make_sbom.NOT_SHIPPED}
    assert shipped == set(listed), shipped ^ set(listed)
    assert all(listed[n] == pins[n] for n in listed)
    names = {c["name"].lower() for c in _all(sbom["components"])}
    assert not names & {"pytest", "cryptography", "pefile"}  # build and test tools are not shipped


def test_sbom_licenses_agree_with_the_dependency_inventory(sbom):
    inventory = (ROOT / "licenses" / "DEPENDENCY_INVENTORY.md").read_text(encoding="utf-8")
    for name, lic in make_sbom.PYPI_LICENSES.items():
        first = lic.split(" ")[0].replace("-only", "").replace("-or-later", "")
        assert first in inventory, (name, lic)


def test_sbom_hashes_match_the_pinned_ocr_engine(sbom):
    pins = json.loads((ROOT / "scripts" / "ci" / "ocr_engine_pins.json").read_text(encoding="utf-8"))
    files = {c["name"]: c["hashes"][0]["content"] for c in _all(sbom["components"]) if c.get("type") == "file"}
    for name, digest in pins["engine"].items():
        assert files[f"engines/ocr/{name}"] == digest
    for name, digest in pins["tessdata"].items():
        assert files[f"models/tessdata/{name}"] == digest


def test_sbom_check_catches_broken_documents(sbom):
    broken = json.loads(json.dumps(sbom))
    broken["components"].append(dict(broken["components"][0]))
    broken["components"][1]["hashes"] = [{"alg": "SHA-256", "content": "xyz"}]
    broken["components"][2].pop("licenses")
    problems = make_sbom.check(broken)
    assert any("duplicate" in p for p in problems) and any("no license" in p for p in problems)


def test_sbom_flags_the_non_osi_components_explicitly(sbom):
    refs = {c["name"]: c["licenses"] for c in sbom["components"]}
    assert refs["Inno Setup"] == [{"license": {"name": "LicenseRef-Inno-Setup"}}]
    assert refs["Microsoft Visual C++ / Universal C runtime"] == [{"license": {"name": "LicenseRef-Microsoft-VC-Redistributable"}}]


# ------------------------------------------------------------------ provenance


def test_provenance_record_traces_artifacts_to_a_commit(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    art = tmp_path / "MonographPDF_0.3.0_Setup.exe"
    art.write_bytes(b"MZ setup")
    rec_path = tmp_path / "prov.json"
    rec = provenance.write(rec_path, "0.3.0", [art], "none", root=repo)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert rec["commit"] == head and rec["artifacts"][art.name]["sha256"] == provenance.sha256(art)
    assert provenance.verify(rec_path, tmp_path, False, root=repo) == []
    art.write_bytes(b"MZ changed")
    assert any("differs" in p for p in provenance.verify(rec_path, tmp_path, False, root=repo))
    # not published: no origin/main, no tag
    assert any("neither on origin/main nor tagged" in p for p in provenance.verify(rec_path, None, True, root=repo))
    subprocess.run(["git", "-C", str(repo), "tag", "v0.3.0"], check=True)
    assert provenance.verify(rec_path, None, True, root=repo) == []


def test_provenance_refuses_uncommitted_builds(tmp_path):
    repo = _repo(tmp_path)
    (repo / "VERSION").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="uncommitted"):
        provenance.write(tmp_path / "p.json", "0.3.0", [], "none", root=repo)


def test_release_verification_checks_the_programs_commit(tmp_path):
    import verify_release

    layout = tmp_path / "MonographPDF"
    res = layout / "_internal" / "resources"
    res.mkdir(parents=True)
    assert "missing" in verify_release.provenance_problems(layout, {"commit": "a" * 40}, "0.3.0")[0]
    (res / "build_info.json").write_text(json.dumps({"commit": "a" * 40, "dirty": False, "version": "0.3.0"}))
    assert verify_release.provenance_problems(layout, {"commit": "a" * 40}, "0.3.0") == []
    assert verify_release.provenance_problems(layout, {"commit": "b" * 40}, "0.3.0")
    (res / "build_info.json").write_text(json.dumps({"commit": "a" * 40, "dirty": True, "version": "0.3.0"}))
    assert any("uncommitted" in p for p in verify_release.provenance_problems(layout, {"commit": "a" * 40}, "0.3.0"))


def test_build_records_its_commit_in_the_program():
    ps = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert "build_info.json" in ps and "rev-parse HEAD" in ps and "status --porcelain" in ps
    from core.product_meta import build_info

    assert build_info() == {} or set(build_info()) == {"commit", "dirty", "version"}


# ------------------------------------------------------------------ GitHub Actions


def _workflows():
    return sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_workflows_have_least_privilege_and_no_secrets():
    assert _workflows()
    for wf in _workflows():
        text = wf.read_text(encoding="utf-8")
        assert re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", text), wf.name
        assert not re.search(r":\s*write\b", text), wf.name
        assert "secrets." not in text and "pull_request_target" not in text, wf.name
        for uses in re.findall(r"uses:\s*([^\s#]+)", text):
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", uses), f"{wf.name}: {uses} is not pinned to a commit"
        if "actions/checkout@" in text:
            assert "persist-credentials: false" in text, wf.name


def test_ci_generates_and_checks_the_sbom():
    text = (ROOT / ".github" / "workflows" / "windows-ci.yml").read_text(encoding="utf-8")
    assert "make_sbom.py --out" in text and "make_sbom.py --check" in text


# ------------------------------------------------------------------ policy documents


def test_signing_documents_state_the_real_status():
    policy = (ROOT / "docs" / "CODE_SIGNING_POLICY.md").read_text(encoding="utf-8")
    for needed in ("not code-signed", "Author", "Reviewer", "Signing Approver", "github.com/aungyemun",
                   "multi-factor", "PRIVACY_POLICY.md", "independent"):
        assert needed in policy, needed
    # The SignPath attribution may only appear once SignPath Foundation actually signs releases
    for doc in list((ROOT / "docs").glob("*.md")) + [ROOT / "README.md", ROOT / "SECURITY.md"]:
        text = doc.read_text(encoding="utf-8")
        assert "Free code signing provided by SignPath.io" not in text, doc.name
        assert not re.search(r"(?i)\bsigned by signpath\b|signpath (foundation )?(has )?approved", text), doc.name
    privacy = (ROOT / "docs" / "PRIVACY_POLICY.md").read_text(encoding="utf-8")
    assert "does not transfer information to other networked systems unless you request it" in privacy
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Code signing policy" in readme and "PRIVACY_POLICY.md" in readme
