# Read-only release check for a Windows test computer (docs/WINDOWS_RELEASE_TEST_CHECKLIST.md).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File windows_release_check.ps1 `
#       [-ReleaseDir <folder with the downloaded release files>] [-SelfTest] [-CollectLogs]
#
# What it does (and nothing else):
#   * -ReleaseDir: SHA-256 of every MonographPDF_* file, SHA256SUMS.txt inside the Installer ZIP compared
#     with Setup.exe and the Source ZIP, Authenticode status of Setup.exe (expected: NotSigned), and,
#     if present, a summary of MonographPDF_update_manifest.json (version, key id, Setup size/hash).
#   * Finds installed copies of Monograph PDF (per-user and all-users registrations) and prints their
#     version, folder and the update configuration they trust (enabled, key ids). Reads only.
#   * -SelfTest: runs the installed program's offline self-check (MonographPDF.exe --smoke-test) with a
#     NEW temporary runtime and settings folder, so the installation and your settings are not touched.
#   * -CollectLogs: copies Monograph PDF's own log folder into a NEW folder on the Desktop for you to
#     review before sharing (it is never sent anywhere).
# It never installs, uninstalls, deletes or changes existing files, settings or registry entries.
# Results are written to a new report file on the Desktop as well as to the console.

param(
    [string]$ReleaseDir = "",
    [switch]$SelfTest,
    [switch]$CollectLogs
)

$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$desktop = [Environment]::GetFolderPath("Desktop")
$reportFile = Join-Path $desktop "MonographPDF-release-check-$stamp.txt"
$lines = New-Object System.Collections.Generic.List[string]
function Out-Line([string]$text) { Write-Host $text; $lines.Add($text) }

Out-Line "Monograph PDF release check  $(Get-Date -Format s)"
$os = Get-CimInstance Win32_OperatingSystem
Out-Line ("Windows: {0} {1} (build {2}), {3}, UI language {4}" -f $os.Caption, $os.Version, $os.BuildNumber,
          $os.OSArchitecture, (Get-UICulture).Name)

# ---------------------------------------------------------------- release files
if ($ReleaseDir) {
    Out-Line ""
    Out-Line "== Release files in $ReleaseDir"
    $files = Get-ChildItem -LiteralPath $ReleaseDir -File -Filter "MonographPDF_*"
    foreach ($f in $files) { Out-Line ("{0}  {1}  {2} bytes" -f (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower(), $f.Name, $f.Length) }
    $setup = $files | Where-Object { $_.Name -match '^MonographPDF_.+_Setup\.exe$' } | Select-Object -First 1
    $inst  = $files | Where-Object { $_.Name -match '^MonographPDF_.+_Installer\.zip$' } | Select-Object -First 1
    $src   = $files | Where-Object { $_.Name -match '^MonographPDF_.+_Source\.zip$' } | Select-Object -First 1
    if ($inst) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [System.IO.Compression.ZipFile]::OpenRead($inst.FullName)
        try {
            $entry = $zip.Entries | Where-Object { $_.FullName -eq "SHA256SUMS.txt" } | Select-Object -First 1
            if ($entry) {
                $reader = New-Object System.IO.StreamReader($entry.Open())
                $sums = $reader.ReadToEnd(); $reader.Close()
                foreach ($pair in @(@("Setup.exe", $setup), @($(if ($src) { $src.Name } else { "" }), $src))) {
                    if (-not $pair[1]) { continue }
                    $want = ([regex]::Match($sums, "(?m)^([0-9A-Fa-f]{64})\s+" + [regex]::Escape($pair[0]) + "\s*$")).Groups[1].Value.ToLower()
                    $have = (Get-FileHash -LiteralPath $pair[1].FullName -Algorithm SHA256).Hash.ToLower()
                    Out-Line ("{0}  SHA256SUMS.txt entry for {1}" -f $(if ($want -and $want -eq $have) { "PASS" } else { "FAIL" }), $pair[0])
                }
            } else { Out-Line "FAIL  SHA256SUMS.txt missing from $($inst.Name)" }
        } finally { $zip.Dispose() }
    }
    if ($setup) {
        $sig = Get-AuthenticodeSignature -LiteralPath $setup.FullName
        Out-Line "INFO  Authenticode status of $($setup.Name): $($sig.Status) (releases are not code-signed: NotSigned is expected)"
    }
    $man = Join-Path $ReleaseDir "MonographPDF_update_manifest.json"
    if (Test-Path -LiteralPath $man) {
        try {
            $m = Get-Content -LiteralPath $man -Raw | ConvertFrom-Json
            $a = $m.signed.artifacts | Select-Object -First 1
            Out-Line ("INFO  update manifest: version {0}, channel {1}, sequence {2}, expires {3}, signed by {4}" -f
                      $m.signed.version, $m.signed.channel, $m.signed.sequence, $m.signed.expires,
                      (($m.signatures | ForEach-Object { $_.keyid }) -join ", "))
            if ($setup) {
                $ok = ($a.name -eq $setup.Name) -and ($a.size -eq $setup.Length) -and
                      ($a.sha256 -eq (Get-FileHash -LiteralPath $setup.FullName -Algorithm SHA256).Hash.ToLower())
                Out-Line ("{0}  manifest names this Setup.exe with its exact size and SHA-256 (the signature itself is checked by the app and by update_manifest.py verify)" -f $(if ($ok) { "PASS" } else { "FAIL" }))
            }
        } catch { Out-Line "FAIL  update manifest is not valid JSON" }
    } else { Out-Line "INFO  no MonographPDF_update_manifest.json in this folder" }
}

