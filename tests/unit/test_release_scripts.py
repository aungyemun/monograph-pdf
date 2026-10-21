"""Static regression checks for the build and release scripts (Windows PowerShell 5.1 pitfalls)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PS_SCRIPTS = sorted(p for p in (ROOT / "scripts").rglob("*.ps1")) + sorted((ROOT / "installer").glob("*.ps1"))


def _code_lines(path: Path):
    for no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        s = line.strip()
        if s and not s.startswith("#"):
            yield no, s


@pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_native_stderr_redirect_while_errors_stop(script):
    """Windows PowerShell 5.1 turns each redirected stderr line of a native program into an error record;
    with $ErrorActionPreference = "Stop" the first one ends the script (the defect fixed in run_tests.ps1
    in 0.2.3 and still present in the retired prepare_windows_release.ps1)."""
    pref = "Continue"
    bad = []
    for no, s in _code_lines(script):
        m = re.search(r'\$ErrorActionPreference\s*=\s*"(\w+)"', s)
        if m:
            pref = m.group(1)
        if pref == "Stop" and re.search(r"2>&1", s) and re.match(r"^(\$\w+\s*=\s*)?&", s):
            bad.append(f"{no}: {s}")
    assert bad == [], bad


def test_retired_release_prepare_script_is_gone():
    """prepare_windows_release.ps1 bumped VERSION on its own, staged an unofficial build and aborted on
    harmless stderr; build_release.ps1 is the only release build."""
    for retired in ("scripts/prepare_windows_release.ps1", "scripts/validate_release_smoke.py",
                    "scripts/write_runtime_manifest.py"):
        assert not (ROOT / retired).exists(), retired


def test_setup_env_uses_python_311_and_stops_on_failed_installs():
    text = (ROOT / "scripts" / "setup_env.ps1").read_text(encoding="utf-8-sig")
    code = "\n".join(s for _, s in _code_lines(ROOT / "scripts" / "setup_env.ps1"))
    # py -3.11 is tried before a generic "python", which is accepted only when it is 3.11
    assert code.index('"py", "-3.11"') < code.index('@("python")')
    assert '$ver -eq "3.11"' in code and "AllowOtherPython" in code
    assert "(or 3.12+)" not in text
    # every install step checks the exit code (it used to report "Environment ready" after a failure)
    for step in ("-m venv", "pip install --upgrade pip", "-r \"$Root\\requirements.txt\"\n", "pip check"):
        at = code.find(step)
        assert at != -1, step
        assert "$LASTEXITCODE -ne 0" in code[at:at + 400], step
