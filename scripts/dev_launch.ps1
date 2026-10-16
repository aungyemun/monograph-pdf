# Development launch without frozen exe.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Error "Missing ./env. Run scripts/setup_env.ps1 first." }
& $Py -m app @args
exit $LASTEXITCODE
