# Installer / uninstaller test of Monograph PDF Setup.exe (per-user install into a test folder).
#
#   clean install (all tasks) -> files, registrations, Start menu, self-check -> launch app ->
#   open User Guide -> uninstall refused while running -> complete uninstall (/REMOVEUSERDATA)
#   with a locked working file -> nothing left behind -> reinstall -> uninstall keeping settings
#   -> upgrade matrix (next-version Setup) -> PDF Editor 0.1.5 -> Monograph PDF migration matrix
#   (the frozen PDF Editor 0.1.5 Setup from releases\PDFEditor_0.1.5 is only run, never changed)
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_installer.ps1 [-Setup <path>]
# Exit code: number of failed checks. The current user's Monograph PDF and PDF Editor settings and
# working files (%APPDATA% / %LOCALAPPDATA% \Monograph PDF and \PDF Editor) are backed up first and
# restored at the end.
# The app and the User Guide window appear briefly on screen.

param(
    [string]$Setup = "",
    [string]$UpgradeSetup = "",
    [string]$LegacySetup = "",
    [switch]$SkipUpgradeTests,
    [switch]$SkipLegacyTests
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Setup) {
    $Setup = (Get-ChildItem (Join-Path $Root "installer\MonographPDF_*_Setup.exe") | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
}
if (-not $Setup -or -not (Test-Path $Setup)) { Write-Error "Setup.exe not found."; exit 99 }

$AppId     = "{64FC0D97-5E17-405F-9461-D6C075E1B467}_is1"
$Dir       = Join-Path $env:LOCALAPPDATA "MonographPDFInstallTest"
# Not in %TEMP%: the uninstaller sweeps %TEMP%\monographpdf* and %TEMP%\pdfeditor* folders
$Work      = Join-Path $Root "build\installer-test"
$Backup    = Join-Path $Work "user-data-backup"
$Roaming   = Join-Path $env:APPDATA "Monograph PDF"
$Local     = Join-Path $env:LOCALAPPDATA "Monograph PDF"
$Group     = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Monograph PDF"
$Desktop   = Join-Path ([Environment]::GetFolderPath("Desktop")) "Monograph PDF.lnk"
# PDF Editor (<= 0.1.5), the predecessor
$LegacyRoaming = Join-Path $env:APPDATA "PDF Editor"
$LegacyLocal   = Join-Path $env:LOCALAPPDATA "PDF Editor"
$LegacyGroup   = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\PDF Editor"
$LegacyDesktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "PDF Editor.lnk"
$LegacyDefault = Join-Path $env:LOCALAPPDATA "Programs\PDF Editor"
$RenamedDefault = Join-Path $env:LOCALAPPDATA "Programs\Monograph PDF"
if (-not $LegacySetup) { $LegacySetup = Join-Path $Root "releases\PDFEditor_0.1.5\PDFEditor_0.1.5_Setup.exe" }
$UninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
$Classes   = "HKCU:\Software\Classes"
$script:Failures = 0

function Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
    if ($Ok) { Write-Host ("  [PASS] " + $Name) -ForegroundColor Green }
    else { Write-Host ("  [FAIL] " + $Name + $(if ($Detail) { " - $Detail" })) -ForegroundColor Red; $script:Failures++ }
}
function Section([string]$Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }
function HasValue([string]$Key, [string]$Name) {
    $item = Get-ItemProperty -LiteralPath $Key -Name $Name -ErrorAction SilentlyContinue
    return $null -ne $item
}
function Registrations {
    # Every HKCU entry a per-user install with all tasks creates
    [ordered]@{
        "Installed apps entry"          = Test-Path -LiteralPath $UninstKey
        "ProgID MonographPDF.Document"     = Test-Path -LiteralPath "$Classes\MonographPDF.Document"
        "ProgID MonographPDF.Convertible"  = Test-Path -LiteralPath "$Classes\MonographPDF.Convertible"
        "Applications\MonographPDF.exe"   = Test-Path -LiteralPath "$Classes\Applications\MonographPDF.exe"
        ".pdf Open with"                = HasValue "$Classes\.pdf\OpenWithProgids" "MonographPDF.Document"
        ".png Open with"                = HasValue "$Classes\.png\OpenWithProgids" "MonographPDF.Convertible"
        ".docx Open with"               = HasValue "$Classes\.docx\OpenWithProgids" "MonographPDF.Convertible"
        "App Paths"                     = Test-Path -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\MonographPDF.exe"
        "Default apps capabilities"     = Test-Path -LiteralPath "HKCU:\Software\Monograph PDF"
        "RegisteredApplications"        = HasValue "HKCU:\Software\RegisteredApplications" "Monograph PDF"
    }
}
function Shortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($Path)
    return @{ Target = $lnk.TargetPath; Arguments = $lnk.Arguments }
}
function WaitExit([System.Diagnostics.Process]$Proc, [int]$Seconds) {
    # Every program this test starts gets a time limit, so a stuck installer cannot hang the run
    if (-not $Proc.WaitForExit($Seconds * 1000)) {
        Write-Host "  [TIMEOUT] $($Proc.ProcessName) did not finish within $Seconds s; stopped" -ForegroundColor Red
        try { $Proc.Kill() } catch {}
        $Proc.WaitForExit(10000) | Out-Null
        return 9999
    }
    return $Proc.ExitCode
}
function Install([string]$Tasks, [string]$Log) {
    $p = Start-Process $Setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/DIR=`"$Dir`"", "/TASKS=`"$Tasks`"", "/LOG=`"$Log`"" -PassThru
    return (WaitExit $p 600)
}
function Uninstall([string[]]$Extra, [string]$Log) {
    $cmd = (Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue).QuietUninstallString
    $exe = Join-Path $Dir "uninstall.exe"
    $argList = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$Log`"") + $Extra
    $p = Start-Process $exe -ArgumentList $argList -PassThru
    $code = WaitExit $p 300
    for ($i = 0; $i -lt 50 -and (Test-Path $Dir); $i++) { Start-Sleep -Milliseconds 200 }  # unins000 removes itself last
    WaitUninstallerGone
    # The uninstaller's second phase (a copy in %TEMP%) does the per-user clean-up after
    # uninstall.exe has returned; its log ends with "Log closed." when it is done
    for ($i = 0; $i -lt 240 -and -not (Select-String -Path $Log -Pattern "Log closed\." -Quiet -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 250 }
    return @{ Exit = $code; Registered = $cmd }
}
function WaitUninstallerGone {
    # Inno Setup's second phase (_iu*.tmp in %TEMP%) finishes the per-user clean-up last
    for ($i = 0; $i -lt 60 -and (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "_iu*" }); $i++) {
        Start-Sleep -Milliseconds 250
    }
}
function WaitWindow([System.Diagnostics.Process]$Proc, [string]$Title, [int]$Seconds = 30) {
    for ($i = 0; $i -lt $Seconds * 4; $i++) {
        Start-Sleep -Milliseconds 250
        $Proc.Refresh()
        if ($Proc.HasExited) { return "" }
        if ($Proc.MainWindowTitle -like "*$Title*") { return $Proc.MainWindowTitle }
    }
    return $Proc.MainWindowTitle
}
function Close([System.Diagnostics.Process]$Proc) {
    if ($Proc.HasExited) { return }
    $Proc.CloseMainWindow() | Out-Null
    if (-not $Proc.WaitForExit(10000)) { $Proc.Kill(); $Proc.WaitForExit() }
}
function InstalledFiles {
    if (-not (Test-Path $Dir)) { return @() }
    return @(Get-ChildItem $Dir -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Dir.Length + 1) } | Sort-Object)
}
function Persistence {
    # Anything that would start Monograph PDF without the user: Run keys, scheduled tasks, services
    $run = @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Run", "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce",
             "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run", "HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce")
    $found = @()
    foreach ($k in $run) {
        $item = Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue
        if ($item) { $item.PSObject.Properties | Where-Object { "$($_.Value)" -match "MonographPDF|Monograph PDF|PDF_editor|PDFEditor|PDF Editor" } | ForEach-Object { $found += "$k\$($_.Name)" } }
    }
    $found += @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match "Monograph|PDF.?Editor" -or ("$($_.Actions.Execute)" -match "MonographPDF|PDF_editor") } | ForEach-Object { "task " + $_.TaskName })
    $found += @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object { $_.PathName -match "MonographPDF|PDF_editor|InstallTest" } | ForEach-Object { "service " + $_.Name })
    $startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    $found += @(Get-ChildItem $startup -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "Monograph|PDF.?Editor" } | ForEach-Object { "startup " + $_.Name })
    return $found
}
function Leftovers {
    $temp = @(Get-ChildItem $env:TEMP -Directory -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -like "monographpdf*" -or $_.Name -eq "monograph-pdf-theme" -or
                             $_.Name -like "pdfeditor*" -or $_.Name -eq "pdf-editor-theme" })
    # uninstall.exe parks itself in %TEMP% while it waits and deletes that copy a few seconds later
    for ($i = 0; $i -lt 40 -and (Get-ChildItem $env:TEMP -Filter "MonographPDF-uninstall-*.exe" -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 250 }
    $parked = @(Get-ChildItem $env:TEMP -Filter "MonographPDF-uninstall-*.exe" -ErrorAction SilentlyContinue)
    [ordered]@{
        "installation folder"    = Test-Path $Dir
        "Start menu folder"      = Test-Path $Group
        "desktop shortcut"       = Test-Path $Desktop
        "%LOCALAPPDATA%\Monograph PDF" = Test-Path $Local
        "%TEMP% work folders"    = $temp.Count -gt 0
        "parked uninstall.exe in %TEMP%" = $parked.Count -gt 0
    }
}

Write-Host "Monograph PDF installer test"
Write-Host "Setup  : $Setup"
Write-Host "Folder : $Dir"
if (Get-Process MonographPDF, PDF_editor -ErrorAction SilentlyContinue) { Write-Error "Close Monograph PDF and PDF Editor before running this test."; exit 98 }
foreach ($d in $LegacyDefault, $RenamedDefault) { if (Test-Path $d) { Write-Error "$d exists (a per-user installation); remove it first."; exit 95 } }
if (Test-Path $Dir) { Write-Error "$Dir exists; remove the earlier test installation first."; exit 97 }
if (Test-Path -LiteralPath $UninstKey) { Write-Error "A per-user Monograph PDF installation exists; uninstall it first (this test installs per-user)."; exit 96 }

Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if (Test-Path $Roaming) { Copy-Item $Roaming (Join-Path $Backup "Roaming") -Recurse }
if (Test-Path $Local) { Copy-Item $Local (Join-Path $Backup "Local") -Recurse }
if (Test-Path $LegacyRoaming) { Copy-Item $LegacyRoaming (Join-Path $Backup "LegacyRoaming") -Recurse }
if (Test-Path $LegacyLocal) { Copy-Item $LegacyLocal (Join-Path $Backup "LegacyLocal") -Recurse }
$hadDesktop = Test-Path $Desktop
if ($hadDesktop) { Copy-Item $Desktop (Join-Path $Backup "Monograph PDF.lnk") }
$hadLegacyDesktop = Test-Path $LegacyDesktop
if ($hadLegacyDesktop) { Copy-Item $LegacyDesktop (Join-Path $Backup "PDF Editor.lnk") }

try {
    # ------------------------------------------------------------------ 1. clean install
    Section "1. Install (Start menu, desktop, .pdf and Open with registrations)"
    $code = Install "startmenu,desktopicon,assocpdf,assocother" (Join-Path $Work "setup1.log")
    Check "Setup exit code 0" ($code -eq 0) "exit $code"
    foreach ($f in "MonographPDF.exe", "uninstall.exe", "unins000.exe", "unins000.dat", "_internal\python311.dll",
                   "engines\ocr\tesseract.exe", "models\tessdata\eng.traineddata", "models\tessdata\jpn.traineddata",
                   "models\tessdata\osd.traineddata", "docs\USER_GUIDE.md", "README.md", "LICENSE.md",
                   "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CHANGELOG.md", "licenses\LGPL-3.0.txt", "licenses\LGPL-2.1.txt",
                   "licenses\GPL-2.0.txt", "licenses\GPL-3.0.txt") {
        Check "installed $f" (Test-Path (Join-Path $Dir $f))
    }
    $u = Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue
    # Inno Setup labels per-user installations "(Current user)" in Installed apps
    Check "Installed apps: name and version" ($u -and $u.DisplayName -in @("Monograph PDF", "Monograph PDF (Current user)") -and $u.DisplayVersion) "$($u.DisplayName) $($u.DisplayVersion)"
    Check "Installed apps: UninstallString runs uninstall.exe" ($u -and $u.UninstallString -eq "`"$Dir\uninstall.exe`"") "$($u.UninstallString)"
    Check "Installed apps: QuietUninstallString" ($u -and $u.QuietUninstallString -eq "`"$Dir\uninstall.exe`" /SILENT") "$($u.QuietUninstallString)"
    $ver = (Get-Item (Join-Path $Dir "uninstall.exe")).VersionInfo
    Check "uninstall.exe version information" ($ver.ProductName -eq "Monograph PDF" -and $ver.FileVersion) "$($ver.ProductName) $($ver.FileVersion)"
    $appVer = (Get-Item (Join-Path $Dir "MonographPDF.exe")).VersionInfo
    Check "MonographPDF.exe version information" ($appVer.ProductName -eq "Monograph PDF" -and $appVer.FileDescription -eq "Monograph PDF" -and
        $appVer.InternalName -eq "MonographPDF" -and $appVer.OriginalFilename -eq "MonographPDF.exe" -and
        $appVer.ProductVersion -eq $u.DisplayVersion -and $appVer.LegalCopyright -eq "$([char]0xA9) 2026$([char]0x2013)Present Aung Ye Mun") `
        "$($appVer.ProductName) / $($appVer.InternalName) / $($appVer.OriginalFilename) / $($appVer.ProductVersion) / $($appVer.LegalCopyright)"
    Check "Installed apps: DisplayIcon is MonographPDF.exe" ($u -and $u.DisplayIcon -like "*\MonographPDF.exe*") "$($u.DisplayIcon)"
    Check "no PDF Editor files installed" (-not (Get-ChildItem $Dir -Recurse -File -Force | Where-Object { $_.Name -like "PDF_editor*" -or $_.Name -like "pdf_editor*" -or $_.Name -eq "PDF_logo.png" }))
    foreach ($r in (Registrations).GetEnumerator()) { Check "registered: $($r.Key)" $r.Value }
    $main = Join-Path $Group "Monograph PDF.lnk"
    $guide = Join-Path $Group "Monograph PDF User Guide.lnk"
    Check "Start menu: Monograph PDF" ((Test-Path $main) -and (Shortcut $main).Target -eq "$Dir\MonographPDF.exe")
    Check "Start menu: User Guide opens in Monograph PDF" ((Test-Path $guide) -and (Shortcut $guide).Arguments -eq "--user-guide") "$((Shortcut $guide).Target) $((Shortcut $guide).Arguments)"
    Check "Start menu: no uninstall shortcut" (-not (Test-Path (Join-Path $Group "Uninstall Monograph PDF.lnk")))
    Check "desktop shortcut" (Test-Path $Desktop)
    Check "installation folder has no logs folder" (-not (Test-Path (Join-Path $Dir "logs")))
    $persist = Persistence
    Check "no startup entries, scheduled tasks or services" ($persist.Count -eq 0) ($persist -join ", ")
    $smoke = Join-Path $Local "logs\install_smoke_test.json"
    if (Test-Path $smoke) {
        $j = Get-Content $smoke -Raw | ConvertFrom-Json
        Check "Setup self-check passed" ([bool]$j.passed)
        Check "Setup self-check ran OCR" ([bool]$j.checks.ocr.ok) "$($j.checks.ocr.error)"
        Check "Setup self-check: every bundled module imports" ([bool]$j.checks.bundle_imports.ok) "$($j.checks.bundle_imports.error)"
        Check "Setup self-check: no network use" ([bool]$j.checks.no_network.ok) "$($j.checks.no_network.error)"
    } else { Check "Setup self-check report" $false "missing" }
    $guideText = Get-Content (Join-Path $Dir "docs\USER_GUIDE.md") -Raw
    Check "installed User Guide has no development paths" (-not ($guideText -match "Software[ ]testing|[A-Z]:\\Users\\|/home/|dev_launch|setup_env"))
    $fresh = Select-String -Path (Join-Path $Work "setup1.log") -Pattern "New install: clearing" -Quiet
    Write-Host "  [INFO] new-install history clean-up: $(if ($fresh) { 'ran (no earlier installation registered)' } else { 'skipped (an earlier installation is registered: upgrade)' })"

    # ------------------------------------------------------------------ 2. launch + docs
    Section "2. Launch Monograph PDF and the User Guide"
    $before = InstalledFiles
    $sample = Join-Path $Work "opened-document.pdf"
    Copy-Item (Join-Path $Root "tests\samples\sample_text.pdf") $sample -ErrorAction SilentlyContinue
    $app = Start-Process (Join-Path $Dir "MonographPDF.exe") -ArgumentList "`"$sample`"" -WorkingDirectory $Work -PassThru
    $title = WaitWindow $app "opened-document"
    Check "Monograph PDF window opens a document" ($title -like "*opened-document*") "title '$title'"

    # ------------------------------------------------------------------ 3. uninstall while running
    Section "3. Uninstall while Monograph PDF is running"
    $r = Uninstall @() (Join-Path $Work "uninstall-running.log")
    Check "silent uninstall refused (non-zero exit)" ($r.Exit -ne 0) "exit $($r.Exit)"
    Check "installation left intact" ((Test-Path (Join-Path $Dir "MonographPDF.exe")) -and (Test-Path (Join-Path $Dir "uninstall.exe")))
    Close $app
    $g = Start-Process (Join-Path $Dir "MonographPDF.exe") -ArgumentList "--user-guide" -PassThru
    $title = WaitWindow $g "User Guide"
    Check "User Guide window opens" ($title -eq "Monograph PDF User Guide") "title '$title'"
    Close $g
    $after = InstalledFiles
    $added = @(Compare-Object $before $after | Where-Object { $_.SideIndicator -eq "=>" } | ForEach-Object { $_.InputObject })
    Check "using Monograph PDF wrote nothing into the installation folder" ($added.Count -eq 0) ($added -join ", ")
    Check "working files are in %LOCALAPPDATA%\Monograph PDF" (Test-Path (Join-Path $Local "runtime"))

    # ------------------------------------------------------------------ 4. complete uninstall
    Section "4. Complete uninstall (/REMOVEUSERDATA) with a working file in use"
    New-Item -ItemType Directory -Force -Path (Join-Path $Local "runtime\temp"), $Roaming | Out-Null
    Set-Content (Join-Path $Roaming "preferences.json") '{"theme": "dark"}'
    Set-Content (Join-Path $Roaming "recent_files.json") '["C:\\Users\\Public\\example.pdf"]'
    New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP "monographpdf-leftover-test") | Out-Null
    $lockedPath = Join-Path $Local "runtime\temp\locked.tmp"
    Set-Content $lockedPath "in use"
    $userPdf = Join-Path $Work "my-document.pdf"
    Set-Content $userPdf "%PDF-1.7 user document"
    $lock = [System.IO.File]::Open($lockedPath, "Open", "Read", "None")
    $log = Join-Path $Work "uninstall-locked.log"
    $r = Uninstall @("/REMOVEUSERDATA") $log
    $lock.Close()
    Check "uninstall exit code 0" ($r.Exit -eq 0) "exit $($r.Exit)"
    Check "registered quiet uninstall used uninstall.exe" ($r.Registered -like "*uninstall.exe*")
    Check "locked file reported in the log" ([bool](Select-String -Path $log -Pattern "Could not remove .*Monograph PDF" -Quiet))
    Check "user document untouched" (Test-Path $userPdf)
    Remove-Item $Local -Recurse -Force -ErrorAction SilentlyContinue   # the folder that was in use

    Section "5. Complete uninstall without files in use"
    $code = Install "startmenu,desktopicon,assocpdf,assocother" (Join-Path $Work "setup2.log")
    Check "reinstall exit code 0" ($code -eq 0) "exit $code"
    $app = Start-Process (Join-Path $Dir "MonographPDF.exe") -PassThru
    $null = WaitWindow $app "Monograph PDF"
    Close $app
    New-Item -ItemType Directory -Force -Path $Roaming | Out-Null
    Set-Content (Join-Path $Roaming "preferences.json") '{"theme": "dark"}'
    New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP "monographpdf-leftover-test") | Out-Null
    $r = Uninstall @("/REMOVEUSERDATA") (Join-Path $Work "uninstall-complete.log")
    Check "uninstall exit code 0" ($r.Exit -eq 0) "exit $($r.Exit)"
    foreach ($l in (Leftovers).GetEnumerator()) { Check "removed: $($l.Key)" (-not $l.Value) }
    Check "removed: %APPDATA%\Monograph PDF (settings)" (-not (Test-Path $Roaming))
    foreach ($reg in (Registrations).GetEnumerator()) { Check "unregistered: $($reg.Key)" (-not $reg.Value) }
    Check "user document untouched" (Test-Path $userPdf)

    # ------------------------------------------------------------------ 6. reinstall, keep settings
    Section "6. Reinstall, then uninstall keeping settings"
    $code = Install "startmenu" (Join-Path $Work "setup3.log")
    Check "reinstall exit code 0" ($code -eq 0) "exit $code"
    Check "reinstalled app starts its self-check cleanly" ((Get-Content (Join-Path $Local "logs\install_smoke_test.json") -Raw | ConvertFrom-Json).passed)
    New-Item -ItemType Directory -Force -Path $Roaming | Out-Null
    Set-Content (Join-Path $Roaming "preferences.json") '{"theme": "dark"}'
    Set-Content (Join-Path $Roaming "recent_files.json") '["C:\\Users\\Public\\example.pdf"]'
    $r = Uninstall @() (Join-Path $Work "uninstall-keep.log")
    Check "uninstall exit code 0" ($r.Exit -eq 0) "exit $($r.Exit)"
    Check "settings kept (preferences.json)" (Test-Path (Join-Path $Roaming "preferences.json"))
    Check "recent-files list removed" (-not (Test-Path (Join-Path $Roaming "recent_files.json")))
    foreach ($l in (Leftovers).GetEnumerator()) { Check "removed: $($l.Key)" (-not $l.Value) }
    Check "unregistered: Installed apps entry" (-not (Test-Path -LiteralPath $UninstKey))

    # ------------------------------------------------------------------ 7–12. upgrade cleanup matrix (next-version Setup)
    if (-not $SkipUpgradeTests) {
        Section "7. Upgrade cleanup (obsolete owned files vs unrelated files)"
        if (-not $UpgradeSetup) {
            $UpgradeSetup = Join-Path $Root "build\installer\MonographPDF_upgrade_test_Setup.exe"
            if (-not (Test-Path $UpgradeSetup)) {
                Write-Host "  [INFO] Building upgrade-test Setup (does not touch frozen release artifacts)..."
                $py = Join-Path $Root "env\Scripts\python.exe"
                $payload = Join-Path $Root "dist\MonographPDF"
                $buildInst = Join-Path $Root "build\installer"
                $uninst = Join-Path $buildInst "uninstall.exe"
                $manifest = Join-Path $buildInst "installed_files.txt"
                $iscc = @(
                    (Join-Path $Root "tools\inno\ISCC.exe"),
                    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
                    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
                ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
                if (-not (Test-Path $payload)) { Write-Error "dist\MonographPDF missing; cannot build upgrade-test Setup."; throw }
                if (-not (Test-Path $uninst)) { Write-Error "build\installer\uninstall.exe missing; run a release build first."; throw }
                if (-not $iscc) { Write-Error "Inno Setup ISCC.exe not found."; throw }
                New-Item -ItemType Directory -Force -Path $buildInst | Out-Null
                & $py (Join-Path $Root "scripts\packaging\write_installed_manifest.py") --payload $payload --out $manifest
                if ($LASTEXITCODE -ne 0) { throw "write_installed_manifest failed" }
                $lic = Get-Content (Join-Path $Root "LICENSE.md") -Raw -Encoding UTF8
                [System.IO.File]::WriteAllText((Join-Path $buildInst "LICENSE.txt"), $lic, (New-Object System.Text.UTF8Encoding($true)))
                & $iscc /Q "/DAppVersion=0.2.1" "/DPayloadDir=$payload" "/DUninstallExe=$uninst" "/DInstalledManifest=$manifest" "/DOutputDirectory=$buildInst" (Join-Path $Root "installer\MonographPDF.iss")
                if ($LASTEXITCODE -ne 0) { throw "ISCC upgrade-test Setup failed" }
                $built = Join-Path $buildInst "MonographPDF_0.2.1_Setup.exe"
                if (-not (Test-Path $built)) { throw "Missing $built" }
                Copy-Item -Force $built $UpgradeSetup
            }
        }
        $DirB = Join-Path $env:LOCALAPPDATA "MonographPDFInstallTestB"
        function InstallUpgrade([string]$Log, [string]$DirOverride = "", [switch]$Migrate) {
            $target = if ($DirOverride) { $DirOverride } else { $Dir }
            $argList = @(
                "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
                "/DIR=`"$target`"", "/TASKS=`"startmenu,desktopicon,assocpdf,assocother`"",
                "/LOG=`"$Log`""
            )
            if ($Migrate) { $argList += "/MIGRATEINSTALL" }
            $p = Start-Process $UpgradeSetup -ArgumentList $argList -PassThru
            return (WaitExit $p 600)
        }
        function GetInstallLocation() {
            $loc = (Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue).InstallLocation
            if ($loc) { return $loc.TrimEnd('\') }
            return ""
        }

        # Baseline install with upgrade Setup
        $code = InstallUpgrade (Join-Path $Work "upgrade-base.log")
        Check "upgrade baseline install exit 0" ($code -eq 0) "exit $code"
        Check "upgrade baseline has installed_files.txt" (Test-Path (Join-Path $Dir "installed_files.txt"))

        # Plant previous-owned obsolete paths (listed in prior manifest) + unrelated user files.
        # Root-level owned orphans are not covered by [InstallDelete] trees — manifest cleanup must remove them.
        $obsoleteFile = Join-Path $Dir "obsolete_owned.dat"
        $obsoleteDir = Join-Path $Dir "obsolete_owned_dir"
        Set-Content -Path $obsoleteFile -Value "stale-owned" -Encoding Ascii
        New-Item -ItemType Directory -Force -Path $obsoleteDir | Out-Null
        Set-Content -Path (Join-Path $obsoleteDir "stale.txt") -Value "stale" -Encoding Ascii
        $manifestPath = Join-Path $Dir "installed_files.txt"
        Add-Content -Path $manifestPath -Value "obsolete_owned.dat"
        Add-Content -Path $manifestPath -Value "obsolete_owned_dir"
        Add-Content -Path $manifestPath -Value "obsolete_owned_dir/stale.txt"
        Set-Content -Path (Join-Path $Dir "my_notes.txt") -Value "keep me" -Encoding Utf8
        New-Item -ItemType Directory -Force -Path (Join-Path $Dir "My Personal Files") | Out-Null
        Set-Content -Path (Join-Path $Dir "My Personal Files\example.txt") -Value "personal" -Encoding Utf8
        New-Item -ItemType Directory -Force -Path $Roaming, (Join-Path $Local "runtime") | Out-Null
        Set-Content -Path (Join-Path $Roaming "preferences.json") '{"theme":"dark"}' -Encoding Utf8
        Set-Content -Path (Join-Path $Roaming "recent_files.json") '["C:\\Users\\Public\\example.pdf"]' -Encoding Utf8
        Set-Content -Path (Join-Path $Local "runtime\marker.txt") "runtime" -Encoding Utf8

        $code = InstallUpgrade (Join-Path $Work "upgrade-same.log")
        Check "same-folder upgrade exit 0" ($code -eq 0) "exit $code"
        Check "obsolete owned file removed" (-not (Test-Path $obsoleteFile))
        Check "obsolete owned directory removed" (-not (Test-Path $obsoleteDir))
        Check "unrelated my_notes.txt preserved" ((Test-Path (Join-Path $Dir "my_notes.txt")) -and ((Get-Content (Join-Path $Dir "my_notes.txt") -Raw) -match "keep me"))
        Check "unrelated nested personal file preserved" (Test-Path (Join-Path $Dir "My Personal Files\example.txt"))
        Check "AppData preferences preserved on upgrade" (Test-Path (Join-Path $Roaming "preferences.json"))
        Check "AppData recent-files preserved on upgrade" (Test-Path (Join-Path $Roaming "recent_files.json"))
        Check "LOCALAPPDATA runtime kept on upgrade" (Test-Path (Join-Path $Local "runtime"))
        Check "new installed_files.txt present after upgrade" (Test-Path (Join-Path $Dir "installed_files.txt"))
        Check "MonographPDF.exe present after upgrade" (Test-Path (Join-Path $Dir "MonographPDF.exe"))
        $mf = Get-Content (Join-Path $Dir "installed_files.txt") -Raw
        Check "new manifest has no obsolete_owned entries" ($mf -notmatch "obsolete_owned")

        Section "8. Silent upgrade refuses while Monograph PDF is running"
        $running = Start-Process (Join-Path $Dir "MonographPDF.exe") -PassThru
        $null = WaitWindow $running "Monograph PDF" 45
        $code = InstallUpgrade (Join-Path $Work "upgrade-running.log")
        Check "silent upgrade fails while running" ($code -ne 0) "exit $code"
        Check "install folder intact after refused upgrade" (Test-Path (Join-Path $Dir "MonographPDF.exe"))
        Close $running
        Get-Process MonographPDF -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dir*" } | Stop-Process -Force

        Section "9. Fresh install into non-empty folder preserves unrelated files"
        $r = Uninstall @("/REMOVEUSERDATA") (Join-Path $Work "upgrade-uninstall.log")
        Check "cleanup uninstall exit 0" ($r.Exit -eq 0) "exit $($r.Exit)"
        New-Item -ItemType Directory -Force -Path $Dir | Out-Null
        Set-Content -Path (Join-Path $Dir "preexisting.txt") -Value "already here" -Encoding Utf8
        $code = InstallUpgrade (Join-Path $Work "upgrade-nonempty.log")
        Check "install into non-empty folder exit 0" ($code -eq 0) "exit $code"
        Check "preexisting unrelated file preserved" (Test-Path (Join-Path $Dir "preexisting.txt"))

        Section "10. Same path with trailing slash / case difference is in-place upgrade"
        $slashDir = $Dir.TrimEnd('\') + '\'
        Set-Content -Path (Join-Path $Dir "my_notes.txt") -Value "keep slash" -Encoding Utf8
        New-Item -ItemType Directory -Force -Path $Roaming | Out-Null
        Set-Content -Path (Join-Path $Roaming "preferences.json") '{"theme":"dark"}' -Encoding Utf8
        $code = InstallUpgrade (Join-Path $Work "upgrade-slash.log") $slashDir
        Check "trailing-slash same-path upgrade exit 0" ($code -eq 0) "exit $code"
        Check "trailing-slash upgrade kept notes" (Test-Path (Join-Path $Dir "my_notes.txt"))
        Check "trailing-slash upgrade kept preferences" (Test-Path (Join-Path $Roaming "preferences.json"))
        $regLoc = GetInstallLocation
        Check "registry still points at primary test dir" (
            $regLoc -and (($regLoc.TrimEnd('\')).ToLowerInvariant() -eq ($Dir.TrimEnd('\').ToLowerInvariant()))
        ) "InstallLocation=$regLoc"

        Section "11. Silent different /DIR without /MIGRATEINSTALL keeps registered location"
        Remove-Item $DirB -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $DirB | Out-Null
        Set-Content -Path (Join-Path $Dir "stay_here.txt") -Value "primary" -Encoding Utf8
        $code = InstallUpgrade (Join-Path $Work "upgrade-keep-old.log") $DirB
        Check "silent different-DIR without migrate exit 0" ($code -eq 0) "exit $code"
        Check "primary install still has MonographPDF.exe" (Test-Path (Join-Path $Dir "MonographPDF.exe"))
        Check "no full duplicate install at new /DIR" (-not (Test-Path (Join-Path $DirB "MonographPDF.exe")))
        $regLoc = GetInstallLocation
        Check "registry still at old location after silent keep" (
            $regLoc -and (($regLoc.TrimEnd('\')).ToLowerInvariant() -eq ($Dir.TrimEnd('\').ToLowerInvariant()))
        ) "InstallLocation=$regLoc"

        Section "12. Registered install authoritative; unregistered second folder untouched"
        # Plant a stale look-alike folder (exe only) that is not the registered InstallLocation
        New-Item -ItemType Directory -Force -Path $DirB | Out-Null
        Copy-Item -Force (Join-Path $Dir "MonographPDF.exe") (Join-Path $DirB "MonographPDF.exe")
        Set-Content -Path (Join-Path $DirB "stale_marker.txt") -Value "do not delete" -Encoding Utf8
        $code = InstallUpgrade (Join-Path $Work "upgrade-stale-second.log")
        Check "upgrade with stale second folder exit 0" ($code -eq 0) "exit $code"
        Check "unregistered second folder exe left" (Test-Path (Join-Path $DirB "MonographPDF.exe"))
        Check "unregistered second folder marker left" (Test-Path (Join-Path $DirB "stale_marker.txt"))
        Check "registered primary still present" (Test-Path (Join-Path $Dir "MonographPDF.exe"))

        Section "13. Silent /MIGRATEINSTALL moves to new location and cleans owned files from old"
        Remove-Item $DirB -Recurse -Force -ErrorAction SilentlyContinue
        Set-Content -Path (Join-Path $Dir "my_notes.txt") -Value "preserve across migrate" -Encoding Utf8
        New-Item -ItemType Directory -Force -Path (Join-Path $Dir "My Personal Files") | Out-Null
        Set-Content -Path (Join-Path $Dir "My Personal Files\example.txt") -Value "personal" -Encoding Utf8
        New-Item -ItemType Directory -Force -Path $Roaming, (Join-Path $Local "runtime") | Out-Null
        Set-Content -Path (Join-Path $Roaming "preferences.json") '{"theme":"migrate"}' -Encoding Utf8
        Set-Content -Path (Join-Path $Roaming "recent_files.json") '["C:\\Users\\Public\\migrate.pdf"]' -Encoding Utf8
        Set-Content -Path (Join-Path $Local "runtime\marker.txt") "runtime" -Encoding Utf8
        $code = InstallUpgrade (Join-Path $Work "upgrade-migrate.log") $DirB -Migrate
        Check "migrate install exit 0" ($code -eq 0) "exit $code"
        Check "new location has MonographPDF.exe" (Test-Path (Join-Path $DirB "MonographPDF.exe"))
        Check "new location has _internal" (Test-Path (Join-Path $DirB "_internal"))
        Check "old owned MonographPDF.exe removed" (-not (Test-Path (Join-Path $Dir "MonographPDF.exe")))
        Check "old owned _internal removed" (-not (Test-Path (Join-Path $Dir "_internal")))
        Check "old unknown my_notes.txt preserved" (Test-Path (Join-Path $Dir "my_notes.txt"))
        Check "old unknown nested folder preserved" (Test-Path (Join-Path $Dir "My Personal Files\example.txt"))
        Check "AppData preferences preserved after migrate" (
            (Test-Path (Join-Path $Roaming "preferences.json")) -and
            ((Get-Content (Join-Path $Roaming "preferences.json") -Raw) -match "migrate")
        )
        Check "AppData recent-files preserved after migrate" (Test-Path (Join-Path $Roaming "recent_files.json"))
        Check "LOCALAPPDATA runtime preserved after migrate" (Test-Path (Join-Path $Local "runtime\marker.txt"))
        $regLoc = GetInstallLocation
        Check "registry InstallLocation moved to new path" (
            $regLoc -and (($regLoc.TrimEnd('\')).ToLowerInvariant() -eq ($DirB.TrimEnd('\').ToLowerInvariant()))
        ) "InstallLocation=$regLoc"
        $exeDefault = ""
        try {
            $k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Microsoft\Windows\CurrentVersion\App Paths\MonographPDF.exe")
            if ($k) { $exeDefault = [string]$k.GetValue(""); $k.Close() }
        } catch { $exeDefault = "" }
        Check "App Paths points at new exe" (
            $exeDefault -and ($exeDefault.ToLowerInvariant() -eq (Join-Path $DirB "MonographPDF.exe").ToLowerInvariant())
        ) "AppPaths=$exeDefault"
        if (Test-Path (Join-Path $Group "Monograph PDF.lnk")) {
            $sm = Shortcut (Join-Path $Group "Monograph PDF.lnk")
            Check "Start Menu shortcut points at new exe" (
                $sm.Target.ToLowerInvariant() -eq (Join-Path $DirB "MonographPDF.exe").ToLowerInvariant()
            ) "target=$($sm.Target)"
        }

        # Final cleanup for outer finally (uninstall from migrated location)
        if (Test-Path (Join-Path $DirB "uninstall.exe")) {
            $null = WaitExit (Start-Process (Join-Path $DirB "uninstall.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/REMOVEUSERDATA" -PassThru) 300
            WaitUninstallerGone
        } else {
            $null = Uninstall @("/REMOVEUSERDATA") (Join-Path $Work "upgrade-final-uninstall.log")
        }
        Remove-Item $Dir, $DirB -Recurse -Force -ErrorAction SilentlyContinue
    }

    # ------------------------------------------------------------------ 14–21. PDF Editor 0.1.5 -> Monograph PDF
    if (-not $SkipLegacyTests) {
        Section "14. PDF Editor 0.1.5 (frozen release) installed per-user in its default folder"
        if (-not (Test-Path $LegacySetup)) { throw "PDF Editor 0.1.5 Setup not found: $LegacySetup (pass -LegacySetup or -SkipLegacyTests)" }
        $legacyHash = (Get-FileHash $LegacySetup -Algorithm SHA256).Hash
        Check "frozen PDF Editor 0.1.5 Setup is the released file" ($legacyHash -eq "6EF9072C9B4B909E9E750EF119EDE45E9465B7A6E648CA1A2B6E76303C22A891") $legacyHash
        $LegacyCustom = Join-Path $env:LOCALAPPDATA "PDFEditorLegacyCustomTest"
        $StaleCopy = Join-Path $env:LOCALAPPDATA "PDFEditorStaleCopyTest"
        $AllTasks = "startmenu,desktopicon,assocpdf,assocother"
        function RunSetup([string]$Exe, [string[]]$Extra, [string]$Log) {
            $argList = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/TASKS=`"$AllTasks`"", "/LOG=`"$Log`"") + $Extra
            return (WaitExit (Start-Process $Exe -ArgumentList $argList -PassThru) 600)
        }
        function RegDefault([string]$Key, [string]$Name = "") {
            $item = Get-ItemProperty -LiteralPath $Key -ErrorAction SilentlyContinue
            if (-not $item) { return "" }
            if ($Name) { return [string]$item.$Name }
            return [string]$item."(default)"
        }
        function LegacyRegistrations {
            [ordered]@{
                "ProgID PDFEditor.Document"      = Test-Path -LiteralPath "$Classes\PDFEditor.Document"
                "ProgID PDFEditor.Convertible"   = Test-Path -LiteralPath "$Classes\PDFEditor.Convertible"
                "Applications\PDF_editor.exe"    = Test-Path -LiteralPath "$Classes\Applications\PDF_editor.exe"
                ".pdf Open with PDFEditor"       = HasValue "$Classes\.pdf\OpenWithProgids" "PDFEditor.Document"
                ".png Open with PDFEditor"       = HasValue "$Classes\.png\OpenWithProgids" "PDFEditor.Convertible"
                ".docx Open with PDFEditor"      = HasValue "$Classes\.docx\OpenWithProgids" "PDFEditor.Convertible"
                "App Paths PDF_editor.exe"       = Test-Path -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\PDF_editor.exe"
                "Software\PDF Editor"            = Test-Path -LiteralPath "HKCU:\Software\PDF Editor"
                "RegisteredApplications PDF Editor" = HasValue "HKCU:\Software\RegisteredApplications" "PDF Editor"
            }
        }
        function UninstallAt([string]$Folder, [string[]]$Extra, [string]$Log) {
            $exe = Join-Path $Folder "uninstall.exe"
            if (-not (Test-Path $exe)) { return 9998 }
            $code = WaitExit (Start-Process $exe -ArgumentList (@("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$Log`"") + $Extra) -PassThru) 300
            for ($i = 0; $i -lt 50 -and (Test-Path (Join-Path $Folder "unins000.exe")); $i++) { Start-Sleep -Milliseconds 200 }
            WaitUninstallerGone
            for ($i = 0; $i -lt 240 -and -not (Select-String -Path $Log -Pattern "Log closed\." -Quiet -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 250 }
            return $code
        }
        function PlantLegacyData([string]$ExistingPdf) {
            New-Item -ItemType Directory -Force -Path $LegacyRoaming, (Join-Path $LegacyLocal "runtime\sessions"),
                (Join-Path $LegacyLocal "runtime\cache"), (Join-Path $LegacyLocal "runtime\temp") | Out-Null
            Set-Content -LiteralPath (Join-Path $LegacyRoaming "preferences.json") '{"theme": "dark", "recent_limit": 9}' -Encoding UTF8
            $recent = ConvertTo-Json @($ExistingPdf, "C:\Users\Public\no-such-file-$([guid]::NewGuid().ToString('N')).pdf")
            Set-Content -LiteralPath (Join-Path $LegacyRoaming "recent_files.json") $recent -Encoding UTF8
            $session = @{ version = 1; saved_at = 0; source = $ExistingPdf; payload = @{ dirty = $true; objects = @(@{ kind = "text" }) } } | ConvertTo-Json -Depth 5
            Set-Content -LiteralPath (Join-Path $LegacyLocal "runtime\sessions\legacy-session.json") $session -Encoding UTF8
            Set-Content -LiteralPath (Join-Path $LegacyLocal "runtime\sessions\unknown-format.json") '{"version": 99}' -Encoding UTF8
            Set-Content -LiteralPath (Join-Path $LegacyLocal "runtime\cache\stale.bin") "cache" -Encoding Ascii
            Set-Content -LiteralPath (Join-Path $LegacyLocal "runtime\temp\stale.tmp") "temp" -Encoding Ascii
        }
        $existingPdf = Join-Path $Work "legacy-recent.pdf"
        Copy-Item (Join-Path $Root "tests\samples\sample_text.pdf") $existingPdf -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $existingPdf)) { Set-Content $existingPdf "%PDF-1.4 legacy recent" }
        Remove-Item $Roaming, $Local, $LegacyRoaming, $LegacyLocal -Recurse -Force -ErrorAction SilentlyContinue

        $code = RunSetup $LegacySetup @() (Join-Path $Work "legacy-install-1.log")
        Check "PDF Editor 0.1.5 installed (exit 0)" ($code -eq 0) "exit $code"
        Check "PDF Editor in %LOCALAPPDATA%\Programs\PDF Editor" (Test-Path (Join-Path $LegacyDefault "PDF_editor.exe"))
        Check "PDF Editor Start menu shortcut" (Test-Path (Join-Path $LegacyGroup "PDF Editor.lnk"))
        foreach ($r in (LegacyRegistrations).GetEnumerator()) { Check "PDF Editor registered: $($r.Key)" $r.Value }
        $u = Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue
        Check "Installed apps shows PDF Editor 0.1.5" ($u -and $u.DisplayName -like "PDF Editor*" -and $u.DisplayVersion -eq "0.1.5") "$($u.DisplayName) $($u.DisplayVersion)"
        PlantLegacyData $existingPdf
        Set-Content -LiteralPath (Join-Path $LegacyDefault "my_notes.txt") "keep me" -Encoding UTF8

        Section "15. Monograph PDF Setup refuses while PDF_editor.exe is running"
        $legacyApp = Start-Process (Join-Path $LegacyDefault "PDF_editor.exe") -PassThru
        $null = WaitWindow $legacyApp "PDF Editor" 45
        $code = RunSetup $Setup @() (Join-Path $Work "legacy-upgrade-running.log")
        Check "silent upgrade fails while PDF Editor runs" ($code -ne 0) "exit $code"
        Check "PDF Editor left intact" ((Test-Path (Join-Path $LegacyDefault "PDF_editor.exe")) -and -not (Test-Path (Join-Path $LegacyDefault "MonographPDF.exe")))
        Close $legacyApp
        Get-Process PDF_editor -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$LegacyDefault*" } | Stop-Process -Force

        Section "16. Silent upgrade in the same location (no /MIGRATEINSTALL)"
        $log = Join-Path $Work "legacy-upgrade-inplace.log"
        $code = RunSetup $Setup @() $log
        Check "in-place upgrade exit 0" ($code -eq 0) "exit $code"
        Check "log: PDF Editor recognised" ([bool](Select-String -Path $log -Pattern "PDF Editor upgrade: existing installation" -Quiet))
        Check "MonographPDF.exe installed in the existing folder" (Test-Path (Join-Path $LegacyDefault "MonographPDF.exe"))
        Check "PDF_editor.exe removed" (-not (Test-Path (Join-Path $LegacyDefault "PDF_editor.exe")))
        Check "unknown file in the folder preserved" (Test-Path (Join-Path $LegacyDefault "my_notes.txt"))
        Check "no Monograph PDF folder created (location kept)" (-not (Test-Path $RenamedDefault))
        $u = Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue
        Check "Installed apps: one entry, now Monograph PDF" ($u -and $u.DisplayName -like "Monograph PDF*" -and $u.DisplayVersion -ne "0.1.5") "$($u.DisplayName) $($u.DisplayVersion)"
        Check "Installed apps: DisplayIcon MonographPDF.exe" ($u.DisplayIcon -like "*\MonographPDF.exe*") "$($u.DisplayIcon)"
        Check "Installed apps: UninstallString uninstall.exe" ($u.UninstallString -eq "`"$LegacyDefault\uninstall.exe`"") "$($u.UninstallString)"
        $entries = @(Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
            Where-Object { (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName -match "Monograph PDF|PDF Editor" })
        Check "exactly one registered installation" ($entries.Count -eq 1) "$($entries.Count) entries"
        foreach ($r in (Registrations).GetEnumerator()) { Check "Monograph PDF registered: $($r.Key)" $r.Value }
        foreach ($r in (LegacyRegistrations).GetEnumerator()) { Check "PDF Editor registration removed: $($r.Key)" (-not $r.Value) }
        Check "App Paths -> MonographPDF.exe in the kept folder" ((RegDefault "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\MonographPDF.exe") -eq (Join-Path $LegacyDefault "MonographPDF.exe"))
        Check "Start menu: Monograph PDF" ((Test-Path (Join-Path $Group "Monograph PDF.lnk")) -and (Shortcut (Join-Path $Group "Monograph PDF.lnk")).Target -eq (Join-Path $LegacyDefault "MonographPDF.exe"))
        Check "Start menu: Monograph PDF User Guide" ((Test-Path (Join-Path $Group "Monograph PDF User Guide.lnk")) -and (Shortcut (Join-Path $Group "Monograph PDF User Guide.lnk")).Arguments -eq "--user-guide")
        Check "old PDF Editor Start menu folder removed" (-not (Test-Path $LegacyGroup))
        Check "old PDF Editor desktop shortcut removed" (-not (Test-Path $LegacyDesktop))
        Check "new desktop shortcut" (Test-Path $Desktop)
        Check "PDF Editor settings untouched by Setup" ((Test-Path (Join-Path $LegacyRoaming "preferences.json")) -and (Test-Path (Join-Path $LegacyLocal "runtime\sessions\legacy-session.json")))

        Section "17. First start of Monograph PDF migrates this user's PDF Editor data"
        $app = Start-Process (Join-Path $LegacyDefault "MonographPDF.exe") -PassThru
        $title = WaitWindow $app "Monograph PDF" 60
        Check "Monograph PDF window opens" ($title -like "*Monograph PDF*") "title '$title'"
        Close $app
        $prefs = Get-Content (Join-Path $Roaming "preferences.json") -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
        Check "preferences.json migrated" ($prefs -and $prefs.theme -eq "dark") "$prefs"
        $recentNew = @(Get-Content (Join-Path $Roaming "recent_files.json") -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json)
        Check "recent_files.json migrated with only existing files" ($recentNew.Count -eq 1 -and $recentNew[0] -eq $existingPdf) ($recentNew -join "; ")
        Check "migration record written" (Test-Path (Join-Path $Roaming "legacy_migration.json"))
        Check "recovery session migrated" (Test-Path (Join-Path $Local "runtime\sessions\legacy-session.json"))
        Check "unknown-format session not migrated" (-not (Test-Path (Join-Path $Local "runtime\sessions\unknown-format.json")))
        Check "PDF Editor cache not migrated" (-not (Test-Path (Join-Path $Local "runtime\cache\stale.bin")))
        Check "PDF Editor temp files not migrated" (-not (Test-Path (Join-Path $Local "runtime\temp\stale.tmp")))
        Check "PDF Editor data left in place" ((Test-Path (Join-Path $LegacyRoaming "preferences.json")) -and (Test-Path $LegacyLocal))
        Check "Setup self-check report under %LOCALAPPDATA%\Monograph PDF\logs" (Test-Path (Join-Path $Local "logs\install_smoke_test.json"))

        Section "18. Complete uninstall after migration (Monograph PDF and migrated PDF Editor data)"
        $code = UninstallAt $LegacyDefault @("/REMOVEUSERDATA") (Join-Path $Work "legacy-uninstall-1.log")
        Check "uninstall exit 0" ($code -eq 0) "exit $code"
        Check "Monograph PDF settings removed" (-not (Test-Path $Roaming))
        Check "Monograph PDF working files removed" (-not (Test-Path $Local))
        # PDF Editor data is removed only when no PDF Editor program remains on the computer (for example a
        # per-machine PDF Editor in Program Files still uses it) - the uninstaller must then keep it
        $legacyElsewhere = (Test-Path -LiteralPath "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\PDF_editor.exe") -or
                           (Test-Path (Join-Path $env:ProgramFiles "PDF Editor\PDF_editor.exe"))
        if ($legacyElsewhere) {
            Write-Host "  [INFO] a per-machine PDF Editor is installed on this computer: its data must be kept"
            Check "PDF Editor settings kept while another PDF Editor program remains" (Test-Path (Join-Path $LegacyRoaming "preferences.json"))
            Check "uninstall log: PDF Editor data not touched" (-not (Select-String -Path (Join-Path $Work "legacy-uninstall-1.log") -Pattern "PDF Editor data folders were migrated" -Quiet))
        } else {
            Check "migrated PDF Editor settings removed (provenance verified)" (-not (Test-Path $LegacyRoaming))
            Check "migrated PDF Editor working files removed" (-not (Test-Path $LegacyLocal))
        }
        Check "unknown file in the install folder preserved" (Test-Path (Join-Path $LegacyDefault "my_notes.txt"))
        Check "no application files left" (-not (Test-Path (Join-Path $LegacyDefault "MonographPDF.exe")) -and -not (Test-Path (Join-Path $LegacyDefault "_internal")))
        foreach ($r in (Registrations).GetEnumerator()) { Check "unregistered: $($r.Key)" (-not $r.Value) }
        foreach ($r in (LegacyRegistrations).GetEnumerator()) { Check "no PDF Editor registration: $($r.Key)" (-not $r.Value) }
        Check "no Start menu folders" (-not (Test-Path $Group) -and -not (Test-Path $LegacyGroup))
        Remove-Item $LegacyDefault -Recurse -Force -ErrorAction SilentlyContinue

        Section "19. Silent /MIGRATEINSTALL moves PDF Editor to the Monograph PDF folder"
        $code = RunSetup $LegacySetup @() (Join-Path $Work "legacy-install-2.log")
        Check "PDF Editor 0.1.5 reinstalled (exit 0)" ($code -eq 0) "exit $code"
        PlantLegacyData $existingPdf
        Set-Content -LiteralPath (Join-Path $LegacyDefault "my_notes.txt") "keep me" -Encoding UTF8
        # An unregistered second PDF Editor copy elsewhere must stay untouched
        Remove-Item $StaleCopy -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $StaleCopy | Out-Null
        Copy-Item (Join-Path $LegacyDefault "PDF_editor.exe") $StaleCopy
        Set-Content -LiteralPath (Join-Path $StaleCopy "stale_marker.txt") "do not delete" -Encoding UTF8
        $log = Join-Path $Work "legacy-migrate.log"
        $code = RunSetup $Setup @("/MIGRATEINSTALL") $log
        Check "migrating upgrade exit 0" ($code -eq 0) "exit $code"
        Check "installed in %LOCALAPPDATA%\Programs\Monograph PDF" (Test-Path (Join-Path $RenamedDefault "MonographPDF.exe"))
        Check "old PDF_editor.exe removed" (-not (Test-Path (Join-Path $LegacyDefault "PDF_editor.exe")))
        Check "old application files removed" (-not (Test-Path (Join-Path $LegacyDefault "_internal")) -and -not (Test-Path (Join-Path $LegacyDefault "unins000.exe")))
        Check "unknown file in the old folder preserved" (Test-Path (Join-Path $LegacyDefault "my_notes.txt"))
        $loc = (Get-ItemProperty -LiteralPath $UninstKey -ErrorAction SilentlyContinue).InstallLocation
        Check "InstallLocation is the Monograph PDF folder" ($loc -and $loc.TrimEnd('\') -eq $RenamedDefault) "$loc"
        Check "App Paths -> new MonographPDF.exe" ((RegDefault "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\MonographPDF.exe") -eq (Join-Path $RenamedDefault "MonographPDF.exe"))
        foreach ($r in (LegacyRegistrations).GetEnumerator()) { Check "PDF Editor registration removed: $($r.Key)" (-not $r.Value) }
        Check ".pdf Open with -> MonographPDF.Document" (HasValue "$Classes\.pdf\OpenWithProgids" "MonographPDF.Document")
        Check "ProgID command -> new MonographPDF.exe" ((RegDefault "$Classes\MonographPDF.Document\shell\open\command") -like "*$RenamedDefault\MonographPDF.exe*")
        Check "Start menu shortcut -> new MonographPDF.exe" ((Shortcut (Join-Path $Group "Monograph PDF.lnk")).Target -eq (Join-Path $RenamedDefault "MonographPDF.exe"))
        Check "old Start menu folder removed" (-not (Test-Path $LegacyGroup))
        Check "unregistered second PDF Editor copy untouched" ((Test-Path (Join-Path $StaleCopy "PDF_editor.exe")) -and (Test-Path (Join-Path $StaleCopy "stale_marker.txt")))
        Check "log: registered PDF Editor install was authoritative" ([bool](Select-String -Path $log -Pattern "Authoritative existing install: PDF Editor" -Quiet))
        $code = UninstallAt $RenamedDefault @("/REMOVEUSERDATA") (Join-Path $Work "legacy-uninstall-2.log")
        Check "uninstall after migration exit 0" ($code -eq 0) "exit $code"
        foreach ($l in (Leftovers).GetEnumerator()) { if ($l.Key -ne "installation folder") { Check "removed: $($l.Key)" (-not $l.Value) } }
        Check "Monograph PDF folder removed" (-not (Test-Path $RenamedDefault))
        Check "settings removed" (-not (Test-Path $Roaming))
        Remove-Item $LegacyDefault, $StaleCopy -Recurse -Force -ErrorAction SilentlyContinue

        Section "20. Start menu fallback: unregistered PDF Editor in a custom folder"
        Remove-Item $LegacyCustom -Recurse -Force -ErrorAction SilentlyContinue
        $code = RunSetup $LegacySetup @("/DIR=`"$LegacyCustom`"") (Join-Path $Work "legacy-install-3.log")
        Check "PDF Editor 0.1.5 installed in a custom folder (exit 0)" ($code -eq 0) "exit $code"
        # Lose the registration (uninstall entry, its uninstaller and App Paths): only the Start menu shortcut remains
        Remove-Item -LiteralPath $UninstKey -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\PDF_editor.exe" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $LegacyCustom "unins000.exe"), (Join-Path $LegacyCustom "unins000.dat") -Force -ErrorAction SilentlyContinue
        $log = Join-Path $Work "legacy-startmenu.log"
        $code = RunSetup $Setup @() $log
        Check "upgrade found through the Start menu (exit 0)" ($code -eq 0) "exit $code"
        Check "log: install inferred from the Start menu shortcut" ([bool](Select-String -Path $log -Pattern "inferred from verified Start Menu shortcut" -Quiet))
        Check "Monograph PDF installed in the custom folder" (Test-Path (Join-Path $LegacyCustom "MonographPDF.exe"))
        Check "PDF_editor.exe removed from the custom folder" (-not (Test-Path (Join-Path $LegacyCustom "PDF_editor.exe")))
        Check "old Start menu folder removed" (-not (Test-Path $LegacyGroup))
        $code = UninstallAt $LegacyCustom @("/REMOVEUSERDATA") (Join-Path $Work "legacy-uninstall-3.log")
        Check "uninstall exit 0" ($code -eq 0) "exit $code"
        Check "custom folder removed" (-not (Test-Path (Join-Path $LegacyCustom "MonographPDF.exe")))
        Remove-Item $LegacyCustom -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item $LegacyRoaming, $LegacyLocal -Recurse -Force -ErrorAction SilentlyContinue

        Section "21. Per-machine PDF Editor in C:\Program Files\PDF Editor"
        $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $machineKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
        if (-not $admin) {
            Write-Host "  [SKIP] needs an elevated PowerShell (Program Files install); covered by the same code paths as the per-user cases" -ForegroundColor Yellow
        } elseif (Test-Path -LiteralPath $machineKey) {
            Write-Host "  [SKIP] a per-machine Monograph PDF / PDF Editor is installed on this computer; not touched" -ForegroundColor Yellow
        } else {
            $pfOld = Join-Path $env:ProgramFiles "PDF Editor"
            $pfNew = Join-Path $env:ProgramFiles "Monograph PDF"
            $pfStale = Join-Path $env:LOCALAPPDATA "PDFEditorStaleCopyTest"
            $hklmCls = "HKLM:\Software\Classes"
            $hklmApp = "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths"
            $commonGroup = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs"
            $userChoiceKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
            $choiceBefore = RegDefault $userChoiceKey "ProgId"
            $argsM = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/TASKS=`"startmenu,assocpdf,assocother`"")
            $code = WaitExit (Start-Process $LegacySetup -ArgumentList ($argsM + "/LOG=`"$(Join-Path $Work 'pf-legacy.log')`"") -PassThru) 600
            Check "PDF Editor installed in Program Files (exit 0)" ($code -eq 0 -and (Test-Path (Join-Path $pfOld "PDF_editor.exe"))) "exit $code"
            Check "PDF Editor registered per machine (HKLM Installed apps)" (Test-Path -LiteralPath $machineKey)
            Set-Content -LiteralPath (Join-Path $pfOld "my_notes.txt") "keep me" -Encoding UTF8
            Remove-Item $pfStale -Recurse -Force -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Force -Path $pfStale | Out-Null
            Copy-Item (Join-Path $pfOld "PDF_editor.exe") $pfStale
            Set-Content -LiteralPath (Join-Path $pfStale "stale_marker.txt") "do not delete" -Encoding UTF8
            $log = Join-Path $Work 'pf-migrate.log'
            $code = WaitExit (Start-Process $Setup -ArgumentList ($argsM + "/MIGRATEINSTALL", "/LOG=`"$log`"") -PassThru) 600
            Check "moved to C:\Program Files\Monograph PDF (exit 0)" ($code -eq 0 -and (Test-Path (Join-Path $pfNew "MonographPDF.exe"))) "exit $code"
            Check "old PDF_editor.exe removed" (-not (Test-Path (Join-Path $pfOld "PDF_editor.exe")))
            Check "old application files removed" (-not (Test-Path (Join-Path $pfOld "_internal")) -and -not (Test-Path (Join-Path $pfOld "unins000.exe")))
            Check "user-added file in the old folder preserved" (Test-Path (Join-Path $pfOld "my_notes.txt"))
            Check "old folder kept because it is not empty" (Test-Path $pfOld)
            $selfOut = Join-Path $Work "pf-smoke.txt"
            $sp = Start-Process (Join-Path $pfNew "MonographPDF.exe") -ArgumentList "--smoke-test" -PassThru -Wait -RedirectStandardOutput $selfOut -ErrorAction SilentlyContinue
            Check "MonographPDF.exe --smoke-test passes from Program Files" ($sp -and $sp.ExitCode -eq 0) "exit $($sp.ExitCode)"
            $u = Get-ItemProperty -LiteralPath $machineKey -ErrorAction SilentlyContinue
            Check "Installed apps (HKLM): Monograph PDF" ($u -and $u.DisplayName -like "Monograph PDF*" -and $u.DisplayVersion -ne "0.1.5") "$($u.DisplayName) $($u.DisplayVersion)"
            Check "Installed apps: InstallLocation Program Files\Monograph PDF" ($u.InstallLocation.TrimEnd('\') -eq $pfNew) "$($u.InstallLocation)"
            Check "Installed apps: UninstallString in the new folder" ($u.UninstallString -eq "`"$pfNew\uninstall.exe`"") "$($u.UninstallString)"
            $entries = @()
            foreach ($root in "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall") {
                $entries += @(Get-ChildItem $root -ErrorAction SilentlyContinue | Where-Object { (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName -match "^(Monograph PDF|PDF Editor)" })
            }
            Check "exactly one Monograph PDF / PDF Editor Installed apps entry" ($entries.Count -eq 1) "$($entries.Count) entries"
            Check "App Paths (HKLM) -> new MonographPDF.exe" ((RegDefault "$hklmApp\MonographPDF.exe") -eq (Join-Path $pfNew "MonographPDF.exe"))
            Check "App Paths (HKLM) PDF_editor.exe removed" (-not (Test-Path -LiteralPath "$hklmApp\PDF_editor.exe"))
            Check "Open with: ProgID MonographPDF.Document (HKLM)" ((Test-Path -LiteralPath "$hklmCls\MonographPDF.Document") -and (HasValue "$hklmCls\.pdf\OpenWithProgids" "MonographPDF.Document"))
            Check "Open with: ProgID command -> Program Files\Monograph PDF" ((RegDefault "$hklmCls\MonographPDF.Document\shell\open\command") -like "*$pfNew\MonographPDF.exe*")
            Check "Applications\MonographPDF.exe registered (HKLM)" (Test-Path -LiteralPath "$hklmCls\Applications\MonographPDF.exe")
            Check "Default apps capabilities registered (HKLM)" ((Test-Path -LiteralPath "HKLM:\Software\Monograph PDF") -and (HasValue "HKLM:\Software\RegisteredApplications" "Monograph PDF"))
            Check "PDF Editor ProgIDs removed (HKLM)" (-not (Test-Path -LiteralPath "$hklmCls\PDFEditor.Document") -and -not (Test-Path -LiteralPath "$hklmCls\PDFEditor.Convertible") -and -not (Test-Path -LiteralPath "$hklmCls\Applications\PDF_editor.exe"))
            Check "PDF Editor Open with / Default apps entries removed (HKLM)" (-not (HasValue "$hklmCls\.pdf\OpenWithProgids" "PDFEditor.Document") -and -not (HasValue "HKLM:\Software\RegisteredApplications" "PDF Editor") -and -not (Test-Path -LiteralPath "HKLM:\Software\PDF Editor"))
            Check "Setup did not change the user's default .pdf app" ((RegDefault $userChoiceKey "ProgId") -eq $choiceBefore) "before '$choiceBefore' after '$(RegDefault $userChoiceKey 'ProgId')'"
            Check "Start menu (all users): Monograph PDF -> Program Files" ((Test-Path (Join-Path $commonGroup "Monograph PDF\Monograph PDF.lnk")) -and (Shortcut (Join-Path $commonGroup "Monograph PDF\Monograph PDF.lnk")).Target -eq (Join-Path $pfNew "MonographPDF.exe"))
            Check "Start menu (all users): Monograph PDF User Guide" (Test-Path (Join-Path $commonGroup "Monograph PDF\Monograph PDF User Guide.lnk"))
            Check "Start menu (all users): PDF Editor folder removed" (-not (Test-Path (Join-Path $commonGroup "PDF Editor")))
            Check "unregistered second PDF Editor copy untouched" ((Test-Path (Join-Path $pfStale "PDF_editor.exe")) -and (Test-Path (Join-Path $pfStale "stale_marker.txt")))
            $code = WaitExit (Start-Process (Join-Path $pfNew "uninstall.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru) 300
            WaitUninstallerGone
            Check "per-machine uninstall exit 0" ($code -eq 0) "exit $code"
            Check "uninstall removed the HKLM registration, App Paths, ProgIDs and Program Files\Monograph PDF" (-not (Test-Path -LiteralPath $machineKey) -and -not (Test-Path -LiteralPath "$hklmApp\MonographPDF.exe") -and -not (Test-Path -LiteralPath "$hklmCls\MonographPDF.Document") -and -not (Test-Path $pfNew))
            Check "user-added file still preserved after uninstall" (Test-Path (Join-Path $pfOld "my_notes.txt"))
            Check "unregistered second PDF Editor copy still untouched" (Test-Path (Join-Path $pfStale "stale_marker.txt"))
            Remove-Item $pfOld, $pfStale -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
finally {
    Section "Restoring this user's Monograph PDF and PDF Editor data"
    $DirBFinally = Join-Path $env:LOCALAPPDATA "MonographPDFInstallTestB"
    Get-Process MonographPDF -ErrorAction SilentlyContinue | Where-Object {
        ($_.Path -like "$Dir*") -or ($_.Path -like "$DirBFinally*")
    } | Stop-Process -Force
    Get-Process PDF_editor -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$env:LOCALAPPDATA*" } | Stop-Process -Force
    $LegacyCustomFinally = Join-Path $env:LOCALAPPDATA "PDFEditorLegacyCustomTest"
    $StaleFinally = Join-Path $env:LOCALAPPDATA "PDFEditorStaleCopyTest"
    foreach ($cleanDir in @($Dir, $DirBFinally, $LegacyDefault, $RenamedDefault, $LegacyCustomFinally)) {
        if (Test-Path (Join-Path $cleanDir "uninstall.exe")) {
            $null = WaitExit (Start-Process (Join-Path $cleanDir "uninstall.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru) 300
        }
    }
    WaitUninstallerGone
    foreach ($cleanDir in @($LegacyDefault, $LegacyCustomFinally)) {
        # A PDF Editor 0.1.5 left by a failed check: its own uninstaller
        if (Test-Path (Join-Path $cleanDir "unins000.exe")) {
            $null = WaitExit (Start-Process (Join-Path $cleanDir "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru) 300
        }
    }
    WaitUninstallerGone
    Remove-Item $Dir, $DirBFinally, $LegacyDefault, $RenamedDefault, $LegacyCustomFinally, $StaleFinally -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($lnk in (Join-Path $LegacyGroup "PDF Editor.lnk"), (Join-Path $LegacyGroup "PDF Editor User Guide.lnk")) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }
    Remove-Item $LegacyGroup -Force -ErrorAction SilentlyContinue
    if (-not $hadLegacyDesktop) { Remove-Item $LegacyDesktop -Force -ErrorAction SilentlyContinue }
    Remove-Item $Roaming, $Local, $LegacyRoaming, $LegacyLocal -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $Backup "Roaming")) { Copy-Item (Join-Path $Backup "Roaming") $Roaming -Recurse }
    if (Test-Path (Join-Path $Backup "Local")) { Copy-Item (Join-Path $Backup "Local") $Local -Recurse }
    if ($hadDesktop) { Copy-Item (Join-Path $Backup "Monograph PDF.lnk") $Desktop -Force }
    if (Test-Path (Join-Path $Backup "LegacyRoaming")) { Copy-Item (Join-Path $Backup "LegacyRoaming") $LegacyRoaming -Recurse }
    if (Test-Path (Join-Path $Backup "LegacyLocal")) { Copy-Item (Join-Path $Backup "LegacyLocal") $LegacyLocal -Recurse }
    if ($hadLegacyDesktop) { Copy-Item (Join-Path $Backup "PDF Editor.lnk") $LegacyDesktop -Force }
    Write-Host "  restored; logs in $Work"
}

Write-Host ""
if ($script:Failures -eq 0) { Write-Host "Installer test passed." -ForegroundColor Green }
else { Write-Host "Installer test: $($script:Failures) check(s) failed." -ForegroundColor Red }
exit $script:Failures
