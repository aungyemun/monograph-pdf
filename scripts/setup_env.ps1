# Create ./env and install locked requirements (Windows-first).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1 [-AllowOtherPython]
#
# Releases bundle Python 3.11 (THIRD_PARTY_NOTICES.md names the exact version), so the environment is
# created with Python 3.11: the "py -3.11" launcher first, then "python" only if it is 3.11.
# -AllowOtherPython accepts another 3.x interpreter for source-only work; do not build releases with it.

param(
    [switch]$AllowOtherPython
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Get-PythonInfo([string[]]$Command) {
    # Returns "<major.minor>|<executable>" or $null; never stops the script when a candidate is missing.
    try {
        $exe = $Command[0]
        $rest = @($Command | Select-Object -Skip 1)
        $out = & $exe @rest -c "import sys; print('%d.%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return "$out".Trim() }
    } catch { }
    return $null
}

$Python = $null
foreach ($candidate in @(, @("py", "-3.11")) + @(, @("python"))) {
    $info = Get-PythonInfo $candidate
    if (-not $info) { continue }
    $ver, $exe = $info.Split("|", 2)
    if ($ver -eq "3.11" -or $AllowOtherPython) { $Python = $exe; break }
    Write-Host "Skipping Python $ver at $exe (Python 3.11 is required; use -AllowOtherPython for source-only work)"
}
if (-not $Python) {
    throw "Python 3.11 not found. Install Python 3.11 (64-bit) and retry."
}

Write-Host "Using $Python"
$EnvPy = "$Root\env\Scripts\python.exe"
if (-not (Test-Path $EnvPy)) {
    & $Python -m venv "$Root\env"
    if ($LASTEXITCODE -ne 0) { throw "Creating .\env failed." }
}
$EnvInfo = Get-PythonInfo @($EnvPy)
if (-not $EnvInfo) { throw "The existing .\env does not start. Delete the env folder and run this script again." }
if (-not $EnvInfo.StartsWith("3.11|") -and -not $AllowOtherPython) {
    throw "The existing .\env uses Python $($EnvInfo.Split('|')[0]), not 3.11. Delete the env folder and run this script again."
}

$Pip = $EnvPy
# Upgrading pip is optional (it needs a network connection); the pinned requirements below are not.
& $Pip -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not upgrade pip (no network?); continuing with the installed pip." }
New-Item -ItemType Directory -Force -Path "$Root\packages\wheels" | Out-Null
# Prefer offline install from flat wheels when present; otherwise use network + pip HTTP cache.
$WheelCount = @(Get-ChildItem "$Root\packages\wheels\*.whl" -ErrorAction SilentlyContinue).Count
if ($WheelCount -gt 0) {
    Write-Host "Installing from $WheelCount cached wheel(s) in packages\wheels (offline-capable)"
    & $Pip -m pip install --no-index --find-links "$Root\packages\wheels" --cache-dir "$Root\packages\wheels" -r "$Root\requirements.txt"
} else {
    & $Pip -m pip install --cache-dir "$Root\packages\wheels" -r "$Root\requirements.txt"
}
if ($LASTEXITCODE -ne 0) { throw "Installing requirements.txt failed - the environment is incomplete." }
# Optional CI-only pins (cryptography, etc.) when requirements-ci.txt is present.
$ReqCi = Join-Path $Root "requirements-ci.txt"
if (Test-Path $ReqCi) {
    Write-Host "Installing requirements-ci.txt (test/signing tooling)"
    if ($WheelCount -gt 0) {
        & $Pip -m pip install --no-index --find-links "$Root\packages\wheels" --cache-dir "$Root\packages\wheels" -r $ReqCi
    } else {
        & $Pip -m pip install --cache-dir "$Root\packages\wheels" -r $ReqCi
    }
    if ($LASTEXITCODE -ne 0) { Write-Warning "requirements-ci.txt install failed; core env is still usable." }
}
& $Pip -m pip check
if ($LASTEXITCODE -ne 0) { throw "pip check reports inconsistent dependencies." }
# Keep flat wheels for offline reinstall (alongside pip's http-v2 cache). Without a network connection
# this step fails; the environment itself is complete, so that is only a warning.
& $Pip -m pip download -r "$Root\requirements.txt" -d "$Root\packages\wheels" --cache-dir "$Root\packages\wheels" | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not refresh the offline wheel cache in packages\wheels (no network?)." }
& $Pip -m pip freeze | Set-Content -Encoding ascii "$Root\packages\pip-freeze.txt"
# OCR notice next to the engine (installer also copies from third_party\licenses).
$Notice = Join-Path $Root "third_party\licenses\TESSERACT_NOTICE.txt"
if (Test-Path $Notice) {
    New-Item -ItemType Directory -Force -Path "$Root\engines\ocr" | Out-Null
    Copy-Item $Notice "$Root\engines\ocr\TESSERACT_NOTICE.txt" -Force
}
Write-Host "Environment ready: $Root\env"
