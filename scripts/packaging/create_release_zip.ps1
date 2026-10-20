# Stage the release folder and MonographPDF_x.y.z_Installer.zip:
#   release\ = Setup.exe + MonographPDF_x.y.z_Source.zip + SHA256SUMS.txt + README / INSTALLATION /
#   LICENSE / THIRD_PARTY_NOTICES / SECURITY / CITATION / CHANGELOG + docs\USER_GUIDE + license texts
#   MonographPDF_x.y.z_Installer.zip = the release folder without the source archive (which is published beside it).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\packaging\create_release_zip.ps1
#        [-SetupExe installer\MonographPDF_x.y.z_Setup.exe] [-SourceZip installer\MonographPDF_x.y.z_Source.zip]
#        [-DestinationZip installer\MonographPDF_x.y.z_Installer.zip] [-ReleaseDir installer\release]
# Refuses to replace a release folder that holds another, unarchived release (check_release.py guard-frozen).

param(
    [string]$SetupExe = "",
    [string]$SourceZip = "",
    [string]$DestinationZip = "",
    [string]$ReleaseDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
if (-not $SetupExe) {
    $SetupExe = Get-ChildItem (Join-Path $Root "installer") -Filter "MonographPDF_${version}_Setup.exe" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SetupExe -or -not (Test-Path $SetupExe)) { throw "No installer found. Build it with installer\build_release.bat." }
if (-not $DestinationZip) { $DestinationZip = Join-Path $Root "installer\MonographPDF_${version}_Installer.zip" }
if (-not $ReleaseDir) { $ReleaseDir = Join-Path $Root "installer\release" }

# Never overwrite a frozen earlier release (for example PDF Editor 0.1.5) that is not archived
$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
& $Py (Join-Path $Root "scripts\packaging\check_release.py") guard-frozen $ReleaseDir $version (Join-Path $Root "releases")
if ($LASTEXITCODE -ne 0) { throw "The release folder holds a frozen release that is not archived." }

if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

function Put($relSource, $relDest) {
    $src = Join-Path $Root $relSource
    if (-not (Test-Path $src)) { Write-Warning "Skipped missing $relSource"; return }
    $dst = Join-Path $ReleaseDir $relDest
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -Force $src $dst
}

Copy-Item -Force $SetupExe (Join-Path $ReleaseDir "Setup.exe")
# The source archive is part of the release (complete corresponding source of this build)
if (-not $SourceZip) {
    $SourceZip = Get-ChildItem (Join-Path $Root "installer") -Filter "MonographPDF_${version}_Source.zip" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SourceZip -or -not (Test-Path $SourceZip)) { throw "No source archive found (scripts\packaging\make_source_archive.py)." }
Copy-Item -Force $SourceZip (Join-Path $ReleaseDir (Split-Path -Leaf $SourceZip))
foreach ($doc in "README.md", "INSTALLATION.md", "LICENSE.md", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CITATION.cff", "CHANGELOG.md") {
    Put $doc $doc
}
Put "docs\USER_GUIDE.md" "docs\USER_GUIDE.md"
Put "third_party\licenses\TESSERACT_NOTICE.txt" "runtime\ocr\TESSERACT_NOTICE.txt"
Put "resources\fonts\OFL.txt" "runtime\fonts\OFL.txt"
foreach ($lic in "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-1.1", "GCC-exception-3.1") {
    Put "third_party\licenses\$lic.txt" "licenses\$lic.txt"
}

# SHA-256 of what is shipped, so a downloaded copy can be checked (the build is not code-signed)
$sums = @("Monograph PDF $version - SHA-256 checksums (this build is not code-signed)", "")
$sums += "{0}  Setup.exe" -f (Get-FileHash (Join-Path $ReleaseDir "Setup.exe") -Algorithm SHA256).Hash
$appExe = Join-Path $Root "dist\MonographPDF\MonographPDF.exe"
if (-not (Test-Path $appExe)) { throw "Missing $appExe (its SHA-256 belongs in SHA256SUMS.txt)" }
$sums += "{0}  MonographPDF.exe (installed program)" -f (Get-FileHash $appExe -Algorithm SHA256).Hash
$sums += "{0}  {1}" -f (Get-FileHash $SourceZip -Algorithm SHA256).Hash, (Split-Path -Leaf $SourceZip)
[System.IO.File]::WriteAllLines((Join-Path $ReleaseDir "SHA256SUMS.txt"), $sums)

if (Test-Path $DestinationZip) { Remove-Item -Force $DestinationZip }
# The installer package ZIP: Setup.exe and documents; the source archive is published beside it (same release folder)
# (portable '/' entry names; Windows PowerShell's Compress-Archive would write '\')
& $Py (Join-Path $Root "scripts\packaging\zip_folder.py") $ReleaseDir $DestinationZip --exclude "*_Source.zip"
if ($LASTEXITCODE -ne 0) { throw "Writing $DestinationZip failed" }
$size = (Get-Item $DestinationZip).Length / 1MB
Write-Host ("Wrote {0} ({1:N1} MB)" -f $DestinationZip, $size)
Write-Host "Release folder: $ReleaseDir"
