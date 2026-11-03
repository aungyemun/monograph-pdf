# Start a Monograph PDF build (dist\ or an installed test copy) with a throw-away profile, for manual
# or automated acceptance tests. Every per-user location is redirected (settings, recent files,
# diagnostics, update state, runtime and single-instance lock), so the run cannot read, change or
# consume anything in the real %APPDATA% / %LOCALAPPDATA%\Monograph PDF folders, and it never hands its
# files to a Monograph PDF the user has open. Prints the process ID; end the run by closing that
# window (or by that PID only).
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\audit\launch_isolated.ps1 `
#            -Exe dist\MonographPDF\MonographPDF.exe -Profile build\accept-profile [-Files a.pdf,b.pdf]
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$Profile,
    [string[]]$Files = @()
)
$ErrorActionPreference = "Stop"
$Exe = (Resolve-Path $Exe).Path
New-Item -ItemType Directory -Force $Profile | Out-Null
$Profile = (Resolve-Path $Profile).Path
$real = @("$env:APPDATA\Monograph PDF", "$env:LOCALAPPDATA\Monograph PDF") | ForEach-Object { $_.TrimEnd('\') }
foreach ($r in $real) {
    if ($Profile.StartsWith($r, [System.StringComparison]::OrdinalIgnoreCase)) { throw "The test profile must not be inside $r" }
}
$dirs = @{ USER_DATA_DIR = "userdata"; RUNTIME_DIR = "runtime"; DIAGNOSTICS_DIR = "diagnostics"; UPDATES_DIR = "updates" }
foreach ($k in $dirs.Keys) {
    $d = Join-Path $Profile $dirs[$k]
    New-Item -ItemType Directory -Force $d | Out-Null
    Set-Item -Path "Env:MONOGRAPH_PDF_$k" -Value $d
}
$argList = @("--new-instance") + ($Files | ForEach-Object { '"' + (Resolve-Path $_).Path + '"' })
$p = Start-Process -FilePath $Exe -ArgumentList $argList -PassThru
"PID $($p.Id)  profile $Profile"
