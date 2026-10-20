# Full Monograph PDF release build:
#   tests -> MonographPDF.exe (PyInstaller onedir) -> --smoke-test -> uninstall.exe -> Setup.exe (Inno Setup)
#   -> MonographPDF_{version}_Source.zip -> installer\release\ + installer\MonographPDF_{version}_Installer.zip
#   -> installer\build_release_summary.txt
# A frozen earlier release in installer\release\ (for example PDF Editor 0.1.5) is never overwritten unless
# an identical copy is kept under releases\ (see docs/RELEASE_AND_VERSIONING.md).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_release.ps1 [-SkipTests] [-SkipExe]

param(
    [switch]$SkipTests,
    [switch]$SkipExe
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Missing .\env. Run scripts\setup_env.ps1 first." }
$Version = (& $Py "scripts\read_version.py").Trim()
$Started = Get-Date
Write-Host "Monograph PDF $Version release build"

# ---- Inno Setup compiler: project-local first, then a normal installation ----
$IsccCandidates = @(
    (Join-Path $Root "tools\inno\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Iscc) { throw "Inno Setup 6 not found. Copy it to tools\inno or run: winget install JRSoftware.InnoSetup" }

$BuildInst = Join-Path $Root "build\installer"
New-Item -ItemType Directory -Force -Path $BuildInst | Out-Null

# ---- 0. Frozen releases are never overwritten ----
# installer\release\ is rebuilt by this script. If it still holds another version's release, that
# release must first be kept, byte for byte, under releases\<Product>_<version>\release\.
& $Py (Join-Path $Root "scripts\packaging\check_release.py") guard-frozen (Join-Path $Root "installer\release") $Version (Join-Path $Root "releases")
if ($LASTEXITCODE -ne 0) { throw "installer\release holds a frozen release that is not archived - see above." }
# Release files of earlier versions left in installer\ would mix with this release set (and fail the
# release-set check): they are moved to build\superseded\<version>\ if an identical copy is archived.
& $Py (Join-Path $Root "scripts\packaging\check_release.py") superseded (Join-Path $Root "installer") $Version (Join-Path $Root "releases") (Join-Path $Root "build\superseded")
if ($LASTEXITCODE -ne 0) { throw "installer holds release files of an earlier version that are not archived - see above." }

# ---- 1. Tests ----
$TestResult = "skipped"
if (-not $SkipTests) {
    Step "Running tests"
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:MONOGRAPH_PDF_HEADLESS = "1"
    # Match pytest.ini: unit + integration + ui (strengthen, do not skip suites)
    $Junit = Join-Path $Root "build\installer\pytest_release.xml"
    New-Item -ItemType Directory -Force (Split-Path $Junit) | Out-Null
    & $Py -m pytest -q -p no:cacheprovider -o addopts="" --junitxml=$Junit tests\unit tests\integration tests\ui
    if ($LASTEXITCODE -ne 0) { throw "Tests failed - release not built." }
    # Exact counts for the summary and the release notes (validate_release_notes.py --tests P,F,S)
    $suite = ([xml](Get-Content $Junit -Raw)).testsuites.testsuite
    $failedCount = [int]$suite.failures + [int]$suite.errors
    $skippedCount = [int]$suite.skipped
    $passedCount = [int]$suite.tests - $failedCount - $skippedCount
    $TestResult = "$passedCount passed, $failedCount failed, $skippedCount skipped (--tests $passedCount,$failedCount,$skippedCount)"
    Remove-Item Env:QT_QPA_PLATFORM, Env:MONOGRAPH_PDF_HEADLESS -ErrorAction SilentlyContinue
}

# ---- 2. Application ----
if (-not $SkipExe) {
    Step "Building MonographPDF.exe"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_exe.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build_exe.ps1 failed." }
}
$Payload = Join-Path $Root "dist\MonographPDF"
$AppExe = Join-Path $Payload "MonographPDF.exe"
if (-not (Test-Path $AppExe)) { throw "Missing $AppExe" }

# OCR engine and language data sit next to the exe once installed (Setup.exe adds them from
# engines\ocr and models\tessdata); copy them in so the self-test checks the installed layout.
foreach ($Side in @("engines\ocr", "models\tessdata")) {
    $Src = Join-Path $Root $Side
    $Dst = Join-Path $Payload $Side
    if (-not (Get-ChildItem (Join-Path $Src "*") -File -Exclude ".gitkeep" -ErrorAction SilentlyContinue)) { throw "Missing OCR files in $Src" }
    Remove-Item -Recurse -Force $Dst -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $Dst | Out-Null
    Copy-Item (Join-Path $Src "*") $Dst -Recurse -Force -Exclude ".gitkeep"
}

# ---- 2a. Product identity in the PE version resource (one source: core\product_meta.py) ----
$vi = (Get-Item $AppExe).VersionInfo
$expected = & $Py -c "import json; from core.product_meta import version_resource_strings as v; print(json.dumps(v()))" | ConvertFrom-Json
foreach ($field in "ProductName", "FileDescription", "InternalName", "OriginalFilename", "ProductVersion", "FileVersion", "LegalCopyright", "CompanyName") {
    if ("$($vi.$field)" -ne "$($expected.$field)") { throw "MonographPDF.exe $field is '$($vi.$field)', expected '$($expected.$field)'" }
}
Write-Host "  MonographPDF.exe version resource: $($vi.ProductName) $($vi.ProductVersion) ($($vi.OriginalFilename))"

# ---- 2b. Release contents: only known components, no secrets or development files ----
Step "Checking release contents"
$Inventory = Join-Path $BuildInst "release_inventory.json"
& $Py (Join-Path $Root "scripts\packaging\check_release.py") check $Payload --json $Inventory
if ($LASTEXITCODE -ne 0) { throw "Release contents check failed - see above." }

# ---- 3. Self-test of the built app ----
Step "Running MonographPDF.exe --smoke-test"
$SmokeRuntime = Join-Path $BuildInst "smoke-runtime"
$SmokeReport = Join-Path $BuildInst "smoke_test.json"
Remove-Item -Recurse -Force $SmokeRuntime, $SmokeReport -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $AppExe -ArgumentList @("--smoke-test", "--runtime-dir", "`"$SmokeRuntime`"", "--report", "`"$SmokeReport`"") -PassThru -WindowStyle Hidden
if (-not $proc.WaitForExit(600000)) { $proc.Kill(); throw "Smoke test did not finish within 10 minutes." }
$Smoke = Get-Content $SmokeReport -Raw -Encoding UTF8 | ConvertFrom-Json
$Smoke.checks.PSObject.Properties | ForEach-Object {
    $ok = if ($_.Value.ok) { "ok  " } else { "FAIL" }
    Write-Host ("  [{0}] {1}" -f $ok, $_.Name)
}
if ($proc.ExitCode -ne 0 -or -not $Smoke.passed) { throw "Smoke test failed (exit $($proc.ExitCode)). See $SmokeReport" }

# ---- 3b. uninstall.exe (standard uninstaller name; starts the Inno Setup uninstaller) ----
Step "Building uninstall.exe"
$Csc = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Csc) { throw "The C# compiler of .NET Framework 4 (csc.exe, part of Windows) was not found." }
$NumericVersion = ($Version -split "[^0-9.]")[0]
while (($NumericVersion -split "\.").Count -lt 4) { $NumericVersion += ".0" }
$BuildInfo = Join-Path $BuildInst "uninstall_buildinfo.cs"
[System.IO.File]::WriteAllText($BuildInfo, "namespace MonographPdfUninstall { internal static class BuildInfo { public const string Version = `"$NumericVersion`"; } }")
$UninstallExe = Join-Path $BuildInst "uninstall.exe"
Remove-Item $UninstallExe -Force -ErrorAction SilentlyContinue
& $Csc /nologo /target:winexe /optimize+ "/out:$UninstallExe" "/win32icon:$(Join-Path $Root 'resources\icons\windows\monograph_pdf.ico')" /reference:System.Windows.Forms.dll (Join-Path $Root "installer\uninstall_launcher.cs") $BuildInfo
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $UninstallExe)) { throw "csc failed to build uninstall.exe." }
# Without unins000.exe beside it, the launcher must report the missing files (exit code 2)
$probe = Start-Process -FilePath $UninstallExe -ArgumentList "/VERYSILENT" -PassThru -WindowStyle Hidden
if (-not $probe.WaitForExit(60000)) { $probe.Kill(); throw "uninstall.exe self-check did not finish." }
if ($probe.ExitCode -ne 2) { throw "uninstall.exe self-check failed (exit $($probe.ExitCode), expected 2)." }
Write-Host "  uninstall.exe $((Get-Item $UninstallExe).VersionInfo.FileVersion) ok"

# ---- 4. Installer ----
Step "Compiling Setup.exe with Inno Setup"
# Licence page: UTF-8 with BOM so (c) and dashes display correctly
$LicenseText = Get-Content (Join-Path $Root "LICENSE.md") -Raw -Encoding UTF8
[System.IO.File]::WriteAllText((Join-Path $BuildInst "LICENSE.txt"), $LicenseText, (New-Object System.Text.UTF8Encoding($true)))
# Owned-file manifest for upgrade cleanup (relative paths only; never user documents)
$InstalledManifest = Join-Path $BuildInst "installed_files.txt"
& $Py (Join-Path $Root "scripts\packaging\write_installed_manifest.py") --payload $Payload --out $InstalledManifest
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $InstalledManifest)) { throw "installed_files.txt manifest failed." }
& $Iscc /Q "/DAppVersion=$Version" "/DPayloadDir=$Payload" "/DUninstallExe=$UninstallExe" "/DInstalledManifest=$InstalledManifest" (Join-Path $Root "installer\MonographPDF.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed." }
$Setup = Join-Path $Root "installer\MonographPDF_${Version}_Setup.exe"
if (-not (Test-Path $Setup)) { throw "Missing $Setup" }

# ---- 4b. Source archive: complete corresponding source for this release ----
Step "Building the source archive"
$SourceZip = Join-Path $Root "installer\MonographPDF_${Version}_Source.zip"
# Third-party source archives are downloaded once into packages\sources and checked against their
# recorded SHA-256 (build time only; the app never downloads anything)
& $Py (Join-Path $Root "scripts\packaging\make_source_archive.py") --out $SourceZip
if ($LASTEXITCODE -ne 0) { throw "Source archive failed - see above." }
& $Py (Join-Path $Root "scripts\packaging\check_release.py") check-source $SourceZip $Payload
if ($LASTEXITCODE -ne 0) { throw "Source archive check failed - see above." }

# ---- 5. Release folder + ZIP ----
Step "Packaging the release folder and MonographPDF_${Version}_Installer.zip"
$Zip = Join-Path $Root "installer\MonographPDF_${Version}_Installer.zip"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\packaging\create_release_zip.ps1") -SetupExe $Setup -SourceZip $SourceZip -DestinationZip $Zip
if ($LASTEXITCODE -ne 0) { throw "create_release_zip.ps1 failed." }
& $Py (Join-Path $Root "scripts\packaging\check_release.py") check $Payload --release (Join-Path $Root "installer\release")
if ($LASTEXITCODE -ne 0) { throw "Release folder check failed - see above." }
# No stale PDF Editor branding in the application or the release folder (history and migration notes allowed)
foreach ($scanned in $Payload, (Join-Path $Root "installer\release")) {
    $scanJson = Join-Path $BuildInst ("branding_scan_" + (Split-Path -Leaf $scanned) + ".json")
    & $Py (Join-Path $Root "scripts\packaging\branding_scan.py") --layout $scanned --json $scanJson
    $scanCode = $LASTEXITCODE
    if ($scanCode -ne 0) { throw "Branding scan of $scanned failed (exit $scanCode) - see $scanJson" }
}

# Every release file together: names, SHA256SUMS, portable ZIP names, notices, versions, privacy, OCR.
# Release notes are checked with --notes before publishing (docs/RELEASE_CHECKLIST.md).
Step "Verifying the release set"
& $Py (Join-Path $Root "scripts\packaging\verify_release.py") --dir (Join-Path $Root "installer") --version $Version --layout $Payload --allow-unreleased
if ($LASTEXITCODE -ne 0) { throw "Release set verification failed - see above." }

# ---- 6. Summary ----
Step "Writing build_release_summary.txt"
function Describe($path) {
    $item = Get-Item $path
    $hash = (Get-FileHash $path -Algorithm SHA256).Hash
    "{0}`r`n    size   {1:N1} MB ({2:N0} bytes)`r`n    sha256 {3}" -f $item.Name, ($item.Length / 1MB), $item.Length, $hash
}
$InternalSize = (Get-ChildItem (Join-Path $Payload "_internal") -Recurse -File | Measure-Object Length -Sum).Sum
$Checks = ($Smoke.checks.PSObject.Properties | ForEach-Object { "    {0,-16} {1}" -f $_.Name, $(if ($_.Value.ok) { "ok" } else { "FAILED: " + $_.Value.error }) }) -join "`r`n"
$Summary = @"
Monograph PDF release build summary
===================================
Version        : $Version
Built          : $($Started.ToString("yyyy-MM-dd HH:mm:ss")) ($([int]((Get-Date) - $Started).TotalMinutes) min)
Machine        : $env:COMPUTERNAME
Python         : $((& $Py --version) -join ' ')
Inno Setup     : $Iscc
Tests          : $TestResult
Smoke test     : passed
$Checks
Uninstaller    : uninstall.exe $((Get-Item $UninstallExe).VersionInfo.FileVersion) (starts unins000.exe)
Contents check : passed (build\installer\release_inventory.json)
Source archive : passed (every AGPL / GPL / LGPL component covered)
Branding scan  : passed (no stale PDF Editor branding in the application or release folder)
Release set    : passed (scripts\packaging\verify_release.py; release notes are checked separately before publishing)
Code signing   : not signed (no code-signing certificate is used for this build)

Application bundle
    dist\MonographPDF\MonographPDF.exe + _internal ($([math]::Round($InternalSize / 1MB, 1)) MB)
$(Describe $AppExe)

Outputs
$(Describe $Setup)
$(Describe $Zip)
$(Describe $SourceZip)

Release folder : installer\release\
"@
[System.IO.File]::WriteAllText((Join-Path $Root "installer\build_release_summary.txt"), $Summary, (New-Object System.Text.UTF8Encoding($false)))
Write-Host $Summary
Write-Host ""
Write-Host "Release build complete." -ForegroundColor Green
