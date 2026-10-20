<#
Runs an installed Monograph PDF copy in an isolated environment and records:
  - smoke-test result with a stripped PATH and redirected APPDATA/LOCALAPPDATA
  - every module loaded by the running GUI process and whether any comes from
    outside the install folder / Windows system folders (e.g. the dev tree)
  - TCP/UDP endpoints owned by the process (offline check)
Read-only for the install folder. User profile settings are not touched: the
sandbox is created under %TEMP% and removed afterwards.

Usage: powershell -ExecutionPolicy Bypass -File scripts\audit\isolated_installed_check.ps1
         [-InstallDir "C:\Program Files\Monograph PDF"] [-OutJson <path>] [-Pdf <file to open>]
#>
param(
  [string]$InstallDir = "C:\Program Files\Monograph PDF",
  [string]$OutJson = "",
  [string]$Pdf = "",
  [int]$GuiSeconds = 8
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $InstallDir "MonographPDF.exe"
if (-not (Test-Path $exe)) { throw "Not found: $exe" }

$sandbox = Join-Path $env:TEMP ("mpdf_iso_" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force "$sandbox\Roaming","$sandbox\Local","$sandbox\work" | Out-Null

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.WorkingDirectory = "$sandbox\work"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$keep = "SystemRoot","SystemDrive","windir","TEMP","TMP","USERPROFILE","USERNAME","COMPUTERNAME","ProgramData","ProgramFiles","ProgramFiles(x86)","CommonProgramFiles","NUMBER_OF_PROCESSORS","PROCESSOR_ARCHITECTURE","OS","ComSpec","PATHEXT","HOMEDRIVE","HOMEPATH","PUBLIC"
$psi.EnvironmentVariables.Clear()
foreach ($k in $keep) { $v = [Environment]::GetEnvironmentVariable($k); if ($v) { $psi.EnvironmentVariables[$k] = $v } }
$psi.EnvironmentVariables["PATH"] = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
$psi.EnvironmentVariables["APPDATA"] = "$sandbox\Roaming"
$psi.EnvironmentVariables["LOCALAPPDATA"] = "$sandbox\Local"

$result = [ordered]@{ install_dir = $InstallDir; sandbox = "(temp, removed)"; started = (Get-Date).ToString("s") }

# 1. smoke test
$psi.Arguments = "--smoke-test"
$p = [System.Diagnostics.Process]::Start($psi)
$out = $p.StandardOutput.ReadToEnd(); $err = $p.StandardError.ReadToEnd()
$p.WaitForExit(300000) | Out-Null
$result.smoke_exit_code = $p.ExitCode
$result.smoke_stdout_tail = ($out -split "`n" | Select-Object -Last 25) -join "`n"
$result.smoke_stderr_tail = ($err -split "`n" | Select-Object -Last 10) -join "`n"

# 2. GUI session: modules + sockets
$psi.Arguments = if ($Pdf) { '"' + $Pdf + '"' } else { "" }
$psi.RedirectStandardOutput = $false; $psi.RedirectStandardError = $false
$g = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds $GuiSeconds
$g.Refresh()
$mods = @()
try { $mods = $g.Modules | ForEach-Object { $_.FileName } } catch { $result.module_error = $_.Exception.Message }
$sys = @("$env:SystemRoot".ToLower())
$inst = $InstallDir.ToLower()
$foreign = $mods | Where-Object { $l = $_.ToLower(); -not ($l.StartsWith($inst) -or $l.StartsWith($sys[0])) }
$result.gui_alive_after_s = (-not $g.HasExited)
$result.module_count = $mods.Count
$result.modules_outside_install_and_windows = @($foreign)
$devRoot = [regex]::Escape((Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path)
$result.modules_from_dev_tree = @($mods | Where-Object { $_ -match "$devRoot|\\AppData\\Local\\Programs\\Python" })
$tcp = @(Get-NetTCPConnection -OwningProcess $g.Id -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State)
$udp = @(Get-NetUDPEndpoint -OwningProcess $g.Id -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort)
$result.tcp_connections = $tcp
$result.udp_endpoints = $udp
$result.working_set_mb = [math]::Round($g.WorkingSet64 / 1MB, 1)
if (-not $g.HasExited) { $g.CloseMainWindow() | Out-Null; if (-not $g.WaitForExit(10000)) { $g.Kill() } }
$result.gui_exit_code = $g.ExitCode

# 3. what the app wrote into the sandbox profile
$result.sandbox_files = @(Get-ChildItem $sandbox -Recurse -File | ForEach-Object { $_.FullName.Replace($sandbox, "<sandbox>") })
# 4. nothing written into the install folder in this run
$result.install_dir_newer_files = @(Get-ChildItem $InstallDir -Recurse -File | Where-Object { $_.LastWriteTime -gt [datetime]$result.started } | ForEach-Object FullName)

Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
$json = $result | ConvertTo-Json -Depth 5
if ($OutJson) { $json | Set-Content -Encoding UTF8 $OutJson }
$json
