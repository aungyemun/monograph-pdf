"""verify_release.py reports its result (never crashes) when its output is redirected on a Windows with a
Japanese, Chinese or Korean code page: the release build captured its output there and stopped with
UnicodeEncodeError at "Verifying the release set" although every check had passed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_output_redirected_with_a_cjk_code_page_does_not_crash(tmp_path):
    for name in ("Setup.exe", "Installer.zip", "Source.zip"):  # placeholders: the checks then print "name — sha256"
        (tmp_path / f"MonographPDF_9.9.9_{name}").write_bytes(b"placeholder")
    env = dict(os.environ, PYTHONIOENCODING="cp932", PYTHONUTF8="0")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "packaging" / "verify_release.py"), "--dir", str(tmp_path),
         "--version", "9.9.9", "--allow-unreleased"],
        capture_output=True, env=env, cwd=str(ROOT), timeout=120)
    out = proc.stdout.decode("utf-8") + proc.stderr.decode("utf-8", errors="replace")
    assert "UnicodeEncodeError" not in out, out[-2000:]
    assert "PASS  artifacts — MonographPDF_9.9.9_Setup.exe" in out, out[-2000:]  # the line that crashed
    assert proc.returncode != 0  # placeholders are not a valid release: still reported as a failure