# ---------------------------------------------------------------- installed copies (read only)
Out-Line ""
Out-Line "== Installed copies"
$appId = "{64FC0D97-5E17-405F-9461-D6C075E1B467}_is1"
$roots = @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId",
           "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId",
           "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$appId")
$found = @()
foreach ($r in $roots) {
    $k = Get-ItemProperty -LiteralPath $r -ErrorAction SilentlyContinue
    if ($k) {
        $dir = $k.InstallLocation; if (-not $dir) { $dir = $k.'Inno Setup: App Path' }
        $found += [pscustomobject]@{ Scope = $(if ($r -like "HKCU:*") { "this user" } else { "all users" }); Version = $k.DisplayVersion; Dir = $dir }
    }
}
if (-not $found) { Out-Line "INFO  no installed Monograph PDF found" }
foreach ($i in $found) {
    Out-Line ("INFO  {0}: version {1} in {2}" -f $i.Scope, $i.Version, $i.Dir)
    $cfgPath = Join-Path $i.Dir "_internal\resources\update\update_config.json"
    if (-not (Test-Path -LiteralPath $cfgPath)) { $cfgPath = Get-ChildItem -LiteralPath $i.Dir -Recurse -Filter update_config.json -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
    if ($cfgPath -and (Test-Path -LiteralPath $cfgPath)) {
        $c = Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json
        Out-Line ("INFO    update checks enabled: {0}; trusted key ids: {1}" -f $c.enabled, $(if ($c.trusted_keys) { ($c.trusted_keys | ForEach-Object { $_.keyid }) -join ", " } else { "(none)" }))
    }
    # Windows subsystem from the PE header: 2 = GUI (no console window), 3 = console
    foreach ($name in @("MonographPDF.exe", "MonographPDFUpdater.exe", "uninstall.exe")) {
        $exePath = Join-Path $i.Dir $name
        if (-not (Test-Path -LiteralPath $exePath)) { continue }
        $fs = [System.IO.File]::Open($exePath, 'Open', 'Read', 'ReadWrite')
        try {
            $br = New-Object System.IO.BinaryReader($fs)
            $fs.Position = 0x3C; $pe = $br.ReadInt32()
            $fs.Position = $pe + 0x5C; $subsystem = $br.ReadUInt16()
        } finally { $fs.Dispose() }
        Out-Line ("{0}    {1} is a {2} program{3}" -f $(if ($subsystem -eq 2) { "PASS" } else { "FAIL" }), $name,
                  $(if ($subsystem -eq 2) { "Windows GUI" } elseif ($subsystem -eq 3) { "console" } else { "subsystem $subsystem" }),
                  $(if ($subsystem -eq 2) { " (opens no console window)" } else { "" }))
    }
}

# ---------------------------------------------------------------- offline self-check
if ($SelfTest) {
    Out-Line ""
    Out-Line "== Offline self-check of the installed program"
    foreach ($i in $found) {
        $exe = Join-Path $i.Dir "MonographPDF.exe"
        if (-not (Test-Path -LiteralPath $exe)) { Out-Line "FAIL  $exe not found"; continue }
        $tmp = Join-Path $env:TEMP ("monograph-release-check-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        $rep = Join-Path $tmp "self-check.json"
        $env:MONOGRAPH_PDF_USER_DATA_DIR = Join-Path $tmp "UserData"   # never the real settings
        $p = Start-Process -FilePath $exe -ArgumentList @("--smoke-test", "--runtime-dir", "`"$tmp\runtime`"", "--report", "`"$rep`"") -PassThru -Wait -WindowStyle Hidden
        Remove-Item Env:\MONOGRAPH_PDF_USER_DATA_DIR
        Out-Line ("{0}  self-check of {1} (exit code {2})" -f $(if ($p.ExitCode -eq 0) { "PASS" } else { "FAIL" }), $i.Scope, $p.ExitCode)
        if (Test-Path -LiteralPath $rep) {
            $j = Get-Content -LiteralPath $rep -Raw | ConvertFrom-Json
            foreach ($prop in $j.checks.PSObject.Properties) {
                Out-Line ("        {0,-4}  {1}" -f $(if ($prop.Value.ok) { "ok" } else { "FAIL" }), $prop.Name)
            }
        }
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue   # only the folder made above
    }
}

# ---------------------------------------------------------------- logs (opt-in, local copy only)
if ($CollectLogs) {
    $dest = Join-Path $desktop "MonographPDF-logs-$stamp"
    $src = Join-Path $env:LOCALAPPDATA "Monograph PDF\logs"
    if (Test-Path -LiteralPath $src) {
        New-Item -ItemType Directory -Path $dest | Out-Null
        Copy-Item -LiteralPath $src -Destination $dest -Recurse
        Out-Line ""
        Out-Line "INFO  logs copied to $dest - read them before sharing; they stay on this computer."
    } else { Out-Line "INFO  no log folder at $src" }
}

$lines | Set-Content -LiteralPath $reportFile -Encoding UTF8
Write-Host ""
Write-Host "Report written to $reportFile"
