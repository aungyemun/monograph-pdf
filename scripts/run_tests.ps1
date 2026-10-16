# Run basic tests; artifacts under tests/outputs only.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing ./env. Run scripts/setup_env.ps1 first."
}

$Junit = Join-Path $Root "tests\outputs\junit\pytest.xml"
$LogDir = Join-Path $Root "tests\outputs\logs"
New-Item -ItemType Directory -Force -Path (Split-Path $Junit), $LogDir | Out-Null
$Log = Join-Path $LogDir ("pytest-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

& $Py -m pytest tests/unit tests/integration -q --junitxml=$Junit 2>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
