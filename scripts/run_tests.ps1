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

# Match pytest.ini testpaths: unit + integration + ui
# Windows PowerShell 5.1 turns redirected stderr lines of a native program into errors; with "Stop"
# the first one (for example Python's faulthandler reporting a handled COM exception) would end this
# script and kill pytest mid-run. The result comes from pytest's exit code instead.
$ErrorActionPreference = "Continue"
& $Py -m pytest tests/unit tests/integration tests/ui -q --junitxml=$Junit 2>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
