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
    Write-Error "No Python interpreter found. Install Python 3.12 (or 3.11+) and retry."
}

Write-Host "Using $Python"
if (-not (Test-Path "$Root\env\Scripts\python.exe")) {
    & $Python -m venv "$Root\env"
}

$Pip = "$Root\env\Scripts\python.exe"
& $Pip -m pip install --upgrade pip
New-Item -ItemType Directory -Force -Path "$Root\packages\wheels" | Out-Null
& $Pip -m pip install --cache-dir "$Root\packages\wheels" -r "$Root\requirements.txt"
Write-Host "Environment ready: $Root\env"
