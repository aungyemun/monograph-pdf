# Create ./env and install locked requirements (Windows-first).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = $null
foreach ($candidate in @("python", "py")) {
    try {
        if ($candidate -eq "py") {
            $ver = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) { $Python = $ver.Trim(); break }
        } else {
            $ver = & python -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) { $Python = $ver.Trim(); break }
        }
    } catch { }
}

if (-not $Python) {
    Write-Error "No Python interpreter found. Install Python 3.11 (or 3.12+) and retry."
}

Write-Host "Using $Python"
if (-not (Test-Path "$Root\env\Scripts\python.exe")) {
    & $Python -m venv "$Root\env"
}

$Pip = "$Root\env\Scripts\python.exe"
& $Pip -m pip install --upgrade pip
New-Item -ItemType Directory -Force -Path "$Root\packages\wheels" | Out-Null
# Prefer offline install from flat wheels when present; otherwise use network + pip HTTP cache.
$WheelCount = @(Get-ChildItem "$Root\packages\wheels\*.whl" -ErrorAction SilentlyContinue).Count
if ($WheelCount -gt 0) {
    Write-Host "Installing from $WheelCount cached wheel(s) in packages\wheels (offline-capable)"
    & $Pip -m pip install --no-index --find-links "$Root\packages\wheels" --cache-dir "$Root\packages\wheels" -r "$Root\requirements.txt"
} else {
    & $Pip -m pip install --cache-dir "$Root\packages\wheels" -r "$Root\requirements.txt"
}
# Keep flat wheels for offline reinstall (alongside pip's http-v2 cache).
& $Pip -m pip download -r "$Root\requirements.txt" -d "$Root\packages\wheels" --cache-dir "$Root\packages\wheels" | Out-Host
& $Pip -m pip freeze | Set-Content -Encoding ascii "$Root\packages\pip-freeze.txt"
# OCR notice next to the engine (installer also copies from third_party\licenses).
$Notice = Join-Path $Root "third_party\licenses\TESSERACT_NOTICE.txt"
if (Test-Path $Notice) {
    New-Item -ItemType Directory -Force -Path "$Root\engines\ocr" | Out-Null
    Copy-Item $Notice "$Root\engines\ocr\TESSERACT_NOTICE.txt" -Force
}
Write-Host "Environment ready: $Root\env"
